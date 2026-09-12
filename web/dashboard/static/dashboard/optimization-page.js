/**
 * Optimization page.
 *
 * The engine runs from the shell, so the empty state has to teach the whole
 * procedure — what to choose, what to run, and how long it takes — instead of
 * printing "no results".
 */
(function () {
  "use strict";

  var URL_SUMMARY = "/api/widgets/optimization-summary/";
  var URL_RUN = "/api/optimization/run/";
  var RUN_SNIPPET =
    "from scanner.optimization import OptimizationService\n" +
    "svc = OptimizationService()\n" +
    "space = svc.build_space(min_score_range=(60, 85, 5), require_htf=True)\n" +
    "report = svc.optimize(space, method='grid')";

  // ── Shared pieces ───────────────────────────────────────────────────────

  function paramChips(params) {
    var keys = Object.keys(params || {});
    if (!keys.length) return '<span class="ds-text-muted">افتراضي</span>';
    return '<div class="opt-params">' + keys.map(function (k) {
      return '<span class="opt-param"><span class="opt-param__key">' + DS.esc(k) +
        '</span>=<span class="opt-param__val">' + DS.esc(String(params[k])) + "</span></span>";
    }).join("") + "</div>";
  }

  function noRunsEmpty(extraText) {
    return DS.EmptyState({
      icon: "◮",
      title: "لم تُشغَّل أي دورة تحسين بعد",
      text: extraText || "التحسين يبحث في مجموعات المعاملات عن التركيبة صاحبة أفضل توقّع، " +
        "ثم يتحقّق منها خارج العيّنة قبل قبولها. لا توجد نتائج تُعرض حتى تُشغَّل أول دورة.",
      steps: [
        "اختر نطاق المعاملات (الدرجة، الفريم الأعلى، الحدّ الأدنى للثقة)",
        "اختر السوق ومدى التاريخ",
        "شغّل الدورة من الطرفية",
        "راجع لوحة المتصدرين ثم Walk-Forward",
      ],
      actions: [
        { id: "opt-run", label: "شغّل التحسين الآن", primary: true },
        { id: "opt-copy", label: "انسخ أمر التشغيل" },
        { href: "/research/", label: "افتح مختبر البحث" },
      ],
      meta: "الزمن المتوقّع: بحث شبكي صغير (نحو 50 تركيبة) من دقيقة إلى ثلاث · بحث موسّع حتى 15 دقيقة",
    });
  }

  /** Wires copy/run buttons rendered by noRunsEmpty, when present. */
  function bindActions(scope) {
    var copyBtn = scope.querySelector("#opt-copy");
    if (copyBtn) {
      copyBtn.onclick = function () {
        var done = function () {
          copyBtn.textContent = "نُسخ الأمر ✓";
          setTimeout(function () { copyBtn.textContent = "انسخ أمر التشغيل"; }, 2200);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(RUN_SNIPPET).then(done, done);
        } else {
          done();
        }
      };
    }
    var runBtn = scope.querySelector("#opt-run");
    if (runBtn) {
      runBtn.onclick = function () {
        runBtn.disabled = true;
        runBtn.textContent = "يعمل…";
        window.postJSON(URL_RUN, {})
          .then(function (d) {
            if (d.ok) {
              runBtn.textContent = "اكتمل ✓";
              DS.loadWidget({ id: "w-opt-summary", url: URL_SUMMARY, render: renderSummary });
            } else {
              runBtn.textContent = d.message || d.error || "فشل";
            }
            setTimeout(function () {
              runBtn.disabled = false;
              runBtn.textContent = "شغّل التحسين الآن";
            }, 3000);
          })
          .catch(function () {
            runBtn.textContent = "تعذّر التشغيل";
            runBtn.disabled = false;
          });
      };
    }
  }

  // ── Summary strip ───────────────────────────────────────────────────────

  function renderSummary(el, data) {
    var latest = data.latest;
    var lb = data.leaderboard;
    var history = data.history || [];
    var top = (lb && lb.top_strategies) || [];
    var best = top[0];

    if (!latest) {
      el.innerHTML = DS.InsightCard({
        tone: "info",
        title: "لا بيانات تحسين",
        text: "شغّل أول دورة لترى هنا أفضل توقّع، عدد التركيبات المقيَّمة، وحالة آخر تجربة.",
      });
      return;
    }

    el.innerHTML = DS.StatGrid([
      {
        label: "أفضل توقّع",
        value: best ? DS.fmtR(best.expectancy) : "—",
        tone: "success",
        valueTone: DS.toneForValue(best && best.expectancy),
        foot: '<span class="ds-text-muted">' +
          (best && best.closed_trades ? best.closed_trades + " صفقة" : "أعلى تركيبة") + "</span>",
      },
      {
        label: "تركيبات مقيَّمة",
        value: String((lb && lb.total_evaluated) || top.length || 0),
        tone: "info",
        foot: '<span class="ds-text-muted">' + DS.esc(latest.method || "—") + "</span>",
      },
      {
        label: "حالة آخر تجربة",
        value: DS.esc(latest.status || "—"),
        valueTone: latest.status === "completed" ? "success" : "warn",
        foot: '<span class="ds-text-muted">' + DS.esc(shortDate(latest.started_at)) + "</span>",
      },
      {
        label: "دورات مسجّلة",
        value: String(history.length),
        foot: '<span class="ds-text-muted">في السجل</span>',
      },
    ], 4);
  }

  function shortDate(v) {
    if (!v) return "—";
    try {
      var d = new Date(v);
      return isNaN(d.getTime()) ? String(v).slice(0, 16)
        : d.toLocaleDateString("ar", { month: "short", day: "numeric" }) + " " +
          d.toLocaleTimeString("ar", { hour: "2-digit", minute: "2-digit" });
    } catch (e) { return String(v).slice(0, 16); }
  }

  // ── Leaderboard ─────────────────────────────────────────────────────────

  function renderLeaderboard(el, data) {
    var lb = data.leaderboard;
    var top = (lb && lb.top_strategies) || [];
    if (!top.length) {
      el.innerHTML = noRunsEmpty();
      bindActions(el);
      return;
    }

    var rows = top.map(function (s, i) {
      return {
        rank: '<span class="opt-rank' + (i === 0 ? " opt-rank--1" : "") + '">' + (i + 1) + "</span>",
        params: paramChips(s.params),
        expectancy: DS.TrendIndicator({ value: s.expectancy }),
        pf: DS.fmtNum(s.profit_factor, 2),
        wr: DS.fmtPct(s.win_rate),
        n: s.closed_trades || "—",
        score: '<strong>' + DS.fmtNum(s.composite_score, 3) + "</strong>",
      };
    });

    el.innerHTML =
      DS.SectionCard({
        flush: true,
        body: DS.DataTable({
          columns: [
            { key: "rank", label: "#", width: "6%" },
            { key: "params", label: "المعاملات", width: "34%" },
            { key: "expectancy", label: "التوقّع", align: "end", width: "13%" },
            { key: "pf", label: "PF", align: "end", width: "11%" },
            { key: "wr", label: "نجاح", align: "end", width: "11%" },
            { key: "n", label: "n", align: "end", width: "9%" },
            { key: "score", label: "الدرجة", align: "end", width: "16%" },
          ],
          rows: rows,
        }),
      }) +
      '<div style="height:var(--ds-sp-3)"></div>' +
      DS.InsightCard({
        tone: "warn",
        title: "الدرجة الأعلى ليست قراراً",
        text: "الترتيب مبنيّ على أداء داخل العيّنة. لا تعتمد أي تركيبة قبل قراءة نتيجتها في تبويب Walk-Forward.",
      });
  }

  // ── Accepted / rejected ─────────────────────────────────────────────────

  /**
   * A parameter set is treated as accepted when it clears the same bar the
   * platform uses elsewhere: positive expectancy, profit factor above one and
   * a sample large enough to mean something.
   */
  function partition(top) {
    var accepted = [];
    var rejected = [];
    top.forEach(function (s) {
      var exp = DS.num(s.expectancy);
      var pf = DS.num(s.profit_factor);
      var n = DS.num(s.closed_trades) || 0;
      var reasons = [];
      if (exp === null || exp <= 0) reasons.push("توقّع غير موجب");
      if (pf !== null && pf < 1) reasons.push("عامل ربح دون 1");
      if (n < 20) reasons.push("عيّنة أقل من 20 صفقة");
      if (reasons.length) rejected.push({ s: s, reasons: reasons });
      else accepted.push(s);
    });
    return { accepted: accepted, rejected: rejected };
  }

  function renderAccepted(el, data) {
    var top = (data.leaderboard && data.leaderboard.top_strategies) || [];
    if (!top.length) { el.innerHTML = noRunsEmpty(); bindActions(el); return; }

    var acc = partition(top).accepted;
    if (!acc.length) {
      el.innerHTML = DS.EmptyState({
        icon: "◍",
        title: "لا تركيبة اجتازت البوابة",
        text: "لم تحقّق أي مجموعة معاملات توقّعاً موجباً وعامل ربح فوق 1 على عيّنة لا تقلّ عن عشرين صفقة.",
        steps: ["وسّع نطاق البحث", "اجمع صفقات أكثر", "أعد تشغيل الدورة"],
        actions: [{ href: "/analytics/", label: "افحص التحليلات أولاً", primary: true }],
      });
      return;
    }
    el.innerHTML =
      DS.SectionHeader({ title: "تركيبات اجتازت البوابة", note: acc.length + " تركيبة" }) +
      acc.map(function (s) {
        return DS.SectionCard({
          tight: true,
          body:
            '<div class="ds-row" style="margin-bottom:.5rem">' +
              DS.StatusBadge({ label: "مقبولة", tone: "success", dot: true }) +
              '<span class="ds-spacer"></span>' +
              DS.TrendIndicator({ value: s.expectancy }) +
            "</div>" + paramChips(s.params) +
            '<div class="ds-text-xs ds-text-muted" style="margin-top:.5rem">' +
              "PF " + DS.fmtNum(s.profit_factor, 2) + " · نجاح " + DS.fmtPct(s.win_rate) +
              " · " + (s.closed_trades || 0) + " صفقة</div>",
        }) + '<div style="height:var(--ds-sp-2)"></div>';
      }).join("");
  }

  function renderRejected(el, data) {
    var top = (data.leaderboard && data.leaderboard.top_strategies) || [];
    if (!top.length) { el.innerHTML = noRunsEmpty(); bindActions(el); return; }

    var rej = partition(top).rejected;
    if (!rej.length) {
      el.innerHTML = DS.EmptyState({
        icon: "✓",
        title: "لا تركيبة مرفوضة",
        text: "كل التركيبات في لوحة المتصدرين اجتازت بوابة القبول.",
        inline: true,
      });
      return;
    }
    el.innerHTML =
      DS.SectionHeader({ title: "تركيبات لم تجتز البوابة", note: rej.length + " تركيبة" }) +
      rej.map(function (r) {
        return DS.SectionCard({
          tight: true,
          body:
            '<div class="ds-row" style="margin-bottom:.5rem">' +
              r.reasons.map(function (x) {
                return DS.StatusBadge({ label: x, tone: "risk" });
              }).join("") +
              '<span class="ds-spacer"></span>' +
              DS.TrendIndicator({ value: r.s.expectancy }) +
            "</div>" + paramChips(r.s.params),
        }) + '<div style="height:var(--ds-sp-2)"></div>';
      }).join("");
  }

  // ── Walk-forward ────────────────────────────────────────────────────────

  function renderWalkForward(el, data) {
    var top = (data.leaderboard && data.leaderboard.top_strategies) || [];
    var withWf = top.filter(function (s) { return s.oos_performance || s.walk_forward; });

    if (!top.length) { el.innerHTML = noRunsEmpty(); bindActions(el); return; }

    if (!withWf.length) {
      el.innerHTML = DS.EmptyState({
        icon: "◑",
        title: "لم يُشغَّل تحقّق خارج العيّنة",
        text: "Walk-Forward يعيد تقييم أفضل المعاملات على فترات لم تُستخدم في البحث. " +
          "بدونه لا يمكن تمييز الميزة الحقيقية من ملاءمة الضجيج.",
        steps: ["اختر أفضل تركيبة من لوحة المتصدرين", "شغّل walk_forward عليها", "قارن الداخل بالخارج"],
        actions: [{ id: "opt-copy", label: "انسخ أمر التشغيل", primary: true }],
        meta: "الزمن المتوقّع: من دقيقتين إلى عشر حسب عدد النوافذ",
      });
      bindActions(el);
      return;
    }

    el.innerHTML =
      DS.SectionHeader({ title: "الأداء داخل العيّنة مقابل خارجها" }) +
      withWf.map(function (s) {
        var oos = s.oos_performance || {};
        var inSample = DS.num(s.expectancy);
        var outSample = DS.num(oos.expectancy);
        var decay = inSample !== null && outSample !== null ? outSample - inSample : null;
        return DS.SectionCard({
          tight: true,
          body: paramChips(s.params) +
            '<div style="height:var(--ds-sp-3)"></div>' +
            DS.Distribution([
              { label: "داخل العيّنة", value: inSample, tone: DS.toneForValue(inSample) },
              { label: "خارج العيّنة", value: outSample, tone: DS.toneForValue(outSample) },
            ]) +
            (decay !== null
              ? '<div style="height:var(--ds-sp-2)"></div>' + DS.InsightCard({
                  tone: decay < -0.15 ? "risk" : decay < 0 ? "warn" : "success",
                  title: decay < -0.15 ? "تدهور كبير خارج العيّنة"
                    : decay < 0 ? "تدهور طفيف" : "صمدت خارج العيّنة",
                  text: "الفارق " + DS.fmtR(decay) + " لكل صفقة بين الداخل والخارج." +
                    (decay < -0.15 ? " هذا نمط ملاءمة زائدة — لا تعتمد التركيبة." : ""),
                })
              : ""),
        }) + '<div style="height:var(--ds-sp-2)"></div>';
      }).join("");
  }

  // ── History ─────────────────────────────────────────────────────────────

  function renderHistory(el, data) {
    var hist = data.history || [];
    if (!hist.length) { el.innerHTML = noRunsEmpty(); bindActions(el); return; }
    el.innerHTML =
      DS.SectionHeader({ title: "سجل الدورات", note: hist.length + " دورة" }) +
      DS.Timeline(hist.map(function (h) {
        return {
          title: (h.title || h.experiment_id || "دورة") + " · " + (h.method || ""),
          meta: shortDate(h.started_at) +
            (h.trade_count ? " · " + h.trade_count + " صفقة" : "") +
            " · " + (h.status || ""),
          tone: h.status === "completed" ? "success"
            : h.status === "failed" ? "risk" : "warn",
        };
      }));
  }

  // ── Boot ────────────────────────────────────────────────────────────────

  DS.loadWidget({ id: "w-opt-summary", url: URL_SUMMARY, render: renderSummary });

  var PANELS = {
    leaderboard: { id: "w-leaderboard", render: renderLeaderboard },
    accepted: { id: "w-accepted", render: renderAccepted },
    rejected: { id: "w-rejected", render: renderRejected },
    walkforward: { id: "w-walkforward", render: renderWalkForward },
    history: { id: "w-history", render: renderHistory },
  };

  DS.initTabs({
    tabsSelector: "#opt-tabs",
    panelSelector: "#opt-panels",
    syncUrl: true,
    onShow: function (name) {
      var p = PANELS[name];
      if (p) DS.loadWidget({ id: p.id, url: URL_SUMMARY, render: p.render });
    },
  });
})();
