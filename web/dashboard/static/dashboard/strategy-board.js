/* لوحة الاستراتيجيات — عمودٌ لكلّ واحدة، وبطاقةٌ لكلّ رمزٍ مطابق.
 *
 * والبطاقة تعرض الشروط المتحقّقة مفصّلةً عند الطلب: «يُطابق» بلا
 * سبب تجعل الاستراتيجية صندوقاً مغلقاً — لا تُحسَّن ولا يُفهَم
 * لماذا اختارت هذا الرمز دون غيره.
 */
(function () {
  "use strict";

  var board = document.getElementById("board");
  if (!board) return;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  var TONE = {
    ENTRY_READY: "var(--ds-success)",
    BREAKOUT_RETEST: "var(--ds-success)",
    BREAKOUT: "var(--ds-info)",
    STRONG_PRE_BREAKOUT: "var(--ds-info)",
    PRE_BREAKOUT: "var(--ds-info)",
    EARLY_MOMENTUM: "var(--ds-warn)",
    WATCH: "var(--ds-warn)",
    ALREADY_EXPANDED: "var(--ds-risk)",
  };

  function price(v) {
    return window.Fmt ? Fmt.price(v) : v;
  }

  function condList(c) {
    return (c.conditions || []).map(function (x) {
      var val = x.value === null || x.value === undefined ? "—" : x.value;
      return '<div class="small" style="display:flex;gap:6px;padding:1px 0;' +
        'color:' + (x.ok ? "var(--ds-text)" : "var(--ds-text-muted)") + '">' +
        (x.ok ? "✓" : "·") + " " + esc(x.label) +
        '<span class="muted" style="margin-inline-start:auto">' +
        esc(val) + esc(x.unit || "") + "</span></div>";
    }).join("");
  }

  function card(c) {
    var tone = TONE[c.state] || "var(--ds-text-muted)";
    var up = (c.supertrend_dir || 0) > 0;
    /* عمر الانقلاب لا الاتّجاه وحده: «صاعد» يقولها EMA و ADX،
       أمّا «صاعد منذ ٣ شمعات» فتوقيتٌ لا يعطيه غيره. */
    var st = c.supertrend_dir
      ? '<span style="color:' + (up ? "var(--ds-success)" : "var(--ds-risk)") +
        '">' + (up ? "▲" : "▼") +
        (c.supertrend_bars != null ? " " + c.supertrend_bars + "ش" : "") +
        "</span>"
      : '<span class="muted">—</span>';
    var dist = (c.distance === null || c.distance === undefined)
      ? "—" : c.distance + "٪";

    return '<div class="kb__card">' +
      '<div class="kb__rail" style="background:' + tone + '"></div>' +
      '<div class="d-flex align-items-baseline gap-2">' +
        "<a class='kb__sym' href='/symbol/" + esc(c.market) + "/" +
          esc(c.symbol) + "/?tf=4h'>" + esc(c.symbol) + "</a>" +
        '<span class="small muted">' + esc(c.market) + "</span>" +
        '<span class="small" style="margin-inline-start:auto;color:' + tone +
          '">' + esc(c.state_label || c.state || "") + "</span>" +
      "</div>" +
      '<div class="d-flex gap-3 mt-2 small">' +
        "<span>" + price(c.close) + "</span>" +
        '<span class="muted">النقاط <b>' + (c.score != null ? c.score : "—") +
          "</b></span>" +
        '<span class="muted">زخم <b>' +
          (c.momentum != null ? c.momentum : "—") + "</b></span>" +
        "<span>" + st + "</span>" +
      "</div>" +
      '<div class="small muted mt-1">للمقاومة ' + esc(dist) + "</div>" +
      "<details class='mt-2'><summary class='small muted'>" +
        "الشروط " + c.met + "/" + c.total + "</summary>" +
        "<div style='margin-top:6px'>" + condList(c) + "</div>" +
      "</details></div>";
  }

  function column(col) {
    var head = '<div class="kb__head">' +
      "<b>" + esc(col.name) + "</b>" +
      '<span class="small muted">' + col.matched + " من " + col.scanned +
      "</span>";
    if (col.truncated) {
      head += '<span class="small muted">(+' + col.truncated + ")</span>";
    }
    head += "</div>";

    var body;
    if (col.error) {
      /* عمودٌ يفشل يُعرَض بسببه ولا يُخفى: استراتيجيةٌ معطوبة
         تبدو «بلا نتائج» وهي لم تعمل أصلاً. */
      body = '<p class="small down">تعذّر: ' + esc(col.error) + "</p>";
    } else if (!col.cards.length) {
      body = '<p class="small muted">لا رمز يستوفي الشروط الآن.</p>';
      if ((col.missing || []).length) {
        body += '<p class="small warn">بلا مسح: ' +
          esc(col.missing.join("، ")) + "</p>";
      }
    } else {
      body = col.cards.map(card).join("");
    }
    return '<div class="kb__col">' + head +
      '<div class="kb__body">' + body + "</div></div>";
  }

  function load() {
    var m = document.getElementById("f-market").value;
    board.innerHTML = '<p class="small muted">يحمّل…</p>';
    fetch("/api/board/?market=" + encodeURIComponent(m),
          { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var cols = d.columns || [];
        if (!cols.length) {
          board.innerHTML = DS.EmptyState({
            icon: "◧", title: "لا استراتيجية بعد",
            text: "ابنِ واحدةً وستظهر هنا عموداً.",
            actions: [{ href: "/strategies/", label: "بناء استراتيجية",
                        primary: true }],
            inline: true,
          });
          return;
        }
        board.innerHTML = '<div class="kb">' +
          cols.map(column).join("") + "</div>";
      });
  }

  document.getElementById("apply").addEventListener("click", load);
  load();
})();
