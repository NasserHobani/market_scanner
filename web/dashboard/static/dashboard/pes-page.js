/* ‏PES — المرحلة أوّلاً، والنقاط مفصّلة بعائلاتها.
 *
 * المرحلة قبل النقاط عمداً: «جاهزة للدخول» بستّين نقطة أهمّ من
 * «للمراقبة» بثمانين — لأنّ الأولى أتمّت التسلسل والثانية لم تبدأه.
 */
(function () {
  "use strict";

  var body = document.getElementById("pes-body");
  if (!body) return;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  var TONE = {
    ENTRY_READY: "var(--ds-success)",
    BREAKOUT_RETEST: "var(--ds-success)",
    BREAKOUT: "var(--ds-info)",
    PRE_BREAKOUT: "var(--ds-info)",
    WATCH: "var(--ds-warn)",
    ALREADY_EXPANDED: "var(--ds-risk)",
    NONE: "var(--ds-text-muted)",
  };

  function famChips(r) {
    var f = r.families || {};
    return Object.keys(f).map(function (k) {
      var g = f[k];
      var on = (r.families_contributing || []).indexOf(k) >= 0;
      return '<span class="small" style="padding:1px 6px;border-radius:4px;' +
        "border:1px solid var(--ds-line);margin-inline-end:4px;color:" +
        (on ? "var(--ds-text)" : "var(--ds-text-muted)") + ";background:" +
        (on ? "var(--ds-surface-3)" : "transparent") + '">' +
        esc(g.label) + " " + g.points + "/" + g.max + "</span>";
    }).join("");
  }

  function factors(r) {
    return (r.factors || []).slice().sort(function (a, b) {
      return b.points - a.points;
    }).map(function (f) {
      var pct = f.max > 0 ? Math.round((f.points / f.max) * 100) : 0;
      return '<div class="small" style="display:flex;gap:8px;padding:1px 0">' +
        '<span style="flex:0 0 8.5rem">' + esc(f.key) + "</span>" +
        '<span style="flex:0 0 3.5rem" class="num">' + f.points + "/" +
          f.max + "</span>" +
        '<span style="flex:0 0 4rem"><span style="display:inline-block;' +
          'height:4px;border-radius:2px;width:' + Math.max(2, pct) +
          '%;background:var(--ds-info)"></span></span>' +
        '<span class="muted">' + esc(f.detail || "") + "</span></div>";
    }).join("");
  }

  function row(r) {
    var tone = TONE[r.state] || TONE.NONE;
    var conf = r.confidence < 1
      ? ' <span class="small warn">ثقة ×' + r.confidence + "</span>" : "";
    return "<tr>" +
      '<td><span style="color:' + tone + ';font-weight:600">' +
        esc(r.state_label) + "</span>" + conf + "</td>" +
      "<td><a href='/symbol/" + esc(r.market) + "/" + esc(r.symbol) +
        "/?tf=4h'><b>" + esc(r.symbol) + "</b></a></td>" +
      '<td class="num">' + r.score + "</td>" +
      '<td class="num">' + (r.distance === null || r.distance === undefined
        ? "—" : r.distance + "٪") + "</td>" +
      '<td class="small">' + r.family_count + "</td>" +
      '<td class="small muted">' + esc(r.why || "") + "</td>" +
      "<td><details><summary class='small muted'>التفصيل</summary>" +
        "<div style='margin:6px 0'>" + famChips(r) + "</div>" +
        factors(r) + "</details></td></tr>";
  }

  function group(g) {
    var btc = g.btc || {};
    var stale = g.stale
      ? ' <span class="small warn">المسح عمره ' + g.age_hours + "س</span>" : "";
    var counts = Object.keys(g.by_state || {}).filter(function (k) {
      return k !== "NONE";
    }).map(function (k) { return k + " " + g.by_state[k]; }).join(" · ");
    var head = '<section class="ds-card mb-4"><div class="ds-card__head">' +
      '<h3 class="ds-card__title">' + esc(g.market) + "</h3>" +
      '<span class="ds-card__meta">' + g.evaluated + " رمزاً · BTC " +
        esc(btc.label || "—") + " (" + (btc.score || 0) + "/10)" +
        (counts ? " · " + counts : "") + stale + "</span></div>";
    if (!g.rows.length) {
      return head + '<div class="p-3"><p class="small muted">' +
        "لا رمز في هذه المرحلة الآن.</p></div></section>";
    }
    return head + '<div class="p-3"><div class="table-responsive">' +
      '<table class="table table-sm align-middle mb-0"><thead><tr>' +
      "<th>المرحلة</th><th>الرمز</th><th>النقاط</th><th>للمقاومة</th>" +
      "<th>عائلات</th><th>السبب</th><th></th>" +
      "</tr></thead><tbody>" + g.rows.map(row).join("") +
      "</tbody></table></div>" +
      '<button type="button" class="ds-btn ds-btn--sm mt-2 pes-refresh" ' +
        'data-market="' + esc(g.market) + '">أعد المسح</button>' +
      "</div></section>";
  }

  function load() {
    var m = document.getElementById("f-market").value;
    var s = document.getElementById("f-state").value;
    var sc = document.getElementById("f-score").value;
    body.innerHTML = '<p class="small muted">يحمّل…</p>';
    fetch("/api/pes/?market=" + encodeURIComponent(m) +
          "&state=" + encodeURIComponent(s) +
          "&min_score=" + encodeURIComponent(sc),
          { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) { body.innerHTML = '<p class="small down">تعذّر</p>'; return; }
        var h = (d.groups || []).map(group).join("");
        if (d.missing && d.missing.length) {
          h += '<p class="small muted">بلا مسح بعد: ' +
            esc(d.missing.join("، ")) +
            " — شغّل مهمّة «مسح ما قبل الانفجار» من /jobs/.</p>";
        }
        body.innerHTML = h || DS.EmptyState({
          icon: "◈", title: "لا مسح محفوظ",
          text: "شغّل مهمّة «مسح ما قبل الانفجار» من صفحة المهامّ.",
          actions: [{ href: "/jobs/", label: "المهامّ", primary: true }],
          inline: true,
        });
        var btcEl = document.getElementById("pes-btc");
        var first = (d.groups || [])[0];
        if (btcEl && first && first.btc) {
          btcEl.textContent = "نظام BTC: " + (first.btc.label || "—") +
            " (" + (first.btc.score || 0) + "/10)";
        }
      });
  }

  body.addEventListener("click", function (e) {
    var b = e.target.closest(".pes-refresh");
    if (!b) return;
    b.disabled = true; b.textContent = "يمسح…";
    window.postJSON("/api/pes/refresh/", new URLSearchParams({
      market: b.dataset.market,
    })).then(function () { setTimeout(load, 12000); });
  });

  document.getElementById("apply").addEventListener("click", load);
  load();
})();
