/* الانضغاط — احتمالٌ مقيس بجانب معدّل الأساس دائماً.
 *
 * ═══ لماذا الأساس ملازم ═══
 *
 * «62٪» رقمٌ يبدو كبيراً. لكنّ الأساس 54٪ — أي أنّ الانضغاط يضيف
 * ثماني نقاط لا اثنتين وستّين. وعرضُ الرقم وحده يجعل القارئ يظنّ
 * أنّه اكتشف ما لم يكن ليعرفه، وهو يعرف نصفه من غير أيّ مؤشّر.
 */
(function () {
  "use strict";

  var body = document.getElementById("sq-body");
  if (!body) return;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function probBlock(g) {
    var p = g.probability || {}, t = g.timing || {};
    if (!p.readable) {
      /* عيّنة صغيرة = لا نعرف. والرقم في هذه الحال ادّعاء. */
      return '<div class="small warn">العيّنة ' + (p.sample || 0) +
        " حالة — دون حدّ النطق. لا احتمال.</div>";
    }
    var tone = p.beats_base ? "var(--ds-success)" : "var(--ds-text-muted)";
    return '<div class="ds-metrics" style="margin:0 0 var(--ds-sp-3)">' +
      '<div class="ds-metric ds-metric--sm">' +
        '<span class="ds-metric__label">احتمال التمدّد</span>' +
        '<span class="ds-metric__value" style="color:' + tone + '">' +
          p.pct + "٪</span>" +
        '<span class="ds-metric__foot"><span class="ds-text-muted">[' +
          p.low + "–" + p.high + "٪] · " + p.sample + " حالة</span></span>" +
      "</div>" +
      '<div class="ds-metric ds-metric--sm">' +
        '<span class="ds-metric__label">معدّل الأساس</span>' +
        '<span class="ds-metric__value">' + p.base_pct + "٪</span>" +
        '<span class="ds-metric__foot"><span class="ds-text-muted">[' +
          p.base_low + "–" + p.base_high + "٪]</span></span>" +
      "</div>" +
      '<div class="ds-metric ds-metric--sm">' +
        '<span class="ds-metric__label">ما يضيفه الانضغاط</span>' +
        '<span class="ds-metric__value" style="color:' + tone + '">' +
          (p.edge > 0 ? "+" : "") + p.edge + "</span>" +
        '<span class="ds-metric__foot"><span class="ds-text-muted">' +
          (p.beats_base ? "يتجاوز الأساس" : "ضمن الأساس — لا يضيف") +
          "</span></span>" +
      "</div>" +
      '<div class="ds-metric ds-metric--sm">' +
        '<span class="ds-metric__label">الوقت المتوقّع</span>' +
        '<span class="ds-metric__value">' + esc(t.human || "—") + "</span>" +
        '<span class="ds-metric__foot"><span class="ds-text-muted">وسيط ' +
          (t.median_bars || "—") + " شمعة · الأفق " +
          esc(t.horizon_human || "—") + "</span></span>" +
      "</div></div>";
  }

  function rows(g) {
    var c = g.candidates || [];
    if (!c.length) {
      return '<p class="small muted">لا رمز منضغط الآن في هذا الفريم.</p>';
    }
    return '<div class="table-responsive"><table class="table table-sm ' +
      'align-middle mb-0"><thead><tr>' +
      "<th>الرمز</th><th>رتبة الانضغاط</th><th>الحركة المطلوبة</th>" +
      "<th>السعر</th><th></th></tr></thead><tbody>" +
      c.map(function (r) {
        /* الرتبة صفر = أضيق ما كان في 120 شمعة. والشريط يجعل
           المقارنة بين الصفوف بلا قراءة أرقام. */
        var w = Math.max(2, 100 - (r.squeeze_rank || 0) * 6);
        return "<tr><td><a href='/symbol/" + esc(g.market) + "/" +
            esc(r.symbol) + "/?tf=" + esc(g.timeframe) + "'>" +
            esc(r.symbol) + "</a></td>" +
          '<td style="min-width:110px">' +
            '<div style="height:5px;border-radius:3px;background:' +
            'var(--ds-surface-3)"><div style="height:5px;border-radius:3px;' +
            'width:' + w + '%;background:var(--ds-info)"></div></div>' +
            '<span class="small muted">' + r.squeeze_rank + "</span></td>" +
          '<td class="num">' + r.expansion_pct + "٪</td>" +
          '<td class="num">' + (window.Fmt ? Fmt.price(r.close) : r.close) +
            "</td>" +
          "<td><a class='ds-btn ds-btn--sm' href='/symbol/" +
            esc(g.market) + "/" + esc(r.symbol) + "/?tf=" +
            esc(g.timeframe) + "'>افتح</a></td></tr>";
      }).join("") + "</tbody></table></div>";
  }

  function group(g) {
    var stale = g.stale
      ? ' <span class="small warn">القياس عمره ' + g.age_hours +
        "س — أعد القياس</span>"
      : "";
    return '<section class="ds-card mb-4"><div class="ds-card__head">' +
      '<h3 class="ds-card__title">' + esc(g.market) + " · " +
        esc(g.timeframe) + "</h3>" +
      '<span class="ds-card__meta">' + (g.symbols_scanned || 0) +
        " رمزاً مقيساً" + stale + "</span></div>" +
      '<div class="p-3">' + probBlock(g) + rows(g) +
      '<button type="button" class="ds-btn ds-btn--sm mt-2 sq-refresh" ' +
        'data-market="' + esc(g.market) + '" data-tf="' +
        esc(g.timeframe) + '">أعد القياس</button>' +
      "</div></section>";
  }

  function load() {
    var m = document.getElementById("f-market").value;
    var t = document.getElementById("f-tf").value;
    body.innerHTML = '<p class="small muted">يحمّل…</p>';
    fetch("/api/squeeze/?market=" + encodeURIComponent(m) +
          "&tf=" + encodeURIComponent(t), { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) { body.innerHTML = '<p class="small down">تعذّر</p>'; return; }
        var h = (d.groups || []).map(group).join("");
        if (d.missing && d.missing.length) {
          /* «لا قياس بعد» غير «لا رموز منضغطة» — والخلط يجعل
             المستخدم ينتظر شيئاً لم يبدأ. */
          h += '<p class="small muted">بلا قياس بعد: ' +
            esc(d.missing.join("، ")) +
            " — شغّل مهمّة «قياس الانضغاط» من /jobs/ أو اضغط أعد القياس.</p>";
        }
        body.innerHTML = h || DS.EmptyState({
          icon: "◇", title: "لا قياس محفوظ",
          text: "شغّل مهمّة «قياس الانضغاط» من صفحة المهامّ المجدولة.",
          actions: [{ href: "/jobs/", label: "المهامّ", primary: true }],
          inline: true,
        });
      });
  }

  body.addEventListener("click", function (e) {
    var b = e.target.closest(".sq-refresh");
    if (!b) return;
    b.disabled = true;
    b.textContent = "يقيس…";
    window.postJSON("/api/squeeze/refresh/", new URLSearchParams({
      market: b.dataset.market, tf: b.dataset.tf,
    })).then(function () {
      /* القياس في خيط: يُنتظر قليلاً ثمّ يُعاد التحميل. */
      setTimeout(load, 6000);
    });
  });

  document.getElementById("apply").addEventListener("click", load);
  load();
})();
