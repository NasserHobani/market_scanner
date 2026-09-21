/* بناء الاستراتيجيات — صفوف شروطٍ تُبنى من سجلّ الحقول.
 *
 * ولا حقل مكتوبٌ هنا: القائمة تأتي من ``custom.FIELDS`` عبر
 * json_script. فإضافة حقلٍ في بايثون تظهر هنا بلا لمس هذا الملفّ —
 * وهو ما يمنع «حقلٌ يُعرَض ولا يُفرَز به».
 */
(function () {
  "use strict";

  function J(id) {
    var el = document.getElementById(id);
    try { return JSON.parse(el.textContent); } catch (e) { return null; }
  }

  var FIELDS = J("field-catalog") || [];
  var OPS = J("op-catalog") || {};
  var BY_KEY = {};
  FIELDS.forEach(function (f) { BY_KEY[f.key] = f; });

  var condsEl = document.getElementById("conds");
  var note = document.getElementById("save-note");
  if (!condsEl) return;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  /* ═══ صفّ شرطٍ واحد ═══
   *
   * الحقل يحدّد العمليات المتاحة، والعملية تحدّد عدد القيم.
   * وبناؤها من البيانات لا بشروط مكتوبة يمنع عرضَ «بين» على
   * حقلٍ نصّيّ — وهو خيارٌ لا معنى له ويُنتج استراتيجية لا تفرز. */
  function condRow(c) {
    c = c || { field: FIELDS[0] && FIELDS[0].key, op: ">=", args: [] };
    var f = BY_KEY[c.field] || FIELDS[0] || {};
    var ops = f.ops || [">="];
    if (ops.indexOf(c.op) < 0) c.op = ops[0];

    var d = document.createElement("div");
    d.className = "cond-row d-flex gap-2 align-items-start flex-wrap mb-2";
    d.style.cssText = "padding:8px;border:1px solid var(--ds-line);" +
      "border-radius:6px;background:var(--ds-surface-2)";

    var fieldSel = '<select class="ds-input c-field" style="min-width:12rem">' +
      FIELDS.map(function (x) {
        return '<option value="' + esc(x.key) + '"' +
          (x.key === c.field ? " selected" : "") + ">" +
          esc(x.label) + "</option>";
      }).join("") + "</select>";

    var opSel = '<select class="ds-input c-op" style="min-width:9rem">' +
      ops.map(function (o) {
        return '<option value="' + esc(o) + '"' +
          (o === c.op ? " selected" : "") + ">" +
          esc((OPS[o] || {}).label || o) + "</option>";
      }).join("") + "</select>";

    d.innerHTML = fieldSel + opSel +
      '<span class="c-args d-flex gap-2"></span>' +
      '<span class="small muted c-unit"></span>' +
      '<button type="button" class="ds-btn ds-btn--sm c-del"' +
      ' style="margin-inline-start:auto">حذف</button>' +
      '<div class="small muted c-help" style="flex-basis:100%"></div>';

    condsEl.appendChild(d);
    renderArgs(d, c);
    return d;
  }

  /* القيم: رقمٌ واحد، أو اثنان لـ«بين»، أو قائمة اختيارٍ للنصّي */
  function renderArgs(row, c) {
    var f = BY_KEY[row.querySelector(".c-field").value] || {};
    var op = row.querySelector(".c-op").value;
    var arity = (OPS[op] || {}).arity;
    var box = row.querySelector(".c-args");
    var args = (c && c.args) || [];
    var html = "";

    if (f.kind === "enum") {
      var multi = arity === "list";
      html = '<select class="ds-input c-arg"' + (multi ? " multiple" : "") +
        ' style="min-width:11rem"' + (multi ? ' size="4"' : "") + ">" +
        (f.choices || []).map(function (ch) {
          var lbl = (f.labels && f.labels[ch]) || ch;
          return '<option value="' + esc(ch) + '"' +
            (args.indexOf(ch) >= 0 ? " selected" : "") + ">" +
            esc(lbl) + "</option>";
        }).join("") + "</select>";
    } else if (f.kind === "bool") {
      html = '<select class="ds-input c-arg" style="min-width:7rem">' +
        '<option value="true"' + (String(args[0]) === "true" ? " selected" : "") +
        ">نعم</option><option value=\"false\"" +
        (String(args[0]) === "false" ? " selected" : "") + ">لا</option></select>";
    } else {
      var n = arity === 2 ? 2 : 1;
      for (var i = 0; i < n; i++) {
        html += '<input type="number" class="ds-input c-arg" ' +
          'style="width:7rem" step="' + (f.step || 1) + '" ' +
          (f.min != null ? 'min="' + f.min + '" ' : "") +
          (f.max != null ? 'max="' + f.max + '" ' : "") +
          'value="' + (args[i] != null ? esc(args[i]) : "") + '">';
      }
    }
    box.innerHTML = html;
    row.querySelector(".c-unit").textContent = f.unit || "";
    row.querySelector(".c-help").textContent = f.help || "";
  }

  function readConds() {
    return Array.prototype.map.call(
      condsEl.querySelectorAll(".cond-row"), function (row) {
        var field = row.querySelector(".c-field").value;
        var op = row.querySelector(".c-op").value;
        var args = [];
        Array.prototype.forEach.call(
          row.querySelectorAll(".c-arg"), function (el) {
            if (el.multiple) {
              Array.prototype.forEach.call(el.selectedOptions, function (o) {
                args.push(o.value);
              });
            } else if (el.value !== "") {
              args.push(el.value);
            }
          });
        return { field: field, op: op, args: args };
      });
  }

  function count() {
    var n = condsEl.querySelectorAll(".cond-row").length;
    document.getElementById("cond-count").textContent =
      n ? n + " شرطاً — كلّها يجب أن تتحقّق" : "بلا شروط";
  }

  condsEl.addEventListener("change", function (e) {
    var row = e.target.closest(".cond-row");
    if (!row) return;
    /* تغيير الحقل قد يُبطل العملية: «بين» لا تنطبق على المرحلة.
       فتُعاد بناء الخيارات بدل تركها تحفظ اختياراً مستحيلاً. */
    if (e.target.classList.contains("c-field")) {
      var f = BY_KEY[e.target.value] || {};
      var opEl = row.querySelector(".c-op");
      var cur = opEl.value;
      opEl.innerHTML = (f.ops || []).map(function (o) {
        return '<option value="' + esc(o) + '"' +
          (o === cur ? " selected" : "") + ">" +
          esc((OPS[o] || {}).label || o) + "</option>";
      }).join("");
    }
    renderArgs(row, null);
  });

  condsEl.addEventListener("click", function (e) {
    if (!e.target.classList.contains("c-del")) return;
    e.target.closest(".cond-row").remove();
    count();
  });

  document.getElementById("add-cond").addEventListener("click", function () {
    condRow(null);
    count();
  });

  // ── الأسواق ──
  var mkBox = document.getElementById("s-markets");
  mkBox.addEventListener("click", function (e) {
    var b = e.target.closest("[data-market]");
    if (b) b.classList.toggle("active");
  });

  function readMarkets() {
    return Array.prototype.map.call(
      mkBox.querySelectorAll("[data-market].active"),
      function (b) { return b.dataset.market; });
  }

  // ── الحفظ ──
  document.getElementById("save").addEventListener("click", function () {
    var body = {
      name: document.getElementById("s-name").value.trim(),
      note: document.getElementById("s-note").value.trim(),
      markets: readMarkets(),
      conditions: readConds(),
      active: true,
    };
    note.textContent = "يحفظ…";
    note.className = "small muted";
    fetch("/api/strategies/save/", {
      method: "POST", credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": (window.csrfToken && window.csrfToken()) || "",
      },
      body: JSON.stringify(body),
    }).then(function (r) { return r.json(); })
      .then(function (d) {
        /* السبب يُعرَض كما جاء من الخادم: «الشرط ٢ يحتاج قيمة»
           أنفع من «تعذّر» — وهي رسالةٌ جاهزة من ``validate``. */
        note.textContent = d.ok ? "حُفظت" : (d.reason || "تعذّر");
        note.className = "small " + (d.ok ? "up" : "down");
        if (d.ok) loadSaved();
      });
  });

  document.getElementById("reset").addEventListener("click", function () {
    document.getElementById("s-name").value = "";
    document.getElementById("s-note").value = "";
    condsEl.innerHTML = "";
    Array.prototype.forEach.call(mkBox.querySelectorAll(".active"),
      function (b) { b.classList.remove("active"); });
    document.getElementById("form-title").textContent = "استراتيجية جديدة";
    note.textContent = "";
    count();
  });

  // ── المحفوظة ──
  function loadSaved() {
    fetch("/api/strategies/", { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var list = d.strategies || [];
        document.getElementById("saved-count").textContent =
          list.length + " / " + d.max;
        document.getElementById("saved").innerHTML = list.length
          ? list.map(function (s) {
              return '<div class="d-flex align-items-center gap-2 mb-2" ' +
                'style="padding:6px;border:1px solid var(--ds-line);' +
                'border-radius:6px">' +
                "<b>" + esc(s.name) + "</b>" +
                '<span class="small muted">' +
                  (s.conditions || []).length + " شرطاً</span>" +
                '<span class="small muted">' +
                  ((s.markets || []).join("، ") || "كل الأسواق") + "</span>" +
                '<button type="button" class="ds-btn ds-btn--sm s-edit" ' +
                  'data-name="' + esc(s.name) + '" ' +
                  'style="margin-inline-start:auto">تحرير</button>' +
                '<button type="button" class="ds-btn ds-btn--sm s-del" ' +
                  'data-name="' + esc(s.name) + '">حذف</button>' +
                "</div>";
            }).join("")
          : '<p class="small muted">لا استراتيجية بعد.</p>';
        window.__saved = list;
      });
  }

  document.getElementById("saved").addEventListener("click", function (e) {
    var name = e.target.dataset && e.target.dataset.name;
    if (!name) return;
    if (e.target.classList.contains("s-del")) {
      window.postJSON("/api/strategies/delete/",
        new URLSearchParams({ name: name })).then(loadSaved);
      return;
    }
    if (e.target.classList.contains("s-edit")) {
      var s = (window.__saved || []).filter(function (x) {
        return x.name === name;
      })[0];
      if (!s) return;
      document.getElementById("s-name").value = s.name;
      document.getElementById("s-note").value = s.note || "";
      condsEl.innerHTML = "";
      (s.conditions || []).forEach(function (c) { condRow(c); });
      Array.prototype.forEach.call(mkBox.querySelectorAll("[data-market]"),
        function (b) {
          b.classList.toggle("active",
            (s.markets || []).indexOf(b.dataset.market) >= 0);
        });
      document.getElementById("form-title").textContent =
        "تحرير: " + s.name;
      count();
    }
  });

  loadSaved();
  count();
})();
