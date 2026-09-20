/* دليل الرموز — جردٌ بلا تحليل.
 *
 * والعمود الأهمّ «الشموع»: رمزٌ بلا شموع لا يدخل أيّ تحليل، فلا
 * يظهر في أيّ شاشةٍ أخرى — لا بوصفه ضعيفاً بل بألّا يُذكر. وهذا
 * هو الفرق بين سوقٍ هادئ وسوقٍ لا يُقرأ.
 */
(function () {
  "use strict";

  var body = document.getElementById("sym-body");
  if (!body) return;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  var TFS = ["15m", "1h", "4h", "1d"];

  /* شاراتُ الفريمات: الموجود مضيء والغائب باهت — لا حذفٌ للغائب.
     الحذف يجعل صفّاً بفريمين يبدو مثل صفٍّ بأربعة عند لمحة. */
  function tfChips(r) {
    return TFS.map(function (tf) {
      var on = (r.timeframes || []).indexOf(tf) >= 0;
      return '<span style="display:inline-block;padding:0 5px;margin-inline-end:3px;' +
        "border-radius:3px;font-size:.72rem;border:1px solid " +
        (on ? "var(--ds-line)" : "transparent") + ";color:" +
        (on ? "var(--ds-text)" : "var(--ds-text-muted)") + ";background:" +
        (on ? "var(--ds-surface-3)" : "transparent") + ';opacity:' +
        (on ? "1" : ".45") + '">' + tf + "</span>";
    }).join("");
  }

  function age(iso) {
    if (!iso) return '<span class="muted">—</span>';
    var t = Date.parse(iso);
    if (isNaN(t)) return esc(iso);
    var h = (Date.now() - t) / 36e5;
    /* العمر لا الطابع: «قبل ٣س» تُقرأ فوراً، و«2026-09-17T12:00»
       تحتاج حساباً ذهنياً في كل صفّ. */
    var txt = h < 1 ? "الآن" : h < 48 ? Math.round(h) + "س"
      : Math.round(h / 24) + "ي";
    var tone = h < 24 ? "var(--ds-text)"
      : h < 24 * 7 ? "var(--ds-warn)" : "var(--ds-risk)";
    return '<span style="color:' + tone + '" title="' + esc(iso) + '">' +
      txt + "</span>";
  }

  function row(r) {
    var flags = "";
    if (r.blocked) {
      flags += ' <span class="small" style="color:var(--ds-risk)">محظور</span>';
    }
    /* «يتيم» = له شموع ولم يعد الاكتشاف يذكره: مشطوبٌ أو هبط
       حجمه تحت العتبة. يُعرَض كي لا يختفي بلا خبر. */
    if (!r.discovered) {
      flags += ' <span class="small" style="color:var(--ds-warn)"' +
        ' title="له شموع ولم يعد الاكتشاف يذكره">يتيم</span>';
    }
    var name = r.tf_count
      ? "<a href='/symbol/" + esc(r.market) + "/" + esc(r.symbol) +
        "/?tf=4h'><b>" + esc(r.symbol) + "</b></a>"
      : "<b>" + esc(r.symbol) + "</b>";
    return "<tr>" +
      "<td>" + name + flags + "</td>" +
      '<td class="small">' + esc(r.market) + "</td>" +
      "<td>" + tfChips(r) + "</td>" +
      '<td class="num small">' + age(r.last_candle) + "</td>" +
      "</tr>";
  }

  function group(g) {
    /* الرقم الأهمّ في الرأس: «بلا شموع». وهو ما لا تقوله أيّ
       شاشةٍ أخرى — لأنّ الغائب لا يُعرَض فيها أصلاً. */
    var gap = g.without_candles
      ? ' · <span class="warn">' + g.without_candles + " بلا شموع</span>" : "";
    var orphan = g.orphans ? " · " + g.orphans + " يتيم" : "";
    var blocked = g.blocked ? " · " + g.blocked + " محظور" : "";
    var head = '<section class="ds-card mb-4"><div class="ds-card__head">' +
      '<h3 class="ds-card__title">' + esc(g.market) + "</h3>" +
      '<span class="ds-card__meta">' + g.discovered + " مكتشَف · " +
        g.with_candles + " له شموع" + gap + orphan + blocked +
      "</span></div>";
    if (!g.rows.length) {
      return head + '<div class="p-3"><p class="small muted">' +
        "لا رمز يطابق.</p></div></section>";
    }
    var more = g.truncated
      ? '<p class="small muted mt-2">وأُخفي ' + g.truncated +
        " صفّاً — ضيّق بالبحث أو بالسوق.</p>" : "";
    return head + '<div class="p-3"><div class="table-responsive">' +
      '<table class="table table-sm align-middle mb-0"><thead><tr>' +
      "<th>الرمز</th><th>السوق</th>" +
      '<th title="الفريمات التي لها شموع على القرص">الشموع</th>' +
      '<th title="عمر آخر شمعة">آخر شمعة</th>' +
      "</tr></thead><tbody>" + g.rows.map(row).join("") +
      "</tbody></table></div>" + more + "</div></section>";
  }

  function load() {
    var m = document.getElementById("f-market").value;
    var q = document.getElementById("f-q").value;
    var only = document.getElementById("f-only").value;
    body.innerHTML = '<p class="small muted">يحمّل…</p>';
    fetch("/api/symbols/?market=" + encodeURIComponent(m) +
          "&q=" + encodeURIComponent(q) +
          "&only=" + encodeURIComponent(only),
          { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) { body.innerHTML = '<p class="small down">تعذّر</p>'; return; }
        var h = (d.groups || []).map(group).join("");
        if (d.discovery_failed && d.discovery_failed.length) {
          h = '<p class="small warn">تعذّر اكتشاف كون: ' +
            esc(d.discovery_failed.join("، ")) +
            " — المعروض من القرص وحده.</p>" + h;
        }
        body.innerHTML = h || DS.EmptyState({
          icon: "◈", title: "لا رموز",
          text: "لم يُكتشف رمزٌ ولا وُجد ملفّ شموع.",
          inline: true,
        });
      });
  }

  document.getElementById("apply").addEventListener("click", load);
  document.getElementById("f-q").addEventListener("keydown", function (e) {
    if (e.key === "Enter") load();
  });
  load();
})();
