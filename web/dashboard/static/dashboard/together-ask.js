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
    if (v === null || v === undefined || v !== v) return "—";
    return "$" + Number(v).toFixed(4);
  }

  /* ═══ الشارة لا تمتلئ بشَرَطات ═══
   *
   * «اليوم — من — · الشهر —» لا تقول شيئاً، وتُقرأ عطباً في كل
   * شيء. فإن غاب الإنفاق يُقال السبب بدل عرض فراغٍ بشكل رقم. */
  function budgetText(d) {
    var s = d.spend || {};
    var lim = s.limits || {};
    if (s.today_usd === undefined || lim.daily_usd === undefined) {
      return '<span class="ds-value-warn">تعذّرت قراءة الإنفاق' +
        (s.error ? ": " + esc(s.error) : "") + "</span>";
    }
    return "اليوم " + usd(s.today_usd) + " من " + usd(lim.daily_usd) +
      " · الشهر " + usd(s.month_usd) + " من " + usd(lim.monthly_usd) +
      ' <span class="ds-text-muted">· ' + esc(d.model || "") + "</span>";
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
      .then(function (r) {
        /* انتهت الجلسة: الوسيط يردّ ‎401‎ لا صفحة دخول */
        if (r.status === 401) { window.location = "/accounts/login/"; return null; }
        return r.json();
      })
      .then(function (d) {
        if (!d) return;
        if (!d.configured || d.enabled === false) {
          badge.textContent = d.why || "غير مضبوط";
          badge.className = "ds-text-xs ds-value-warn tg-budget";
          return;
        }
        btn.disabled = false;
        badge.innerHTML = budgetText(d);
      })
      .catch(function (e) {
        badge.textContent = "تعذّر فحص الحال: " + String(e).slice(0, 60);
      });

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
        // الموضوع يُرشَّح به الأرشيف — ولولاه لاختلطت الرموز
        subject: String(opts.subject || ""),
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

  var idleHits = 0;

  function poll(key, btn, out, badge) {
    fetch("/api/ai/together/status/?key=" + encodeURIComponent(key),
          { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.ok) return;
        if (d.state === "running") {
          idleHits = 0;
          out.innerHTML = '<span class="ds-text-muted small">يعمل… ' +
            (d.elapsed || 0) + " ث</span>";
          return;
        }
        /* ═══ ‎idle‎ ليست نجاحاً ═══
         *
         * كانت تمرّ إلى فرع «تمّ» فتُرسَم نتيجةٌ فارغة:
         * «كلّف — · 0 داخل · 0 خارج». فيبدو النداء ناجحاً ولم
         * يُنتج شيئاً — وهو أسوأ من خطأٍ صريح.
         *
         * ومهلةٌ قصيرة قبل الحكم: الكتابة على القرص قد تتأخّر
         * لحظةً بعد البدء. */
        if (d.state === "idle") {
          idleHits += 1;
          if (idleHits < 4) {
            out.innerHTML =
              '<span class="ds-text-muted small">ينتظر البدء…</span>';
            return;
          }
          clearInterval(timer); timer = null;
          btn.disabled = false;
          out.innerHTML = '<p class="small down">ضاع أثر الطلب — ' +
            "لم تُعثَر حالته. أعد المحاولة، وإن تكرّر فالسبب في " +
            "السجلّ: <code dir='ltr'>docker logs &lt;web&gt;</code></p>";
          return;
        }
        clearInterval(timer); timer = null;
        btn.disabled = false;

        badge.innerHTML = budgetText({ spend: d.spend, model: "" });

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
        out.innerHTML =
          renderAnswer(r.text || "") +
          '<p class="ds-text-xs ds-text-muted mt-2">' +
          "كلّف " + usd(u.cost) + " · " + (u.tokens_in || 0) + " داخل · " +
          (u.tokens_out || 0) + " خارج · " + (r.latency_ms || 0) + " م.ث" +
          (r.archive_id ? " · محفوظة" : "") +
          "</p>" +
          '<p class="ds-text-xs ds-text-muted">قراءةٌ لغوية لأرقامٍ ' +
          "محسوبة. وإن تعارضت مع الأرقام فالأرقام هي الحقيقة.</p>";
        if (window.__tgReload) window.__tgReload();
      })
      .catch(function () {});
  }

  /* ═══════════════════════════════════════════════════════════
   *  عرض الإجابة
   * ═══════════════════════════════════════════════════════════
   *
   * كان: ``JSON.stringify(JSON.parse(text), null, 2)`` — فيُعاد
   * تهريب النصّ، فتظهر ‎\n‎ و‎\"‎ حروفاً على الشاشة. وهو ما رآه
   * المستخدم: فقرةٌ متلاصقة فيها ``•n\.`` و``\"الدرجة\"``.
   *
   * والعلاج ليس تجميلاً: القيمة تُقرأ **بعد** التحليل وتُرسَم
   * أقساماً — عنواناً ونصّاً أو قائمة.
   */

  var TONE = {
    "يدعم": "success", "يضعف": "risk",
    "ما_لا_نعرفه": "warn", "الخلاصة": "",
  };

  function humanize(k) {
    return String(k).replace(/_/g, " ");
  }

  /* نصٌّ قد يحمل أسطراً أو نقاطاً — يصير فقراتٍ أو قائمة */
  function textBlock(s) {
    var parts = String(s)
      .split(/\r?\n+|(?:^|\s)[•·\-−]\s+/)
      .map(function (x) { return x.trim(); })
      .filter(Boolean);
    if (parts.length <= 1) {
      return '<p class="mb-1">' + esc(parts[0] || s) + "</p>";
    }
    return '<ul class="mb-1" style="padding-inline-start:1.1rem">' +
      parts.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") +
      "</ul>";
  }

  function valueBlock(v) {
    if (Array.isArray(v)) {
      if (!v.length) return '<p class="ds-text-muted mb-1">—</p>';
      return '<ul class="mb-1" style="padding-inline-start:1.1rem">' +
        v.map(function (x) {
          return "<li>" + (typeof x === "object"
            ? esc(JSON.stringify(x)) : esc(x)) + "</li>";
        }).join("") + "</ul>";
    }
    if (v && typeof v === "object") {
      return Object.keys(v).map(function (k) {
        return '<div class="mb-1"><span class="ds-text-xs ds-text-muted">' +
          esc(humanize(k)) + ":</span> " + esc(String(v[k])) + "</div>";
      }).join("");
    }
    return textBlock(v);
  }

  function section(key, value) {
    var tone = TONE[key] === undefined ? "" : TONE[key];
    return '<section class="mb-3">' +
      '<h4 class="h6 mb-1' + (tone ? " ds-value-" + tone : "") + '">' +
      esc(humanize(key)) + "</h4>" +
      '<div class="small">' + valueBlock(value) + "</div></section>";
  }

  function renderAnswer(text) {
    var data = null;
    try { data = JSON.parse(text); } catch (e) { data = null; }

    /* ═══ والنصّ لا يُرمى إن لم يكن JSON ═══
     *
     * ردٌّ غير متوافق مع المخطَّط كلّفك مالاً فعلاً. فيُعرَض
     * نصّاً مقروءاً — لا يُخفى ولا يُعرَض خاماً بين أقواس. */
    if (!data || typeof data !== "object") {
      return '<div class="small">' + textBlock(text) + "</div>" +
        '<p class="ds-text-xs ds-value-warn">لم يلتزم النموذج ' +
        "بالمخطَّط — عُرض نصّه كما ورد.</p>";
    }

    /* الترتيب مقصود: الخلاصة أوّلاً، ثمّ ما يضعف قبل ما يدعم —
       فالانحياز الطبيعيّ نحو التأكيد، وما يُقرأ أوّلاً يُوزن أكثر. */
    var ORDER = ["الخلاصة", "يضعف", "يدعم", "ما_لا_نعرفه"];
    var seen = {};
    var html = "";
    ORDER.forEach(function (k) {
      if (data[k] !== undefined) { html += section(k, data[k]); seen[k] = 1; }
    });
    Object.keys(data).forEach(function (k) {
      if (!seen[k]) html += section(k, data[k]);
    });
    return '<div style="background:var(--ds-surface-2);padding:12px 14px;' +
      'border-radius:8px">' + html + "</div>";
  }

  /* ═══════════════════════════════════════════════════════════
   *  الإجابات المحفوظة
   * ═══════════════════════════════════════════════════════════ */

  function mountHistory(host, subject) {
    if (!host) return;
    function load() {
      fetch("/api/ai/together/history/?subject=" +
            encodeURIComponent(subject), { credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          var list = (d && d.answers) || [];
          if (!list.length) {
            host.innerHTML = '<p class="ds-text-xs ds-text-muted">' +
              "لا إجابة محفوظة لهذا الرمز بعد.</p>";
            return;
          }
          host.innerHTML = list.map(function (a) {
            return '<div class="d-flex align-items-center gap-2 py-1 ' +
              'tg-hist-row" style="cursor:pointer" data-id="' +
              esc(a.id) + '">' +
              '<span class="ds-text-xs ds-text-muted" dir="ltr">' +
              esc(String(a.at).replace("T", " ").slice(0, 16)) + "</span>" +
              '<span class="ds-text-xs">' + usd(a.cost) + "</span>" +
              '<span class="ds-text-xs ds-text-muted">' +
              esc(a.model || "") + "</span>" +
              '<span class="ds-btn ds-btn--sm" style="margin-inline-start:auto"' +
              ">اعرض</span></div>" +
              '<div class="tg-hist-body" data-for="' + esc(a.id) +
              '" hidden></div>';
          }).join("");
        })
        .catch(function () {});
    }
    window.__tgReload = load;
    load();

    host.addEventListener("click", function (e) {
      var row = e.target.closest(".tg-hist-row");
      if (!row) return;
      var id = row.dataset.id;
      var body = host.querySelector('[data-for="' + CSS.escape(id) + '"]');
      if (!body) return;
      if (!body.hidden) { body.hidden = true; return; }
      body.hidden = false;
      body.innerHTML = '<span class="ds-text-muted small">يحمّل…</span>';
      fetch("/api/ai/together/history/?id=" + encodeURIComponent(id),
            { credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d || !d.ok) {
            body.innerHTML = '<p class="small down">تعذّر</p>';
            return;
          }
          body.innerHTML = renderAnswer(d.answer.answer || "");
        })
        .catch(function () {
          body.innerHTML = '<p class="small down">تعذّر</p>';
        });
    });
  }

  window.TogetherAsk = { mount: mount, mountHistory: mountHistory,
                         renderAnswer: renderAnswer };
})();
