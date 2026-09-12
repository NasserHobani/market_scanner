/* الاستشارة بالأدلّة — «لماذا خسرت؟» و«هل أدخل؟».
 *
 * ═══ لماذا الأدلّة أوّلاً ═══
 *
 * الأرقام محسوبة من سجلّ صفقاتك ولا تحتاج نموذجاً لغويّاً. فتُعرَض
 * فوراً، ثمّ يُستدعى النموذج للحكم. وعطلُ النموذج يترك الأرقام
 * قائمة بدل أن يحجب كل شيء.
 */
(function () {
  "use strict";

  var timer = null;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g,
      function (c) { return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]; });
  }

  /* ═══ «لماذا قد تنجح» ═══
   *
   * أسباب الإشارة كما زعمها الماسح، وبجانب كلٍّ منها سجلّه
   * الحقيقي. والدرجة تُلوَّن صراحةً: «أثبتت» ليست «مبشّرة»،
   * و«مبشّرة» ليست يقيناً — والخلط بينها هو ما يجعل ستّة أسبابٍ
   * مزعومة تُقرأ إجماعاً.
   */
  var STRENGTH_TONE = {
    "أثبتت": "var(--up)",
    "مبشّرة": "var(--ds-text)",
    "محايدة": "var(--ds-text-muted)",
    "لم تُختبر": "var(--ds-text-muted)",
    "ضدّك": "var(--down)",
  };

  function reasonRow(r, sign) {
    var col = STRENGTH_TONE[r.strength] || "var(--ds-text-muted)";
    var h = '<div class="small" style="display:flex;gap:6px;' +
      'align-items:baseline;padding:2px 0">' +
      '<span style="color:' + col + ';flex:0 0 auto">' + sign + "</span>" +
      '<span style="flex:1 1 auto">' + esc(r.text) + "</span>";
    if (r.pct === null || r.pct === undefined) {
      h += '<span class="muted" style="flex:0 0 auto">لم تُختبر (' +
        (r.total || 0) + ")</span>";
    } else {
      h += '<span style="flex:0 0 auto;color:' + col + '">' +
        r.wins + "/" + r.total + " = " + r.pct + "٪" +
        '</span><span class="muted" style="flex:0 0 auto">(' +
        (r.edge > 0 ? "+" : "") + r.edge + " نقطة · " + esc(r.strength) +
        ")</span>";
    }
    return h + "</div>";
  }

  function whyBlock(w) {
    if (!w) return "";
    var h = '<div class="mb-1"><b class="small">لماذا قد تنجح — ' +
      "وما يعمل ضدّها</b></div>" +
      '<div class="small mb-2" style="color:var(--ds-text)">' +
      esc(w.headline) + "</div>";
    (w.supporting || []).forEach(function (r) { h += reasonRow(r, "▲"); });
    (w.opposing || []).forEach(function (r) { h += reasonRow(r, "▼"); });
    var un = w.untested || [];
    if (un.length) {
      h += '<details class="small mt-1"><summary class="muted">' +
        un.length + " سبباً بلا عيّنة كافية</summary>";
      un.forEach(function (r) { h += reasonRow(r, "·"); });
      h += "</details>";
    }
    /* الضبط يُذكر رقماً لا يُخفى: من رأى «مبشّرة» يستحقّ أن يعرف
       على كم فرضيةٍ جرى البحث. */
    h += '<div class="small muted mt-1">اختُبرت ' + w.tested +
      " فرضية على سجلّك · نجت ضبط التعدّد " + w.survived + "</div>";
    return h;
  }

  function ratePill(r) {
    if (!r) return "";
    if (!r.readable) {
      return '<span class="badge" style="background:var(--ds-neutral);' +
        'color:var(--ds-text-muted)">لا سابقة كافية</span>';
    }
    var col = r.significant ? (r.pct >= r.baseline ? "var(--up)" : "var(--down)")
                            : "var(--ds-text-muted)";
    return '<span style="color:' + col + ';font-weight:600">' +
      r.wins + "/" + r.total + " = " + r.pct + "٪</span>" +
      '<span class="muted small"> [' + r.low + "–" + r.high + "] · الأساس " +
      r.baseline + "٪" + (r.significant ? " · يتجاوز الصدفة"
                                        : " · ضمن الصدفة") + "</span>";
  }

  /* الأدلّة تُعرَض بلا انتظار النموذج */
  function showEvidence(box, qs) {
    box.innerHTML = '<div class="small muted">يحسب الأدلّة من سجلّك…</div>';
    return fetch("/api/advice/evidence/" + qs)
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) { box.innerHTML = '<div class="small down">✗ ' +
          esc(d.reason) + "</div>"; return d; }
        var h = '<div class="small mb-1">' + ratePill(d.rate) + "</div>";
        if (d.why) {
          h += '<div class="mb-2" style="border-inline-start:2px solid ' +
            "var(--ds-line);padding-inline-start:8px\">" +
            whyBlock(d.why) + "</div>";
        }
        if (d.causes && d.causes.length) {
          h += '<ul class="small muted mb-1" style="padding-inline-start:18px">';
          d.causes.forEach(function (c) {
            h += "<li>" + esc(c.arabic) + "</li>";
          });
          h += "</ul>";
        }
        h += '<details class="small"><summary class="muted">' +
          "الأدلّة الكاملة (" + d.population + " صفقة محسومة)</summary>" +
          '<pre class="small muted" style="white-space:pre-wrap;' +
          'margin:6px 0 0">' + esc(d.evidence) + "</pre></details>";
        if (d.note) {
          h += '<div class="small warn mt-1">' + esc(d.note) + "</div>";
        }
        box.innerHTML = h;
        return d;
      })
      .catch(function (e) {
        box.innerHTML = '<div class="small down">✗ ' + esc(e) + "</div>";
      });
  }

  function renderVerdict(box, res) {
    if (!res) return;
    if (!res.accepted) {
      /* الرفض يُعرَض بسببه: «لم يُنتج جواباً» أصدق من كلامٍ لطيف */
      box.innerHTML = '<div class="small warn">⚠ لم يُنتج النموذج ' +
        "جواباً قابلاً للفحص — " + esc(res.rejected_because) + "</div>" +
        '<div class="small muted">الأرقام أعلاه محسوبة من سجلّك ' +
        "وتبقى صالحة.</div>";
      return;
    }
    var f = res.fields || {};
    var d = f["القرار"];
    var cls = d === "ادخل" ? "up" : (d === "لا تدخل" ? "down" : "warn");
    var h = "";
    if (d) {
      h += '<div class="mb-1"><span class="' + cls +
        '" style="font-weight:700;font-size:15px">' + esc(d) + "</span></div>";
    }
    Object.keys(f).forEach(function (k) {
      if (k === "القرار") return;
      h += '<div class="small"><span class="muted">' + esc(k) +
        ":</span> " + esc(f[k]) + "</div>";
    });
    h += '<div class="small muted mt-1">' + esc(res.model || "") + " · " +
      res.attempts + " محاولة · " + Math.round(res.latency_ms) + "ms</div>";
    box.innerHTML = h;
  }

  function poll(box) {
    fetch("/api/advice/status/")
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var j = d.job || {};
        if (j.state === "running") {
          box.innerHTML = '<div class="small muted">' +
            esc(j.note || "يستشير النموذج…") + "</div>";
          return;
        }
        clearInterval(timer); timer = null;
        if (d.result) renderVerdict(box, d.result);
        else box.innerHTML = '<div class="small warn">' +
          esc(j.note || j.error || "انتهى بلا نتيجة") + "</div>";
      })
      .catch(function () { clearInterval(timer); timer = null; });
  }

  function ask(url, body, box) {
    box.innerHTML = '<div class="small muted">يستشير النموذج…</div>';
    window.postJSON(url, body)
      .then(function () {
        if (timer) clearInterval(timer);
        timer = setInterval(function () { poll(box); }, 1500);
        poll(box);
      })
      .catch(function (e) {
        box.innerHTML = '<div class="small down">✗ ' + esc(e) + "</div>";
      });
  }


  /* ═══ درج «هل أدخل؟» ═══
   *
   * يُبنى في الشيفرة لا في القالب: الزرّ مطلوب في الماسح ولوحة
   * المراقبة وصفحة الرمز، وثلاث نسخ من نفس الترميز في ثلاثة قوالب
   * تتباعد بعد أوّل تعديل.
   */
  var drawerEl = null, drawerCtrl = null;

  function ensureDrawer() {
    if (drawerEl) return;
    var bd = document.createElement("div");
    bd.id = "advice-backdrop";
    bd.className = "ds-drawer-backdrop";
    bd.setAttribute("aria-hidden", "true");

    drawerEl = document.createElement("aside");
    drawerEl.id = "advice-drawer";
    drawerEl.className = "ds-drawer";
    drawerEl.setAttribute("aria-hidden", "true");
    drawerEl.setAttribute("role", "dialog");
    drawerEl.innerHTML =
      '<div class="ds-drawer__head"><div class="ds-drawer__title-row">' +
        '<div><h2 class="ds-drawer__title" id="advice-title">هل أدخل؟</h2>' +
        '<p class="small muted" id="advice-sub"></p></div>' +
        '<button type="button" class="ds-drawer__close" id="advice-close" ' +
        'aria-label="إغلاق">×</button>' +
      "</div></div>" +
      '<div class="ds-drawer__body">' +
        '<div class="mb-2"><b class="small">ماذا يقول سجلّك</b></div>' +
        '<div id="advice-d-evidence" class="mb-3"></div>' +
        '<div class="mb-2"><b class="small">حكم النموذج</b></div>' +
        '<div id="advice-d-verdict"></div>' +
      "</div>" +
      '<div class="ds-drawer__foot">' +
        '<button type="button" class="ds-btn ds-btn--primary" ' +
        'id="advice-d-ask">اسأل النموذج</button></div>';

    document.body.appendChild(bd);
    document.body.appendChild(drawerEl);
    drawerCtrl = window.DS.createDrawer("advice-drawer", "advice-backdrop");
    document.getElementById("advice-close").onclick = function () {
      drawerCtrl.close();
    };
  }

  /* الحقول الفارغة تُحذف: ``score=`` فارغةً تصير سمةً وهميّة
     في الأدلّة وتضيّق العيّنة بلا سبب. */
  function clean(o) {
    var out = {};
    Object.keys(o).forEach(function (k) {
      var v = o[k];
      if (v !== null && v !== undefined && v !== "") out[k] = String(v);
    });
    return out;
  }

  function openSetup(setup) {
    ensureDrawer();
    var s = clean(setup);
    document.getElementById("advice-title").textContent =
      "هل أدخل " + (s.symbol || "؟");
    document.getElementById("advice-sub").textContent =
      [s.market, s.timeframe, s.grade ? "تصنيف " + s.grade : ""]
        .filter(Boolean).join(" · ");
    var evBox = document.getElementById("advice-d-evidence");
    var vBox = document.getElementById("advice-d-verdict");
    vBox.innerHTML = '<div class="small muted">لم يُسأل بعد.</div>';
    showEvidence(evBox, "?kind=prospective&" +
      new URLSearchParams(s).toString());
    var btn = document.getElementById("advice-d-ask");
    btn.disabled = false;
    btn.onclick = function () {
      btn.disabled = true;
      ask("/api/advice/prospective/", new URLSearchParams(s), vBox);
    };
    drawerCtrl.open();
  }

  window.Advice = {
    /* صفقة محسومة: لماذا فازت أو خسرت */
    settled: function (tradeId, evBox, vBox) {
      showEvidence(evBox, "?kind=settled&trade_id=" +
        encodeURIComponent(tradeId));
      ask("/api/advice/settled/",
          new URLSearchParams({ trade_id: String(tradeId) }), vBox);
    },
    /* إعداد قائم: هل أدخل */
    prospective: function (setup, evBox, vBox) {
      var qs = new URLSearchParams(setup).toString();
      showEvidence(evBox, "?kind=prospective&" + qs);
      ask("/api/advice/prospective/", new URLSearchParams(setup), vBox);
    },
    openSetup: openSetup,
    evidenceOnly: showEvidence,
  };
})();
