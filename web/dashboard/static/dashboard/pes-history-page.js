/* سجلّ رصد PES — العتبة مرشِّح، والعيّنة الرقيقة تُعلَن.
 *
 * ═══ ثلاث حالات لا اثنتان ═══
 *
 *   بلغ العتبة   ·   لم يبلغها   ·   قيد المتابعة
 *
 * والثالثة **ليست فشلاً**: هي «لم يُقَس بعد». وخلطُها بالفشل يجعل
 * كل رصدٍ حديث يبدو خاسراً، فتنخفض النسبة كلّما مسحتَ أكثر —
 * وتبدو الاستراتيجية تسوء وهي لم تتغيّر.
 */
(function () {
  "use strict";

  var body = document.getElementById("history-body");
  if (!body) return;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function num(v, digits) {
    return (v === null || v === undefined || isNaN(v)) ? "—"
      : Number(v).toFixed(digits === undefined ? 1 : digits);
  }

  function ago(iso) {
    if (!iso) return "—";
    var d = new Date(iso);
    if (isNaN(d)) return "—";
    var h = (Date.now() - d.getTime()) / 3.6e6;
    if (h < 24) return Math.round(h) + " ساعة";
    return Math.round(h / 24) + " يوم";
  }

  /* ═══ النسبة لا تُعرض عاريةً ═══
   *
   * «٧٥٪» من أربع رصدات لا يعني شيئاً، وفترة ثقته من ٣٠٪ إلى ٩٥٪.
   * فالفترة تُعرض دائماً، ورقّة العيّنة تُقال بنصٍّ لا بلون وحده. */
  function rateBlock(s, title) {
    if (s.rate === null || s.rate === undefined) {
      return '<div class="small muted">' + esc(title) +
        ": لا رصد اكتمل مداه بعد</div>";
    }
    var warn = s.thin
      ? '<div class="small" style="color:var(--ds-warn)">⚠ العيّنة ' +
        s.settled + " — أرقّ من أن تُقرأ نتيجة</div>"
      : "";
    return '<div style="margin-bottom:.35rem">' +
      '<span class="small muted">' + esc(title) + "</span> " +
      '<strong style="font-size:1.35rem">' + num(s.rate) + "٪</strong> " +
      '<span class="small muted">(' + s.hits + " من " + s.settled +
      ") · فترة الثقة " + num(s.ci_low, 0) + "–" + num(s.ci_high, 0) +
      "٪</span>" + warn + "</div>";
  }

  function overall(d) {
    var s = d.overall;
    var curve = (d.curve || []).map(function (c) {
      var on = Math.abs(c.threshold - d.threshold) < 0.01;
      return '<button type="button" class="btn btn-sm btn-outline-secondary ' +
        'chip curve-pick' + (on ? " active" : "") +
        '" data-threshold="' + c.threshold + '">' +
        c.threshold + "٪ → " +
        (c.rate === null ? "—" : num(c.rate) + "٪") + "</button>";
    }).join("");

    return '<section class="ds-card"><div class="ds-card__body">' +
      rateBlock(s, "بلغت " + num(d.threshold) + "٪ خلال " +
                d.horizon_days + " يوماً") +
      '<div class="small muted" style="margin-bottom:.5rem">' +
      "المجموع " + s.total + " رصداً · اكتمل " + s.settled +
      " · قيد المتابعة " + s.watching +
      (s.no_data ? " · تعذّرت متابعة " + s.no_data : "") + "</div>" +
      '<div class="small" style="margin-bottom:.5rem">' +
      "وسيط أقصى ارتفاع " + num(s.median_gain) + "٪ · " +
      "وسيط الساعات حتى القمّة " + num(s.median_hours_to_hit, 0) + " · " +
      /* التراجع يُعرض دائماً: ارتفاعٌ +20٪ سبقه نزول -15٪ لا
         يُدرَك عملياً — الوقف يضربك قبله. */
      "وسيط أقصى تراجع " + num(s.median_drawdown) + "٪" + "</div>" +
      '<div class="small muted" style="margin-bottom:.25rem">' +
      "النسبة عند عتباتٍ أخرى:</div>" +
      '<div class="chips">' + curve + "</div>" +
      "</div></section>";
  }

  function byState(d) {
    if (!(d.by_state || []).length) return "";
    var rows = d.by_state.map(function (s) {
      return "<tr><td>" + esc(s.label) + "</td>" +
        '<td class="text-center">' + s.settled + "</td>" +
        '<td class="text-center"><strong>' +
        (s.rate === null ? "—" : num(s.rate) + "٪") + "</strong></td>" +
        '<td class="text-center small muted">' +
        num(s.ci_low, 0) + "–" + num(s.ci_high, 0) + "٪</td>" +
        '<td class="text-center">' + num(s.median_gain) + "٪</td>" +
        '<td class="text-center small">' + s.broke_resistance + "</td>" +
        '<td class="small muted">' + (s.thin ? "عيّنة رقيقة" : "") +
        "</td></tr>";
    }).join("");
    return '<section class="ds-card"><div class="ds-card__body">' +
      '<h2 class="h6">هل التصنيف يفرّق؟</h2>' +
      '<p class="small muted">رقمٌ واحد بلا مرجع لا يقول شيئاً. ' +
      "والمقارنة بين الحالات هي ما يقول: هل الترقية تعني شيئاً فعلاً؟</p>" +
      '<table class="table table-sm align-middle"><thead><tr>' +
      "<th>الحالة عند الرصد</th><th class='text-center'>اكتمل</th>" +
      "<th class='text-center'>بلغ العتبة</th>" +
      "<th class='text-center'>فترة الثقة</th>" +
      "<th class='text-center'>وسيط الارتفاع</th>" +
      "<th class='text-center'>اخترق المقاومة</th><th></th>" +
      "</tr></thead><tbody>" + rows + "</tbody></table></div></section>";
  }

  var VERDICT_TONE = {
    "بلغ العتبة": "var(--ds-success)",
    "لم يبلغها": "var(--ds-risk)",
    "قيد المتابعة": "var(--ds-text-muted)",
    "تعذّرت المتابعة": "var(--ds-warn)",
  };

  function table(d) {
    if (!(d.rows || []).length) {
      return '<section class="ds-card"><div class="ds-card__body">' +
        '<p class="empty">لا رصد بعد. السجلّ يمتلئ مع كل دورة مسح — ' +
        "وأوّل نتيجةٍ تُقرأ تحتاج أسبوعين على الأقلّ.</p></div></section>";
    }
    var rows = d.rows.map(function (r) {
      return "<tr>" +
        '<td><a href="' + esc(r.url) + '">' + esc(r.symbol) + "</a>" +
        '<div class="small muted">' + esc(r.market) + "</div></td>" +
        "<td class='small'>" + esc(r.state_label) +
        '<div class="muted">نقاط ' + num(r.score) +
        " · زخم " + num(r.momentum_score) + "</div></td>" +
        "<td class='small'>" + ago(r.detected_at) +
        '<div class="muted">' + esc((r.candle_time || "").slice(0, 16)
                                    .replace("T", " ")) + "</div></td>" +
        "<td class='text-center'>" +
        (r.max_gain_pct === null ? "—"
          : "<strong>" + num(r.max_gain_pct) + "٪</strong>") +
        (r.hours_to_max !== null
          ? '<div class="small muted">بعد ' + num(r.hours_to_max, 0) +
            " ساعة</div>" : "") + "</td>" +
        "<td class='text-center small' style='color:var(--ds-risk)'>" +
        (r.max_drawdown_pct === null ? "—" : num(r.max_drawdown_pct) + "٪") +
        "</td>" +
        "<td class='text-center small'>" +
        (r.broke_resistance ? "✓" : "—") + "</td>" +
        "<td class='text-center small'>" +
        (r.volatility_expanded ? "✓" : "—") + "</td>" +
        "<td class='small' style='color:" +
        (VERDICT_TONE[r.verdict] || "inherit") + "'>" +
        esc(r.verdict) +
        '<div class="muted">' + r.bars_seen + " شمعة</div></td>" +
        "</tr>";
    }).join("");

    return '<section class="ds-card"><div class="ds-card__body">' +
      '<h2 class="h6">الرصدات</h2>' +
      '<div style="overflow-x:auto">' +
      '<table class="table table-sm align-middle"><thead><tr>' +
      "<th>الرمز</th><th>عند الرصد</th><th>متى</th>" +
      "<th class='text-center'>أقصى ارتفاع</th>" +
      "<th class='text-center'>أقصى تراجع</th>" +
      "<th class='text-center'>اخترق</th>" +
      "<th class='text-center'>تمدّد</th><th>الحكم</th>" +
      "</tr></thead><tbody>" + rows + "</tbody></table></div>" +
      "</div></section>";
  }

  function load() {
    var m = document.getElementById("f-market").value;
    var s = document.getElementById("f-state").value;
    var t = document.getElementById("f-threshold").value;
    body.innerHTML = '<p class="small muted">يحمّل…</p>';
    fetch("/api/pes/history/?market=" + encodeURIComponent(m) +
          "&state=" + encodeURIComponent(s) +
          "&threshold=" + encodeURIComponent(t),
          { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || d.ok === false) {
          body.innerHTML = '<p class="empty">' +
            esc((d && d.reason) || "تعذّر التحميل") + "</p>";
          return;
        }
        body.innerHTML = overall(d) + byState(d) + table(d);
      })
      .catch(function () {
        body.innerHTML = '<p class="empty">تعذّر الاتصال بالخادم</p>';
      });
  }

  ["f-market", "f-state"].forEach(function (id) {
    document.getElementById(id).addEventListener("change", load);
  });
  /* العتبة تُطبَّق عند الإدخال مباشرةً: أثرُها هو الفائدة، وزرُّ
     «اعرض» بينها وبين النتيجة يقتل ذلك. */
  document.getElementById("f-threshold")
    .addEventListener("input", function () {
      clearTimeout(window.__pesHistTimer);
      window.__pesHistTimer = setTimeout(load, 350);
    });

  document.addEventListener("click", function (e) {
    var chip = e.target.closest("[data-threshold]");
    if (!chip) return;
    document.getElementById("f-threshold").value = chip.dataset.threshold;
    load();
  });

  var btn = document.getElementById("refresh");
  if (btn) {
    btn.addEventListener("click", function () {
      btn.disabled = true;
      btn.textContent = "يحسب…";
      /* ‏postJSON لا يرفض أبداً — يعيد {ok:false} عند الفشل.
         فالفحص على ‎d.ok‎ لا على ‎.catch‎، وإلّا بدا الفشل نجاحاً. */
      window.postJSON("/api/pes/history/refresh/", new URLSearchParams({}))
        .then(function (d) {
          btn.disabled = false;
          btn.textContent = "حدّث المسارات";
          if (!d || d.ok === false) {
            body.insertAdjacentHTML("afterbegin",
              '<p class="empty">تعذّر التحديث: ' +
              esc((d && d.reason) || "سبب غير معروف") + "</p>");
            return;
          }
          load();
        });
    });
  }

  load();
})();
