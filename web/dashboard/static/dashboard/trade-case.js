/* الحجّة بوجهيها — عارضٌ واحد تستعمله كل الشاشات.
 *
 * ═══ لماذا ملفٌّ مشترك ═══
 *
 * لو رُسمت الحجّة في كل شاشةٍ على حدة لانحرفت: شاشةٌ تعرض
 * الوجهين وأخرى تكتفي بالدعم، فيُقرأ الرمز نفسه قراءتين. وهو
 * نفس العطب الذي ظهر في «الالتقاء ‎/3‎» — مقياسٌ مكتوبٌ باليد في
 * الواجهة يخالف ما يحسبه الخادم.
 *
 * ═══ والعمودان متساويان بصرياً ═══
 *
 * «يدعم» أعرض أو أعلى من «يضعف» يجعل القارئ يزن بالمساحة لا
 * بالمحتوى. فهما متساويان، والمضادّ **أوّلاً** على الجوّال —
 * لأنّ ما يُقرأ أوّلاً يُوزن أكثر، والانحياز الطبيعيّ نحو
 * التأكيد لا نحو الشكّ.
 */
(function () {
  "use strict";

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function side(items, tone, title, hint) {
    var rows = (items || []).map(function (x) {
      return '<li style="padding:6px 0;border-bottom:1px solid var(--ds-line)">' +
        (x.family_label
          ? '<span class="ds-text-xs ds-text-muted">' +
            esc(x.family_label) + "</span> " : "") +
        esc(x.text) + "</li>";
    }).join("");
    return '<div style="flex:1 1 18rem;min-width:0">' +
      '<div class="d-flex align-items-center gap-2 mb-1">' +
      '<span class="ds-value-' + tone + '" style="font-weight:600">' +
      esc(title) + "</span>" +
      '<span class="ds-text-xs ds-text-muted">' + (items || []).length +
      "</span></div>" +
      '<ul style="list-style:none;padding:0;margin:0" class="small">' +
      rows + "</ul>" +
      (hint ? '<p class="ds-text-xs ds-text-muted mt-1">' + esc(hint) +
        "</p>" : "") + "</div>";
  }

  /* ═══ العائلات المساهِمة تُعدّ لا تُجمَع ═══
   *
   * ‏EMA و ADX و Supertrend تقيس الاتّجاه — ثلاث نقاطٍ في عمود
   * «يدعم» ليست ثلاثة شهود بل شاهدٌ واحد بثلاثة أسماء. */
  function familyBar(d) {
    var fams = d.families_supporting || [];
    var tone = fams.length >= 3 ? "success" : fams.length === 2
      ? "warn" : "risk";
    return '<div class="ds-text-xs mb-2">' +
      'عائلات مساهِمة: <span class="ds-value-' + tone + '">' +
      fams.length + " من 4</span>" +
      '<span class="ds-text-muted"> — القاعدة ١٧ تشترط ثلاثاً. ' +
      "واجتماع مؤشّرات تقيس الشيء نفسه ليس تأكيداً.</span></div>";
  }

  function render(host, d) {
    if (!host) return;
    if (!d || d.error) {
      host.innerHTML = '<p class="small ds-text-muted">' +
        esc((d && (d.error || d.reason)) || "لا حجّة متاحة") + "</p>";
      return;
    }
    host.innerHTML =
      familyBar(d) +
      '<div class="d-flex gap-4 flex-wrap">' +
      /* المضادّ أوّلاً عمداً */
      side(d.con, "risk", "لماذا قد تفشل",
           "ما يضعفها في المقاييس المحسوبة وفي سجلّك.") +
      side(d.pro, "success", "لماذا قد تنجح",
           "عائلةٌ واحدة مرّةً واحدة — لا يُعدّ الاتّجاه ثلاث مرّات.") +
      "</div>" +
      /* ═══ ولا احتمال ═══
         النموذج الوحيد الذي حاول ذلك هنا لم يتجاوز خطّ الأساس
         فأُخفي احتماله. والمعيار نفسه يُطبَّق. */
      '<p class="ds-text-xs ds-text-muted mt-2">' + esc(d.note || "") +
      " لا يُعرَض احتمال نجاحٍ لهذه الصفقة: نسبُ سجلّك تصف ما مضى، " +
      "ولا تتنبّأ بما يأتي.</p>";
  }

  /* ═══ تشريح النتيجة ═══
   *
   * أين كان الخلل — في الدخول أم في الخروج؟ صفقةٌ بلغت ‎+2.3R‎ ثمّ
   * خسرت ليست كصفقةٍ لم تتحرّك قطّ، ونتيجتهما في الجدول واحدة. */
  var BLAME_AR = { entry: "الدخول", exit: "الخروج" };

  function renderAnatomy(host, a) {
    if (!host) return;
    if (!a) { host.innerHTML = ""; return; }
    if (a.kind === "unknown") {
      host.innerHTML = '<p class="small ds-text-muted">' +
        esc(a.label) + " — لا مسار مسجَّل لهذه الصفقة.</p>";
      return;
    }
    var won = (a.r_multiple || 0) > 0;
    var tone = won ? "success" : "risk";
    var blame = a.blame
      ? '<span class="ds-badge ds-badge--' +
        (a.blame === "exit" ? "warn" : "risk") + '">الخلل في ' +
        esc(BLAME_AR[a.blame] || a.blame) + "</span>"
      : "";

    function cell(label, v, suffix) {
      return '<div class="col-6 col-md-3"><div class="ds-text-xs ' +
        'ds-text-muted">' + esc(label) + "</div>" +
        '<div class="ds-num" dir="ltr">' +
        (v === null || v === undefined ? "—" :
          (v > 0 ? "+" : "") + Number(v).toFixed(2) + (suffix || "")) +
        "</div></div>";
    }

    host.innerHTML =
      '<div class="d-flex align-items-center gap-2 flex-wrap mb-2">' +
      '<span class="ds-value-' + tone + '" style="font-weight:600">' +
      esc(a.label) + "</span>" + blame + "</div>" +
      '<div class="row g-2 mb-2">' +
      cell("أقصى ربح بلغته", a.best_r, "R") +
      cell("أقصى تراجع", a.worst_r, "R") +
      cell("النتيجة", a.r_multiple, "R") +
      cell("ما رُدّ من الربح", a.given_back_r, "R") +
      "</div>" +
      (a.capture_pct !== null && a.capture_pct !== undefined
        ? '<div class="ds-text-xs ds-text-muted mb-2">اقتنصتَ ' +
          a.capture_pct + "٪ من الحركة المتاحة.</div>" : "") +
      (a.notes || []).map(function (n) {
        return '<p class="small mb-1">' + esc(n) + "</p>";
      }).join("") +
      (a.stop_context && a.stop_context.ok
        ? '<div class="ds-insight ds-insight--info mt-2">' +
          '<div class="ds-insight__body"><p class="ds-insight__text small">' +
          esc(a.stop_context.verdict) + "</p></div></div>"
        : a.stop_context
          ? '<p class="ds-text-xs ds-text-muted mt-2">سياق الوقف: ' +
            esc(a.stop_context.why) + "</p>"
          : "");
  }

  window.TradeCase = { render: render, renderAnatomy: renderAnatomy,
                       esc: esc };
})();
