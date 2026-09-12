/* لوحة المحادثة الحيّة مع المستشار — على كل الشاشات.
 *
 * ═══ لماذا ═══
 *
 * المراجعة تستغرق 116 ثانية بالوسيط، وكان المستخدم يرى شريط انتظار
 * أعمى ثم صندوقاً أسود: حكماً بلا معرفة ما بُني عليه. وهذا يناقض
 * مشروعاً كل شيء فيه قابل للقياس.
 *
 * ═══ سلوكها ═══
 *
 * تظهر **تلقائياً** حين تبدأ محادثة، وتُطوى بنقرة، ولا تستعلم إلا
 * حين تكون مفتوحة أو حين تكون هناك محادثة جارية — فلا تستهلك شيئاً
 * في الصفحات الساكنة.
 */
(function () {
  "use strict";

  var IDLE_MS = 6000;      // لا محادثة: نسأل بتباعد
  var LIVE_MS = 1200;      // محادثة جارية: نسأل بسرعة الكتابة

  var root = document.getElementById("ai-live");
  if (!root) return;

  var body = root.querySelector("[data-live-body]");
  var head = root.querySelector("[data-live-head]");
  var dot = root.querySelector("[data-live-dot]");
  var title = root.querySelector("[data-live-title]");
  var stagesEl = root.querySelector("[data-live-stages]");
  var promptEl = root.querySelector("[data-live-prompt]");
  var answerEl = root.querySelector("[data-live-answer]");
  var metaEl = root.querySelector("[data-live-meta]");

  var open = false;
  var timer = null;
  var currentId = null;
  var received = 0;          // محارف الإجابة التي وصلتنا
  var userScrolled = false;

  function setOpen(v) {
    open = v;
    root.classList.toggle("is-open", v);
    if (body) body.classList.toggle("d-none", !v);
    schedule();
  }

  if (head) head.addEventListener("click", function () { setOpen(!open); });

  /* المستخدم الذي مرّر لأعلى يقرأ شيئاً — لا نسحبه إلى الأسفل مع كل
     جزء يصل. وهذا فرق بين متابعة مريحة ومطاردة نصّ. */
  if (answerEl) {
    answerEl.addEventListener("scroll", function () {
      var atEnd = answerEl.scrollHeight - answerEl.scrollTop
        - answerEl.clientHeight < 24;
      userScrolled = !atEnd;
    });
  }

  function stateLabel(s) {
    return s === "sending" ? "يُرسل الموجّه…"
      : s === "streaming" ? "يكتب الإجابة…"
        : s === "done" ? "اكتملت" : s === "failed" ? "فشلت" : "";
  }

  function paint(d) {
    var cur = d.current;
    if (!cur) {
      if (dot) dot.style.background = "var(--dim)";
      if (title) {
        var last = (d.recent || [])[0];
        title.textContent = last
          ? "آخر محادثة: " + (last.symbol || "—") + " · " +
            stateLabel(last.state)
          : "لا محادثة جارية";
      }
      return;
    }

    // محادثة جديدة: نصفّر ما جمّعناه بدل لصق إجابتين
    if (cur.id !== currentId) {
      currentId = cur.id;
      received = 0;
      if (answerEl) answerEl.textContent = "";
      if (promptEl) {
        promptEl.textContent =
          "── تعليمات النظام ──\n" + (cur.system || "") +
          "\n\n── المعطيات ──\n" + (cur.user || "");
      }
      if (!open) setOpen(true);        // تظهر وحدها عند بدء محادثة
    }

    if (dot) {
      dot.style.background = cur.state === "failed" ? "var(--down)"
        : cur.state === "done" ? "var(--up)" : "var(--warn, #e0b341)";
    }
    if (title) {
      title.textContent = (cur.symbol || "—") +
        (cur.timeframe ? " · " + cur.timeframe : "") + " — " +
        stateLabel(cur.state) + " · " + (cur.elapsed || 0) + "ث";
    }
    if (stagesEl) {
      stagesEl.innerHTML = (cur.stages || []).map(function (s) {
        return '<span class="badge text-bg-secondary me-1">' +
          s.name + " <span class=\"muted\">" + s.at + "ث</span></span>";
      }).join("");
    }
    if (metaEl) {
      metaEl.textContent = [cur.provider, cur.model,
                            (cur.answer_len || 0) + " محرفاً"]
        .filter(Boolean).join(" · ");
    }

    if (answerEl && cur.answer) {
      // الخادم يرسل الجديد فقط حين يطابق ما لدينا — وإلا يرسل الكامل
      if ((cur.answer_from || 0) === 0) answerEl.textContent = "";
      answerEl.textContent += cur.answer;
      received = cur.answer_len || answerEl.textContent.length;
      if (!userScrolled) answerEl.scrollTop = answerEl.scrollHeight;
    }

    if (cur.state === "failed" && cur.error && answerEl) {
      answerEl.textContent += "\n\n⚠ " + cur.error;
    }
  }

  function poll() {
    var url = "/api/ai/live/" + (received ? "?since=" + received : "");
    fetch(url)
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.ok) return;
        paint(d);
        schedule(d.active);
      })
      .catch(function () { schedule(false); });
  }

  function schedule(active) {
    clearTimeout(timer);
    // مغلقة وبلا محادثة: استعلام متباعد يكفي لالتقاط البداية
    var wait = active ? LIVE_MS : IDLE_MS;
    timer = setTimeout(poll, wait);
  }

  poll();
})();
