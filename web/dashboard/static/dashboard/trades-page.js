/**
 * Trades page — operational view plus the trade investigation drawer.
 *
 * Tables refresh row-by-row (no full innerHTML rebuild on poll). New trades
 * appear at the top when sorted by date descending.
 */
(function () {
  "use strict";

  var pageData = (function () {
    var el = document.getElementById("page-data");
    try { return el ? JSON.parse(el.textContent) : {}; } catch (e) { return {}; }
  })();
  var baseQs = pageData.query || "";
  var drawer = DS.createDrawer("trade-drawer", "drawer-backdrop");
  var drawerTabs = null;
  var current = null;

  var fmtPrice = function (v) {
    return window.Fmt ? Fmt.price(v) : (v === null || v === undefined ? "—" : String(v));
  };

  var tabState = {
    open: { trades: [], sort: "opened_desc", wired: {} },
    waiting: { trades: [], sort: "date_desc", wired: {} },
    closed: { trades: [], sort: "closed_desc", wired: {} },
  };

  function tradesUrl(status, sort) {
    var qs = baseQs + (baseQs ? "&" : "?") + "status=" + status;
    if (sort) qs += "&sort=" + encodeURIComponent(sort);
    return "/api/widgets/trades/" + qs;
  }

  // ── Row rendering ───────────────────────────────────────────────────────

  var STATUS_TONE = {
    won: "success", lost: "risk", open: "info",
    pending: "warn", expired: "neutral", cancelled: "neutral",
  };

  var SORT_OPTIONS = {
    open: [
      { key: "opened_desc", label: "الأحدث دخولاً" },
      { key: "opened_asc", label: "الأقدم دخولاً" },
      { key: "date_desc", label: "الأحدث رصداً" },
      { key: "date_asc", label: "الأقدم رصداً" },
    ],
    waiting: [
      { key: "date_desc", label: "الأحدث أولاً" },
      { key: "date_asc", label: "الأقدم أولاً" },
    ],
    closed: [
      { key: "closed_desc", label: "الأحدث إغلاقاً" },
      { key: "closed_asc", label: "الأقدم إغلاقاً" },
      { key: "date_desc", label: "الأحدث رصداً" },
      { key: "date_asc", label: "الأقدم رصداً" },
    ],
  };

  function gradeBadge(grade) {
    if (!grade) return "";
    var tone = grade === "A" ? "success" : grade === "B" ? "info" : "neutral";
    return DS.StatusBadge({ label: grade, tone: tone });
  }

  function muted(text) {
    return '<span class="ds-text-xs ds-text-muted">' + DS.esc(text || "—") + "</span>";
  }

  function priceCell(v, tone) {
    var cls = "ds-num" + (tone ? " ds-value-" + tone : "");
    return '<span class="' + cls + '" dir="ltr">' + DS.esc(fmtPrice(v)) + "</span>";
  }

  function splitFactors(raw) {
    return String(raw || "").split(/[·,،|;؛]+/)
      .map(function (s) { return s.trim(); })
      .filter(Boolean);
  }

  function reasonsCell(raw) {
    var list = splitFactors(raw);
    if (!list.length) return muted("");
    var shown = list.slice(0, 2).map(function (s) {
      return '<span class="trade-reason">' + DS.esc(s) + "</span>";
    }).join("");
    var rest = list.length - 2;
    return '<div class="trade-reasons" title="' + DS.esc(list.join(" · ")) + '">' + shown +
      (rest > 0
        ? '<span class="trade-reason trade-reason--more">' + DS.ltr("+" + rest) + "</span>"
        : "") +
      "</div>";
  }

  var COLUMNS = {
    open: [
      { key: "symbol", label: "الرمز", width: "12%" },
      { key: "entry", label: "الدخول", align: "end", width: "9%" },
      { key: "stop", label: "الوقف", align: "end", width: "9%" },
      { key: "target", label: "الهدف", align: "end", width: "9%" },
      { key: "fill", label: "التنفيذ", align: "end", width: "9%" },
      { key: "last", label: "السعر", align: "end", width: "9%" },
      { key: "r", label: "R", align: "end", width: "8%" },
      { key: "grade", label: "تصنيف", width: "7%" },
      { key: "opened", label: "التاريخ", width: "11%", sortable: true },
      { key: "reasons", label: "السبب", width: "17%" },
    ],
    waiting: [
      { key: "symbol", label: "الرمز", width: "14%" },
      { key: "entry", label: "الدخول", align: "end", width: "10%" },
      { key: "stop", label: "الوقف", align: "end", width: "10%" },
      { key: "target", label: "الهدف", align: "end", width: "10%" },
      { key: "grade", label: "تصنيف", width: "8%" },
      { key: "signal", label: "التاريخ", width: "12%", sortable: true },
      { key: "reasons", label: "سبب الرصد", width: "36%" },
    ],
    closed: [
      { key: "symbol", label: "الرمز", width: "11%" },
      { key: "status", label: "النتيجة", width: "9%" },
      { key: "entry", label: "الدخول", align: "end", width: "8%" },
      { key: "stop", label: "الوقف", align: "end", width: "8%" },
      { key: "target", label: "الهدف", align: "end", width: "8%" },
      { key: "fill", label: "التنفيذ", align: "end", width: "8%" },
      { key: "exit", label: "البيع", align: "end", width: "8%" },
      { key: "r", label: "R", align: "end", width: "7%" },
      { key: "grade", label: "تصنيف", width: "6%" },
      { key: "closed", label: "التاريخ", width: "10%", sortable: true },
      { key: "held", label: "المدّة", width: "9%" },
    ],
  };

  function sortKeyFor(t, sort) {
    if (sort.indexOf("opened") === 0) return t.opened_at || t.signal_at || "";
    if (sort.indexOf("closed") === 0) return t.closed_at || t.signal_at || "";
    return t.signal_at || t.opened_at || "";
  }

  function sortTrades(trades, sort) {
    var asc = sort.indexOf("_asc") > 0;
    return trades.slice().sort(function (a, b) {
      var ka = sortKeyFor(a, sort);
      var kb = sortKeyFor(b, sort);
      if (!ka && !kb) return 0;
      if (!ka) return 1;
      if (!kb) return -1;
      return asc ? (ka < kb ? -1 : ka > kb ? 1 : 0)
        : (ka > kb ? -1 : ka < kb ? 1 : 0);
    });
  }

  function rowCells(t, variant) {
    var r = t.r !== null && t.r !== undefined ? t.r : t.unrealized;
    return {
      symbol: '<div class="trade-symbol">' +
        '<span class="trade-symbol__name">' + DS.esc(t.symbol) + "</span>" +
        '<span class="trade-symbol__meta">' + DS.esc(t.market || "") + " · " +
        DS.esc(t.timeframe || "") + "</span></div>",
      status: DS.StatusBadge({
        label: t.label || t.status,
        tone: STATUS_TONE[t.status] || "neutral",
        dot: true,
      }),
      entry: priceCell(t.entry),
      stop: priceCell(t.stop, "risk"),
      target: priceCell(t.target1, "success"),
      fill: priceCell(t.entry_price),
      last: priceCell(t.last_price),
      exit: priceCell(t.exit_price),
      r: DS.TrendIndicator({ value: r }),
      grade: gradeBadge(t.grade) || '<span class="ds-text-muted">—</span>',
      opened: muted(t.opened_full || t.opened),
      closed: muted(t.closed_full || t.closed),
      held: muted(t.held),
      signal: '<span class="ds-text-xs ds-num" dir="ltr">' +
        DS.esc(t.candle_time || t.opened || "—") + "</span>",
      reasons: reasonsCell(t.reasons),
      _raw: t,
      _attrs: 'data-key="' + t.id + '" class="is-clickable" tabindex="0" role="button" ' +
        'aria-label="تفاصيل ' + DS.esc(t.symbol) + '"',
    };
  }

  function patchTradeRow(tr, t, variant) {
    var cells = rowCells(t, variant);
    var cols = COLUMNS[variant] || COLUMNS.open;
    cols.forEach(function (c) {
      DS.setCellText(tr, c.key, cells[c.key]);
    });
  }

  function sortToolbar(variant) {
    var st = tabState[variant];
    var opts = SORT_OPTIONS[variant] || SORT_OPTIONS.open;
    return '<div class="trades-sort-bar" role="group" aria-label="ترتيب">' +
      '<span class="ds-text-xs ds-text-muted">ترتيب:</span>' +
      opts.map(function (o) {
        var active = st.sort === o.key ? " ds-btn--primary" : "";
        return '<button type="button" class="ds-btn ds-btn--sm trades-sort-btn' + active +
          '" data-sort="' + DS.esc(o.key) + '">' + DS.esc(o.label) + "</button>";
      }).join("") +
      "</div>";
  }

  function wireTable(el, variant) {
    if (tabState[variant].wired[el.id]) return;
    tabState[variant].wired[el.id] = true;

    el.addEventListener("click", function (e) {
      var sortBtn = e.target.closest(".trades-sort-btn");
      if (sortBtn) {
        tabState[variant].sort = sortBtn.getAttribute("data-sort");
        el.querySelectorAll(".trades-sort-btn").forEach(function (b) {
          b.classList.toggle("ds-btn--primary",
            b.getAttribute("data-sort") === tabState[variant].sort);
        });
        syncTradesTable(el, { trades: tabState[variant].trades, counts: lastCounts },
          TABS[variant].empty, variant, true);
        return;
      }
      var tr = e.target.closest("tr[data-key]");
      if (!tr) return;
      var id = Number(tr.getAttribute("data-key"));
      var t = tabState[variant].trades.find(function (x) { return x.id === id; });
      if (t) openTrade(t);
    });

    el.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" && e.key !== " ") return;
      var tr = e.target.closest("tr[data-key]");
      if (!tr) return;
      e.preventDefault();
      var id = Number(tr.getAttribute("data-key"));
      var t = tabState[variant].trades.find(function (x) { return x.id === id; });
      if (t) openTrade(t);
    });
  }

  function syncTradesTable(el, data, emptyCfg, variant, resort) {
    var incoming = data.trades || [];
    // الإحصاء يأتي مع الاستجابة نفسها؛ وغيابه يُبقي السابق ولا
    // يمحوه — استجابةٌ ناقصة لا تُفرغ بطاقةً كانت مملوءة.
    if (data.stats) lastStats = data.stats;
    updateSummary(data.counts);

    if (!incoming.length) {
      el.innerHTML = DS.EmptyState(emptyCfg);
      tabState[variant].trades = [];
      return;
    }

    var st = tabState[variant];
    if (resort || !st.trades.length) {
      st.trades = incoming;
    } else {
      var byId = {};
      st.trades.forEach(function (t) { byId[t.id] = t; });
      incoming.forEach(function (t) { byId[t.id] = t; });
      st.trades = Object.keys(byId).map(function (k) { return byId[k]; });
    }

    var sorted = sortTrades(st.trades, st.sort);
    var toolbar = sortToolbar(variant);

    DS.patchDataTable(el, {
      columns: COLUMNS[variant] || COLUMNS.open,
      items: sorted,
      keyFn: function (t) { return t.id; },
      toolbar: toolbar,
      emptyHtml: emptyCfg ? DS.EmptyState(emptyCfg) : "",
      buildRow: function (t) { return rowCells(t, variant); },
      patchRow: function (tr, t) { patchTradeRow(tr, t, variant); },
      onWire: function (container) { wireTable(container, variant); },
    });

    wireTable(el, variant);
  }

  // ── Summary strip (patch counts, build once) ────────────────────────────

  var summaryBuilt = false;
  var lastCounts = null;

  var lastStats = null;

  /* الإحصاء يُرسم من بيانات الخادم — و«لا بيانات» تُقال صراحةً.
   * الصفر في خانة نسبة الفوز يُقرأ «خسرتَ كل شيء»، وهو غير
   * «لم تُحسم صفقةٌ بعد». */
  function applyStats(el, st) {
    function put(key, text, tone) {
      var n = el.querySelector('[data-stat="' + key + '"]');
      if (!n) return;
      n.textContent = text;
      n.classList.remove("ds-value-success", "ds-value-risk");
      if (tone) n.classList.add(tone);
    }
    function foot(key, text) {
      var n = el.querySelector('[data-stat-foot="' + key + '"]');
      if (n) n.textContent = text;
    }
    if (!st || !st.settled) {
      put("avg_r", "—"); put("win_rate", "—");
      foot("r", "لا صفقة محسومة بعد");
      foot("win", "لا صفقة محسومة بعد");
      return;
    }
    if (st.avg_r === null || st.avg_r === undefined) {
      put("avg_r", "—");
      foot("r", "لا R مسجَّل");
    } else {
      put("avg_r", (st.avg_r > 0 ? "+" : "") + st.avg_r.toFixed(2),
          st.avg_r > 0 ? "ds-value-success" : "ds-value-risk");
      foot("r", "الوسيط " + (st.median_r > 0 ? "+" : "") +
           (st.median_r === null ? "—" : st.median_r.toFixed(2)));
    }
    put("win_rate", st.win_rate.toFixed(1) + "٪");
    /* الفاصل والعدد معاً: بلا العدد يبدو الفاصل الواسع تعسّفاً. */
    foot("win", "[" + st.win_low + "–" + st.win_high + "٪] · " +
         st.settled + " صفقة");
  }

  function updateSummary(counts) {
    if (!counts) return;
    lastCounts = counts;
    var shell = document.getElementById("w-summary");
    var el = shell.querySelector(".ds-widget__content");

    if (!summaryBuilt) {
      el.innerHTML =
        '<div class="trades-summary">' +
        '<div class="ds-metric ds-metric--info ds-metric--sm">' +
          '<span class="ds-metric__label">مفتوحة</span>' +
          '<span class="ds-metric__value"><span data-count="open">0</span></span>' +
          '<span class="ds-metric__foot"><span class="ds-text-muted">مراكز نشطة</span></span>' +
        "</div>" +
        '<div class="ds-metric ds-metric--warn ds-metric--sm">' +
          '<span class="ds-metric__label">تنتظر الدخول</span>' +
          '<span class="ds-metric__value"><span data-count="pending">0</span></span>' +
          '<span class="ds-metric__foot"><span class="ds-text-muted">لم تُفعَّل بعد</span></span>' +
        "</div>" +
        '<div class="ds-metric ds-metric--success ds-metric--sm">' +
          '<span class="ds-metric__label">رابحة</span>' +
          '<span class="ds-metric__value ds-value-success"><span data-count="won">0</span></span>' +
          '<span class="ds-metric__foot"><span class="ds-text-muted" data-foot-won>من 0 محسومة</span></span>' +
        "</div>" +
        '<div class="ds-metric ds-metric--risk ds-metric--sm">' +
          '<span class="ds-metric__label">خاسرة</span>' +
          '<span class="ds-metric__value ds-value-risk"><span data-count="lost">0</span></span>' +
          '<span class="ds-metric__foot"><span class="ds-text-muted" data-foot-lost>من 0 محسومة</span></span>' +
        "</div>" +
        /* ═══ متوسّط R ونسبة الفوز ═══
         *
         * التوزيع ملتوٍ: خسائرُ محدودة عند ‎-1‎ وأرباحٌ ممتدّة.
         * فالوسيط يُذكر مع المتوسّط — متوسّطٌ موجب ووسيطٌ سالب
         * يعني أنّ الربح كلّه من صفقاتٍ قليلة، وهو ما لا يظهر من
         * المتوسّط وحده. */
        '<div class="ds-metric ds-metric--sm">' +
          '<span class="ds-metric__label">متوسّط R</span>' +
          '<span class="ds-metric__value num" data-stat="avg_r">—</span>' +
          '<span class="ds-metric__foot"><span class="ds-text-muted" data-stat-foot="r">—</span></span>' +
        "</div>" +
        /* والنسبة بفاصلها: رقمٌ مفرد على عشرين صفقة يُقرأ كما
         * يُقرأ على ألفين، وهو ليس كذلك. */
        '<div class="ds-metric ds-metric--sm">' +
          '<span class="ds-metric__label">نسبة الفوز</span>' +
          '<span class="ds-metric__value num" data-stat="win_rate">—</span>' +
          '<span class="ds-metric__foot"><span class="ds-text-muted" data-stat-foot="win">—</span></span>' +
        "</div>" +
        "</div>";
      summaryBuilt = true;
    }

    function setCount(key, val) {
      var node = el.querySelector('[data-count="' + key + '"]');
      if (node) node.textContent = String(val);
    }
    setCount("open", counts.open || 0);
    setCount("pending", counts.pending || 0);
    setCount("won", counts.won || 0);
    setCount("lost", counts.lost || 0);
    var footWon = el.querySelector("[data-foot-won]");
    var footLost = el.querySelector("[data-foot-lost]");
    if (footWon) footWon.textContent = "من " + (counts.closed || 0) + " محسومة";
    if (footLost) footLost.textContent = "من " + (counts.closed || 0) + " محسومة";
    applyStats(el, lastStats);
    shell.setAttribute("data-state", "ready");
  }

  // ── Drawer ──────────────────────────────────────────────────────────────

  function kv(pairs) {
    return '<dl class="ds-kv">' + pairs.map(function (p) {
      return "<dt>" + DS.esc(p[0]) + "</dt><dd>" + (p[1] || "—") + "</dd>";
    }).join("") + "</dl>";
  }

  function factorList(t) {
    return splitFactors(t.reasons);
  }

  function panel(name) {
    return document.querySelector('[data-tab-panel="' + name + '"]');
  }

  function symbolUrl(t) {
    return "/symbol/" + encodeURIComponent(t.market) + "/" +
      encodeURIComponent(t.symbol) + "/?tf=" + encodeURIComponent(t.timeframe || "");
  }

  function fillOverview(t) {
    var realized = t.status === "won" || t.status === "lost";
    var r = realized ? t.r
      : (t.unrealized !== null && t.unrealized !== undefined ? t.unrealized : t.r);
    panel("overview").innerHTML =
      DS.StatGrid([
        {
          label: realized ? "النتيجة" : "غير محقّق",
          value: DS.fmtR(r),
          size: "sm",
          valueTone: DS.toneForValue(r),
        },
        { label: "التصنيف", value: t.grade || "—", size: "sm" },
        { label: "الفريم", value: t.timeframe || "—", size: "sm" },
      ], 3) +
      '<div style="height:var(--ds-sp-4)"></div>' +
      kv([
        ["الحالة", DS.StatusBadge({
          label: t.label || t.status, tone: STATUS_TONE[t.status] || "neutral", dot: true })],
        ["السوق", DS.esc(t.market || "—")],
        ["سعر الدخول", '<span dir="ltr">' + DS.esc(fmtPrice(t.entry)) + "</span>"],
        ["الوقف", '<span dir="ltr" class="ds-value-risk">' + DS.esc(fmtPrice(t.stop)) + "</span>"],
        ["الهدف", '<span dir="ltr" class="ds-value-success">' + DS.esc(fmtPrice(t.target1)) + "</span>"],
        ["سعر التنفيذ", '<span dir="ltr">' + DS.esc(fmtPrice(t.entry_price)) + "</span>"],
        ["سعر البيع", '<span dir="ltr">' + DS.esc(fmtPrice(t.exit_price)) + "</span>"],
        ["السعر الحالي", '<span dir="ltr">' + DS.esc(fmtPrice(t.last_price)) + "</span>"],
        ["وقت الرصد", DS.esc(t.candle_time || "—")],
        ["وقت الدخول", DS.esc(t.opened_full || t.opened || "—")],
        ["وقت الخروج", DS.esc(t.closed_full || t.closed || "—")],
        ["مدّة الاحتفاظ", DS.esc(t.held || "—")],
      ]);
  }

  /* ═══ الاستشارة بالأدلّة ═══
   *
   * تُوضَع **فوق** قراءة لحظة الرصد لا تحتها: القراءة القديمة تصف
   * ما كان، والسؤال المطروح هو «لماذا انتهت كذلك؟». والأدلّة
   * تُحمَّل تلقائياً لأنّها حسابٌ محلّي على سجلّك بلا نموذج؛
   * والحكم بزرّ لأنّه نداء بطيء قد يعطب.
   */
  function adviceBlock(t) {
    var settled = t.status === "won" || t.status === "lost";
    if (!settled) return "";
    var q = t.status === "won" ? "لماذا فازت هذه الصفقة؟"
                               : "لماذا خسرت هذه الصفقة؟";
    return DS.SectionCard({
      title: q,
      body:
        '<div id="advice-evidence" class="mb-2"></div>' +
        '<button type="button" class="ds-btn ds-btn--primary" ' +
        'id="advice-ask">اسأل النموذج عن الحكم</button>' +
        '<div id="advice-verdict" class="mt-2"></div>',
    }) + '<div style="height:var(--ds-sp-3)"></div>';
  }

  function bindAdvice(t) {
    if (!window.Advice) return;
    var evBox = document.getElementById("advice-evidence");
    var vBox = document.getElementById("advice-verdict");
    var btn = document.getElementById("advice-ask");
    if (!evBox || !btn) return;
    /* الأرقام أوّلاً وبلا انتظار — والحكم عند الطلب */
    window.Advice.evidenceOnly(evBox,
      "?kind=settled&trade_id=" + encodeURIComponent(t.id));
    btn.onclick = function () {
      btn.disabled = true;
      window.Advice.settled(t.id, evBox, vBox);
    };
  }

  function fillAi(t) {
    var gradeScore = { A: 85, B: 65, C: 45, D: 25 }[t.grade];
    var factors = factorList(t);
    var body = "";

    if (gradeScore !== undefined) {
      body += DS.ConfidenceBar({
        label: "جودة الإشارة",
        value: gradeScore,
        note: "مشتقّة من تصنيف الإشارة (" + t.grade + ") وقت الرصد",
      });
    }
    if (factors.length) {
      body += DS.ConfidenceBar({
        label: "الالتقاء",
        value: Math.min(100, factors.length * 25),
        note: factors.length + " عامل مؤيِّد عند الرصد",
      });
    }
    if (!body) {
      panel("ai").innerHTML = adviceBlock(t) + decisionBox(t) +
        '<div style="height:var(--ds-sp-3)"></div>' +
        DS.EmptyState({
          icon: "◈",
          title: "لا قراءة ذكاء لهذه الصفقة",
          text: "لم تُسجَّل إشارة مصنّفة لهذه الصفقة، فلا يوجد ما يُفسَّر هنا.",
          actions: [{ href: "/ai/", label: "مركز الذكاء", primary: true }],
          inline: true,
        });
      bindDecision(t);
      bindAdvice(t);
      return;
    }
    panel("ai").innerHTML =
      adviceBlock(t) +
      decisionBox(t) +
      '<div style="height:var(--ds-sp-3)"></div>' +
      DS.SectionCard({ title: "قراءة الإشارة عند الرصد", body: body }) +
      '<div style="height:var(--ds-sp-3)"></div>' +
      DS.InsightCard({
        tone: "info",
        title: "هذه قراءة لحظة الرصد",
        text: "الأرقام أعلاه تصف الإشارة كما كانت وقت فتح الصفقة. لتفسير توصيات الذكاء الحالية افتح مركز الذكاء.",
      }) +
      '<div style="height:var(--ds-sp-3)"></div>' +
      '<a class="ds-btn" href="/ai/">افتح مركز الذكاء</a>';
    bindDecision(t);
    bindAdvice(t);
  }

  /* ── تقييم جودة القرار ──
   *
   * السؤال ليس «لماذا خسرت» — فالنموذج يعرف النتيجة وسيبني إليها
   * سرداً. بل «هل كان القرار سليماً بما كان معلوماً وقت الدخول؟»
   * والنتيجة **محجوبة** عن النموذج، ثمّ تُكشَف هنا لتقابَل بحكمه.
   *
   * والمقابلة هي الفائدة: «قرار ضعيف · ربح» حالة لا يراها أحد بلا هذا
   * الفصل، لأن السجلّ يعدّ الأرباح لا القرارات.
   */
  var decisionTimer = null;

  function decisionBox(t) {
    var settled = t.status === "won" || t.status === "lost";
    return DS.SectionCard({
      title: "تقييم جودة القرار",
      body:
        '<div class="ds-text-xs ds-text-muted mb-2">' +
        (settled
          ? "يُقيَّم الدخول بما كان معلوماً وقته — نتيجة الصفقة محجوبة عن النموذج."
          : "الصفقة لم تُحسم بعد؛ التقييم متاح وسيقارَن بالنتيجة لاحقاً.") +
        "</div>" +
        '<button type="button" class="ds-btn ds-btn--primary" ' +
        'id="dq-btn" data-trade="' + t.id + '">قيّم بالذكاء</button> ' +
        '<span class="ds-text-xs ds-text-muted" id="dq-state"></span>' +
        '<div id="dq-out" class="mt-2"></div>',
    });
  }

  function bindDecision(t) {
    var btn = document.getElementById("dq-btn");
    if (!btn) return;
    btn.addEventListener("click", function () {
      btn.disabled = true;
      setDq("يبدأ…", "");
      document.getElementById("dq-out").innerHTML = "";
      window.postJSON("/api/trade/" + t.id + "/review/", new URLSearchParams())
        .then(function (d) {
          setDq((d && d.reason) || "يعمل…", "");
          clearInterval(decisionTimer);
          decisionTimer = setInterval(function () { pollDq(t.id, btn); }, 2000);
        });
    });
  }

  function setDq(text, color) {
    var el = document.getElementById("dq-state");
    if (el) { el.textContent = text; el.style.color = color || ""; }
  }

  function pollDq(id, btn) {
    fetch("/api/trade/" + id + "/review/status/")
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.ok) return;
        if (d.state === "running") {
          setDq("يقيّم… " + (d.elapsed || 0) + " ث", "");
          return;
        }
        clearInterval(decisionTimer); decisionTimer = null;
        if (btn) btn.disabled = false;
        if (d.state === "failed") {
          setDq("تعذّر: " + (d.error || ""), "var(--ds-risk)");
          return;
        }
        setDq("اكتمل في " + (d.elapsed || 0) + " ث", "");
        renderDq(d.result);
      })
      .catch(function () {});
  }

  function renderDq(res) {
    var out = document.getElementById("dq-out");
    if (!out || !res) return;
    var a = res.assessment || {};
    var h = "";

    /* المقابلة أولاً: هي الخلاصة، وما تحتها تفصيلها */
    if (res.match) {
      h += DS.InsightCard({
        tone: res.match.tone === "up" ? "success"
            : res.match.tone === "down" ? "danger"
            : res.match.tone === "warn" ? "warning" : "info",
        title: res.match.label,
        text: res.match.note,
      }) + '<div style="height:var(--ds-sp-2)"></div>';
    }

    h += '<div class="ds-text-sm mb-2"><strong>حكم القرار:</strong> '
      + esc(a.decision_quality || "—")
      + (a.confidence != null ? " · ثقة " + esc(String(a.confidence)) : "")
      + "</div>";
    if (a.summary) h += '<p class="ds-text-sm">' + esc(a.summary) + "</p>";
    h += dqList("ما يدعم الدخول", a.supporting);
    h += dqList("ما يُضعفه", a.concerns);
    h += dqList("ما كان ينبغي فحصه", a.missing_checks);

    if (res.outcome && Object.keys(res.outcome).length) {
      h += '<div class="ds-text-xs ds-text-muted mt-2">النتيجة الفعلية: '
        + esc(String(res.outcome.status || "—"))
        + (res.outcome.r_multiple != null
            ? " · " + esc(String(res.outcome.r_multiple)) + "R" : "")
        + " — لم يرَها النموذج.</div>";
    }
    out.innerHTML = h;
  }

  function dqList(title, items) {
    if (!items || !items.length) return "";
    var h = '<div class="ds-text-xs ds-text-muted mt-2">' + title + "</div><ul class='ds-text-sm mb-0'>";
    items.forEach(function (x) { h += "<li>" + esc(String(x)) + "</li>"; });
    return h + "</ul>";
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function fillChart(t) {
    panel("chart").innerHTML = DS.EmptyState({
      icon: "◪",
      title: "الشارت الكامل في صفحة الرمز",
      text: "صفحة " + t.symbol + " تعرض الشموع والمؤشرات وتاريخ الدرجة على الفريم نفسه.",
      actions: [{ href: symbolUrl(t), label: "افتح شارت " + t.symbol, primary: true }],
      meta: t.market + " · " + t.timeframe,
      inline: true,
    });
  }

  function fillResearch(t) {
    panel("research").innerHTML = DS.EmptyState({
      icon: "◐",
      title: "تحليل الشريحة في مختبر البحث",
      text: "لا يوجد اختبار إحصائي على مستوى الصفقة الواحدة — الدلالة تحتاج عيّنة. راجع أداء شريحة " +
        (t.grade ? "التصنيف " + t.grade : "هذا الفريم") + " في التحليلات والبحث.",
      actions: [
        { href: "/analytics/?tab=splits", label: "تقسيمات الأداء", primary: true },
        { href: "/research/", label: "مختبر البحث" },
      ],
      inline: true,
    });
  }

  function fillPrediction(t) {
    panel("prediction").innerHTML = DS.EmptyState({
      icon: "◭",
      title: "لا تنبؤ محفوظ لهذه الصفقة",
      text: "محرك التنبؤ يعمل على الإشارات الحيّة ولا يخزّن تنبؤاً تاريخياً لكل صفقة. حالة النماذج ودقّتها معروضة في مركز الذكاء.",
      actions: [{ href: "/ai/?tab=prediction", label: "حالة نماذج التنبؤ", primary: true }],
      inline: true,
    });
  }

  function fillOptimization(t) {
    panel("optimization").innerHTML = DS.EmptyState({
      icon: "◮",
      title: "التحسين يعمل على الاستراتيجية لا على الصفقة",
      text: "لمعرفة ما إذا كانت معاملات أفضل كانت ستغيّر نتيجة صفقات مثل هذه، شغّل دورة تحسين واقرأ لوحة المتصدرين.",
      actions: [{ href: "/optimization/", label: "صفحة التحسين", primary: true }],
      inline: true,
    });
  }

  function fillHistory(t) {
    var items = [];
    if (t.candle_time) {
      items.push({ title: "رُصدت الإشارة", meta: t.candle_time, tone: "info" });
    }
    if (t.opened_full || t.opened) {
      items.push({ title: "فُتحت الصفقة", meta: t.opened_full || t.opened, tone: "info" });
    }
    if (t.closed_full || t.closed) {
      items.push({
        title: "أُغلقت الصفقة · " + DS.fmtR(t.r),
        meta: (t.closed_full || t.closed) + (t.held ? " · استمرّت " + t.held : ""),
        tone: t.status === "won" ? "success" : t.status === "lost" ? "risk" : "warn",
      });
    }
    if (!items.length) {
      panel("history").innerHTML = DS.EmptyState({
        icon: "◷", title: "لا أحداث مسجّلة", text: "لم تُحفظ أوقات لهذه الصفقة.", inline: true,
      });
      return;
    }
    panel("history").innerHTML = DS.SectionCard({
      title: "مسار الصفقة",
      body: DS.Timeline(items),
    });
  }

  function fillEvidence(t) {
    var factors = factorList(t);
    if (!factors.length) {
      panel("evidence").innerHTML = DS.EmptyState({
        icon: "◇",
        title: "لا أسباب مسجّلة",
        text: "لم تُحفظ عوامل الدخول لهذه الصفقة، غالباً لأنها فُتحت يدوياً.",
        inline: true,
      });
      return;
    }
    panel("evidence").innerHTML = DS.SectionCard({
      title: "عوامل الدخول",
      meta: factors.length + " عامل",
      body: '<div class="ds-row">' + factors.map(function (f) {
        return DS.StatusBadge({ label: f, tone: "info" });
      }).join("") + "</div>" +
      '<p class="ds-text-xs ds-text-muted" style="margin:.75rem 0 0">' +
      "مساهمة كل عامل على مستوى المحفظة معروضة في التحليلات ← مساهمة العوامل.</p>",
    });
  }

  function fillNotes(t) {
    if (!t.note) {
      panel("notes").innerHTML = DS.EmptyState({
        icon: "◌",
        title: "لا ملاحظة حسم",
        text: t.status === "open" || t.status === "pending"
          ? "تُكتب ملاحظة الحسم تلقائياً عند إغلاق الصفقة."
          : "أُغلقت هذه الصفقة بلا ملاحظة مسجّلة.",
        inline: true,
      });
      return;
    }
    panel("notes").innerHTML = DS.SectionCard({
      title: "ملاحظة الحسم",
      body: '<p class="ds-text-sm" style="margin:0;line-height:1.7">' + DS.esc(t.note) + "</p>",
    });
  }

  function openTrade(t) {
    if (!t) return;
    current = t;
    document.getElementById("drawer-title").textContent = t.symbol;
    document.getElementById("drawer-status").innerHTML = DS.StatusBadge({
      label: t.label || t.status, tone: STATUS_TONE[t.status] || "neutral", dot: true });
    document.getElementById("drawer-headline").textContent =
      [t.market, t.timeframe, t.grade ? "تصنيف " + t.grade : ""].filter(Boolean).join(" · ");

    fillOverview(t);
    fillAi(t);
    fillChart(t);
    fillResearch(t);
    fillPrediction(t);
    fillOptimization(t);
    fillHistory(t);
    fillEvidence(t);
    fillNotes(t);

    document.getElementById("drawer-foot").innerHTML =
      '<a class="ds-btn ds-btn--primary" href="' + symbolUrl(t) + '">افتح الرمز</a>' +
      (t.status === "open" || t.status === "pending"
        ? '<button type="button" class="ds-btn" id="drawer-cancel">ألغِ التتبّع</button>' : "");

    var cancel = document.getElementById("drawer-cancel");
    if (cancel) {
      cancel.onclick = function () {
        cancel.disabled = true;
        window.postJSON("/api/trade/" + t.id + "/cancel/", new URLSearchParams())
          .then(function () { drawer.close(); reloadActive(); });
      };
    }

    if (drawerTabs) drawerTabs.activate("overview");
    drawer.open();
  }

  document.getElementById("drawer-close").onclick = drawer.close;

  // ── Widgets ─────────────────────────────────────────────────────────────

  var TABS = {
    open: {
      id: "w-trades-open",
      status: "open",
      empty: {
        icon: "◎",
        title: "لا صفقات مفتوحة",
        text: "لا مراكز نشطة الآن. ابدأ من الماسح لمراجعة الإشارات الجاهزة على الفريم الحالي.",
        actions: [{ href: "/scanner/", label: "افتح الماسح", primary: true }],
      },
    },
    waiting: {
      id: "w-trades-waiting",
      status: "pending",
      empty: {
        icon: "◔",
        title: "لا صفقات تنتظر الدخول",
        text: "الصفقات المعلّقة هي إشارات رُصدت ولم يتحقّق شرط دخولها بعد. تظهر هنا فور رصدها.",
        actions: [{ href: "/scanner/", label: "افتح الماسح", primary: true }],
      },
    },
    closed: {
      id: "w-trades-closed",
      status: "closed",
      empty: {
        icon: "◍",
        title: "لا صفقات محسومة",
        text: "بعد إغلاق أول صفقة تظهر هنا نتيجتها، ويبدأ حساب التوقّع ونسبة النجاح.",
        actions: [{ href: "/analytics/", label: "التحليلات" }],
      },
    },
  };

  var activeTab = "open";

  function renderTradesTable(el, data, emptyCfg, variant) {
    syncTradesTable(el, data, emptyCfg, variant, false);
  }

  function widgetFor(name) {
    var cfg = TABS[name];
    return {
      id: cfg.id,
      url: tradesUrl(cfg.status, tabState[name].sort),
      render: function (el, data) { renderTradesTable(el, data, cfg.empty, name); },
    };
  }

  function pollActive() {
    var cfg = TABS[activeTab];
    var shell = document.getElementById(cfg.id);
    if (!shell) return;
    var content = shell.querySelector(".ds-widget__content");
    return fetch(tradesUrl(cfg.status, tabState[activeTab].sort), { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data && data.error) return;
        renderTradesTable(content, data, cfg.empty, activeTab);
      })
      .catch(function () {});
  }

  function reloadActive() {
    DS.loadWidget(widgetFor(activeTab));
  }

  drawerTabs = DS.initTabs({
    tabsSelector: "#drawer-tabs",
    panelSelector: "#drawer-panels",
    initial: "overview",
  });

  DS.initTabs({
    tabsSelector: "#trades-tabs",
    panelSelector: "#trades-panels",
    syncUrl: true,
    onShow: function (name) {
      activeTab = name;
      DS.loadWidget(widgetFor(name));
    },
  });

  // Row-level refresh — no full table flash.
  EVERY(5000, pollActive);

  // ── Toolbar actions ─────────────────────────────────────────────────────

  fetch("/api/widgets/settlement/", { credentials: "same-origin" })
    .then(function (r) { return r.json(); })
    .then(function (j) {
      var el = document.getElementById("settle-state");
      if (el && j.settlement) {
        el.textContent = j.settlement.running ? "يحسم الآن…" : "الحسم جاهز";
      }
    })
    .catch(function () {});

  document.getElementById("settle-now").onclick = function () {
    var btn = this;
    btn.disabled = true;
    btn.textContent = "يحسم…";
    window.postJSON("/api/settle/", new URLSearchParams()).then(function () {
      btn.disabled = false;
      btn.textContent = "احسم الآن";
      reloadActive();
    });
  };

  document.getElementById("repair-times").onclick = function () {
    var btn = this;
    btn.disabled = true;
    window.postJSON("/api/repair-times/", new URLSearchParams()).then(function () {
      btn.disabled = false;
      reloadActive();
    });
  };
})();
