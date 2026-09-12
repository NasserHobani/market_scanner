/* الصفقات الذهبية — بطاقةٌ لكل سوق، وسبب الاختيار ظاهر.
 *
 * ═══ لماذا يُعرض تفصيل الترتيب ═══
 *
 * درجةٌ مفردة («87 نقطة») تُصدَّق أو تُهمَل ولا تُناقَش. والتفصيل
 * يجعل القارئ يخالف الترتيب وهو يعرف على ماذا بُني — وقد يكون
 * محقّاً: العائد/المخاطرة معروفٌ يقيناً، وسجلّ الأسباب مقيس، أمّا
 * النقاط فرقمٌ يعطيه النظام لنفسه.
 */
(function () {
  "use strict";

  var grid = document.getElementById("golden-grid");
  if (!grid) return;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function px(v) { return window.Fmt ? Fmt.price(v) : String(v); }

  function bar(p) {
    /* شريطٌ للمركّب الواحد: الطول من نصيبه لا من الإجمالي، فيُرى
       أيّ مركّبٍ رفع الترتيب وأيّه خفضه. */
    var pct = Math.max(0, Math.min(100, (p.points / p.max) * 100));
    var neg = p.points < 0;
    return '<div class="small" style="margin:3px 0">' +
      '<div style="display:flex;justify-content:space-between;gap:6px">' +
        "<span>" + esc(p.label) + '</span>' +
        '<span class="muted">' + esc(p.value) + " · " +
        (p.points > 0 ? "+" : "") + p.points + "</span></div>" +
      '<div style="height:4px;border-radius:2px;background:var(--ds-surface-3)">' +
        '<div style="height:4px;border-radius:2px;width:' +
        (neg ? 100 : pct) + '%;background:' +
        (neg ? "var(--ds-risk)" : "var(--ds-info)") + '"></div></div></div>';
  }

  function whyBlock(w) {
    if (!w) return "";
    var h = '<div class="small muted" style="margin-top:6px">' +
      esc(w.headline) + "</div>";
    (w.supporting || []).forEach(function (t) {
      h += '<div class="small" style="color:var(--ds-success)">▲ ' +
        esc(t) + "</div>";
    });
    (w.opposing || []).forEach(function (t) {
      h += '<div class="small" style="color:var(--ds-risk)">▼ ' +
        esc(t) + "</div>";
    });
    if (w.untested) {
      h += '<div class="small muted">· ' + w.untested +
        " سبباً بلا عيّنة كافية</div>";
    }
    return h;
  }

  function card(m) {
    var head = '<div class="ds-card__head">' +
      '<h3 class="ds-card__title">' + esc(m.label) + "</h3>";
    if (!m.candidate) {
      /* الفراغ يُعلَّل: بطاقةٌ فارغة تُقرأ «السوق هادئ»، وقد يكون
         المسح متوقّفاً منذ يومين — والفرق يغيّر ما تفعله. */
      return '<section class="ds-card">' + head + "</div>" +
        '<div class="p-3"><p class="small muted">' + esc(m.reason) +
        '</p><a class="ds-btn ds-btn--sm" href="/scanner/?market=' +
        esc(m.market) + '">افتح الماسح</a></div></section>';
    }
    var c = m.candidate;
    var tone = c.action === "now" ? "var(--ds-success)" : "var(--ds-warn)";
    var h = '<section class="ds-card">' + head +
      '<span class="ds-card__meta">' + c.considered + " مرشّحاً</span></div>" +
      '<div class="p-3">' +
      '<div style="display:flex;align-items:baseline;gap:8px;flex-wrap:wrap">' +
        '<a href="' + c.url + '" style="font-size:1.15rem;font-weight:700;' +
        'color:var(--ds-info);text-decoration:none">' + esc(c.symbol) + "</a>" +
        '<span class="small" style="color:' + tone + '">' +
        (c.action === "now" ? "شراء الآن" : "شراء لاحقاً") + "</span>" +
        '<span class="small muted">' + esc(c.timeframe) +
        (c.grade && c.grade !== "—" ? " · " + esc(c.grade) : "") + "</span>" +
      "</div>" +

      '<table class="table table-sm mt-2 mb-1"><tbody>' +
        '<tr><td class="small muted">الدخول</td><td class="num">' +
          px(c.entry) + "</td></tr>" +
        '<tr><td class="small muted">الوقف</td><td class="num down">' +
          px(c.stop) + (c.risk_pct !== null
            ? ' <span class="small muted">(−' + c.risk_pct + "٪)</span>" : "") +
          "</td></tr>" +
        '<tr><td class="small muted">الهدف</td><td class="num up">' +
          px(c.target1) + (c.gain_pct !== null
            ? ' <span class="small muted">(+' + c.gain_pct + "٪)</span>" : "") +
          "</td></tr>" +
        '<tr><td class="small muted">عائد/مخاطرة</td><td class="num">' +
          (c.rr ? Number(c.rr).toFixed(2) : "—") + "</td></tr>" +
      "</tbody></table>" +

      '<details class="small"><summary class="muted">لماذا اختير — ' +
        c.rank_total + " نقطة</summary><div style='margin-top:6px'>" +
        (c.rank_parts || []).map(bar).join("") + "</div></details>" +

      whyBlock(c.why) +

      '<div class="mt-2" style="display:flex;gap:6px;flex-wrap:wrap">' +
        '<button type="button" class="ds-btn ds-btn--sm ds-btn--primary ' +
        'golden-ask" data-market="' + esc(c.market) + '" data-symbol="' +
        esc(c.symbol) + '" data-tf="' + esc(c.timeframe) + '" data-grade="' +
        esc(c.grade || "") + '" data-score="' + (c.score || "") +
        '" data-rr="' + (c.rr || "") + '" data-entry="' + (c.entry || "") +
        '" data-stop="' + (c.stop || "") + '" data-target="' +
        (c.target1 || "") + '" data-reasons="' + esc(c.reasons) +
        '">هل أدخل؟</button>' +
        (c.chart_url ? '<a class="ds-btn ds-btn--sm" target="_blank" ' +
          'rel="noopener" href="' + c.chart_url + '">الشارت ↗</a>' : "") +
      "</div></div></section>";
    return h;
  }

  function load() {
    fetch("/api/golden/", { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) {
          grid.innerHTML = '<p class="small down">' + esc(d.reason) + "</p>";
          return;
        }
        grid.style.gridTemplateColumns =
          "repeat(auto-fit, minmax(300px, 1fr))";
        grid.innerHTML = (d.markets || []).map(card).join("");
        var meta = document.getElementById("golden-meta");
        if (meta) {
          meta.textContent = "على " + d.population + " صفقة محسومة · " +
            "أحدث " + d.max_age_hours + "س · عائد/مخاطرة ≥ " + d.min_rr;
        }
      })
      .catch(function () {
        grid.innerHTML = '<p class="small down">تعذّر التحميل.</p>';
      });
  }

  grid.addEventListener("click", function (e) {
    var b = e.target.closest(".golden-ask");
    if (!b || !window.Advice) return;
    Advice.openSetup({
      symbol: b.dataset.symbol, market: b.dataset.market,
      timeframe: b.dataset.tf, grade: b.dataset.grade,
      score: b.dataset.score, rr: b.dataset.rr,
      entry: b.dataset.entry, stop: b.dataset.stop,
      target1: b.dataset.target, reasons: b.dataset.reasons,
      source: "auto", side: "buy",
    });
  });

  document.getElementById("refresh").addEventListener("click", load);
  load();
})();
