/* تشريح الصفقات المحسومة — الأرقام أولاً، والتفسير بطلب.
 *
 * ═══ لماذا زرّان لا زرّ واحد ═══
 *
 * القياس أجزاء من الثانية، ونداء النموذج المحلّي بلغ 116 ثانية وسيطاً.
 * فدمجهما يعني صفحة معلَّقة دقيقتين — وهو العطب الذي أصاب صفحة
 * البتكوين قبلُ وعولج بنمط المهمّة الخلفية نفسه المستعمل هنا.
 *
 * والزرّ يبقى معطّلاً حين لا يوجد فرق ثابت: زرٌّ يدعوك لطلب تفسير
 * لشيء لم يثبت هو إغراء بالسرد، وأخطر من غياب الميزة.
 */
(function () {
  "use strict";

  var reportEl = document.getElementById("pm-report");
  if (!reportEl) return;

  var btn = document.getElementById("pm-ai-btn");
  var stateEl = document.getElementById("pm-ai-state");
  var scopeEl = document.getElementById("pm-scope");
  var outEl = document.getElementById("pm-ai");
  var pollTimer = null;

  function qs() {
    var p = new URLSearchParams(window.location.search);
    var keep = ["market", "tf", "source"];
    var out = [];
    keep.forEach(function (k) {
      if (p.get(k)) out.push(k + "=" + encodeURIComponent(p.get(k)));
    });
    return out.length ? "?" + out.join("&") : "";
  }

  function loadReport() {
    return fetch("/api/postmortem/" + qs())
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.ok) {
          reportEl.textContent = (d && d.error) || "تعذّر القياس";
          return;
        }
        reportEl.textContent = d.text || "—";
        var rep = d.report || {};
        if (scopeEl) {
          scopeEl.textContent = rep.n_total + " صفقة محسومة · "
            + Math.round((rep.baseline_win_rate || 0) * 100) + "٪ نجاح";
        }
        if (btn) {
          btn.disabled = !d.explainable;
          btn.title = d.explainable
            ? "يفسّر الفروق الثابتة — قد يستغرق دقيقتين"
            : "لا فرق يتجاوز الضجيج — لا شيء يُفسَّر";
        }
      })
      .catch(function () { reportEl.textContent = "تعذّر الاتصال"; });
  }

  function renderAnalysis(res) {
    if (!outEl) return;
    if (!res) { outEl.innerHTML = ""; return; }
    if (res.skipped) {
      outEl.innerHTML = '<div class="small muted">' + esc(res.reason) + "</div>";
      return;
    }
    var a = res.analysis || {};
    var html = '<div class="card"><div class="card-body">';
    html += '<div class="small muted mb-2">' + esc(res.provider || "")
          + " · " + esc(res.model || "") + "</div>";
    if (a.verdict) html += "<div class='fw-semibold mb-2'>" + esc(a.verdict) + "</div>";
    if (a.summary) html += "<p class='mb-3'>" + esc(a.summary) + "</p>";

    html += drivers("أسباب النجاح", a.success_drivers, "up");
    html += drivers("أسباب الفشل", a.failure_drivers, "down");
    html += list("تفسيرات متنافسة", a.competing_explanations);
    html += experiments(a.suggested_experiments);
    html += list("ما لا يجوز استنتاجه", a.what_not_to_conclude);

    /* المخالفات تُعرَض لا تُخفى: النموذج حاول إسناد سبب لعامل لم يثبت،
       والخادم حذفه. وإظهار ذلك يبني ثقتك في الحاجز بدل أن تظنّه لم
       يعمل. */
    if (a.grounding_violations && a.grounding_violations.length) {
      html += '<div class="small mt-3" style="color:var(--warn)">⚠ حُذفت '
        + a.grounding_violations.length
        + " نسبة سبب إلى عامل لم يجتز الدلالة.</div>";
    }
    html += "</div></div>";
    outEl.innerHTML = html;
  }

  function drivers(title, items, tone) {
    if (!items || !items.length) return "";
    var h = '<div class="mb-3"><div class="small muted mb-1">' + title + "</div><ul class='mb-0'>";
    items.forEach(function (it) {
      h += "<li><span class='" + tone + "'>" + esc(it.factor || "") + "</span>"
        + (it.mechanism ? " — " + esc(it.mechanism) : "")
        + (it.confidence != null ? " <span class='muted small'>(ثقة "
            + esc(String(it.confidence)) + ")</span>" : "")
        + "</li>";
    });
    return h + "</ul></div>";
  }

  function list(title, items) {
    if (!items || !items.length) return "";
    var h = '<div class="mb-3"><div class="small muted mb-1">' + title + "</div><ul class='mb-0'>";
    items.forEach(function (x) { h += "<li>" + esc(String(x)) + "</li>"; });
    return h + "</ul></div>";
  }

  function experiments(items) {
    if (!items || !items.length) return "";
    var h = '<div class="mb-3"><div class="small muted mb-1">تجارب تحسم المرشَّحين</div><ul class="mb-0">';
    items.forEach(function (e) {
      h += "<li><strong>" + esc(e.hypothesis || "") + "</strong>"
        + (e.method ? " — " + esc(e.method) : "")
        + (e.expected_outcome ? " <span class='muted'>← " + esc(e.expected_outcome) + "</span>" : "")
        + "</li>";
    });
    return h + "</ul></div>";
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function poll() {
    fetch("/api/postmortem/ai/status/")
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.ok) return;
        if (d.state === "running") {
          if (stateEl) stateEl.textContent = "يحلّل… " + (d.elapsed || 0) + " ث";
          return;
        }
        clearInterval(pollTimer); pollTimer = null;
        if (btn) { btn.disabled = false; btn.textContent = "حلّل بالذكاء"; }
        if (d.state === "failed") {
          if (stateEl) {
            stateEl.textContent = "تعذّر: " + (d.error || "");
            stateEl.style.color = "var(--down)";
          }
          return;
        }
        if (stateEl) {
          stateEl.textContent = "اكتمل في " + (d.elapsed || 0) + " ث";
          stateEl.style.color = "";
        }
        renderAnalysis(d.result);
      })
      .catch(function () {});
  }

  if (btn) {
    btn.addEventListener("click", function () {
      btn.disabled = true;
      btn.textContent = "يحلّل…";
      if (stateEl) { stateEl.textContent = "يبدأ…"; stateEl.style.color = ""; }
      if (outEl) outEl.innerHTML = "";
      var body = new URLSearchParams(qs().replace(/^\?/, ""));
      window.postJSON("/api/postmortem/ai/", body).then(function (d) {
        if (d && d.reason && stateEl) stateEl.textContent = d.reason;
        clearInterval(pollTimer);
        pollTimer = setInterval(poll, 2000);
      });
    });
  }

  loadReport();
})();
