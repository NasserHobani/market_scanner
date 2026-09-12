/**
 * AI intelligence centre.
 *
 * Rule for this screen: no raw JSON, no internal object dumps, no debug
 * output. Every internal number is rendered as a confidence bar, a badge or a
 * distribution, and every bar states where its value came from.
 */
(function () {
  "use strict";

  var pageData = (function () {
    var el = document.getElementById("page-data");
    try { return el ? JSON.parse(el.textContent) : {}; } catch (e) { return {}; }
  })();
  var qs = pageData.query || "";

  // The health score is a weighted composite; these are the component maxima
  // it is built from, so each part can be shown as a percentage of its own
  // ceiling instead of an unlabelled raw number.
  var PART_MAX = {
    expectancy: 35, profit_factor: 20, sharpe: 15,
    drawdown: 15, reliability: 10, baseline: 5,
  };
  var PART_LABEL = {
    expectancy: "قوة التوقّع",
    profit_factor: "عامل الربح",
    sharpe: "جودة العائد",
    drawdown: "تحمّل التراجع",
    reliability: "كفاية العيّنة",
    baseline: "التفوّق على الأساس",
  };
  var PART_NOTE = {
    expectancy: "متوسّط الربح لكل صفقة مقارنةً بالمدى المستهدف",
    profit_factor: "إجمالي الربح مقسوماً على إجمالي الخسارة",
    sharpe: "ثبات العائد مقابل تذبذبه",
    drawdown: "كم ابتعد المنحنى عن قمّته",
    reliability: "هل عدد الصفقات كافٍ لتكون النسب ذات معنى",
    baseline: "هل تتفوّق الاستراتيجية على مقارنة الأساس",
  };

  // ── Verdict ─────────────────────────────────────────────────────────────

  function renderVerdict(el, data) {
    var h = data.health || {};
    var score = DS.num(h.health_score);
    var tone = DS.toneForScore(score);
    var closed = h.closed_trades || 0;

    var text;
    if (closed < 20) {
      text = "العيّنة الحالية " + closed + " صفقة محسومة فقط. تحت عشرين صفقة لا يملك النظام " +
        "أساساً إحصائياً كافياً، فتُقرأ كل توصية على أنها فرضية لا نتيجة.";
    } else if (score >= 70) {
      text = "المكوّنات الستّة التي تُبنى منها التوصية في نطاقها الصحّي. التوقّع " +
        DS.fmtR(h.expectancy) + " لكل صفقة على " + closed + " صفقة محسومة.";
    } else if (score >= 45) {
      text = "بعض مكوّنات القرار ضعيفة. اقرأ الأعمدة أدناه لمعرفة أيّها يسحب الثقة للأسفل " +
        "قبل اتباع أي توصية.";
    } else {
      text = "أغلب مكوّنات القرار خارج نطاقها الصحّي. التوصيات في هذه الحالة غير مدعومة " +
        "بأداء مثبت — عالجها كإشارات للمراجعة لا للتنفيذ.";
    }

    el.innerHTML = DS.SectionCard({
      body:
        '<div class="ai-verdict">' +
          '<div class="ai-verdict__score ds-value-' + tone + '">' +
            (score === null ? "—" : score) + '<span style="font-size:1rem;color:var(--ds-text-muted)">/100</span></div>' +
          '<div class="ai-verdict__body">' +
            '<div class="ds-row" style="margin-bottom:.35rem">' +
              '<strong style="font-size:var(--ds-fs-md)">ثقة النظام في توصياته</strong>' +
              DS.StatusBadge({ label: h.health_label || "غير معروف", tone: tone, dot: true }) +
            "</div>" +
            '<p class="ds-text-sm ds-text-muted" style="margin:0;max-width:70ch">' +
              DS.esc(text) + "</p>" +
          "</div>" +
        "</div>",
    });
  }

  // ── Decision foundations: the composite, decomposed ─────────────────────

  function renderFoundations(el, data) {
    var parts = (data.health && data.health.health_parts) || {};
    var keys = Object.keys(PART_MAX).filter(function (k) { return parts[k] !== undefined; });

    if (!keys.length) {
      el.innerHTML = DS.SectionCard({
        title: "مكوّنات القرار",
        body: DS.EmptyState({
          icon: "◈",
          title: "لا مكوّنات بعد",
          text: "تُحسب مكوّنات القرار من الصفقات المحسومة. ابدأ بتتبّع صفقات ليظهر التحليل.",
          actions: [{ href: "/scanner/", label: "افتح الماسح", primary: true }],
          inline: true,
        }),
      });
      return;
    }

    var bars = keys.map(function (k) {
      var pct = (DS.num(parts[k]) || 0) / PART_MAX[k] * 100;
      return DS.ConfidenceBar({
        label: PART_LABEL[k] || k,
        value: pct,
        note: PART_NOTE[k],
      });
    }).join("");

    // Name the weakest component explicitly — that is the actionable part.
    var weakest = keys.reduce(function (lo, k) {
      var pct = (DS.num(parts[k]) || 0) / PART_MAX[k];
      return lo === null || pct < lo.pct ? { key: k, pct: pct } : lo;
    }, null);

    el.innerHTML = DS.SectionCard({
      title: "مكوّنات القرار",
      meta: "كل عمود نسبة من سقفه",
      body: bars +
        (weakest ? '<div style="height:var(--ds-sp-3)"></div>' + DS.InsightCard({
          tone: weakest.pct < .45 ? "risk" : weakest.pct < .7 ? "warn" : "success",
          title: "الحلقة الأضعف: " + (PART_LABEL[weakest.key] || weakest.key),
          text: PART_NOTE[weakest.key] + " — عالج هذا المكوّن أولاً؛ رفعه يرفع الثقة الكلّية أكثر من أي مكوّن آخر.",
        }) : ""),
    });
  }

  // ── Module status ───────────────────────────────────────────────────────

  function moduleRow(name, desc, badge) {
    return '<div class="ai-module">' +
      '<div class="ai-module__body">' +
        '<div class="ai-module__name">' + DS.esc(name) + "</div>" +
        '<div class="ai-module__desc">' + DS.esc(desc) + "</div>" +
      "</div>" + badge + "</div>";
  }

  function renderModules(el, d) {
    var pred = d.prediction || {};
    var sim = d.similarity || {};
    var dec = d.decision_ai || {};
    var feat = d.feature_intelligence || {};
    var mh = d.model_health || {};
    var drift = d.drift || {};

    var ok = DS.StatusBadge({ label: "متصل", tone: "success", dot: true });
    var off = DS.StatusBadge({ label: "غير مهيّأ", tone: "neutral", dot: true });

    el.innerHTML = DS.SectionCard({
      title: "وحدات الذكاء",
      meta: "الحالة الحيّة",
      body:
        moduleRow("محرك التنبؤ",
          pred.available ? pred.model_count + " نموذج مدرَّب" : "لا نماذج مدرَّبة",
          pred.available ? ok : off) +
        moduleRow("التشابه التاريخي",
          sim.available ? sim.closed_trades + " صفقة مرجعية · توقّع " + DS.fmtR(sim.expectancy)
            : "لا سوابق كافية",
          sim.available ? ok : off) +
        moduleRow("محرك القرار",
          dec.available ? "يدمج مخرجات الوحدات في توصية واحدة" : "غير متاح",
          dec.available ? ok : off) +
        moduleRow("ذكاء الميزات",
          feat.available ? "يقيس جودة مدخلات النموذج" : "لا تقرير جودة ميزات",
          feat.available ? ok : off) +
        moduleRow("صحة النماذج", mh.label || "غير متاح",
          DS.StatusBadge({
            label: mh.label || "غير متاح",
            tone: mh.label === "نشط" ? "success" : "neutral",
          })) +
        moduleRow("انحراف النموذج",
          drift.detected ? "تغيّر سلوك السوق عمّا تدرّب عليه النموذج" : "لا انحراف مرصود",
          DS.StatusBadge({
            label: drift.detected ? "مكتشف" : "سليم",
            tone: drift.detected ? "risk" : "success",
            dot: true,
          })),
    });
  }

  // ── Prediction tab ──────────────────────────────────────────────────────

  function renderSnapshotRuntimeCard(fs) {
    if (!fs || !fs.available) return "";
    var qual = fs.quality || {};
    var missing = fs.missing_feature_reasons || {};
    var missLines = Object.keys(missing).slice(0, 6).map(function (k) {
      return "<li>" + DS.esc(k) + ": " + missing[k] + "</li>";
    }).join("");
    return '<div style="height:var(--ds-sp-4)"></div>' +
      DS.SectionCard({
        title: "لقطات الميزات (PIT)",
        meta: DS.esc(fs.status || "—"),
        body:
          DS.StatGrid([
            { label: "تغطية تاريخية", value: (fs.historical_coverage_pct || 0) + "%" },
            { label: "تغطية وقت التشغيل", value: (fs.runtime_coverage_pct || 0) + "%" },
            { label: "متوسط تغطية الميزات", value: (fs.average_feature_coverage_pct || 0) + "%" },
            { label: "صفقات V3 المؤهلة", value: String(fs.v3_eligible_trades || 0) },
          ], 4) +
          '<div style="height:var(--ds-sp-3)"></div>' +
          DS.StatGrid([
            { label: "GOOD", value: String(qual.GOOD || 0), tone: "success" },
            { label: "PARTIAL", value: String(qual.PARTIAL || 0), tone: "warn" },
            { label: "FAILED", value: String(fs.failed_snapshots || 0), tone: "risk" },
            { label: "تسريبات", value: String(fs.leakage_events || 0),
              tone: fs.leakage_events ? "risk" : "success" },
          ], 4) +
          (missLines
            ? '<div class="ds-insight ds-insight--warn" style="margin-top:var(--ds-sp-3)">' +
                '<div class="ds-insight__title">ميزات ناقصة (أسباب):</div>' +
                '<ul style="margin:var(--ds-sp-2) 0 0;padding-right:var(--ds-sp-4)">' +
                  missLines + "</ul></div>"
            : ""),
      });
  }

  function renderReadinessCard(readiness, pred) {
    var r = readiness || (pred && pred.readiness) || (pred && pred.v3) || {};
    if (!r || (r.eligible_rows == null && r.eligible == null)) return "";
    var elig = r.eligible_rows != null ? r.eligible_rows : (r.eligible || 0);
    var req = r.required_rows != null ? r.required_rows : (r.required || 100);
    var pct = r.progress_percent != null ? r.progress_percent
      : (req ? Math.min(100, Math.round((elig / req) * 1000) / 10) : 0);
    var status = r.status || (elig >= req ? "READY_FOR_TRAINING" : "COLLECTING");
    var statusAr = r.status_ar || (status === "READY_FOR_TRAINING"
      ? "جاهز للتدريب" : status === "TRAINING" ? "جاري التدريب"
        : status === "COLLECTING" ? "جاري جمع البيانات" : status);
    var cov = r.runtime_coverage_pct != null ? r.runtime_coverage_pct : "—";
    var trainHint = "";
    if (status === "COLLECTING") {
      trainHint = "لم يبدأ — البيانات غير كافية";
    } else if (status === "READY_FOR_TRAINING") {
      trainHint = "سيتم تشغيل التدريب تلقائيًا";
    } else if (status === "TRAINING") {
      trainHint = "TRAINING";
    } else {
      trainHint = status;
    }
    return '<div style="height:var(--ds-sp-4)"></div>' +
      DS.SectionCard({
        title: "DATASET READINESS",
        meta: DS.esc(statusAr),
        body:
          '<div style="font-size:1.25rem;font-weight:600;margin-bottom:var(--ds-sp-2)">' +
            elig + " / " + req + " eligible trades · " + pct + "%</div>" +
          '<div style="margin-bottom:var(--ds-sp-3);color:var(--ds-text-muted)">' +
            DS.esc(statusAr) + "</div>" +
          DS.StatGrid([
            { label: "Runtime PIT coverage", value: cov === "—" ? "—" : (cov + "%") },
            { label: "Good", value: String(r.good_snapshot_count || 0), tone: "success" },
            { label: "Partial", value: String(r.partial_snapshot_count || 0), tone: "warn" },
            { label: "Failed", value: String(r.failed_snapshot_count || 0), tone: "risk" },
          ], 4) +
          '<div style="height:var(--ds-sp-3)"></div>' +
          DS.StatGrid([
            { label: "Linked closed trades", value: String(r.linked_closed_trades || 0) },
            { label: "Training", value: DS.esc(trainHint) },
          ], 2),
      });
  }

  function renderPredictionCycleCard(cycle, pred) {
    var c = cycle || {};
    var r = (pred && pred.readiness) || {};
    var elig = c.eligible_rows != null ? c.eligible_rows : (r.eligible_rows || 0);
    var req = c.required_rows != null ? c.required_rows : (r.required_rows || 100);
    var statusAr = c.status_ar || r.status_ar || "جاري جمع البيانات";
    var lastTrain = c.last_training_status || (r.retrain_state && r.retrain_state.last_status) || "—";
    var active = c.active_model_id || r.active_model_id || "لا يوجد";
    var why = c.prediction_reason || r.prediction_reason || "no_active_model";
    return '<div style="height:var(--ds-sp-4)"></div>' +
      DS.SectionCard({
        title: "دورة التنبؤ",
        meta: DS.esc(statusAr),
        body:
          DS.StatGrid([
            { label: "صفقات مؤهلة", value: elig + " / " + req },
            { label: "التقدم", value: (c.progress_percent != null ? c.progress_percent : "—") + "%" },
            { label: "الحالة", value: DS.esc(statusAr) },
            { label: "تغطية PIT", value: (c.runtime_coverage_pct != null ? c.runtime_coverage_pct : "—") + "%" },
          ], 4) +
          '<div style="height:var(--ds-sp-3)"></div>' +
          DS.StatGrid([
            { label: "آخر تدريب / النتيجة", value: DS.esc(String(lastTrain)) },
            { label: "النموذج النشط", value: DS.esc(String(active || "لا يوجد")) },
            { label: "سبب Prediction", value: DS.esc(String(why)) },
          ], 3),
      });
  }

  function renderPrediction(el, d) {
    var pred = d.prediction || {};
    var ps = d.prediction_status || {};
    var dataset = (pred.dataset || ps.dataset || {});
    var training = (pred.training || ps.training || {});
    var models = (pred.models || ps.models || {});
    var cfg = ps.config || {};
    var readiness = pred.readiness || {};
    var cycle = d.prediction_cycle || {};

    if (!pred.available) {
      var reason = pred.reason || "لا يوجد نموذج اجتاز بوابة الجودة";
      var oos = pred.oos_accuracy;
      var base = pred.baseline_accuracy;
      var diff = (oos != null && base != null)
        ? ((oos - base) * 100).toFixed(1) + "%" : "—";
      var wfStatus = pred.walk_forward_status ||
        (pred.walk_forward_pass === true ? "PASS" :
          pred.walk_forward_pass === false ? "FAILED" : "—");
      var calStatus = pred.calibration || "—";
      var gateStatus = pred.quality_gate || "NOT_PROMOTED";
      var rejections = pred.rejection_reasons || [];
      var registry = pred.model_registry || models.registry || [];
      var eligible = readiness.eligible_rows != null
        ? readiness.eligible_rows
        : (pred.eligible_samples || dataset.eligible || 0);
      var nextTrigger = cfg.min_new_trades || training.next_trigger_trades || 20;
      var newTrades = training.trades_since_last_training || 0;

      var rejectHtml = "";
      if (rejections.length) {
        rejectHtml =
          '<div class="ds-insight ds-insight--warn" style="margin-top:var(--ds-sp-3)">' +
            '<div class="ds-insight__title">سبب الرفض:</div>' +
            '<ul style="margin:var(--ds-sp-2) 0 0;padding-right:var(--ds-sp-4)">' +
            rejections.map(function (r) {
              return "<li>" + DS.esc(r) + "</li>";
            }).join("") +
            "</ul></div>";
      }

      var registryHtml = "";
      if (registry.length) {
        registryHtml =
          '<div style="height:var(--ds-sp-4)"></div>' +
          DS.SectionCard({
            title: "نماذج أخرى",
            body: registry.map(function (m) {
              var acc = m.oos_accuracy != null ? DS.fmtPct(m.oos_accuracy * 100, 1) : "—";
              var icon = m.passed ? "✅" : "❌";
              var promo = m.promotion_status || "NOT_PROMOTED";
              return '<div class="ai-module" style="padding:var(--ds-sp-2) 0">' +
                '<span style="font-weight:600;min-width:2.5rem;display:inline-block">' +
                  DS.esc(m.version || "?") + "</span> " +
                '<span style="margin:0 var(--ds-sp-3)">' + acc + "</span> " +
                icon + " " + DS.esc(promo) +
                "</div>";
            }).join(""),
          });
      }

      el.innerHTML =
        DS.SectionCard({
          title: "Prediction",
          body:
            '<div style="font-size:0.75rem;color:var(--ds-text-muted);letter-spacing:0.05em">' +
              "الحالة</div>" +
            '<div style="font-size:1.1rem;font-weight:600;margin:var(--ds-sp-1) 0 var(--ds-sp-3)">' +
              DS.esc(pred.status || "UNAVAILABLE") + "</div>" +
            '<div style="font-size:0.75rem;color:var(--ds-text-muted)">السبب</div>' +
            '<div style="margin:var(--ds-sp-1) 0 var(--ds-sp-4)">' + DS.esc(reason) + "</div>" +
            '<hr style="border:none;border-top:1px solid var(--ds-line);margin:var(--ds-sp-4) 0">' +
            '<div style="font-size:0.75rem;color:var(--ds-text-muted)">النموذج الحالي</div>' +
            '<div style="font-family:monospace;margin:var(--ds-sp-1) 0 var(--ds-sp-3)">' +
              DS.esc(pred.current_model_id || "—") + "</div>" +
            DS.StatGrid([
              { label: "OOS Accuracy", value: oos != null ? DS.fmtPct(oos * 100, 1) : "—" },
              { label: "Baseline", value: base != null ? DS.fmtPct(base * 100, 1) : "—" },
              { label: "Difference", value: diff },
              { label: "Walk-Forward", value: wfStatus,
                tone: wfStatus === "PASS" ? "success" : wfStatus === "FAILED" ? "risk" : "neutral" },
            ], 4) +
            '<div style="height:var(--ds-sp-3)"></div>' +
            DS.StatGrid([
              { label: "Calibration", value: calStatus },
              { label: "Quality Gate", value: gateStatus, tone: "risk" },
              { label: "الميزات", value: String(pred.feature_count || "—") },
              { label: "العيّنات", value: String(eligible) },
            ], 4) +
            (pred.why_unavailable_ar
              ? '<div class="ds-insight ds-insight--warn" style="margin-top:var(--ds-sp-3)">' +
                  '<div class="ds-insight__title">لماذا النموذج غير متاح؟</div>' +
                  '<pre style="white-space:pre-wrap;margin:var(--ds-sp-2) 0 0;font:inherit">' +
                    DS.esc(pred.why_unavailable_ar) + "</pre></div>"
              : "") +
            rejectHtml,
        }) +
        renderReadinessCard(readiness, pred) +
        renderPredictionCycleCard(cycle, pred) +
        renderSnapshotRuntimeCard(d.feature_snapshots) +
        registryHtml +
        '<div style="height:var(--ds-sp-4)"></div>' +
        DS.SectionCard({
          title: "الخطوة التالية",
          body:
            '<p style="margin:0 0 var(--ds-sp-2)">' + eligible + " عينة متاحة</p>" +
            '<p style="margin:0 0 var(--ds-sp-4)">' +
              "عتبة التدريب 100 · إعادة التدريب +" + nextTrigger +
              " صفقة مؤهلة جديدة (" + newTrades + "/" + nextTrigger + ")</p>" +
            '<button type="button" class="ds-btn ds-btn--primary" id="btn-train-prediction">' +
              "تدريب يدوي</button>",
        });
      var btn = el.querySelector("#btn-train-prediction");
      if (btn) {
        btn.onclick = function () {
          btn.disabled = true;
          fetch("/api/prediction/train/", { method: "POST", credentials: "same-origin" })
            .then(function () { DS.loadWidget({ id: "w-prediction", url: aiUrl, render: renderPrediction }); })
            .finally(function () { btn.disabled = false; });
        };
      }
      return;
    }

    el.innerHTML =
      DS.InsightCard({
        tone: "success",
        title: "التنبؤ نشط",
        text: "النموذج يعمل في وضع استشاري — لا يعدّل قرارات التداول.",
      }) +
      '<div style="height:var(--ds-sp-4)"></div>' +
      DS.StatGrid([
        { label: "النموذج", value: pred.latest_model || "—" },
        { label: "دقة OOS", value: pred.oos_accuracy != null ? DS.fmtPct(pred.oos_accuracy * 100, 1) : "—" },
        { label: "المعايرة", value: pred.calibration || "—" },
        { label: "الحالة", value: pred.promotion_status || pred.status || "ACTIVE", tone: "success" },
      ], 4) +
      renderReadinessCard(readiness, pred) +
      renderPredictionCycleCard(cycle, pred) +
      renderSnapshotRuntimeCard(d.feature_snapshots) +
      '<div style="height:var(--ds-sp-4)"></div>' +
      DS.SectionCard({
        title: "انحراف النموذج",
        body: (d.drift || {}).detected
          ? DS.InsightCard({ tone: "risk", title: "انحراف مرصود",
              text: "أعد التدريب قبل الاعتماد على الاحتمالات." })
          : DS.InsightCard({ tone: "success", title: "لا انحراف",
              text: "المدخلات ضمن نطاق التدريب." }),
      });
  }

  // ── Fusion tab ───────────────────────────────────────────────────────────

  function renderFusion(el, d) {
    var fusion = d.ai_fusion || {};
    var metrics = fusion.metrics || {};
    var cmp = fusion.comparison || {};
    var ps = fusion.prediction_status || {};
    var engine = fusion.prediction_engine || "UNAVAILABLE";
    var table = (cmp.comparison_table || []).map(function (row) {
      var acc = row.accuracy != null ? DS.fmtPct(row.accuracy * 100, 1) : "—";
      return "<tr><td>" + DS.esc(row.component) + "</td><td>" + acc +
        "</td><td>" + String(row.sample || 0) + "</td></tr>";
    }).join("");

    el.innerHTML =
      DS.SectionCard({
        title: "دمج القرار",
        body:
          DS.StatGrid([
            { label: "محرك التنبؤ", value: engine,
              tone: engine === "ACTIVE" ? "success" : "neutral" },
            { label: "حالة الدمج", value: metrics.status || "EARLY_SIGNAL" },
            { label: "مراجعات", value: String(metrics.sample_size || 0) },
            { label: "معدل التعارض", value: metrics.conflict_rate != null
              ? DS.fmtPct(metrics.conflict_rate * 100, 1) : "—" },
          ], 4) +
          '<div style="height:var(--ds-sp-4)"></div>' +
          DS.StatGrid([
            { label: "دقة المنصة", value: metrics.platform_accuracy != null
              ? DS.fmtPct(metrics.platform_accuracy * 100, 1) : "—" },
            { label: "دقة LightGBM", value: metrics.prediction_accuracy != null
              ? DS.fmtPct(metrics.prediction_accuracy * 100, 1) : "—" },
            { label: "دقة LLM", value: metrics.llm_accuracy != null
              ? DS.fmtPct(metrics.llm_accuracy * 100, 1) : "—" },
            { label: "تكلفة/مراجعة", value: metrics.cost && metrics.cost.avg_cost_per_review
              ? "$" + metrics.cost.avg_cost_per_review : "—" },
          ], 4) +
          '<div style="height:var(--ds-sp-4)"></div>' +
          '<div class="table-wrap"><table class="table"><thead><tr>' +
          "<th>المكوّن</th><th>الدقة</th><th>العيّنة</th></tr></thead><tbody>" +
          (table || "<tr><td colspan=\"3\">لا بيانات كافية بعد</td></tr>") +
          "</tbody></table></div>" +
          (engine === "UNAVAILABLE"
            ? '<div style="height:var(--ds-sp-3)"></div>' +
              DS.InsightCard({
                tone: "warn",
                title: "التنبؤ غير متاح",
                text: ps.reason || "لا يوجد نموذج ACTIVE — الدمج يعمل بدون طبقة إحصائية.",
              })
            : ""),
      });
  }

  // ── Decision tab: fusion weights as a distribution, never as JSON ──────

  var WEIGHT_LABEL = {
    reasoning: "الاستدلال",
    similarity: "التشابه",
    prediction: "التنبؤ",
    research: "البحث",
    knowledge: "المعرفة",
    features: "الميزات",
    feature_intelligence: "ذكاء الميزات",
    rules: "القواعد",
    technical: "الفنّي",
  };

  function renderDecision(el, d) {
    var dec = d.decision_ai || {};
    if (!dec.available) {
      el.innerHTML = DS.EmptyState({
        icon: "◈",
        title: "محرك القرار غير متاح",
        text: "محرك القرار يدمج مخرجات الوحدات في توصية واحدة. عند تعطّله يعود النظام إلى قواعد الماسح المباشرة.",
        actions: [{ href: "/settings/", label: "راجع الإعدادات", primary: true }],
      });
      return;
    }

    var w = dec.fusion_weights || {};
    var keys = Object.keys(w).filter(function (k) {
      return typeof w[k] === "number";
    });

    if (!keys.length) {
      el.innerHTML = DS.SectionCard({
        title: "محرك القرار",
        body: DS.InsightCard({
          tone: "info",
          title: "المحرك متصل",
          text: "لم يُصرّح المحرك بأوزان الدمج، فلا يمكن عرض حصّة كل مصدر في التوصية.",
        }),
      });
      return;
    }

    var total = keys.reduce(function (s, k) { return s + Math.abs(w[k]); }, 0) || 1;
    var rows = keys
      .sort(function (a, b) { return Math.abs(w[b]) - Math.abs(w[a]); })
      .map(function (k) {
        var share = Math.abs(w[k]) / total * 100;
        return {
          label: WEIGHT_LABEL[k] || k,
          value: share,
          text: DS.fmtPct(share, 0),
          tone: "info",
        };
      });

    var top = rows[0];
    el.innerHTML =
      DS.SectionCard({
        title: "حصّة كل مصدر في التوصية",
        meta: keys.length + " مصدر",
        body: DS.Distribution(rows),
      }) +
      '<div style="height:var(--ds-sp-3)"></div>' +
      DS.InsightCard({
        tone: "info",
        title: "المصدر الأثقل: " + top.label,
        text: "يمثّل " + top.text + " من وزن القرار النهائي. تغيّر أداء هذا المصدر هو الأكثر تأثيراً على التوصيات.",
      });
  }

  // ── Features tab ────────────────────────────────────────────────────────

  function renderFeatures(el, d) {
    var feat = d.feature_intelligence || {};
    if (!feat.available) {
      el.innerHTML = DS.EmptyState({
        icon: "◇",
        title: "لا تقرير جودة ميزات",
        text: "ذكاء الميزات يقيس أي مدخلات النموذج ما زالت مفيدة وأيها صار ضجيجاً. لا تقرير محفوظ حالياً.",
        steps: ["شغّل تحليل الميزات", "راجع مساهمة العوامل في التحليلات"],
        actions: [
          { href: "/analytics/?tab=factors", label: "مساهمة العوامل", primary: true },
          { href: "/research/", label: "مختبر البحث" },
        ],
      });
      return;
    }
    el.innerHTML = DS.SectionCard({
      title: "جودة الميزات",
      body: DS.InsightCard({
        tone: "success",
        title: "تقرير الميزات متاح",
        text: "راجع مساهمة كل عامل في صفحة التحليلات لمعرفة أيّها يرفع التوقّع فعلياً.",
      }) + '<div style="height:var(--ds-sp-3)"></div>' +
      '<a class="ds-btn ds-btn--primary" href="/analytics/?tab=factors">مساهمة العوامل</a>',
    });
  }

  // ── Boot ────────────────────────────────────────────────────────────────

  function renderAdvisorRuntime(el, data) {
    if (!data || !data.available) {
      el.innerHTML = DS.SectionCard({ title: "مستشار الذكاء",
        body: '<p class="ds-text-muted">غير متصل</p>' });
      return;
    }
    var status = data.runtime_status || "disconnected";
    var statusLabel = data.runtime_status_label || status;
    var agreeLabel = data.agreement_label || data.agreement || "—";
    var tone = status === "running" ? "success"
      : status === "connected" ? "info"
      : status === "failed" ? "risk" : "warn";
    var a = data.analyst || {};
    var analystCard = DS.SectionCard({
      title: "محلل الأسواق بالذكاء",
      meta: "AI Analyst",
      body:
        DS.StatGrid([
          { label: "القرار", value: a.advisor_decision || "—" },
          { label: "الاتجاه الحالي", value: a.current_market_view || "—" },
          { label: "نظرة 3–7 أيام", value: a.near_term_outlook || "—" },
          { label: "ثقة المستشار", value: a.advisor_confidence || "—" },
        ], 4) +
        '<div style="height:var(--ds-sp-3)"></div>' +
        DS.StatGrid([
          { label: "ثقة المنصة", value: a.platform_confidence || "—" },
          { label: "الاحتمال الإحصائي", value: a.prediction_probability || "غير متاح" },
          { label: "المزوّد", value: data.provider || "—" },
          { label: "النموذج", value: data.model || "—" },
        ], 4) +
        (a.review_id
          ? '<div style="margin-top:var(--ds-sp-3)">' +
              '<button type="button" class="ds-btn ds-btn--sm" id="btn-open-analyst-review">' +
              "عرض التحليل الكامل</button></div>"
          : ""),
    });
    el.innerHTML = DS.SectionCard({
      title: "مستشار الذكاء",
      meta: data.provider + " · " + (data.model || ""),
      body: DS.StatGrid([
          { label: "الحالة", value: statusLabel },
          { label: "مراجعات", value: data.successful_reviews || 0 },
          { label: "توكنات", value: data.total_tokens || "—" },
          { label: "تكلفة", value: data.estimated_cost != null ? "$" + Number(data.estimated_cost).toFixed(4) : "—" },
          { label: "تأريض", value: DS.fmtNum(data.grounding_score, 1) },
          { label: "اتفاق", value: agreeLabel },
        ]) + DS.StatusBadge({ label: statusLabel, tone: tone, dot: true }),
    }) + '<div style="height:var(--ds-sp-4)"></div>' + analystCard;
    var openBtn = el.querySelector("#btn-open-analyst-review");
    if (openBtn && a.review_id && window.AIExplain) {
      openBtn.onclick = function () { AIExplain.openReview(a.review_id); };
    }
  }

  function renderLearning(el, data) {
    if (!data || !data.available) {
      el.innerHTML = DS.EmptyState({ title: "التعلّم", text: "لا بيانات تعلّم بعد." });
      return;
    }
    var cards = data.lesson_cards || [];
    if (!cards.length) {
      var lessons = (data.lessons || []).slice(0, 5);
      if (!lessons.length) {
        el.innerHTML = DS.EmptyState({
          title: "التعلّم",
          text: "لا دروس بعد — تُولَّد تلقائياً بعد إغلاق الصفقات وتقييم المستشار.",
        });
        return;
      }
      cards = lessons.map(function (l) {
        return {
          lesson_id: l.lesson_id,
          pattern: l.title_ar || l.title,
          pattern_en: l.title,
          sample_size: l.sample_size,
          description_ar: l.description_ar || l.description,
          provider: l.provider,
          recommendation: l.recommendation_ar || l.recommendation,
          lesson: l,
        };
      });
    }

    var html = '<div class="ai-learning-list">';
    cards.forEach(function (c) {
      var lesson = c.lesson || c;
      html +=
        '<article class="ai-learning-card" data-lesson-id="' + DS.esc(c.lesson_id || "") + '">' +
          '<header class="ai-learning-card__head">' +
            '<span class="ai-learning-card__icon" aria-hidden="true">🧠</span>' +
            '<div>' +
              '<h3 class="ai-learning-card__title">' + DS.esc(c.pattern || lesson.title_ar || lesson.title) + "</h3>" +
              '<p class="ai-learning-card__sub ai-ltr">' + DS.esc(c.pattern_en || lesson.title || "") + "</p>" +
            "</div>" +
          "</header>" +
          '<p class="ai-learning-card__desc">' + DS.esc(c.description_ar || lesson.description_ar || "") + "</p>" +
          '<dl class="ai-learning-card__stats">' +
            "<div><dt>العيّنة</dt><dd>" + DS.ltr(String(c.sample_size || 0)) + " صفقة</dd></div>" +
            (c.win_rate != null
              ? "<div><dt>نسبة الربح</dt><dd dir=\"ltr\">" + DS.ltr(String(c.win_rate)) + "%</dd></div>"
              : "") +
            (c.avg_r != null
              ? "<div><dt>متوسط R</dt><dd dir=\"ltr\">" + DS.fmtR(c.avg_r) + "</dd></div>"
              : "") +
            (c.confidence_avg != null
              ? "<div><dt>الثقة</dt><dd dir=\"ltr\">" + DS.ltr(String(c.confidence_avg)) + "%</dd></div>"
              : "") +
            "<div><dt>المزوّد</dt><dd>" + DS.esc(c.provider || "—") + "</dd></div>" +
          "</dl>" +
          (c.affected_symbols && c.affected_symbols.length
            ? '<p class="ai-learning-card__meta"><span class="ds-text-muted">الرموز:</span> ' +
              c.affected_symbols.map(function (s) {
                return '<span class="trade-reason" dir="ltr">' + DS.esc(s) + "</span>";
              }).join(" ") + "</p>"
            : "") +
          (c.affected_timeframes && c.affected_timeframes.length
            ? '<p class="ai-learning-card__meta"><span class="ds-text-muted">الفريم:</span> ' +
              DS.esc(c.affected_timeframes.join(" · ")) + "</p>"
            : "") +
          '<footer class="ai-learning-card__foot">' +
            '<span class="ds-badge ds-badge--info">' +
              DS.esc(c.lifecycle_label_ar || c.recommendation || lesson.recommendation_ar || "") + "</span>" +
            '<button type="button" class="ds-btn ds-btn--sm ai-lesson-detail">التفاصيل</button>' +
          "</footer>" +
        "</article>";
    });
    html += "</div>";
    el.innerHTML = DS.SectionCard({ title: "دروس التعلّم", body: html });

    el.querySelectorAll(".ai-lesson-detail").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        var card = btn.closest(".ai-learning-card");
        if (!card || !window.AIExplain) return;
        var id = card.getAttribute("data-lesson-id");
        var found = cards.find(function (x) {
          return (x.lesson_id || (x.lesson && x.lesson.lesson_id)) === id;
        });
        if (found) AIExplain.openLessonDrawer(found.lesson || found);
      });
    });
  }

  function renderEvaluation(el, data) {
    if (!data || !data.available) {
      el.innerHTML = DS.EmptyState({ title: "التقييم", text: "لا تقييمات بعد." });
      return;
    }
    var rel = data.reliability_label_ar || data.reliability_label || "";
    var caution = data.accuracy_caution || "";
    el.innerHTML = DS.SectionCard({
      title: "تقييم المستشار",
      meta: rel,
      body:
        DS.StatGrid([
          {
            label: "الدقة",
            value: data.overall_accuracy != null ? DS.fmtPct(data.overall_accuracy, 1) : "—",
            foot: caution ? '<span class="ds-text-muted">' + DS.esc(caution) + "</span>" : "",
          },
          { label: "العيّنة", value: data.sample_size || 0 },
          { label: "الموثوقية", value: rel || "—" },
          { label: "الدرجة", value: DS.fmtNum(data.advisor_score, 0) },
        ], 4) +
        (data.interpretable === false
          ? '<div style="height:var(--ds-sp-3)"></div>' +
            DS.InsightCard({
              tone: "warn",
              title: "عيّنة غير كافية",
              text: "لا تُفسَّر الدقة الحالية على أنها فشل للنموذج — العيّنة صغيرة جداً (" +
                (data.sample_size || 0) + " تقييمات).",
            })
          : ""),
    });
  }

  function renderProviders(el, data) {
    var providers = (data && data.providers) || [];
    if (!providers.length) {
      el.innerHTML = DS.EmptyState({ title: "إحصاءات المزوّد", text: "لا مراجعات بعد." });
      return;
    }
    var rows = providers.map(function (p) {
      return "<tr><td>" + DS.esc(p.provider) + "</td><td>" + p.review_count +
        "</td><td>" + p.total_tokens + "</td><td>$" + Number(p.total_cost).toFixed(4) +
        "</td><td>" + DS.fmtNum(p.avg_latency_ms, 0) + "ms</td></tr>";
    }).join("");
    el.innerHTML = '<div class="table-wrap"><table class="table"><thead><tr>' +
      "<th>مزوّد</th><th>مراجعات</th><th>توكنات</th><th>تكلفة</th><th>زمن</th></tr></thead><tbody>" +
      rows + "</tbody></table></div>";
  }

  function renderModelsLeaderboard(el, data) {
    var lb = (data && data.leaderboard) || {};
    var claude = lb.claude || {};
    var ollama = lb.ollama || {};
    var diff = lb.difference || {};
    function providerCard(name, p, costLabel) {
      return '<div class="ai-model-card">' +
        '<h3 class="ai-model-card__title">' + DS.esc(name) + "</h3>" +
        '<dl class="ds-kv">' +
          "<dt>الحالة</dt><dd>" + (p.reviews ? "نشط" : "لا بيانات") + "</dd>" +
          "<dt>مراجعات</dt><dd>" + DS.fmtInt(p.reviews) + "</dd>" +
          "<dt>نجاح</dt><dd>" + DS.fmtNum(p.success_rate, 1) + "%</dd>" +
          "<dt>ثقة</dt><dd>" + DS.fmtNum(p.avg_confidence, 1) + "%</dd>" +
          "<dt>زمن</dt><dd>" + DS.fmtNum(p.avg_latency_ms, 0) + " ms</dd>" +
          "<dt>تأصيل</dt><dd>" + DS.fmtNum(p.avg_grounding, 1) + "</dd>" +
          "<dt>هلوسة</dt><dd>" + DS.fmtNum(p.avg_hallucination, 1) + "</dd>" +
          "<dt>تكلفة</dt><dd>" + costLabel + "</dd>" +
        "</dl></div>";
    }
    el.innerHTML = DS.SectionCard({
      title: "النماذج — Claude vs Qwen",
      meta: lb.note || "مراقبة فقط — لا اختيار فائز",
      body:
        '<div class="ai-models-grid">' +
          providerCard("Claude", claude, "$" + Number(claude.estimated_cost || 0).toFixed(4)) +
          providerCard("Qwen (Ollama)", ollama, "$0 API") +
        "</div>" +
        '<div class="ai-models-diff">' +
          "<strong>الفرق (Claude − Qwen):</strong> " +
          "ثقة " + DS.fmtNum(diff.confidence, 1) + " · " +
          "زمن " + DS.fmtNum(diff.latency_ms, 0) + " ms · " +
          "تأصيل " + DS.fmtNum(diff.grounding, 1) +
        "</div>",
    });
  }

  function renderComparisons(el, data) {
    var items = (data && data.items) || [];
    if (!items.length) {
      el.innerHTML = DS.SectionCard({
        title: "مقارنات حديثة",
        body: '<p class="ds-text-muted">لا مقارنات بعد. فعّل وضع compare في الإعدادات.</p>',
      });
      return;
    }
    var rows = items.map(function (c) {
      return "<tr>" +
        "<td dir=\"ltr\">" + DS.esc(c.symbol || "") + "</td>" +
        "<td dir=\"ltr\">" + DS.esc(c.timeframe || "") + "</td>" +
        "<td>" + DS.esc(c.claude_agreement || "—") + " / " +
          DS.fmtNum(c.claude_confidence, 0) + "%</td>" +
        "<td>" + DS.esc(c.local_agreement || "—") + " / " +
          DS.fmtNum(c.local_confidence, 0) + "%</td>" +
        "<td>" + DS.fmtNum(c.claude_latency_ms, 0) + " / " +
          DS.fmtNum(c.local_latency_ms, 0) + " ms</td>" +
        "</tr>";
    }).join("");
    el.innerHTML = DS.SectionCard({
      title: "مقارنات حديثة",
      body: '<div class="table-wrap"><table class="table"><thead><tr>' +
        "<th>رمز</th><th>فريم</th><th>Claude</th><th>Qwen</th><th>زمن</th>" +
        "</tr></thead><tbody>" + rows + "</tbody></table></div>",
    });
  }

  function loadHistoryPage(page) {
    fetch("/api/ai/reviews/?page=" + (page || 1))
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var el = document.getElementById("w-review-history");
        if (!el) return;
        el.setAttribute("data-state", "ready");
        var host = el.querySelector(".ds-widget__content");
        if (host && window.AIExplain) AIExplain.renderHistoryTable(host, d, loadHistoryPage);
      });
  }

  var aiUrl = "/api/widgets/ai-platform/" + qs;
  var healthUrl = "/api/widgets/health/" + qs;
  var advisorUrl = "/api/widgets/ai-advisor/";
  var evalUrl = "/api/widgets/ai-advisor-evaluation/";
  var learnUrl = "/api/widgets/ai-learning/";

  DS.loadWidget({ id: "w-verdict", url: healthUrl, render: renderVerdict });

  DS.initTabs({
    tabsSelector: "#ai-tabs",
    panelSelector: "#ai-panels",
    syncUrl: true,
    onShow: function (name) {
      if (name === "overview") {
        DS.loadWidget({ id: "w-advisor-runtime", url: advisorUrl, render: renderAdvisorRuntime });
        DS.loadWidget({ id: "w-foundations", url: healthUrl, render: renderFoundations });
        DS.loadWidget({ id: "w-modules", url: aiUrl, render: renderModules });
      } else if (name === "live") {
        var liveShell = document.getElementById("w-live-review");
        var liveEl = liveShell && liveShell.querySelector(".ds-widget__content");
        if (liveEl && window.AIExplain) {
          AIExplain.startLivePolling(liveEl, 12000);
        } else if (liveShell) {
          liveShell.setAttribute("data-state", "ready");
        }
      } else if (name === "history") {
        loadHistoryPage(1);
      } else if (name === "learning") {
        DS.loadWidget({ id: "w-learning", url: learnUrl, render: renderLearning });
      } else if (name === "evaluation") {
        DS.loadWidget({ id: "w-evaluation", url: evalUrl, render: renderEvaluation });
      } else if (name === "providers") {
        fetch("/api/ai/providers/", { credentials: "same-origin" })
          .then(function (r) { return r.json(); })
          .then(function (d) {
            var shell = document.getElementById("w-providers");
            var el = shell && shell.querySelector(".ds-widget__content");
            if (el) renderProviders(el, d);
            if (shell) shell.setAttribute("data-state", "ready");
          })
          .catch(function () {
            var shell = document.getElementById("w-providers");
            if (shell) shell.setAttribute("data-state", "error");
          });
      } else if (name === "models") {
        fetch("/api/ai/local/leaderboard/", { credentials: "same-origin" })
          .then(function (r) { return r.json(); })
          .then(function (d) {
            var shell = document.getElementById("w-models");
            var el = shell && shell.querySelector(".ds-widget__content");
            if (el) renderModelsLeaderboard(el, d);
            if (shell) shell.setAttribute("data-state", "ready");
          })
          .catch(function () {
            var shell = document.getElementById("w-models");
            if (shell) shell.setAttribute("data-state", "error");
          });
        fetch("/api/ai/local/comparisons/?limit=10", { credentials: "same-origin" })
          .then(function (r) { return r.json(); })
          .then(function (d) {
            var shell = document.getElementById("w-compare");
            var el = shell && shell.querySelector(".ds-widget__content");
            if (el) renderComparisons(el, d);
            if (shell) shell.setAttribute("data-state", "ready");
          })
          .catch(function () {
            var shell = document.getElementById("w-compare");
            if (shell) shell.setAttribute("data-state", "error");
          });
      } else if (name === "prediction") {
        DS.loadWidget({ id: "w-prediction", url: aiUrl, render: renderPrediction });
      } else if (name === "fusion") {
        DS.loadWidget({ id: "w-fusion", url: aiUrl, render: renderFusion });
      } else if (name === "decision") {
        DS.loadWidget({ id: "w-decision", url: aiUrl, render: renderDecision });
      } else if (name === "features") {
        DS.loadWidget({ id: "w-features", url: aiUrl, render: renderFeatures });
      }
    },
  });

  // Deep-link: ?review=adv_xxx opens drawer
  (function () {
    var m = location.search.match(/[?&]review=([^&]+)/);
    if (m && window.AIExplain) AIExplain.openReview(decodeURIComponent(m[1]));
  })();
})();
