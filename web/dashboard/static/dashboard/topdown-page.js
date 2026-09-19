/* من الأعلى للأسفل: الأسبوعيّ يأذن · اليوميّ يوافق · الـ4س يوقّت.
 *
 * والمرحلة التي سقط عندها الرمز معروضة عمداً. «لا يُطابق» بلا سبب
 * تجعل الشاشة صندوقاً مغلقاً: من سقط عند «ممتدّ» يُراقَب غداً،
 * ومن سقط عند «الأسبوعيّ» لا يُنظَر إليه أصلاً — والفرق بينهما
 * هو كل قيمة الشاشة.
 */
(function () {
  "use strict";

  var body = document.getElementById("td-body");
  if (!body) return;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  var STAGE_TONE = {
    ready: "var(--ds-success)",
    entry: "var(--ds-info)",
    not_extended: "var(--ds-warn)",
    daily: "var(--ds-text-muted)",
    weekly: "var(--ds-text-muted)",
  };

  /* سهمٌ للانحياز: ▲ صاعد · ◆ محايد · ▼ هابط.
   * والمحايد ليس «قريباً من الصاعد» — هو اتّجاهٌ يلتفت، وأخطر من
   * الهابط الصريح لأنّه يُقرأ صعوداً. فله رمزُه ولونُه. */
  function bias(v) {
    if (v > 0) return '<span style="color:var(--ds-success)">▲</span>';
    if (v < 0) return '<span style="color:var(--ds-risk)">▼</span>';
    return '<span style="color:var(--ds-warn)">◆</span>';
  }

  function checks(list) {
    return (list || []).map(function (c) {
      return '<div class="small" style="padding:1px 0;color:' +
        (c.ok ? "var(--ds-text)" : "var(--ds-text-muted)") + '">' +
        (c.ok ? "✓ " : "· ") + esc(c.name) + "</div>";
    }).join("");
  }

  function stages(r) {
    return (r.stages || []).map(function (s) {
      return '<span class="small" style="padding:1px 6px;border-radius:4px;' +
        "border:1px solid var(--ds-line);margin-inline-end:4px;color:" +
        (s.ok ? "var(--ds-text)" : "var(--ds-text-muted)") + ";background:" +
        (s.ok ? "var(--ds-surface-3)" : "transparent") + '">' +
        (s.ok ? "✓ " : "") + esc(s.label) + "</span>";
    }).join("");
  }

  function row(r) {
    var tone = STAGE_TONE[r.stage] || "var(--ds-text-muted)";
    /* المخاطرة = بعد الوقف عن السعر. وهي العمود الذي يُفرز به:
       فرصتان متساويتان في كل شيء ووقفُ إحداهما نصفُ الأخرى ليستا
       متساويتين. */
    var risk = (r.risk_pct === null || r.risk_pct === undefined)
      ? "—" : r.risk_pct + "٪";
    var zone = r.entry_ok && r.entry_zone
      ? esc(r.entry_zone) +
        (r.entry_bars_ago ? ' <span class="muted">قبل ' +
          r.entry_bars_ago + "ش</span>" : "")
      : '<span class="muted">—</span>';
    return "<tr>" +
      '<td><span style="color:' + tone + ';font-weight:600">' +
        esc(r.stage_label) + "</span></td>" +
      "<td><a href='/symbol/" + esc(r.market) + "/" + esc(r.symbol) +
        "/?tf=4h'><b>" + esc(r.symbol) + "</b></a></td>" +
      '<td class="num">' + bias(r.weekly_bias) + "</td>" +
      '<td class="num">' + bias(r.daily_bias) + "</td>" +
      '<td class="small">' + zone + "</td>" +
      '<td class="num">' + risk + "</td>" +
      '<td class="small muted">' + esc(r.reason || "") + "</td>" +
      "<td><details><summary class='small muted'>التفصيل</summary>" +
        "<div style='margin:6px 0'>" + stages(r) + "</div>" +
        '<div class="small" style="margin-top:6px"><b>الأسبوعيّ</b></div>' +
        checks(r.weekly_checks) +
        '<div class="small" style="margin-top:6px"><b>اليوميّ</b>' +
          (r.ext_daily_pct === null || r.ext_daily_pct === undefined ? "" :
            ' <span class="muted">بُعدٌ عن EMA20: ' + r.ext_daily_pct +
            "٪</span>") + "</div>" +
        checks(r.daily_checks) +
        '<div class="small" style="margin-top:6px"><b>الدخول (4س)</b></div>' +
        checks(r.entry_checks) +
      "</details></td></tr>";
  }

  function group(g) {
    var stale = g.stale
      ? ' <span class="small warn">المسح عمره ' + g.age_hours + "س</span>" : "";
    /* عدّ المراحل يبقى ظاهراً ولو لم يُعرض صفٌّ واحد: «صفر جاهز»
       مع «١٤٠ سقط عند الأسبوعيّ» خبرٌ عن السوق، لا عطبٌ في المسح. */
    var bs = g.by_stage || {};
    var counts = ["ready", "entry", "not_extended", "daily", "weekly"]
      .filter(function (k) { return bs[k]; })
      .map(function (k) { return k + " " + bs[k]; }).join(" · ");
    var head = '<section class="ds-card mb-4"><div class="ds-card__head">' +
      '<h3 class="ds-card__title">' + esc(g.market) + "</h3>" +
      '<span class="ds-card__meta">' + g.evaluated + " رمزاً · جاهز " +
        g.ready_count + (counts ? " · " + counts : "") + stale +
      "</span></div>";
    if (!g.rows.length) {
      return head + '<div class="p-3"><p class="small muted">' +
        "لا رمز في هذه المرحلة الآن." +
        "</p><button type=\"button\" class=\"ds-btn ds-btn--sm mt-2 td-refresh\" " +
        'data-market="' + esc(g.market) + '">أعد المسح</button>' +
        "</div></section>";
    }
    return head + '<div class="p-3"><div class="table-responsive">' +
      '<table class="table table-sm align-middle mb-0"><thead><tr>' +
      "<th>المرحلة</th><th>الرمز</th>" +
      '<th title="انحياز الفريم الأسبوعيّ">أسبوعيّ</th>' +
      '<th title="انحياز الفريم اليوميّ">يوميّ</th>' +
      '<th title="من أين ارتدّ السعر على 4س">الارتداد</th>' +
      '<th title="بعد الوقف المقترح عن السعر">المخاطرة</th>' +
      "<th>السبب</th><th></th>" +
      "</tr></thead><tbody>" + g.rows.map(row).join("") +
      "</tbody></table></div>" +
      '<button type="button" class="ds-btn ds-btn--sm mt-2 td-refresh" ' +
        'data-market="' + esc(g.market) + '">أعد المسح</button>' +
      "</div></section>";
  }

  function load() {
    var m = document.getElementById("f-market").value;
    var s = document.getElementById("f-stage").value;
    body.innerHTML = '<p class="small muted">يحمّل…</p>';
    fetch("/api/topdown/?market=" + encodeURIComponent(m) +
          "&stage=" + encodeURIComponent(s),
          { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) { body.innerHTML = '<p class="small down">تعذّر</p>'; return; }
        var h = (d.groups || []).map(group).join("");
        if (d.missing && d.missing.length) {
          h += '<p class="small muted">بلا مسح بعد: ' +
            esc(d.missing.join("، ")) +
            " — شغّل مهمّة «المسح من الأعلى للأسفل» من /jobs/.</p>";
        }
        body.innerHTML = h || DS.EmptyState({
          icon: "◈", title: "لا مسح محفوظ",
          text: "شغّل مهمّة «المسح من الأعلى للأسفل» من صفحة المهامّ.",
          actions: [{ href: "/jobs/", label: "المهامّ", primary: true }],
          inline: true,
        });
      });
  }

  body.addEventListener("click", function (e) {
    var b = e.target.closest(".td-refresh");
    if (!b) return;
    b.disabled = true; b.textContent = "يمسح…";
    window.postJSON("/api/topdown/refresh/", new URLSearchParams({
      market: b.dataset.market,
    })).then(function () { setTimeout(load, 15000); });
  });

  document.getElementById("apply").addEventListener("click", load);
  load();
})();
