/* شاشة المهامّ المجدولة — عرضٌ وتحكّم.
 *
 * ═══ ما تجيب عنه ═══
 *
 * كانت الحلقات الأربع بلا شاشة: تعرف أنّها تعمل من السجلّات، ولا
 * تعرف متى عملت آخر مرّة ولا لماذا فشلت — الحالة في الذاكرة تُمحى
 * مع كل إعادة تشغيل.
 *
 * والسؤال العملي: «منذ متى وهذا معطّل؟» — فالعمود الأوّل هو الحالة،
 * والثاني آخر تشغيل، والثالث الموعد القادم.
 */
(function () {
  "use strict";

  var shell = document.getElementById("w-jobs");
  if (!shell) return;
  var content = shell.querySelector(".ds-widget__content");
  var timer = null;
  var openRuns = null;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  var TONE = {
    ok: "var(--ds-success)",
    fail: "var(--ds-risk)",
    running: "var(--ds-info)",
    skipped: "var(--ds-warn)",
    never: "var(--ds-text-muted)",
  };
  var LABEL = {
    ok: "نجحت", fail: "فشلت", running: "تعمل الآن",
    skipped: "مؤجَّلة", never: "لم تعمل بعد",
  };

  /* المدّة بوحدةٍ يقرأها الإنسان: «1847ms» تحتاج قسمة ذهنية. */
  function ms(v) {
    if (v === null || v === undefined) return "—";
    if (v < 1000) return v + "ms";
    if (v < 60000) return (v / 1000).toFixed(1) + "ث";
    return Math.round(v / 60000) + "د";
  }

  /* الفارق الزمني نسبيّاً: «قبل 3 د» أوضح من «12:44» — لا يتطلّب
     معرفة الساعة الحالية ولا المنطقة الزمنية. */
  function ago(iso) {
    if (!iso) return "—";
    var s = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 0) return "الآن";
    if (s < 60) return "قبل " + s + "ث";
    if (s < 3600) return "قبل " + Math.round(s / 60) + "د";
    if (s < 86400) return "قبل " + Math.round(s / 3600) + "س";
    return "قبل " + Math.round(s / 86400) + "ي";
  }

  function dueText(job) {
    if (!job.active) return '<span class="muted">موقوفة</span>';
    var s = job.due_in;
    if (s === null || s === undefined) return "—";
    /* السالب حالةٌ لا تاريخ: «مستحقّة» تعني أنّ النبضة القادمة
       ستلتقطها، و«قبل 3 دقائق» تُقرأ خطأً على أنّها فاتت. */
    if (s <= 0) return '<span style="color:var(--ds-info)">مستحقّة</span>';
    if (s < 60) return "بعد " + s + "ث";
    if (s < 3600) return "بعد " + Math.round(s / 60) + "د";
    return "بعد " + Math.round(s / 3600) + "س";
  }

  function row(j) {
    var tone = TONE[j.last_status] || TONE.never;
    return '<tr data-id="' + j.id + '">' +
      '<td><span style="color:' + tone + ';font-weight:600">●</span> ' +
        esc(LABEL[j.last_status] || j.last_status) + "</td>" +
      "<td><b>" + esc(j.name) + "</b>" +
        '<div class="small muted">' + esc(j.code) + "</div></td>" +
      '<td class="small">' + esc(j.handler_label) + "</td>" +
      /* الفترة قابلة للتحرير في مكانها: فتح نافذة لتغيير رقمٍ
         واحد يجعل المستخدم يؤجّل التغيير. */
      "<td>" +
        '<input type="number" min="1" class="ds-input job-num" ' +
        'value="' + j.interval_number + '" style="width:4.5rem">' +
        '<select class="ds-input job-unit" style="width:6rem">' +
        ["minutes", "hours", "days"].map(function (u) {
          var lbl = { minutes: "دقيقة", hours: "ساعة", days: "يوم" }[u];
          return '<option value="' + u + '"' +
            (u === j.interval_type ? " selected" : "") + ">" + lbl + "</option>";
        }).join("") + "</select>" +
      "</td>" +
      /* السطران كانا يُقرآن رقماً واحداً: «قبل 6د 27.4ث».
         والثاني مدّة التنفيذ لا جزءٌ من الأوّل. */
      '<td class="small">' + ago(j.last_run_at) +
        '<div class="muted">استغرقت ' + ms(j.last_duration_ms) +
        "</div></td>" +
      '<td class="small">' + dueText(j) + "</td>" +
      '<td class="small" style="max-width:16rem">' +
        (j.last_message
          ? '<span style="color:' + (j.last_status === "fail"
              ? "var(--ds-risk)" : "var(--ds-text-muted)") + '">' +
            esc(j.last_message) + "</span>"
          : '<span class="muted">—</span>') + "</td>" +
      '<td class="small num">' + j.run_count +
        (j.fail_count
          ? ' <span style="color:var(--ds-risk)">(' + j.fail_count + ")</span>"
          : "") + "</td>" +
      '<td style="white-space:nowrap">' +
        '<button type="button" class="ds-btn ds-btn--sm job-run">شغّل</button> ' +
        '<button type="button" class="ds-btn ds-btn--sm job-toggle">' +
          (j.active ? "أوقف" : "فعّل") + "</button> " +
        '<button type="button" class="ds-btn ds-btn--sm job-save">احفظ</button> ' +
        '<button type="button" class="ds-btn ds-btn--sm job-runs">السجلّ</button>' +
      "</td></tr>";
  }

  function render(d) {
    if (!d.jobs || !d.jobs.length) {
      content.innerHTML = DS.EmptyState({
        icon: "◷",
        title: "لا مهامّ مجدولة",
        text: "اضغط «أنشئ الناقصة» لبذر المهامّ الافتراضية.",
        inline: true,
      });
      return;
    }
    content.innerHTML =
      '<div class="table-responsive"><table class="table table-sm ' +
      'align-middle mb-0"><thead><tr>' +
      "<th>الحالة</th><th>المهمّة</th><th>النوع</th><th>كل</th>" +
      "<th>آخر تشغيل</th><th>القادم</th><th>الرسالة</th>" +
      "<th>مرّات</th><th></th>" +
      "</tr></thead><tbody>" + d.jobs.map(row).join("") + "</tbody></table></div>";

    var eng = document.getElementById("engine-state");
    if (eng) {
      /* حالة المحرّك نفسه: نبضةٌ توقّفت تعني أنّ كل شيء متوقّف،
         وهو ما لا يظهر من صفوف المهامّ — تبدو كلّها «مستحقّة». */
      var e = d.engine || {};
      eng.textContent = e.thread_started
        ? "المحرّك يعمل · نبضة كل " + d.tick_seconds + "ث · " +
          (e.ticks || 0) + " نبضة"
        : "المحرّك متوقّف";
      eng.style.color = e.thread_started
        ? "var(--ds-text-muted)" : "var(--ds-risk)";
    }
    shell.setAttribute("data-state", "ready");
  }

  function load() {
    return fetch("/api/jobs/", { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) {
          shell.setAttribute("data-state", "error");
          var box = shell.querySelector(".ds-widget__error");
          if (box) { box.hidden = false; box.textContent = d.reason || "تعذّر"; }
          return;
        }
        render(d);
        if (openRuns) showRuns(openRuns.id, openRuns.name);
      })
      .catch(function () {
        shell.setAttribute("data-state", "error");
        var box = shell.querySelector(".ds-widget__error");
        if (box) { box.hidden = false; box.textContent = "تعذّر تحميل المهامّ."; }
      });
  }

  function post(url, body) {
    return window.postJSON(url, body || new URLSearchParams())
      .then(function () { return load(); });
  }

  function showRuns(id, name) {
    openRuns = { id: id, name: name };
    var card = document.getElementById("runs-card");
    var body = document.getElementById("runs-body");
    document.getElementById("runs-title").textContent = "سجلّ التشغيل — " + name;
    card.hidden = false;
    fetch("/api/jobs/" + id + "/runs/?limit=30", { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.runs || !d.runs.length) {
          body.innerHTML = '<p class="small muted p-3">لم تعمل بعد.</p>';
          return;
        }
        body.innerHTML =
          '<table class="table table-sm mb-0"><thead><tr>' +
          "<th>الوقت</th><th>الحالة</th><th>المدّة</th><th>الرسالة</th>" +
          "<th>المصدر</th></tr></thead><tbody>" +
          d.runs.map(function (r) {
            return "<tr>" +
              '<td class="small muted">' +
                esc(String(r.started_at).replace("T", " ").slice(0, 19)) +
                "</td>" +
              '<td class="small"><span style="color:' +
                (TONE[r.status] || TONE.never) + '">●</span> ' +
                esc(LABEL[r.status] || r.status) + "</td>" +
              '<td class="small num">' + ms(r.duration_ms) + "</td>" +
              '<td class="small">' + esc(r.message || "—") + "</td>" +
              '<td class="small muted">' +
                (r.manual ? "يدويّ" : "مجدول") + "</td></tr>";
          }).join("") + "</tbody></table>";
      });
  }

  content.addEventListener("click", function (e) {
    var tr = e.target.closest("tr[data-id]");
    if (!tr) return;
    var id = tr.getAttribute("data-id");
    var name = tr.querySelector("b") ? tr.querySelector("b").textContent : "";

    if (e.target.closest(".job-run")) {
      e.target.disabled = true;
      post("/api/jobs/" + id + "/run/");
    } else if (e.target.closest(".job-toggle")) {
      post("/api/jobs/" + id + "/toggle/");
    } else if (e.target.closest(".job-save")) {
      var num = tr.querySelector(".job-num").value;
      var unit = tr.querySelector(".job-unit").value;
      post("/api/jobs/" + id + "/save/", new URLSearchParams({
        interval_number: num, interval_type: unit,
      }));
    } else if (e.target.closest(".job-runs")) {
      showRuns(id, name);
    }
  });

  document.getElementById("refresh").addEventListener("click", load);
  document.getElementById("seed").addEventListener("click", function () {
    post("/api/jobs/seed/");
  });
  document.getElementById("runs-close").addEventListener("click", function () {
    openRuns = null;
    document.getElementById("runs-card").hidden = true;
  });

  load();
  /* التحديث الدوري: الصفحة تراقب ما يتغيّر بلا فعل من المستخدم،
     فبقاؤها ساكنة يجعلها تكذب بعد دقيقة. */
  timer = setInterval(load, 10000);
  window.addEventListener("beforeunload", function () {
    if (timer) clearInterval(timer);
  });
})();
