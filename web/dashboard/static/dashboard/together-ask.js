/* نداء Together — والثمن يُرى قبل الضغط وبعده.
 *
 * ═══ لماذا التكلفة في الواجهة ═══
 *
 * «عند الطلب فقط» شرطٌ عن المال. ومن لا يرى ما أنفقه لا يعرف
 * متى تجاوز — حتى تصل الفاتورة. فالمتبقّي من السقف معروضٌ على
 * الزرّ نفسه، والتقدير يظهر لحظة الضغط، والفعليّ بعد الردّ.
 *
 * ═══ ويُركَّب حيث يُحتاج ═══
 *
 * ‏``TogetherAsk.mount(host, {purpose, payload})`` — والحمولة
 * دالّةٌ تُنادى **عند الضغط** لا عند التركيب: فتحمل ما يراه
 * المستخدم في تلك اللحظة لا ما كان عند فتح الصفحة.
 */
(function () {
  "use strict";

  var timer = null;

  function esc(s) { return DS.esc(String(s == null ? "" : s)); }

  function usd(v) {
    if (v === null || v === undefined) return "—";
    return "$" + Number(v).toFixed(4);
  }

  function mount(host, opts) {
    if (!host) return;
    opts = opts || {};
    host.innerHTML =
      '<div class="d-flex align-items-center gap-2 flex-wrap">' +
      '<button type="button" class="ds-btn ds-btn--sm tg-ask" disabled>' +
      "اسأل gpt-oss-120b</button>" +
      '<span class="ds-text-xs ds-text-muted tg-budget">يفحص…</span>' +
      "</div>" +
      '<div class="tg-out mt-2"></div>';

    var btn = host.querySelector(".tg-ask");
    var badge = host.querySelector(".tg-budget");
    var out = host.querySelector(".tg-out");

    /* الحال يُقرأ بلا نداءٍ مدفوع */
    fetch("/api/ai/together/", { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.configured) {
          badge.textContent = d.why || "غير مضبوط";
          badge.className = "ds-text-xs ds-value-warn tg-budget";
          return;
        }
        var s = d.spend || {};
        btn.disabled = false;
        badge.innerHTML = "اليوم " + usd(s.today_usd) + " من " +
          usd((s.limits || {}).daily_usd) +
          " · الشهر " + usd(s.month_usd) + " من " +
          usd((s.limits || {}).monthly_usd) +
          ' <span class="ds-text-muted">· ' + esc(d.model) + "</span>";
      })
      .catch(function () { badge.textContent = "تعذّر فحص الحال"; });

    btn.addEventListener("click", function () {
      var payload = typeof opts.payload === "function"
        ? opts.payload() : String(opts.payload || "");
      if (!payload) { badge.textContent = "لا بيانات لإرسالها"; return; }

      btn.disabled = true;
      out.innerHTML = '<span class="ds-text-muted small">يبدأ…</span>';
      var body = new URLSearchParams({
        purpose: opts.purpose || "symbol",
        payload: payload,
        max: String(opts.max || 1200),
      });

      window.postJSON("/api/ai/together/ask/", body)
        .then(function (d) {
          if (!d || !d.ok) {
            btn.disabled = false;
            out.innerHTML = '<p class="small down">' +
              esc((d && d.reason) || "تعذّر") + "</p>";
            return;
          }
          /* التقدير قبل النتيجة: الثمن يُرى لا يُفاجئ */
          out.innerHTML = '<span class="ds-text-muted small">يعمل… ' +
            "التقدير " + usd(d.estimate_usd) + "</span>";
          clearInterval(timer);
          timer = setInterval(function () { poll(d.key, btn, out, badge); },
                              2000);
        })
        .catch(function (e) {
          btn.disabled = false;
          out.innerHTML = '<p class="small down">' +
            esc(String(e).slice(0, 140)) + "</p>";
        });
    });
  }

  function poll(key, btn, out, badge) {
    fetch("/api/ai/together/status/?key=" + encodeURIComponent(key),
          { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.ok) return;
        if (d.state === "running") {
          out.innerHTML = '<span class="ds-text-muted small">يعمل… ' +
            (d.elapsed || 0) + " ث</span>";
          return;
        }
        clearInterval(timer); timer = null;
        btn.disabled = false;

        var s = d.spend || {};
        badge.innerHTML = "اليوم " + usd(s.today_usd) + " من " +
          usd((s.limits || {}).daily_usd) +
          " · الشهر " + usd(s.month_usd);

        if (d.state === "budget") {
          /* تجاوزُ السقف ليس عطباً — هو الحارس يعمل */
          out.innerHTML = '<div class="ds-insight ds-insight--warn">' +
            '<div class="ds-insight__body"><p class="ds-insight__title">' +
            "بلغتَ السقف</p><p class='ds-insight__text'>" +
            esc(d.error) + "</p></div></div>";
          return;
        }
        if (d.state === "failed") {
          out.innerHTML = '<p class="small down">' + esc(d.error) + "</p>";
          return;
        }

        var r = d.result || {};
        var u = r.usage || {};
        var text = r.text || "";
        var body;
        try {
          body = JSON.stringify(JSON.parse(text), null, 2);
        } catch (e) { body = text; }

        out.innerHTML =
          '<pre class="small" style="white-space:pre-wrap;' +
          'background:var(--ds-surface-2);padding:10px;border-radius:6px;' +
          'max-height:26rem;overflow:auto">' + esc(body) + "</pre>" +
          '<p class="ds-text-xs ds-text-muted">' +
          "كلّف " + usd(u.cost) + " · " + (u.tokens_in || 0) + " داخل · " +
          (u.tokens_out || 0) + " خارج · " + (r.latency_ms || 0) + " م.ث" +
          "</p>" +
          '<p class="ds-text-xs ds-text-muted">قراءةٌ لغوية لأرقامٍ ' +
          "محسوبة. وإن تعارضت مع الأرقام فالأرقام هي الحقيقة.</p>";
      })
      .catch(function () {});
  }

  window.TogetherAsk = { mount: mount };
})();
