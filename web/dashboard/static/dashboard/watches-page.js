/**
 * Watchlist page — "which opportunity is closest to triggering?".
 *
 * Distance to entry is the only number that decides what the user does next,
 * so it leads the table as a proximity bar; every other column is supporting
 * detail read after that.
 */
(function () {
  "use strict";

  var summary = document.getElementById("w-watch-summary");
  var table = document.getElementById("w-watch-table");
  var state = document.getElementById("mon-state");

  function near(w, limit) {
    var d = w.distance_pct;
    return d !== null && d !== undefined && Math.abs(d) <= limit;
  }

  function distanceCell(w) {
    var d = w.distance_pct;
    if (d === null || d === undefined) return '<span class="ds-text-muted">—</span>';
    var abs = Math.abs(d);
    var tone = abs <= 1 ? "success" : abs <= 3 ? "warn" : "muted";
    // Full bar = touching entry, empty = 5% away or further.
    var pct = Math.max(0, Math.min(100, (1 - abs / 5) * 100));
    return '<div class="watch-distance">' +
      '<span class="watch-distance__track">' +
        '<span class="watch-distance__fill watch-distance__fill--' + tone +
        '" style="width:' + pct.toFixed(1) + '%"></span></span>' +
      '<span class="ds-value-' + tone + ' ds-num">' + DS.fmtPct(abs, 2) + "</span>" +
      "</div>";
  }

  function reasonChips(raw) {
    var list = String(raw || "").split(/[·,،|;؛]+/)
      .map(function (s) { return s.trim(); }).filter(Boolean);
    if (!list.length) return '<span class="ds-text-muted">—</span>';
    var shown = list.slice(0, 2).map(function (s) {
      return '<span class="trade-reason">' + DS.esc(s) + "</span>";
    }).join("");
    var rest = list.length - 2;
    return '<div class="trade-reasons" title="' + DS.esc(list.join(" · ")) + '">' + shown +
      (rest > 0
        ? '<span class="trade-reason trade-reason--more">' + DS.ltr("+" + rest) + "</span>"
        : "") + "</div>";
  }

  function renderSummary(rows, monitor) {
    var closest = rows.reduce(function (best, w) {
      var d = w.distance_pct;
      if (d === null || d === undefined) return best;
      return best === null || Math.abs(d) < Math.abs(best) ? d : best;
    }, null);
    var content = summary.querySelector(".ds-widget__content");
    content.innerHTML = DS.StatGrid([
      {
        label: "تحت المراقبة", value: String(rows.length), size: "sm", tone: "info",
        foot: '<span class="ds-text-muted">فرصة تنتظر بلوغ الدخول</span>',
      },
      {
        label: "على وشك التحقق", value: String(rows.filter(function (w) { return near(w, 1); }).length),
        size: "sm", tone: "success", valueTone: "success",
        foot: '<span class="ds-text-muted">ضمن ' + DS.fmtPct(1, 0) + " من الدخول</span>",
      },
      {
        label: "أقرب مسافة",
        value: closest === null ? "—" : DS.fmtPct(Math.abs(closest), 2),
        size: "sm", tone: "warn",
        foot: '<span class="ds-text-muted">بين السعر الآن والدخول</span>',
      },
      {
        label: "تحققت", value: String(monitor.triggered_total || 0), size: "sm",
        foot: '<span class="ds-text-muted">منذ تشغيل المراقبة</span>',
      },
    ]);
    summary.setAttribute("data-state", "ready");
  }

  var WATCH_COLUMNS = [
    { key: "symbol", label: "الرمز", width: "14%" },
    { key: "distance", label: "المسافة للدخول", width: "16%" },
    { key: "side", label: "الاتجاه", width: "8%" },
    { key: "entry", label: "الدخول", align: "end", width: "10%" },
    { key: "price", label: "السعر الآن", align: "end", width: "10%" },
    { key: "stop", label: "الوقف", align: "end", width: "9%" },
    { key: "target", label: "الهدف", align: "end", width: "9%" },
    { key: "rr", label: "R:R", align: "end", width: "6%" },
    { key: "grade", label: "تصنيف", width: "6%" },
    { key: "reasons", label: "الأسباب", width: "12%" },
    { key: "ai", label: "AI", width: "6%" },
  ];

  function watchKey(w) {
    return w.symbol + "|" + (w.market || "") + "|" + (w.timeframe || "");
  }

  function watchRow(w) {
    return {
      symbol: '<a class="ds-cell-strong" href="' + DS.esc(w.url) + '">' +
        DS.esc(w.symbol) + '</a><span class="trade-symbol__meta"> ' +
        DS.esc(w.timeframe || "") + "</span>",
      distance: distanceCell(w),
      side: DS.StatusBadge({
        label: w.side === "buy" ? "شراء" : "بيع",
        tone: w.side === "buy" ? "success" : "risk",
      }),
      entry: '<span class="ds-num" dir="ltr">' + Fmt.price(w.entry) + "</span>",
      price: '<span class="ds-num" dir="ltr">' + Fmt.price(w.last_price) + "</span>",
      stop: '<span class="ds-num ds-value-risk" dir="ltr">' + Fmt.price(w.stop) + "</span>",
      target: '<span class="ds-num ds-value-success" dir="ltr">' + Fmt.price(w.target1) + "</span>",
      rr: '<span class="ds-num">' + Fmt.ratio(w.rr) + "</span>",
      grade: w.grade
        ? DS.StatusBadge({
            label: w.grade,
            tone: w.grade === "A" ? "success" : w.grade === "B" ? "info" : "neutral",
          })
        : '<span class="ds-text-muted">—</span>',
      reasons: reasonChips(w.reasons),
      ai: window.AIExplain
        ? '<button type="button" class="ds-btn ds-btn--sm ai-watch-analyze" data-symbol="' +
          DS.esc(w.symbol) + '" data-market="' + DS.esc(w.market || "crypto") +
          '" data-tf="' + DS.esc(w.timeframe || "4h") + '">AI</button>'
        : "—",
      _attrs: 'data-key="' + DS.esc(watchKey(w)) + '"',
    };
  }

  function wireAiButtons(root) {
    root.querySelectorAll(".ai-watch-analyze").forEach(function (btn) {
      if (btn._wired) return;
      btn._wired = true;
      btn.addEventListener("click", function () {
        if (!window.AIExplain) return;
        AIExplain.runManualAnalysis({
          symbol: btn.getAttribute("data-symbol"),
          market: btn.getAttribute("data-market"),
          timeframe: btn.getAttribute("data-tf"),
        });
      });
    });
  }

  function renderTable(rows, setupError, meta) {
    var content = table.querySelector(".ds-widget__content");
    /* ═══ الفراغ بسبب المرشّح ليس فراغاً ═══
     *
     * «لا فرص مراقَبة الآن» مع أربعين مراقبة قائمة وواحدةٍ لا
     * تطابق الرمز المكتوب — رسالةٌ صحيحة الشكل كاذبة المعنى،
     * تدفع المستخدم للبحث عن عطبٍ في المراقبة لا في بحثه. */
    if (!rows.length && meta && meta.filtered && meta.total) {
      content.innerHTML = DS.EmptyState({
        icon: "◔",
        title: "لا مراقبة تطابق الترشيح",
        text: "لديك " + meta.total + " مراقبة مسلّحة، ولا واحدة منها " +
              "تطابق ما رشّحت.",
        actions: [{ href: window.location.pathname, label: "امسح الترشيح",
                    primary: true }],
        inline: true,
      });
      table.setAttribute("data-state", "ready");
      return;
    }
    if (!rows.length) {
      content.innerHTML = DS.EmptyState(setupError
        ? {
            icon: "◭",
            title: "المراقبة متوقفة",
            text: setupError,
            actions: [{ href: "/settings/", label: "الإعدادات", primary: true }],
          }
        : {
            icon: "◔",
            title: "لا فرص مراقَبة الآن",
            text: "تُنشأ المراقبة تلقائياً عند صدور توصية معلّقة من المسح، ثم " +
              "يصلك تنبيه تيليجرام لحظة بلوغ سعر الدخول.",
            steps: ["افتح الماسح على الفريم المطلوب", "شغّل مسحاً جديداً",
                    "التوصيات المعلّقة تظهر هنا تلقائياً"],
            actions: [{ href: "/scanner/", label: "افتح الماسح", primary: true }],
          });
      table.setAttribute("data-state", "ready");
      return;
    }

    DS.patchDataTable(content, {
      columns: WATCH_COLUMNS,
      items: rows,
      keyFn: watchKey,
      buildRow: watchRow,
      patchRow: function (tr, w) {
        var cells = watchRow(w);
        WATCH_COLUMNS.forEach(function (c) {
          DS.setCellText(tr, c.key, cells[c.key]);
        });
      },
      onWire: wireAiButtons,
    });
    wireAiButtons(content);
    table.setAttribute("data-state", "ready");
  }

  function renderMonitorState(monitor, rows) {
    var m = monitor || {};
    if (m.last_error) {
      state.textContent = "خطأ: " + m.last_error;
      state.className = "ds-text-xs ds-value-risk";
      return;
    }
    var when = m.running ? "يفحص الآن"
      : m.seconds_ago !== null && m.seconds_ago !== undefined
        ? "آخر فحص قبل " + DS.ltr(m.seconds_ago + "ث") : "لم يبدأ بعد";
    state.textContent = when + " · " + rows.length + " مراقَبة";
    state.className = "ds-text-xs ds-text-muted";
  }

  /* ═══ المرشّح يُنقل من العنوان إلى النداء ═══
   *
   * الجدول يُبنى من ‎/api/watches/‎ لا من القالب. فشريط الترشيح
   * يُعيد تحميل الصفحة بمرشّحٍ في العنوان، ثمّ يطلب هذا النداء
   * البيانات **بلا** ذلك المرشّح — فيظهر الشريط ممتلئاً والجدول
   * غير مرشَّح، وهو أسوأ من غياب المرشّح: يبدو أنّه يعمل.
   *
   * والنقل بأخذ المفاتيح التي تخصّ الترشيح وحدها: تمرير العنوان
   * كلّه يُرسل مفاتيح واجهة (مثل ‎tab‎) لا يعرفها الخادم. */
  var FILTER_KEYS = ["symbol", "tf", "market", "from", "to"];

  function filterQuery() {
    var src = new URLSearchParams(window.location.search);
    var out = new URLSearchParams();
    FILTER_KEYS.forEach(function (k) {
      var v = src.get(k);
      if (v) out.set(k, v);
    });
    var q = out.toString();
    return q ? "?" + q : "";
  }

  function load() {
    return fetch("/api/watches/" + filterQuery(), { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var rows = d.watches || [];
        renderMonitorState(d.monitor, rows);
        renderSummary(rows, d.monitor || {});
        renderTable(rows, d.setup_error, d);
      })
      .catch(function () {
        table.setAttribute("data-state", "error");
        var box = table.querySelector(".ds-widget__error");
        if (box) { box.hidden = false; box.textContent = "تعذّر تحميل المراقبة."; }
      });
  }

  document.getElementById("check-now").addEventListener("click", function () {
    var b = this;
    b.disabled = true;
    b.textContent = "يفحص…";
    window.postJSON("/api/check/")
      .then(function (d) {
        b.textContent = "افحص الآن";
        b.disabled = false;
        if (d.ok === false && d.reason) {
          state.textContent = d.reason;
          state.className = "ds-text-xs ds-value-risk";
        }
        if (d.triggered) location.reload(); else load();
      })
      .catch(function () { b.textContent = "افحص الآن"; b.disabled = false; });
  });

  var tg = document.getElementById("tg-test");
  tg.addEventListener("click", function () {
    var old = tg.textContent;
    tg.disabled = true;
    tg.textContent = "يرسل…";
    window.postJSON("/api/telegram-test/")
      .then(function (d) {
        tg.disabled = false;
        tg.textContent = d.ok ? "أُرسلت ✓" : "فشل ✗";
        state.textContent = d.ok ? "افتح تيليجرام — يجب أن تصلك الرسالة الآن" : d.reason;
        state.className = "ds-text-xs " + (d.ok ? "ds-value-success" : "ds-value-risk");
        setTimeout(function () { tg.textContent = old; }, 4000);
      })
      .catch(function () { tg.disabled = false; tg.textContent = old; });
  });

  load();
  EVERY(20000, load);
})();
