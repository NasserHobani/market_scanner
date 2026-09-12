/**
 * Operations Dashboard.
 *
 * Answers four questions above the fold: can I trust the system, what is
 * happening now, what opportunities exist, and what should I do next.
 *
 * Every widget fetches on its own. Nothing here waits for anything else, so a
 * slow or failing endpoint degrades one card instead of the page.
 */
(function () {
  "use strict";

  var pageData = (function () {
    var el = document.getElementById("page-data");
    try { return el ? JSON.parse(el.textContent) : {}; } catch (e) { return {}; }
  })();
  var qs = pageData.query || window.location.search || "";
  var market = pageData.market || "crypto";
  var equityChart = null;
  var healthCache = null;

  function withQs(path) {
    return path + qs;
  }

  // ── System trust: one hero metric plus four supporting KPIs ─────────────

  function renderHealth(el, data) {
    var h = data.health || {};
    healthCache = h;
    var score = DS.num(h.health_score);
    var tone = DS.toneForScore(score);
    var closed = h.closed_trades || 0;

    var hero = DS.MetricCard({
      label: "صحة النظام",
      value: score === null ? "—" : String(score),
      size: "hero",
      tone: tone,
      valueTone: tone,
      foot: DS.StatusBadge({ label: h.health_label || "غير معروف", tone: tone, dot: true }) +
        '<span class="ds-text-muted">' + closed + " صفقة محسومة</span>",
    });

    var kpis = DS.StatGrid([
      {
        label: "التوقّع لكل صفقة",
        value: DS.fmtR(h.expectancy),
        valueTone: DS.toneForValue(h.expectancy),
        foot: '<span class="ds-text-muted">الحصيلة ' + DS.fmtR(h.total_r) + "</span>",
      },
      {
        label: "عامل الربح",
        value: h.profit_factor === null || h.profit_factor === undefined
          ? "—" : DS.fmtNum(h.profit_factor, 2),
        valueTone: DS.num(h.profit_factor) === null ? "muted"
          : h.profit_factor >= 1 ? "success" : "risk",
        foot: '<span class="ds-text-muted">' +
          (DS.num(h.profit_factor) === null ? "لا خسائر بعد" : "الربح ÷ الخسارة") + "</span>",
      },
      {
        label: "نسبة النجاح",
        value: DS.fmtPct(h.win_rate),
        valueTone: DS.num(h.win_rate) === null ? "muted"
          : h.win_rate >= 50 ? "success" : "warn",
        foot: '<span class="ds-text-muted">' +
          (DS.num(h.win_rate_low) === null ? "—"
            : "مجال " + DS.ltr(Math.round(h.win_rate_low) + "–" +
              Math.round(h.win_rate_high) + "%")) +
          "</span>",
      },
      {
        // Drawdown is a magnitude, so a leading "+" would read as a gain.
        label: "أقصى تراجع",
        value: DS.fmtRAbs(h.max_drawdown_r),
        valueTone: DS.num(h.max_drawdown_r) ? "risk" : "muted",
        foot: '<span class="ds-text-muted">شارب ' + DS.fmtNum(h.sharpe, 2) + "</span>",
      },
    ], 4);

    el.innerHTML = '<div class="ops-trust-row">' + hero + kpis + "</div>";
    stampUpdated();
    renderInsightIfReady();
  }

  // ── Insight: the numbers translated into a recommended posture ──────────

  var trendsCache = null;

  function renderInsightIfReady() {
    var shell = document.getElementById("w-insight");
    if (!shell || !healthCache) return;
    var content = shell.querySelector(".ds-widget__content");
    var h = healthCache;
    var score = DS.num(h.health_score);
    var deg = (trendsCache && trendsCache.degradation) || {};

    var tone, title, text;
    if (score === null || (h.closed_trades || 0) < 20) {
      tone = "info";
      title = "العيّنة ما زالت قصيرة";
      text = "عدد الصفقات المحسومة " + (h.closed_trades || 0) +
        " — تحت عشرين صفقة تكون الأرقام ضجيجاً أكثر منها إشارة. تابع التتبّع قبل الاعتماد عليها.";
    } else if (deg.level === "critical") {
      tone = "risk";
      title = "تدهور مؤكَّد — أوقف الاعتماد على التوصيات";
      text = deg.message + ". راجع التحليلات وشغّل تحسيناً قبل فتح صفقات جديدة.";
    } else if (score < 45) {
      tone = "risk";
      title = "لا تتبع التوصيات الآن";
      text = "درجة الصحة " + score + " من 100 والتوقّع " + DS.fmtR(h.expectancy) +
        ". ابدأ من صفحة التحليلات لمعرفة أي شريحة تستنزف الأداء.";
    } else if (deg.level === "warn" || score < 70) {
      tone = "warn";
      title = "تعامل بحذر";
      text = (deg.message ? deg.message + ". " : "") + "درجة الصحة " + score +
        " من 100. اقصر الدخول على الشرائح التي تثبت التحليلات تفوّقها.";
    } else {
      tone = "success";
      title = "النظام ضمن نطاقه الطبيعي";
      text = "درجة الصحة " + score + " من 100 بتوقّع " + DS.fmtR(h.expectancy) +
        " لكل صفقة. يمكن اتباع التوصيات مع الالتزام بحجم المخاطرة المعتاد.";
    }

    content.innerHTML = DS.InsightCard({ title: title, text: text, tone: tone });
    content.classList.add("ds-fade-in");
    shell.setAttribute("data-state", "ready");
  }

  // ── Current opportunities ───────────────────────────────────────────────

  function renderOpportunities(el, data) {
    var run = data.run;
    if (!run) {
      el.innerHTML = DS.SectionCard({
        title: "الفرص الحالية",
        tight: true,
        body: '<p class="ds-text-sm ds-text-muted" style="margin:0">لم يُشغَّل مسح بعد.</p>' +
          '<a class="ds-btn ds-btn--sm" style="margin-top:.5rem" href="/scanner/">شغّل الماسح</a>',
      });
      return;
    }
    var ready = run.ready || 0;
    el.innerHTML = DS.SectionCard({
      title: "الفرص الحالية",
      meta: run.timeframe,
      tight: true,
      body:
        '<div class="ops-status-value ds-value-' + (ready ? "success" : "muted") + '">' +
          ready + "</div>" +
        '<div class="ops-status-foot">' +
          '<span class="ds-text-muted">جاهزة من ' + (run.scanned || 0) + " رمزاً</span>" +
          '<a class="ds-section-header__link" href="/scanner/">الماسح ←</a>' +
        "</div>",
    });
  }

  // ── AI status ───────────────────────────────────────────────────────────

  function renderAiAdvisor(el, data) {
    var status = data.runtime_status || "disconnected";
    var statusLabels = {
      running: "يعمل",
      connected: "متصل",
      disconnected: "غير متصل",
      failed: "فشل",
      disabled: "معطّل",
    };
    var statusTones = {
      running: "success",
      connected: "info",
      disconnected: "muted",
      failed: "risk",
      disabled: "muted",
    };
    var tone = statusTones[status] || "muted";
    var label = statusLabels[status] || status;

    if (!data.available) {
      el.innerHTML = DS.SectionCard({
        title: "مستشار الذكاء الاصطناعي",
        tight: true,
        body: '<p class="ds-text-sm ds-text-muted" style="margin:0">غير متاح</p>',
      });
      return;
    }

    var diag = data.package_diagnostics || {};
    var diagRows = [
      ["إصدار الحزمة", diag.package_version || "—"],
      ["حجم الحزمة", diag.package_size_bytes ? diag.package_size_bytes + " B" : "—"],
      ["تقدير الرموز", diag.token_estimate || "—"],
      ["نسبة الضغط", diag.compression_ratio != null ? diag.compression_ratio : "—"],
      ["عدد الأدلة", diag.evidence_count != null ? diag.evidence_count : "—"],
      ["أقسام مضمنة", (diag.sections_included || []).length || "—"],
      ["أقسام محذوفة", (diag.sections_removed || []).length || "—"],
    ];

    var rows = [
      ["الحالة", label],
      ["المزوّد", data.model || data.provider || "—"],
      ["آخر مراجعة", data.last_review_time || "—"],
      ["الزمن", data.latency_ms ? data.latency_ms + " ms" : "—"],
      ["رموز المطالبة", data.prompt_tokens != null ? data.prompt_tokens : "—"],
      ["رموز الإكمال", data.completion_tokens != null ? data.completion_tokens : "—"],
      ["إجمالي الرموز", data.total_tokens != null ? data.total_tokens : "—"],
      ["التكلفة", data.estimated_cost != null ? "$" + Number(data.estimated_cost).toFixed(4) : "—"],
      ["التأصيل", data.grounding_score != null ? data.grounding_score + "%" : "—"],
      ["الهلوسة", data.hallucination_score != null ? data.hallucination_score + "%" : "—"],
      ["المراجعات", data.successful_reviews || 0],
    ];

    var body =
      '<div class="ops-status-value ds-value-' + tone + '" style="font-size:1.35rem">' +
        DS.esc(label) + "</div>" +
      '<div class="ops-advisor-metrics">' +
        rows.map(function (r) {
          return '<div class="ops-advisor-row"><span class="ds-text-muted">' +
            DS.esc(r[0]) + '</span><span dir="ltr">' + DS.esc(String(r[1])) + "</span></div>";
        }).join("") +
      "</div>" +
      '<div class="ops-advisor-metrics" style="margin-top:0.75rem;border-top:1px solid var(--ds-line);padding-top:0.5rem">' +
        '<div class="ds-text-sm ds-text-muted" style="margin-bottom:0.35rem">تشخيص الحزمة</div>' +
        diagRows.map(function (r) {
          return '<div class="ops-advisor-row"><span class="ds-text-muted">' +
            DS.esc(r[0]) + '</span><span dir="ltr">' + DS.esc(String(r[1])) + "</span></div>";
        }).join("") +
      "</div>" +
      '<div class="ops-status-foot">' +
        '<span class="ds-text-muted" dir="ltr">' + DS.esc(data.review_id || "") + "</span>" +
        '<a class="ds-section-header__link" href="/ai/">التفاصيل ←</a></div>';

    el.innerHTML = DS.SectionCard({ title: "مستشار الذكاء الاصطناعي", tight: true, body: body });
  }

  function renderAiStatus(el, data) {
    renderAiAdvisor(el, data);
  }

  // ── Optimization status ─────────────────────────────────────────────────

  function renderOptStatus(el, data) {
    var latest = data.latest;
    var lb = data.leaderboard;
    var best = lb && lb.top_strategies && lb.top_strategies[0];
    var body;
    if (!latest) {
      body =
        '<div class="ops-status-value ds-value-muted" style="font-size:1.35rem">لا تحسين</div>' +
        '<div class="ops-status-foot">' +
          '<span class="ds-text-muted">لم تُشغَّل أي دورة</span>' +
          '<a class="ds-section-header__link" href="/optimization/">ابدأ ←</a></div>';
    } else {
      body =
        '<div class="ops-status-value ds-value-' + DS.toneForValue(best && best.expectancy) + '">' +
          (best ? DS.fmtR(best.expectancy) : "—") + "</div>" +
        '<div class="ops-status-foot">' +
          '<span class="ds-text-muted">أفضل معاملات · ' +
            DS.esc(latest.method || latest.status || "") + "</span>" +
          '<a class="ds-section-header__link" href="/optimization/">التفاصيل ←</a></div>';
    }
    el.innerHTML = DS.SectionCard({ title: "حالة التحسين", tight: true, body: body });
  }

  // ── Recent performance ──────────────────────────────────────────────────

  function renderEquity(el, data) {
    trendsCache = data.trends || {};
    var eq = trendsCache.equity || [];
    var deg = trendsCache.degradation || {};
    renderInsightIfReady();

    if (!eq.length) {
      el.innerHTML = DS.SectionHeader({ title: "منحنى الحصيلة" }) +
        DS.EmptyState({
          icon: "◔",
          title: "لا صفقات محسومة بعد",
          text: "يُرسم المنحنى بعد أول صفقة تُحسم. حتى ذلك الحين لا يوجد أداء تاريخي يُعرض.",
          actions: [{ href: "/scanner/", label: "ابحث عن فرصة", primary: true }],
          inline: true,
        });
      return;
    }

    var last = eq[eq.length - 1];
    el.innerHTML =
      DS.SectionHeader({
        title: "منحنى الحصيلة",
        note: eq.length + " صفقة",
        link: { href: "/analytics/", label: "التحليلات ←" },
      }) +
      '<div class="ops-equity-head">' +
        '<span class="ops-equity-total ds-value-' + DS.toneForValue(last.cumulative_r) + '">' +
          DS.fmtR(last.cumulative_r) + "</span>" +
        '<span class="ds-text-xs ds-text-muted">آخر 30: ' + DS.fmtR(deg.rolling_30) +
          " · آخر 50: " + DS.fmtR(deg.rolling_50) + "</span>" +
        (deg.level && deg.level !== "none"
          ? DS.StatusBadge({ label: deg.message, tone: deg.level === "critical" ? "risk" : "warn" })
          : DS.StatusBadge({ label: "مستقر", tone: "success" })) +
      "</div>" +
      '<div class="ops-equity-canvas"><canvas id="ops-equity"></canvas></div>';

    drawEquity(eq);
  }

  function drawEquity(eq) {
    var canvas = document.getElementById("ops-equity");
    if (!canvas || typeof Chart === "undefined") return;
    if (equityChart) equityChart.destroy();
    var last = eq[eq.length - 1].cumulative_r;
    var line = last >= 0 ? "#3ddc97" : "#ff6b6b";
    var ctx = canvas.getContext("2d");
    var fill = ctx.createLinearGradient(0, 0, 0, 170);
    fill.addColorStop(0, last >= 0 ? "rgba(61,220,151,.22)" : "rgba(255,107,107,.22)");
    fill.addColorStop(1, "rgba(0,0,0,0)");

    equityChart = new Chart(canvas, {
      type: "line",
      data: {
        labels: eq.map(function (p) { return p.index; }),
        datasets: [{
          data: eq.map(function (p) { return p.cumulative_r; }),
          borderColor: line,
          backgroundColor: fill,
          fill: true,
          tension: 0.25,
          pointRadius: 0,
          pointHoverRadius: 3,
          borderWidth: 1.75,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 350 },
        interaction: { intersect: false, mode: "index" },
        plugins: {
          legend: { display: false },
          tooltip: {
            displayColors: false,
            callbacks: {
              title: function (i) { return "صفقة " + i[0].label; },
              label: function (c) { return DS.fmtR(c.parsed.y); },
            },
          },
        },
        scales: {
          x: { display: false },
          y: {
            grid: { color: "rgba(255,255,255,.045)" },
            ticks: {
              maxTicksLimit: 4,
              font: { size: 10 },
              color: "#97a0b5",
              callback: function (v) { return "\u2066" + v + "\u2069"; },
            },
          },
        },
      },
    });
  }

  // ── Alerts ──────────────────────────────────────────────────────────────

  function renderAlerts(el, data) {
    var alerts = (data.alerts || []).slice(0, 9);
    if (!alerts.length) {
      el.innerHTML = DS.SectionHeader({ title: "تنبيهات حديثة" }) +
        DS.EmptyState({
          icon: "◇",
          title: "لا تنبيهات",
          text: "تظهر هنا الإشارات التي تجاوزت عتبة التنبيه في آخر عمليات المسح.",
          inline: true,
        });
      return;
    }
    el.innerHTML =
      DS.SectionHeader({ title: "تنبيهات حديثة", note: alerts.length + " إشارة" }) +
      DS.Timeline(alerts.map(function (a) {
        return {
          title: a.symbol + (a.market ? " · " + a.market : ""),
          meta: (a.text || "") + (a.created_at ? " · " + shortTime(a.created_at) : ""),
          tone: "info",
        };
      }));
  }

  function shortTime(iso) {
    try {
      return new Date(iso).toLocaleTimeString("ar", { hour: "2-digit", minute: "2-digit" });
    } catch (e) { return ""; }
  }

  // ── Open trades (incremental list refresh) ──────────────────────────────

  var openTradesState = { trades: [], wired: false };

  function patchOpenTradeRow(rowEl, t) {
    var r = t.unrealized !== null && t.unrealized !== undefined ? t.unrealized : t.r;
    var end = DS.num(r) === null
      ? DS.StatusBadge({ label: t.label || "تنتظر", tone: "warn" })
      : DS.TrendIndicator({ value: r });
    var title = rowEl.querySelector(".ds-list__title");
    var sub = rowEl.querySelector(".ds-list__sub");
    var endEl = rowEl.querySelector(".ds-list__end");
    if (title) title.textContent = t.symbol;
    if (sub) {
      sub.textContent = t.timeframe + " · " + (t.label || "") +
        (t.opened ? " · منذ " + t.opened : "");
    }
    if (endEl) endEl.innerHTML = end;
  }

  function syncOpenTrades(el, data) {
    var trades = (data.trades || []).slice(0, 5);
    var header = DS.SectionHeader({
      title: "الصفقات المفتوحة",
      note: trades.length + " من " + (data.trades || []).length,
      link: { href: "/trades/", label: "كل الصفقات ←" },
    });

    if (!trades.length) {
      el.innerHTML = header + DS.EmptyState({
        icon: "◎",
        title: "لا صفقات مفتوحة",
        text: "لا مراكز نشطة الآن. افتح الماسح لمراجعة الفرص الجاهزة على الفريم الحالي.",
        actions: [{ href: "/scanner/", label: "افتح الماسح", primary: true }],
        inline: true,
      });
      openTradesState.trades = [];
      return;
    }

    var list = el.querySelector(".ds-list");
    if (!list) {
      el.innerHTML = header + DS.List(trades.map(function (t) {
        var r = t.unrealized !== null && t.unrealized !== undefined ? t.unrealized : t.r;
        var end = DS.num(r) === null
          ? DS.StatusBadge({ label: t.label || "تنتظر", tone: "warn" })
          : DS.TrendIndicator({ value: r });
        return {
          title: t.symbol,
          sub: t.timeframe + " · " + (t.label || "") + (t.opened ? " · منذ " + t.opened : ""),
          end: end,
          attrs: 'data-trade-key="' + t.id + '"',
        };
      }));
      openTradesState.trades = data.trades || [];
      return;
    }

    var headerEl = el.querySelector(".ds-section-header");
    if (headerEl) {
      var note = headerEl.querySelector(".ds-section-header__note");
      if (note) note.textContent = trades.length + " من " + (data.trades || []).length;
    }

    var existing = {};
    Array.prototype.forEach.call(
      list.querySelectorAll("[data-trade-key]"),
      function (row) { existing[row.getAttribute("data-trade-key")] = row; }
    );

    var desired = trades.map(function (t) { return String(t.id); });
    Object.keys(existing).forEach(function (id) {
      if (desired.indexOf(id) < 0) existing[id].remove();
    });

    trades.forEach(function (t, i) {
      var key = String(t.id);
      var row = existing[key];
      if (row) {
        patchOpenTradeRow(row, t);
        var at = list.children[i];
        if (at !== row) list.insertBefore(row, at || null);
      } else {
        var r = t.unrealized !== null && t.unrealized !== undefined ? t.unrealized : t.r;
        var end = DS.num(r) === null
          ? DS.StatusBadge({ label: t.label || "تنتظر", tone: "warn" })
          : DS.TrendIndicator({ value: r });
        var wrap = document.createElement("div");
        wrap.innerHTML = '<div class="ds-list__row" data-trade-key="' + t.id + '">' +
          '<div class="ds-list__main">' +
            '<div class="ds-list__title">' + DS.esc(t.symbol) + "</div>" +
            '<div class="ds-list__sub">' + DS.esc(t.timeframe + " · " + (t.label || "") +
              (t.opened ? " · منذ " + t.opened : "")) + "</div>" +
          "</div>" +
          '<div class="ds-list__end">' + end + "</div></div>";
        row = wrap.firstChild;
        list.insertBefore(row, list.children[i] || null);
        row.style.transition = "background .8s";
        row.style.background = "rgba(106,169,255,.12)";
        setTimeout(function () { row.style.background = ""; }, 1200);
      }
    });

    openTradesState.trades = data.trades || [];
  }

  function renderOpenTrades(el, data) {
    syncOpenTrades(el, data);
  }

  function pollOpenTrades() {
    var shell = document.getElementById("w-open-trades");
    if (!shell) return;
    var content = shell.querySelector(".ds-widget__content");
    return fetch(withQs("/api/widgets/open-trades/"), { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data && data.error) return;
        syncOpenTrades(content, data);
      })
      .catch(function () {});
  }

  // ── Boot: staged so the trust answer paints first ───────────────────────

  function stampUpdated() {
    var el = document.getElementById("ops-updated");
    if (el) {
      el.textContent = "محدَّث " +
        new Date().toLocaleTimeString("ar", { hour: "2-digit", minute: "2-digit" });
    }
  }

  var W = {
    health: { id: "w-health", url: withQs("/api/widgets/health/"), render: renderHealth },
    equity: { id: "w-equity", url: withQs("/api/widgets/trends/"), render: renderEquity },
    open: { id: "w-open-trades", url: withQs("/api/widgets/open-trades/"), render: renderOpenTrades },
    alerts: { id: "w-alerts", url: withQs("/api/widgets/alerts/"), render: renderAlerts },
    opps: {
      id: "w-opportunities",
      url: "/api/widgets/scanner/summary/?market=" + encodeURIComponent(market),
      render: renderOpportunities,
    },
    ai: { id: "w-ai", url: withQs("/api/widgets/ai-advisor/"), render: renderAiAdvisor },
    opt: { id: "w-optimization", url: "/api/widgets/optimization-summary/", render: renderOptStatus },
  };

  // Trust answer and live positions go out immediately.
  DS.loadWidget(W.health);
  DS.loadWidget(W.open);

  // Status readouts follow on the next frame so they never delay the hero.
  requestAnimationFrame(function () {
    DS.loadWidget(W.opps);
    DS.loadWidget(W.ai);
    DS.loadWidget(W.opt);
  });

  // Chart and alerts are the heaviest, so they load once the page is idle.
  var idle = window.requestIdleCallback || function (fn) { return setTimeout(fn, 120); };
  idle(function () {
    DS.loadWidget(W.equity);
    DS.loadWidget(W.alerts);
  });

  // Refresh cadence mirrors how fast each source actually changes.
  EVERY(5000, pollOpenTrades);
  setInterval(function () { DS.loadWidget(W.opps); }, 30000);
  setInterval(function () {
    DS.loadWidget(W.health);
    DS.loadWidget(W.equity);
    DS.loadWidget(W.alerts);
  }, 60000);
})();
