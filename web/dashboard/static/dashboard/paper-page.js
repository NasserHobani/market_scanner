/* المحفظة الورقية — الرصيد والصفقات والإعدادات.
 *
 * ═══ الرسوم عمودٌ مستقلّ ═══
 *
 * مجموعها على مئة صفقة يبتلع أرباحاً كثيرة، ولا يُرى إن ذاب في
 * صافي الربح. فيُعرض وحده في الملخّص وفي كل صفّ.
 */
(function () {
  "use strict";

  var tab = "open";

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function money(v) {
    if (v === null || v === undefined) return "—";
    return Number(v).toLocaleString("en-US", { minimumFractionDigits: 2,
                                               maximumFractionDigits: 2 });
  }
  function px(v) { return window.Fmt ? Fmt.price(v) : String(v); }

  function metric(label, value, foot, tone) {
    return '<div class="ds-metric ds-metric--sm' +
      (tone ? " ds-metric--" + tone : "") + '">' +
      '<span class="ds-metric__label">' + esc(label) + "</span>" +
      '<span class="ds-metric__value">' + value + "</span>" +
      '<span class="ds-metric__foot"><span class="ds-text-muted">' +
      esc(foot || "") + "</span></span></div>";
  }

  function renderSummary(s) {
    var tone = s.pnl > 0 ? "success" : (s.pnl < 0 ? "risk" : "");
    var gate = s.can_open || {};
    var html =
      metric("قيمة المحفظة", money(s.equity),
             "رأس المال " + money(s.initial_balance)) +
      metric("الربح", (s.pnl > 0 ? "+" : "") + money(s.pnl),
             (s.pnl_pct > 0 ? "+" : "") + s.pnl_pct + "٪", tone) +
      metric("النقد", money(s.cash),
             "في المراكز " + money(s.open_value)) +
      /* الرسوم تُعرض وحدها — وإلّا لم تُرَ */
      metric("الرسوم", money(s.fees_total), "مدفوعة حتى الآن") +
      metric("مفتوحة", s.open_count,
             gate.ok ? "الفتح مسموح" : (gate.reason || "")) +
      metric("رابحة / خاسرة", s.won + " / " + s.lost,
             s.win_rate === null ? "لا محسومة بعد"
                                 : "نسبة الفوز " + s.win_rate + "٪") +
      metric("متوسّط R", s.avg_r === null ? "—" :
             ((s.avg_r > 0 ? "+" : "") + s.avg_r),
             s.profit_factor === null ? "" :
             "عامل الربح " + s.profit_factor) +
      metric("الهدف", s.target_pct + "٪",
             s.target_reached ? "بُلغ — توقّف الفتح" : "لم يُبلغ بعد",
             s.target_reached ? "success" : "");
    document.getElementById("paper-summary").innerHTML = html;
    var t = document.getElementById("tgt-label");
    if (t) t.textContent = s.target_pct + "٪";
  }

  function tradeRow(t) {
    var isOpen = t.status === "open";
    var val = isOpen ? t.unrealized : t.pnl;
    var tone = val > 0 ? "up" : (val < 0 ? "down" : "");
    return "<tr>" +
      "<td><b>" + esc(t.symbol) + "</b>" +
        '<div class="small muted">' + esc(t.market) + " · " +
        esc(t.timeframe || "—") + " · " + esc(t.source || "") + "</div></td>" +
      '<td class="num">' + px(t.entry) + "</td>" +
      '<td class="num down">' + px(t.stop) + "</td>" +
      '<td class="num up">' + (t.target ? px(t.target) : "—") + "</td>" +
      '<td class="num">' + money(t.notional) +
        '<div class="small muted">مخاطرة ' + money(t.risk_amount) +
        "</div></td>" +
      '<td class="num">' + (isOpen ? px(t.last_price) : px(t.exit_price)) +
        (isOpen ? "" : '<div class="small muted">' +
          esc(t.exit_reason || "") + "</div>") + "</td>" +
      '<td class="num muted">' + money(t.fees) + "</td>" +
      '<td class="num ' + tone + '">' +
        (val === null || val === undefined ? "—"
          : (val > 0 ? "+" : "") + money(val)) +
        (t.r_multiple !== null && t.r_multiple !== undefined
          ? '<div class="small muted">' +
            (t.r_multiple > 0 ? "+" : "") + t.r_multiple + "R</div>" : "") +
      "</td>" +
      "<td>" + (isOpen
        ? '<button type="button" class="ds-btn ds-btn--sm pt-close" ' +
          'data-id="' + t.id + '">أغلق</button>'
        : '<span class="small muted">' + esc(t.status_label) + "</span>") +
      "</td></tr>";
  }

  function renderTrades(rows) {
    var el = document.getElementById("paper-trades");
    if (!rows.length) {
      el.innerHTML = DS.EmptyState({
        icon: "○",
        title: tab === "open" ? "لا صفقات مفتوحة" : "لا صفقات هنا",
        text: "اضغط «شغّل دورة» لتقييم المفتوح وفتح ما تسمح به القواعد.",
        inline: true,
      });
      return;
    }
    el.innerHTML = '<div class="table-responsive"><table class="table ' +
      'table-sm align-middle mb-0"><thead><tr>' +
      "<th>الرمز</th><th>الدخول</th><th>الوقف</th><th>الهدف</th>" +
      "<th>القيمة</th><th>السعر/الخروج</th><th>الرسوم</th>" +
      "<th>الربح</th><th></th></tr></thead><tbody>" +
      rows.map(tradeRow).join("") + "</tbody></table></div>";
  }

  function fillSettings(s) {
    var f = document.getElementById("settings-form");
    Object.keys(s).forEach(function (k) {
      var el = f.elements[k];
      if (!el) return;
      if (el.type === "checkbox") el.checked = !!s[k];
      else el.value = s[k];
    });
    var rb = document.getElementById("reset-balance");
    if (rb && !rb.value) rb.value = "";
  }

  function load() {
    var q = tab === "all" ? "" : "?status=" + tab;
    fetch("/api/paper/" + q, { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) {
          document.getElementById("paper-trades").innerHTML =
            '<p class="small down">' + esc(d.reason) + "</p>";
          return;
        }
        renderSummary(d.summary);
        fillSettings(d.settings);
        renderTrades(d.trades || []);
        var rb = document.getElementById("reset-balance");
        if (rb && !rb.value) rb.value = d.summary.initial_balance;
      });
  }

  document.getElementById("paper-tabs").addEventListener("click",
    function (e) {
      var b = e.target.closest(".ds-tab");
      if (!b) return;
      tab = b.getAttribute("data-tab");
      this.querySelectorAll(".ds-tab").forEach(function (x) {
        x.classList.toggle("is-active", x === b);
      });
      load();
    });

  document.getElementById("settings-form").addEventListener("submit",
    function (e) {
      e.preventDefault();
      var msg = document.getElementById("settings-msg");
      window.postJSON("/api/paper/settings/",
                      new URLSearchParams(new FormData(this)))
        .then(function (d) {
          /* ‏postJSON لا يرفض — الفشل في الحمولة */
          if (!d || d.ok === false) {
            msg.textContent = "✗ " + ((d && d.reason) || "تعذّر الحفظ");
            msg.style.color = "var(--ds-risk)";
            return;
          }
          msg.textContent = "✓ حُفظت";
          msg.style.color = "var(--ds-success)";
          load();
        });
    });

  document.getElementById("reset").addEventListener("click", function () {
    var v = document.getElementById("reset-balance").value;
    if (!window.confirm("تصفير المحفظة برأس مال " + v +
        "؟\nسيُحذف كل سجلّ الصفقات ولا يمكن التراجع.")) return;
    window.postJSON("/api/paper/reset/",
                    new URLSearchParams({ initial_balance: v }))
      .then(function (d) {
        if (!d || d.ok === false) {
          window.alert((d && d.reason) || "تعذّر التصفير");
          return;
        }
        load();
      });
  });

  document.getElementById("paper-trades").addEventListener("click",
    function (e) {
      var b = e.target.closest(".pt-close");
      if (!b) return;
      b.disabled = true;
      window.postJSON("/api/paper/" + b.dataset.id + "/close/",
                      new URLSearchParams()).then(function (d) {
        if (!d || d.ok === false) {
          b.disabled = false;
          window.alert((d && d.reason) || "تعذّر الإغلاق");
          return;
        }
        load();
      });
    });

  document.getElementById("tick").addEventListener("click", function () {
    var b = this;
    b.disabled = true; b.textContent = "يشغّل…";
    window.postJSON("/api/paper/tick/", new URLSearchParams())
      .then(function () {
        /* الدورة في خيط: تُنتظر ثمّ يُعاد التحميل */
        setTimeout(function () {
          b.disabled = false; b.textContent = "شغّل دورة"; load();
        }, 8000);
      });
  });

  document.getElementById("refresh").addEventListener("click", load);
  document.querySelector('#paper-tabs .ds-tab').classList.add("is-active");
  load();
})();
