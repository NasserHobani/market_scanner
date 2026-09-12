/* الرموز المحظورة — إضافة ورفع، والأثر فوري.
 *
 * الحظر يسري على المسح التالي بلا إعادة تشغيل: القائمة تُقرأ من
 * القاعدة بذاكرةٍ عمرها ثوانٍ. وهذا الفرق العملي عن ملفّ YAML.
 */
(function () {
  "use strict";

  var shell = document.getElementById("w-blocked");
  if (!shell) return;
  var content = shell.querySelector(".ds-widget__content");

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function row(b) {
    return '<tr data-id="' + b.id + '">' +
      "<td><b>" + esc(b.symbol) + "</b>" +
        (b.active ? "" :
          ' <span class="small muted">(معطّل)</span>') + "</td>" +
      '<td class="small">' + esc(b.market) + "</td>" +
      '<td class="small muted">' + esc(b.scope_label) + "</td>" +
      '<td class="small">' + esc(b.reason || "—") + "</td>" +
      /* المصدر عمودٌ ظاهر لا تفصيل مطويّ: من راجع قائمته بعد
         شهرٍ يحتاج أن يعرف على ماذا بنى بلا نقرة. */
      '<td class="small muted">' + esc(b.source || "—") + "</td>" +
      '<td style="white-space:nowrap">' +
        '<button type="button" class="ds-btn ds-btn--sm blk-toggle">' +
          (b.active ? "عطّل" : "فعّل") + "</button> " +
        '<button type="button" class="ds-btn ds-btn--sm blk-remove">احذف</button>' +
      "</td></tr>";
  }

  function render(d) {
    var meta = document.getElementById("blocked-meta");
    if (meta) meta.textContent = d.total + " رمزاً محظوراً";
    if (!d.blocked || !d.blocked.length) {
      content.innerHTML = DS.EmptyState({
        icon: "○",
        title: "لا رموز محظورة",
        text: "أضف رموزاً أعلاه لتُستبعد من المسح والتحليل وفتح الصفقات.",
        inline: true,
      });
      shell.setAttribute("data-state", "ready");
      return;
    }
    content.innerHTML =
      '<div class="table-responsive"><table class="table table-sm ' +
      'align-middle mb-0"><thead><tr>' +
      "<th>الرمز</th><th>السوق</th><th>النطاق</th><th>السبب</th>" +
      "<th>المصدر</th><th></th></tr></thead><tbody>" +
      d.blocked.map(row).join("") + "</tbody></table></div>";
    shell.setAttribute("data-state", "ready");
  }

  function load() {
    return fetch("/api/blocked/", { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) {
          content.innerHTML = '<p class="small down">' + esc(d.reason) + "</p>";
          shell.setAttribute("data-state", "ready");
          return;
        }
        render(d);
      });
  }

  content.addEventListener("click", function (e) {
    var tr = e.target.closest("tr[data-id]");
    if (!tr) return;
    var id = tr.getAttribute("data-id");
    if (e.target.closest(".blk-remove")) {
      window.postJSON("/api/blocked/" + id + "/remove/",
                      new URLSearchParams()).then(load);
    } else if (e.target.closest(".blk-toggle")) {
      window.postJSON("/api/blocked/" + id + "/toggle/",
                      new URLSearchParams()).then(load);
    }
  });

  document.getElementById("block-form").addEventListener("submit",
    function (e) {
      e.preventDefault();
      var f = new FormData(this);
      var out = document.getElementById("block-result");
      window.postJSON("/api/blocked/add/", new URLSearchParams(f))
        .then(function (d) {
          /* ‏postJSON لا يرفض: يعيد ``{ok:false, reason}``. فقراءة
             ``d.added`` مباشرةً تجعل الفشل يبدو «لم يُضف شيء» —
             وهو خطأٌ يُقرأ نتيجةً. */
          if (!d || d.ok === false) {
            out.textContent = "✗ " + ((d && d.reason) || "تعذّر الحظر");
            out.style.color = "var(--ds-risk)";
            return;
          }
          out.style.color = "";
          /* يُقال ما أُضيف وما كان موجوداً: «تمّ» وحدها تترك
             المستخدم يشكّ هل لُصقت الخمسون كلّها أم بعضها. */
          var msg = [];
          if (d.added && d.added.length) {
            msg.push("أُضيف " + d.added.length + ": " + d.added.join("، "));
          }
          if (d.existed && d.existed.length) {
            msg.push("موجود سلفاً " + d.existed.length + ": " +
                     d.existed.join("، "));
          }
          out.textContent = msg.join(" · ") || "لم يُضف شيء";
          e.target.reset();
          load();
        })
        .catch(function (err) { out.textContent = "✗ " + err; });
    });

  load();
})();
