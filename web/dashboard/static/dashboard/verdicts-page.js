/* سجلّ الأحكام — ما قاله المستشار، وما رُفض ولماذا.
 *
 * ═══ ما استُبدل ═══
 *
 * الجدول القديم أعمدته «القرار · اتفاق · ثقة». وقِيست ٧٥ مراجعة
 * فكانت wait ×65 و insufficient ×5 (عُرضت «مراقبة») و avoid ×4 و
 * **buy ×0** — وعمود «الثقة» رقمٌ من النموذج عن نفسه، لا قياس.
 *
 * وهنا: القرار من ثلاثة محصورة، والرقم من سجلّ الصفقات المحسومة،
 * وشرط الإبطال سعرٌ يمكن مراقبته، والمرفوض **معروضٌ بسببه**.
 */
(function () {
  "use strict";

  var state = { page: 1, q: "", decision: "" };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  var TONE = {
    "ادخل": "var(--up)",
    "لا تدخل": "var(--down)",
    "انتظر": "var(--warn)",
  };

  function decisionCell(r) {
    if (!r.accepted) {
      /* الرفض ليس فشلاً يُخفى: هو أصدق مقياسٍ لصلاحية النموذج. */
      return '<span style="color:var(--ds-text-muted)">◌ لم يُنتج حكماً</span>' +
        '<div class="small muted">' + esc(r.rejected_because) + "</div>";
    }
    var d = (r.fields || {})["القرار"] || "—";
    return '<span style="color:' + (TONE[d] || "var(--ds-text-muted)") +
      ';font-weight:700">' + esc(d) + "</span>";
  }

  function rateCell(r) {
    if (!r.rate) return '<span class="muted">لا سابقة كافية</span>';
    var col = r.rate.significant
      ? (r.rate.edge > 0 ? "var(--up)" : "var(--down)")
      : "var(--ds-text-muted)";
    return '<span style="color:' + col + '">' + r.rate.wins + "/" +
      r.rate.total + " = " + r.rate.pct + "٪</span>" +
      '<div class="small muted">الأساس ' + r.rate.baseline + "٪ · " +
      (r.rate.edge > 0 ? "+" : "") + r.rate.edge + " نقطة</div>";
  }

  function whyCell(r) {
    if (!r.why) return '<span class="muted">—</span>';
    var h = '<div class="small">' + esc(r.why.headline) + "</div>";
    (r.why.opposing || []).forEach(function (t) {
      h += '<div class="small" style="color:var(--down)">▼ ' + esc(t) + "</div>";
    });
    (r.why.supporting || []).forEach(function (t) {
      h += '<div class="small" style="color:var(--up)">▲ ' + esc(t) + "</div>";
    });
    return h;
  }

  function row(r) {
    var f = r.fields || {};
    var when = String(r.at || "").replace("T", " ").slice(0, 16);
    return "<tr>" +
      '<td class="small muted">' + esc(when) + "</td>" +
      "<td><b>" + esc(r.symbol) + "</b>" +
        '<div class="small muted">' + esc(r.market) + " · " +
        esc(r.timeframe) + "</div></td>" +
      "<td>" + decisionCell(r) + "</td>" +
      '<td class="small">' + esc(f["السبب"] || "—") + "</td>" +
      "<td>" + rateCell(r) + "</td>" +
      /* شرط الإبطال سعرٌ يمكن مراقبته — كان صفراً في 164 مراجعة */
      '<td class="small">' + esc(f["الإبطال"] || "—") + "</td>" +
      "<td>" + whyCell(r) + "</td>" +
      '<td class="small muted">' + esc(r.model || r.provider || "") +
        "<div>" + (r.attempts || 1) + " محاولة</div></td>" +
      "</tr>";
  }

  function statsBar(s) {
    if (!s || !s.total) return "";
    var h = '<div class="small mb-2">' +
      "الأحكام " + s.accepted + " من " + s.total;
    if (s.rejected) {
      h += ' · <span style="color:var(--warn)">لم يُنتج حكماً ' +
        s.rejected + "</span>";
    }
    Object.keys(s.decisions || {}).forEach(function (k) {
      if (k === "مرفوض") return;
      h += " · " + esc(k) + " " + s.decisions[k];
    });
    return h + "</div>";
  }

  function render(el, d) {
    if (!d.total) {
      el.innerHTML = DS.EmptyState({
        icon: "◈",
        title: "لا أحكام بعد",
        text: "تُنتَج تلقائياً عند كل مسح للمرشّحين القابلين للتنفيذ، " +
              "أو عند ضغط «هل أدخل؟» في الماسح.",
        inline: true,
      });
      return;
    }
    var h = statsBar(d.stats) +
      '<div class="d-flex flex-wrap gap-2 mb-2">' +
        '<input class="form-control form-control-sm" id="vd-q" ' +
        'placeholder="بحث برمز" style="max-width:180px" value="' +
        esc(state.q) + '">' +
        '<select class="form-select form-select-sm" id="vd-dec" ' +
        'style="max-width:160px">' +
        ["", "ادخل", "لا تدخل", "انتظر", "مرفوض"].map(function (o) {
          return '<option value="' + o + '"' +
            (o === state.decision ? " selected" : "") + ">" +
            (o || "كل القرارات") + "</option>";
        }).join("") + "</select></div>" +
      '<div class="table-responsive"><table class="table table-sm ' +
      'align-middle mb-0"><thead><tr>' +
      "<th>الوقت</th><th>الرمز</th><th>القرار</th><th>السبب</th>" +
      "<th>سابقة مماثلة</th><th>الإبطال</th><th>لماذا</th><th>النموذج</th>" +
      "</tr></thead><tbody>" +
      (d.items || []).map(row).join("") + "</tbody></table></div>";

    if (d.pages > 1) {
      h += '<div class="d-flex gap-2 mt-2 align-items-center">' +
        '<button class="ds-btn" id="vd-prev"' +
        (d.page <= 1 ? " disabled" : "") + ">السابق</button>" +
        '<span class="small muted">' + d.page + " / " + d.pages + "</span>" +
        '<button class="ds-btn" id="vd-next"' +
        (d.page >= d.pages ? " disabled" : "") + ">التالي</button></div>";
    }
    el.innerHTML = h;
    wire(el);
  }

  function wire(el) {
    var q = el.querySelector("#vd-q");
    if (q) {
      q.onchange = function () { state.q = q.value; state.page = 1; load(); };
    }
    var dec = el.querySelector("#vd-dec");
    if (dec) {
      dec.onchange = function () {
        state.decision = dec.value; state.page = 1; load();
      };
    }
    var prev = el.querySelector("#vd-prev");
    if (prev) prev.onclick = function () { state.page--; load(); };
    var next = el.querySelector("#vd-next");
    if (next) next.onclick = function () { state.page++; load(); };
  }

  function load() {
    var shell = document.getElementById("w-verdicts");
    if (!shell) return;
    var el = shell.querySelector(".ds-widget__content");
    var qs = "?page=" + state.page +
      "&q=" + encodeURIComponent(state.q) +
      "&decision=" + encodeURIComponent(state.decision);
    fetch("/api/verdicts/" + qs, { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        shell.setAttribute("data-state", "ready");
        if (!d.ok) {
          el.innerHTML = '<div class="small down">✗ ' +
            esc(d.reason || "تعذّر التحميل") + "</div>";
          return;
        }
        render(el, d);
      })
      .catch(function (e) {
        shell.setAttribute("data-state", "ready");
        el.innerHTML = '<div class="small down">✗ ' + esc(e) + "</div>";
      });
  }

  window.VerdictsPage = { load: load, state: state };
  if (document.getElementById("w-verdicts")) load();
})();
