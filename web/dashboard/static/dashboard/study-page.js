/* دراسة رمز — والفاصل يُعرَض دائماً بجانب النسبة.
 *
 * ═══ لماذا الفاصل لا النسبة وحدها ═══
 *
 * «ارتدّ ٣ من ٣ = ١٠٠٪» رقمٌ صحيح ومضلّل تماماً: فاصله ‎[31–100]‎.
 * والنسبة وحدها تجعل العيّنة الصغيرة تتصدّر كل شيء — وهي أضعف ما
 * في الجدول لا أقواه.
 *
 * فكل صفٍّ يحمل: النسبة · العدد · الفاصل. والترتيب بالحدّ الأدنى.
 */
(function () {
  "use strict";

  var btn = document.getElementById("s-run");
  var state = document.getElementById("s-state");
  var timer = null;

  function say(t, cls) {
    state.textContent = t || "";
    state.className = "mt-2 ds-text-xs " + (cls || "ds-text-muted");
  }

  function esc(s) { return DS.esc(String(s == null ? "" : s)); }

  function money(v) {
    if (v === null || v === undefined || v !== v) return "—";
    return window.Fmt ? Fmt.price(v) : Number(v).toFixed(4);
  }

  /* شريطٌ يُظهر الفاصل بصرياً: الطول هو عدم اليقين */
  function ciBar(lo, hi, rate) {
    if (rate === null || rate === undefined) return "";
    var w = Math.max(1, hi - lo);
    return '<span style="display:inline-block;width:7rem;height:6px;' +
      'position:relative;background:var(--ds-surface-2);border-radius:3px;' +
      'vertical-align:middle">' +
      '<span style="position:absolute;height:100%;border-radius:3px;' +
      'inset-inline-start:' + lo + '%;width:' + w + '%;' +
      'background:var(--dim)"></span>' +
      '<span style="position:absolute;top:-2px;height:10px;width:2px;' +
      'inset-inline-start:' + rate + '%;background:var(--up)"></span>' +
      "</span>";
  }

  function pct(v) {
    return (v === null || v === undefined) ? "—" : Number(v).toFixed(1) + "٪";
  }

  function renderSummary(d) {
    var host = document.getElementById("s-summary");
    var b = d.baseline || {};
    var p = d.params || {};
    host.innerHTML = DS.StatGrid([
      { label: "خطّ الأساس", value: pct(b.rate),
        hint: b.n + " حالة محسومة من " + d.candles + " شمعة" },
      { label: "الشرط المقيس",
        value: p.target_atr + "×/" + p.stop_atr + "×",
        hint: "هدف/وقف بمضاعف ATR خلال " + p.horizon + " شمعة" },
      { label: "المدى", value: String(d.candles),
        hint: d.from + " ← " + d.to },
      { label: "السياق اليوميّ",
        value: d.daily_available ? "متاح" : "غائب",
        tone: d.daily_available ? "neutral" : "warn",
        hint: d.daily_available ? "" : "زامن الفريم اليوميّ لهذا الرمز" },
    ]);
  }

  function renderZones(d) {
    var card = document.getElementById("s-zones-card");
    var host = document.getElementById("s-zones");
    card.hidden = false;
    var z = d.zones || [];
    if (!z.length) {
      host.innerHTML = '<p class="ds-text-muted">' +
        "لا منطقة بلغت الحدّ الأدنى من اللمسات. وهذا جواب: " +
        "لا مستوى تكرّر عنده شيءٌ يُعتدّ به.</p>";
      return;
    }
    host.innerHTML =
      '<div class="ds-table-scroll"><table class="ds-table"><thead><tr>' +
      "<th>المنطقة</th><th class='num'>البعد</th><th class='num'>لمسات</th>" +
      "<th class='num'>صمدت</th><th>النسبة والفاصل</th></tr></thead><tbody>" +
      z.map(function (x) {
        var tone = x.above ? "ds-text-muted" : "ds-value-success";
        return "<tr><td dir='ltr' class='ds-num'>" + money(x.low) + " – " +
          money(x.high) + "</td>" +
          "<td class='num " + tone + "' dir='ltr'>" +
          (x.distance_pct > 0 ? "+" : "") + x.distance_pct + "%</td>" +
          "<td class='num'>" + x.settled + "</td>" +
          "<td class='num'>" + x.held + " / " + x.settled + "</td>" +
          "<td>" + ciBar(x.lo, x.hi, x.rate) +
          " <span class='ds-num'>" + pct(x.rate) + "</span>" +
          " <span class='ds-text-xs ds-text-muted'>[" + x.lo + "–" + x.hi +
          "]</span></td></tr>";
      }).join("") + "</tbody></table></div>" +
      '<p class="ds-text-xs ds-text-muted mt-2">' +
      "المنطقة فوق السعر الحالي رماديّة — ليست موضع دخولٍ الآن. " +
      "والترتيب بالحدّ الأدنى للفاصل لا بالنسبة: منطقةٌ ٣ من ٣ " +
      "نسبتها ١٠٠٪ ولا تعني شيئاً.</p>";
  }

  var VERDICT_TONE = {
    "صمد داخل العيّنة وخارجها": "success",
    "صمد داخل العيّنة — ولم يُختبَر خارجها بعد": "warn",
    "صمد داخلها وسقط خارجها — ملاءمة": "risk",
    "ضمن الضجيج بعد التصحيح": "muted",
    "عيّنة قصيرة — لا حكم": "muted",
  };

  function renderConds(d) {
    var card = document.getElementById("s-conds-card");
    var host = document.getElementById("s-conds");
    var meta = document.getElementById("s-conds-meta");
    card.hidden = false;
    var c = d.conditions || {};
    if (!c.ok) {
      host.innerHTML = '<p class="ds-text-muted">' +
        esc(c.why || "تعذّر") + "</p>";
      return;
    }
    meta.textContent = c.tests + " شرطاً · خطّ الأساس " +
      pct(c.baseline.rate);

    host.innerHTML =
      '<div class="ds-table-scroll"><table class="ds-table"><thead><tr>' +
      "<th>الشرط</th><th>داخل العيّنة</th><th>خارجها</th>" +
      "<th>الحكم</th></tr></thead><tbody>" +
      c.conditions.map(function (r) {
        var a = r.in_sample, b = r.out_sample;
        var tone = VERDICT_TONE[r.verdict] || "muted";
        return "<tr><td>" + esc(r.label) + "</td>" +
          "<td>" + ciBar(a.lo, a.hi, a.rate) +
          " <span class='ds-num'>" + pct(a.rate) + "</span>" +
          " <span class='ds-text-xs ds-text-muted'>ن=" + a.n + "</span></td>" +
          "<td>" + ciBar(b.lo, b.hi, b.rate) +
          " <span class='ds-num'>" + pct(b.rate) + "</span>" +
          " <span class='ds-text-xs ds-text-muted'>ن=" + b.n + "</span></td>" +
          "<td><span class='ds-value-" + (tone === "muted" ? "" : tone) +
          "'>" + esc(r.verdict) + "</span></td></tr>";
      }).join("") + "</tbody></table></div>" +
      '<p class="ds-text-xs ds-text-muted mt-2">' + esc(c.note) + "</p>";
  }

  function render(d) {
    if (!d.ok) {
      say(d.why || "تعذّرت الدراسة", "ds-value-risk");
      document.getElementById("s-summary").innerHTML = "";
      document.getElementById("s-zones-card").hidden = true;
      document.getElementById("s-conds-card").hidden = true;
      return;
    }
    renderSummary(d);
    renderZones(d);
    renderConds(d);
    document.getElementById("s-notes").innerHTML =
      (d.notes || []).map(function (n) {
        return '<p class="ds-text-xs ds-text-muted mb-1">' + esc(n) + "</p>";
      }).join("");
  }

  function poll(q) {
    fetch("/api/study/status/?" + q, { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.ok) return;
        if (d.state === "running") {
          say("يدرس… " + (d.elapsed || 0) + " ث");
          return;
        }
        clearInterval(timer); timer = null;
        btn.disabled = false;
        if (d.state === "failed") {
          say(d.error || "تعذّرت الدراسة", "ds-value-risk");
          return;
        }
        say("اكتملت في " + (d.elapsed || 0) + " ث", "ds-value-success");
        render(d.result || {});
      })
      .catch(function () {});
  }

  btn.addEventListener("click", function () {
    var symbol = document.getElementById("s-symbol").value.trim().toUpperCase();
    if (!symbol) { say("اكتب الرمز أوّلاً", "ds-value-risk"); return; }
    var body = new URLSearchParams({
      symbol: symbol,
      market: document.getElementById("s-market").value,
      tf: document.getElementById("s-tf").value,
      target: document.getElementById("s-target").value,
      stop: document.getElementById("s-stop").value,
      horizon: document.getElementById("s-horizon").value,
    });
    btn.disabled = true;
    say("يبدأ…");
    window.postJSON("/api/study/start/", body)
      .then(function (d) {
        if (!d || !d.ok) {
          btn.disabled = false;
          say((d && d.reason) || "تعذّر البدء", "ds-value-risk");
          return;
        }
        var q = new URLSearchParams({
          symbol: symbol,
          market: document.getElementById("s-market").value,
          tf: document.getElementById("s-tf").value,
        }).toString();
        clearInterval(timer);
        timer = setInterval(function () { poll(q); }, 1500);
        poll(q);
      })
      .catch(function (e) {
        btn.disabled = false;
        say(String(e).slice(0, 120), "ds-value-risk");
      });
  });

  // رمزٌ في العنوان: ‎/study/?symbol=BTCUSDT‎ من صفحة الرمز
  var pre = new URLSearchParams(window.location.search);
  if (pre.get("symbol")) {
    document.getElementById("s-symbol").value = pre.get("symbol").toUpperCase();
    if (pre.get("market")) document.getElementById("s-market").value = pre.get("market");
    if (pre.get("tf")) document.getElementById("s-tf").value = pre.get("tf");
    btn.click();
  }
})();
