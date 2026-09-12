/**
 * Analytics and research renderers.
 *
 * Every view here used to be a wide table. Where the question is comparative
 * ("which slice is better?") the table is replaced by a distribution or a
 * heatmap, because a bar answers that question without being read row by row.
 */
(function (global) {
  "use strict";

  var charts = {};

  function destroyChart(key) {
    if (charts[key]) { charts[key].destroy(); charts[key] = null; }
  }

  // ── Trends ──────────────────────────────────────────────────────────────

  function renderTrends(el, data) {
    var t = data.trends || {};
    var eq = t.equity || [];
    var deg = t.degradation || {};

    if (!eq.length) {
      el.innerHTML = DS.EmptyState({
        icon: "◔",
        title: "لا منحنى بعد",
        text: "يُبنى اتجاه الأداء من الصفقات المحسومة. بعد أول عشرين صفقة يصبح الاتجاه قابلاً للقراءة.",
        actions: [{ href: "/trades/", label: "الصفقات", primary: true }],
      });
      return;
    }

    var last = eq[eq.length - 1].cumulative_r;
    var degTone = deg.level === "critical" ? "risk" : deg.level === "warn" ? "warn" : "success";

    el.innerHTML =
      DS.StatGrid([
        {
          label: "الحصيلة التراكمية", value: DS.fmtR(last),
          tone: DS.toneForValue(last), valueTone: DS.toneForValue(last),
          foot: '<span class="ds-text-muted">' + eq.length + " صفقة محسومة</span>",
        },
        {
          label: "توقّع آخر 30", value: DS.fmtR(deg.rolling_30),
          valueTone: DS.toneForValue(deg.rolling_30),
        },
        {
          label: "توقّع آخر 50", value: DS.fmtR(deg.rolling_50),
          valueTone: DS.toneForValue(deg.rolling_50),
        },
      ], 3) +
      '<div style="height:var(--ds-sp-4)"></div>' +
      DS.InsightCard({
        tone: degTone,
        title: deg.level === "none" || !deg.level ? "الاتجاه مستقر" : "تنبيه اتجاه",
        text: deg.message || "لا تغيّر جوهري في الأداء الأخير.",
      }) +
      '<div style="height:var(--ds-sp-4)"></div>' +
      '<div class="analytics-grid">' +
        DS.SectionCard({
          title: "منحنى الحصيلة التراكمية",
          body: '<div class="analytics-chart"><canvas id="an-equity"></canvas></div>',
        }) +
        DS.SectionCard({
          title: "التوقّع المتحرّك",
          meta: "نافذتا 30 و50",
          body: '<div class="analytics-chart"><canvas id="an-rolling"></canvas></div>',
        }) +
      "</div>";

    drawEquity(eq);
    drawRolling(t.rolling_30 || [], t.rolling_50 || []);
  }

  // Canvas text obeys bidi too, so an unisolated "-0.1" axis tick draws as
  // "0.1-" on this RTL page.
  var AXIS = {
    color: "#97a0b5",
    font: { size: 10 },
    callback: function (v) { return "\u2066" + v + "\u2069"; },
  };
  var GRID = { color: "rgba(255,255,255,.045)" };

  function drawEquity(eq) {
    var c = document.getElementById("an-equity");
    if (!c || typeof Chart === "undefined") return;
    destroyChart("equity");
    var last = eq[eq.length - 1].cumulative_r;
    var color = last >= 0 ? "#3ddc97" : "#ff6b6b";
    var grad = c.getContext("2d").createLinearGradient(0, 0, 0, 250);
    grad.addColorStop(0, last >= 0 ? "rgba(61,220,151,.2)" : "rgba(255,107,107,.2)");
    grad.addColorStop(1, "rgba(0,0,0,0)");
    charts.equity = new Chart(c, {
      type: "line",
      data: {
        labels: eq.map(function (p) { return p.index; }),
        datasets: [{
          data: eq.map(function (p) { return p.cumulative_r; }),
          borderColor: color, backgroundColor: grad, fill: true,
          tension: .25, pointRadius: 0, borderWidth: 1.75,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { intersect: false, mode: "index" },
        plugins: {
          legend: { display: false },
          tooltip: { displayColors: false,
            callbacks: { label: function (x) { return DS.fmtR(x.parsed.y); } } },
        },
        scales: { x: { display: false }, y: { grid: GRID, ticks: AXIS } },
      },
    });
  }

  function drawRolling(r30, r50) {
    var c = document.getElementById("an-rolling");
    if (!c || typeof Chart === "undefined" || (!r30.length && !r50.length)) return;
    destroyChart("rolling");
    charts.rolling = new Chart(c, {
      type: "line",
      data: {
        labels: (r30.length ? r30 : r50).map(function (p) { return p.index; }),
        datasets: [
          { label: "30 صفقة", data: r30.map(function (p) { return p.expectancy; }),
            borderColor: "#e8c05a", tension: .25, pointRadius: 0, borderWidth: 1.6 },
          { label: "50 صفقة", data: r50.map(function (p) { return p.expectancy; }),
            borderColor: "#6ba4ff", tension: .25, pointRadius: 0, borderWidth: 1.6 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { intersect: false, mode: "index" },
        plugins: {
          legend: { position: "bottom",
            labels: { boxWidth: 10, font: { size: 10 }, color: "#97a0b5" } },
        },
        scales: { x: { display: false }, y: { grid: GRID, ticks: AXIS } },
      },
    });
  }

  // ── Factor contribution ─────────────────────────────────────────────────

  function renderFactors(el, data) {
    var items = data.contributions || [];
    if (!items.length) {
      el.innerHTML = DS.EmptyState({
        icon: "◇",
        title: "لا عوامل كافية بعد",
        text: "يقيس هذا التحليل كم يضيف كل عامل دخول إلى التوقّع. يحتاج كل عامل عيّنة كافية قبل أن يظهر.",
        actions: [{ href: "/trades/", label: "الصفقات", primary: true }],
      });
      return;
    }

    var helps = items.filter(function (f) { return f.verdict === "helps"; });
    var hurts = items.filter(function (f) { return f.verdict === "hurts"; });

    el.innerHTML =
      DS.StatGrid([
        { label: "عوامل تساعد", value: String(helps.length), tone: "success", valueTone: "success" },
        { label: "عوامل تضر", value: String(hurts.length), tone: "risk", valueTone: "risk" },
        { label: "عوامل محايدة", value: String(items.length - helps.length - hurts.length) },
      ], 3) +
      '<div style="height:var(--ds-sp-4)"></div>' +
      DS.SectionCard({
        title: "الأثر الهامشي لكل عامل",
        meta: "الفرق في التوقّع بوجود العامل مقابل غيابه",
        body: DS.Distribution(items.map(function (f) {
          return {
            label: f.label,
            value: f.marginal_delta,
            text: DS.fmtR(f.marginal_delta),
            tone: DS.toneForValue(f.marginal_delta),
          };
        })),
      }) +
      '<div style="height:var(--ds-sp-4)"></div>' +
      DS.SectionCard({
        flush: true,
        body: DS.DataTable({
          columns: [
            { key: "label", label: "العامل", width: "30%" },
            { key: "freq", label: "تكرار", align: "end", width: "14%" },
            { key: "closed", label: "محسومة", align: "end", width: "14%" },
            { key: "exp", label: "التوقّع", align: "end", width: "16%" },
            { key: "verdict", label: "الحكم", width: "26%" },
          ],
          rows: items.map(function (f) {
            return {
              label: '<span class="ds-cell-strong">' + DS.esc(f.label) + "</span>",
              freq: DS.fmtPct(f.frequency_pct, 0),
              closed: f.closed,
              exp: DS.TrendIndicator({ value: f.expectancy }),
              verdict: DS.StatusBadge({
                label: f.verdict === "helps" ? "يساعد" : f.verdict === "hurts" ? "يضر" : "محايد",
                tone: f.verdict === "helps" ? "success" : f.verdict === "hurts" ? "risk" : "neutral",
              }),
            };
          }),
        }),
      });
  }

  // ── Splits ──────────────────────────────────────────────────────────────

  function renderSplits(el, data) {
    var splits = data.splits || [];
    var overall = data.overall || {};
    var populated = splits.filter(function (s) { return s.rows && s.rows.length; });

    if (!populated.length) {
      el.innerHTML = DS.EmptyState({
        icon: "◫",
        title: "لا شرائح كافية",
        text: "تحتاج كل شريحة ثلاث صفقات محسومة على الأقل قبل أن تُعرض، وإلا كان الرقم انطباعاً لا قياساً.",
        actions: [{ href: "/trades/", label: "الصفقات", primary: true }],
      });
      return;
    }

    el.innerHTML =
      DS.StatGrid([
        { label: "محسومة", value: String(overall.closed || 0) },
        { label: "نسبة النجاح", value: DS.fmtPct(overall.win_rate),
          valueTone: overall.win_rate >= 50 ? "success" : "warn" },
        { label: "التوقّع", value: DS.fmtR(overall.expectancy),
          valueTone: DS.toneForValue(overall.expectancy) },
        { label: "الحصيلة", value: DS.fmtR(overall.total_r),
          valueTone: DS.toneForValue(overall.total_r) },
      ], 4) +
      '<div style="height:var(--ds-sp-4)"></div>' +
      '<div class="splits-grid">' + populated.map(splitCard).join("") + "</div>";
  }

  function splitCard(s) {
    var best = s.rows[0];
    var body =
      DS.Heatmap(s.rows.map(function (r) {
        return {
          label: String(r.value),
          value: r.expectancy,
          text: DS.fmtR(r.expectancy),
          sub: r.closed + " صفقة · " + DS.fmtPct(r.win_rate, 0),
        };
      })) +
      '<div style="height:var(--ds-sp-3)"></div>' +
      DS.Distribution(s.rows.map(function (r) {
        return {
          label: String(r.value),
          value: r.total_r,
          text: DS.fmtR(r.total_r),
          tone: DS.toneForValue(r.total_r),
        };
      }));

    return DS.SectionCard({
      title: s.title,
      meta: s.rows.length + " شريحة",
      body: body +
        (s.rows.length > 1 && DS.num(best.expectancy) > 0
          ? '<p class="ds-text-xs ds-text-muted" style="margin:.75rem 0 0">' +
            "الأفضل: <strong>" + DS.esc(String(best.value)) + "</strong> بتوقّع " +
            DS.fmtR(best.expectancy) + " على " + best.closed + " صفقة.</p>"
          : ""),
    });
  }

  // ── Experiments ─────────────────────────────────────────────────────────

  function renderExperiments(el, data) {
    var exps = data.experiments || [];
    if (!exps.length) {
      el.innerHTML = DS.EmptyState({
        icon: "◈",
        title: "لا تجارب مسجّلة",
        text: "التجربة تختبر فرضية واحدة على بيانات محدَّدة وتسجّل نتيجتها، حتى لا تُتّخذ القرارات من الانطباع.",
        steps: ["صُغ فرضية قابلة للدحض", "حدّد العيّنة والبذرة", "سجّل النتيجة مقارنةً بالأساس"],
        actions: [{ href: "/analytics/", label: "ابدأ من التحليلات", primary: true }],
        meta: "التجارب تُسجَّل من سجلّ الأبحاث في المستودع",
      });
      return;
    }
    el.innerHTML = DS.SectionCard({
      flush: true,
      body: DS.DataTable({
        columns: [
          { key: "hypothesis", label: "الفرضية", width: "34%" },
          { key: "status", label: "الحالة", width: "14%" },
          { key: "trades", label: "صفقات", align: "end", width: "10%" },
          { key: "exp", label: "التوقّع", align: "end", width: "14%" },
          { key: "delta", label: "Δ الأساس", align: "end", width: "14%" },
          { key: "accepted", label: "مقبولة", width: "14%" },
        ],
        rows: exps.map(function (e) {
          return {
            hypothesis: '<span class="ds-cell-strong">' + DS.esc(e.hypothesis || "—") + "</span>",
            status: DS.StatusBadge({ label: e.status || "—", tone: "neutral" }),
            trades: e.trades || "—",
            exp: DS.TrendIndicator({ value: e.expectancy }),
            delta: e.baseline_delta === null || e.baseline_delta === undefined
              ? '<span class="ds-text-muted">—</span>'
              : DS.TrendIndicator({ value: e.baseline_delta }),
            accepted: e.accepted === "yes"
              ? DS.StatusBadge({ label: "نعم", tone: "success" })
              : e.accepted === "no"
                ? DS.StatusBadge({ label: "لا", tone: "risk" })
                : DS.StatusBadge({ label: "قيد النظر", tone: "neutral" }),
          };
        }),
      }),
    });
  }

  // ── Statistical confidence ──────────────────────────────────────────────

  function renderConfidence(el, data) {
    var c = data.confidence || {};
    var n = c.sample_size || 0;
    if (!n) {
      el.innerHTML = DS.EmptyState({
        icon: "◐",
        title: "لا عيّنة لحساب الثقة",
        text: "تحتاج الفواصل الإحصائية صفقات محسومة. تظهر هذه الأعمدة تلقائياً بعد أول دفعة.",
        actions: [{ href: "/trades/", label: "الصفقات", primary: true }],
      });
      return;
    }

    var indep = data.independent_events || 0;
    // p-value inverted into a plain "how sure are we this is not luck" reading.
    var certainty = c.p_value_vs_zero === null || c.p_value_vs_zero === undefined
      ? null : (1 - Number(c.p_value_vs_zero)) * 100;

    el.innerHTML =
      DS.SectionCard({
        title: "ما مدى ثقتنا في هذه الأرقام؟",
        meta: n + " صفقة · " + indep + " حدث مستقل",
        body:
          DS.ConfidenceBar({
            label: "ليست صدفة",
            value: certainty,
            note: certainty === null ? "لا يمكن حساب الدلالة على هذه العيّنة"
              : "احتمال أن يكون هذا الأداء محض حظّ: " +
                DS.fmtPct(Number(c.p_value_vs_zero) * 100, 1),
          }) +
          DS.ConfidenceBar({
            label: "نسبة النجاح",
            value: c.win_rate,
            note: "المجال الحقيقي بين " + DS.fmtPct(c.win_rate_low) + " و" +
              DS.fmtPct(c.win_rate_high) + " (ويلسون)",
          }) +
          DS.ConfidenceBar({
            label: "كفاية العيّنة",
            value: Math.min(100, n / 50 * 100),
            note: n >= 50 ? "العيّنة كافية للاستنتاج"
              : n >= 20 ? "العيّنة مقبولة ولا تزال حسّاسة للصفقات الجديدة"
              : "العيّنة قصيرة — الأرقام ضجيج أكثر منها إشارة",
          }) +
          DS.ConfidenceBar({
            label: "استقلال الأحداث",
            value: n ? Math.min(100, indep / n * 100) : 0,
            note: "الصفقات المتزامنة على السوق نفسه تكرّر المخاطرة ولا تضيف دليلاً",
          }),
      }) +
      '<div style="height:var(--ds-sp-4)"></div>' +
      DS.SectionCard({
        title: "التوقّع ومجال الثقة",
        body: DS.StatGrid([
          { label: "التوقّع", value: DS.fmtR(c.expectancy),
            valueTone: DS.toneForValue(c.expectancy),
            foot: '<span class="ds-text-muted">لكل صفقة</span>' },
          { label: "الحدّ الأدنى", value: DS.fmtR(c.expectancy_ci_low),
            valueTone: DS.toneForValue(c.expectancy_ci_low) },
          { label: "الحدّ الأعلى", value: DS.fmtR(c.expectancy_ci_high),
            valueTone: DS.toneForValue(c.expectancy_ci_high) },
        ], 3),
      }) +
      ((c.warnings || []).length
        ? '<div style="height:var(--ds-sp-3)"></div>' +
          (c.warnings || []).map(function (w) {
            return DS.InsightCard({ tone: "warn", title: "تحذير إحصائي", text: w }) +
              '<div style="height:var(--ds-sp-2)"></div>';
          }).join("")
        : '<div style="height:var(--ds-sp-3)"></div>' + DS.InsightCard({
            tone: c.significant ? "success" : "warn",
            title: c.significant ? "النتيجة ذات دلالة" : "النتيجة دون عتبة الدلالة",
            text: c.significant
              ? "التوقّع الموجب لا يُفسَّر بالصدفة عند العيّنة الحالية."
              : "لا يمكن استبعاد الصدفة بعد. وسّع العيّنة قبل بناء قرار على هذا الرقم.",
          }));
  }

  // ── Baselines ───────────────────────────────────────────────────────────

  function renderBaselines(el, data) {
    var rows = (data.baselines || {}).rows || [];
    if (!rows.length) {
      el.innerHTML = DS.EmptyState({
        icon: "◎",
        title: "لا مقارنة أساس",
        text: "المقارنة تضع أداء الاستراتيجية بجانب بدائل بسيطة. بدونها لا يُعرف إن كانت الإضافة حقيقية.",
        actions: [{ href: "/optimization/", label: "صفحة التحسين", primary: true }],
      });
      return;
    }
    var passed = rows.filter(function (r) { return r.pass_gate; }).length;
    el.innerHTML =
      DS.SectionCard({
        title: "التوقّع مقابل خطوط الأساس",
        meta: passed + " من " + rows.length + " اجتازت البوابة",
        body: DS.Distribution(rows.map(function (r) {
          return {
            label: r.name, value: r.expectancy, text: DS.fmtR(r.expectancy),
            tone: DS.toneForValue(r.expectancy),
          };
        })),
      }) +
      '<div style="height:var(--ds-sp-4)"></div>' +
      DS.SectionCard({
        flush: true,
        body: DS.DataTable({
          columns: [
            { key: "name", label: "الاستراتيجية", width: "28%" },
            { key: "trades", label: "صفقات", align: "end", width: "12%" },
            { key: "pf", label: "PF", align: "end", width: "12%" },
            { key: "dd", label: "التراجع", align: "end", width: "14%" },
            { key: "sharpe", label: "شارب", align: "end", width: "12%" },
            { key: "gate", label: "البوابة", width: "22%" },
          ],
          rows: rows.map(function (r) {
            return {
              name: '<span class="ds-cell-strong">' + DS.esc(r.name) + "</span>",
              trades: r.trades || "—",
              pf: DS.fmtNum(r.profit_factor, 2),
              dd: '<span class="ds-value-risk">' + DS.fmtRAbs(r.max_drawdown_r) + "</span>",
              sharpe: DS.fmtNum(r.sharpe, 2),
              gate: r.pass_gate
                ? DS.StatusBadge({ label: "اجتازت", tone: "success", dot: true })
                : DS.StatusBadge({ label: "لم تجتز", tone: "neutral" }),
            };
          }),
        }),
      });
  }

  function renderAutomationStatus(el, data) {
    var ui = data.ui || {};
    var obs = data.observability || {};
    var on = ui.automatic_research_on ? "ON" : "OFF";
    var onTone = ui.automatic_research_on ? "success" : "neutral";
    var stages = ui.progress_stages || [
      "queued", "dataset", "hypothesis", "metrics", "comparison", "report", "completed",
    ];
    var idx = ui.progress_index != null ? ui.progress_index : -1;
    var progressHtml = "";
    if (ui.active_job_id) {
      progressHtml = '<ol class="ds-progress-steps">';
      stages.forEach(function (s, i) {
        var cls = "ds-progress-step";
        if (i < idx) cls += " is-done";
        else if (i === idx) cls += " is-active";
        progressHtml += '<li class="' + cls + '">' + DS.esc(s) + "</li>";
      });
      progressHtml += "</ol>";
    }

    el.innerHTML =
      DS.SectionCard({
        title: "حالة البحث التلقائي",
        meta: ui.last_research_at ? "آخر تشغيل: " + DS.esc(ui.last_research_at) : "لم يُشغَّل بعد",
        body:
          DS.StatGrid([
            {
              label: "البحث التلقائي",
              value: on,
              valueTone: onTone,
              foot: '<span class="ds-text-muted">Automatic Research</span>',
            },
            {
              label: "صفقات جديدة",
              value: (ui.new_trades || 0) + " / " + (ui.new_trades_threshold || 10),
              foot: '<span class="ds-text-muted">New Trades</span>',
            },
            {
              label: "معلّقة",
              value: String(ui.pending_jobs || data.pending_jobs || 0),
              foot: '<span class="ds-text-muted">Pending</span>',
            },
            {
              label: "مكتملة",
              value: String(ui.completed_jobs || data.completed_jobs || 0),
              foot: '<span class="ds-text-muted">Completed</span>',
            },
          ], 4) +
          '<div style="height:var(--ds-sp-3)"></div>' +
          DS.StatGrid([
            {
              label: "آخر تجربة",
              value: ui.latest_experiment_id
                ? ui.latest_experiment_id.slice(0, 16) + "…"
                : "—",
            },
            {
              label: "آخر فرضية",
              value: ui.latest_hypothesis
                ? (ui.latest_hypothesis.length > 40
                  ? ui.latest_hypothesis.slice(0, 40) + "…"
                  : ui.latest_hypothesis)
                : "—",
            },
            {
              label: "آخر نتيجة",
              value: ui.latest_result || obs.latest_result || "—",
            },
            {
              label: "تشغيل يدوي / تلقائي",
              value: (obs.manual_research_count || 0) + " / " + (obs.automatic_research_count || 0),
            },
          ], 4) +
          (progressHtml
            ? '<div style="height:var(--ds-sp-4)"></div>' +
              DS.SectionCard({
                title: "تقدّم التجربة الجارية",
                meta: ui.active_job_id || "",
                body: progressHtml,
              })
            : "") +
          '<div style="height:var(--ds-sp-4)"></div>' +
          '<button type="button" class="ds-btn ds-btn--primary" id="btn-manual-research">تشغيل بحث يدوي</button>',
      });

    var btn = el.querySelector("#btn-manual-research");
    if (btn) {
      btn.onclick = function () {
        btn.disabled = true;
        fetch("/api/research/run/", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: "{}",
        })
          .then(function (r) { return r.json(); })
          .then(function () { loadAutomationStatus(); })
          .finally(function () { btn.disabled = false; });
      };
    }
  }

  global.ResearchWidgets = {
    renderTrends: renderTrends,
    renderFactors: renderFactors,
    renderSplits: renderSplits,
    renderExperiments: renderExperiments,
    renderConfidence: renderConfidence,
    renderBaselines: renderBaselines,
    renderAutomationStatus: renderAutomationStatus,
  };
})(window);
