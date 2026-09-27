/* المحفظة الحقيقية — والربح غير المحقّق يُحسب هنا لا على الخادم.
 *
 * ═══ لماذا هنا ═══
 *
 * الخادم يعطي ما يتغيّر ببطء: الكمّية ومتوسّط التكلفة. والسعر
 * يتغيّر كل ثانية — ويصل من ``LiveFeed`` وهو بثّ Binance العام
 * نفسه الذي تستعمله بقيّة الشاشات.
 *
 * فالربح = (السعر − متوسّط التكلفة) × الكمّية، يُعاد حسابه مع كل
 * تكّة بلا نداءٍ واحد. والبديل — أن يحسبه الخادم ويُرسله كل
 * ثانية — يعني استعمال مفاتيح الحساب ستّين مرّة في الدقيقة بلا
 * حاجة.
 *
 * ═══ وما لا يُدَّعى ═══
 *
 * مركزٌ ``basis_partial`` تكلفتُه مجهولة جزئياً (إيداعٌ لا شراء).
 * فربحُه يُعرَض بعلامة تحذير ولا يدخل المجموع — رقمٌ واثقٌ مبنيّ
 * على تكلفةٍ مجهولة أسوأ من لا رقم.
 */
(function () {
  "use strict";

  var summary = document.getElementById("w-wallet-summary");
  var table = document.getElementById("w-wallet-table");
  var state = document.getElementById("wallet-state");
  var dlg = document.getElementById("rule-dialog");

  var POSITIONS = [];
  var PRICES = {};

  function say(t, cls) {
    if (state) {
      state.textContent = t || "";
      state.className = "ds-text-xs " + (cls || "ds-text-muted");
    }
  }

  function num(v) {
    return (v === null || v === undefined || v !== v) ? null : Number(v);
  }

  /* ═══ الربح غير المحقّق ═══
   *
   * ‏null حين لا متوسّط تكلفة — لا صفر. والصفر رقمٌ يُجمَع ويُلوَّن
   * ويُقرأ «لا ربح ولا خسارة»، وهو هنا «لا أعرف». */
  function pnl(p) {
    var px = PRICES[p.symbol];
    var avg = num(p.avg_cost);
    if (px === undefined || avg === null || !p.qty) return null;
    return { abs: (px - avg) * p.qty, pct: ((px - avg) / avg) * 100 };
  }

  function money(v, d) {
    if (v === null || v === undefined || v !== v) return "—";
    return (window.Fmt && Fmt.price) ? Fmt.price(v) : Number(v).toFixed(d || 2);
  }

  var COLUMNS = [
    { key: "asset", label: "الأصل", width: "12%" },
    { key: "qty", label: "الكمّية", align: "end", width: "13%" },
    { key: "avg", label: "متوسّط التكلفة", align: "end", width: "13%" },
    { key: "price", label: "السعر الآن", align: "end", width: "12%" },
    { key: "value", label: "القيمة", align: "end", width: "12%" },
    { key: "pnl", label: "غير محقّق", align: "end", width: "14%" },
    { key: "rules", label: "قواعد الخروج", width: "16%" },
    { key: "act", label: "", width: "8%" },
  ];

  function ruleChips(p) {
    var list = p.rules || [];
    if (!list.length) return '<span class="ds-text-muted">—</span>';
    return list.map(function (r) {
      var tone = !r.active ? "neutral"
        : r.kind === "stop" ? "risk"
          : r.kind === "target" ? "success" : "info";
      var val = r.kind === "trail" ? (r.pct + "٪")
        : r.price !== null && r.price !== undefined ? money(r.price) : "";
      var fired = r.fired_at
        ? ' <span class="ds-text-xs down" title="آخر تنبيه">•</span>' : "";
      return DS.StatusBadge({ label: r.kind_label + " " + DS.ltr(val),
                              tone: tone }) + fired;
    }).join(" ");
  }

  function row(p) {
    var px = PRICES[p.symbol];
    var pl = pnl(p);
    var val = px !== undefined ? px * p.qty : null;
    var warn = p.basis_partial
      ? ' <span class="down" title="' + DS.esc(p.basis_note) + '">⚠</span>'
      : "";

    return {
      asset: '<span class="ds-cell-strong">' + DS.esc(p.asset) + "</span>" +
        '<span class="trade-symbol__meta"> ' + DS.esc(p.symbol) + "</span>",
      qty: '<span class="ds-num" dir="ltr">' + DS.ltr(p.qty) + "</span>" +
        (p.locked ? '<span class="ds-text-xs ds-text-muted d-block">' +
          "محجوز " + DS.ltr(p.locked) + "</span>" : ""),
      avg: '<span class="ds-num" dir="ltr">' +
        (p.avg_cost === null ? "—" : money(p.avg_cost)) + "</span>" + warn,
      price: '<span class="ds-num" dir="ltr" data-px="' + DS.esc(p.symbol) +
        '">' + (px === undefined ? "…" : money(px)) + "</span>",
      value: '<span class="ds-num" dir="ltr">' + money(val) + "</span>",
      pnl: pl === null
        ? '<span class="ds-text-muted" title="متوسّط التكلفة غير معروف">—</span>'
        : '<span class="ds-num ds-value-' + (pl.abs >= 0 ? "success" : "risk") +
          '" dir="ltr">' + money(pl.abs) + " (" +
          (pl.pct >= 0 ? "+" : "") + pl.pct.toFixed(2) + "%)</span>",
      rules: ruleChips(p),
      act: '<button class="ds-btn ds-btn--sm w-rule" data-symbol="' +
        DS.esc(p.symbol) + '" data-asset="' + DS.esc(p.asset) +
        '">قاعدة</button>' +
        '<button class="ds-btn ds-btn--sm w-hist" data-symbol="' +
        DS.esc(p.symbol) + '">تاريخ</button>',
      _attrs: 'data-key="' + DS.esc(p.symbol) + '"',
    };
  }

  function renderSummary() {
    var content = summary.querySelector(".ds-widget__content");
    var invested = 0, value = 0, known = 0, partial = 0;
    POSITIONS.forEach(function (p) {
      var px = PRICES[p.symbol];
      if (px !== undefined) value += px * p.qty;
      /* المجهول لا يدخل المجموع: تكلفةٌ ناقصة تُنتج «ربحاً» وهمياً */
      if (p.basis_partial) { partial++; return; }
      if (p.cost) { invested += p.cost; known++; }
    });
    var realized = POSITIONS.reduce(function (s, p) {
      return s + (p.realized || 0);
    }, 0);

    content.innerHTML = DS.StatGrid([
      { label: "قيمة المراكز", value: money(value),
        hint: POSITIONS.length + " مركزاً" },
      { label: "التكلفة المعروفة", value: money(invested),
        hint: known + " من " + POSITIONS.length + " مركزاً" },
      { label: "محقّق سابقاً", value: money(realized),
        tone: realized >= 0 ? "success" : "risk",
        hint: "من عمليات بيعٍ تمّت" },
      { label: "تكلفة ناقصة", value: String(partial),
        tone: partial ? "warn" : "neutral",
        hint: partial ? "إيداعٌ لا شراء — لا يُحتسب ربحها" : "لا شيء" },
    ]);
    summary.setAttribute("data-state", "ready");
  }

  function renderTable() {
    var content = table.querySelector(".ds-widget__content");
    if (!POSITIONS.length) {
      content.innerHTML = DS.EmptyState({
        icon: "◔", title: "لا مراكز",
        text: "لا أصول غير نقدية في الحساب، أو المفتاح لا يقرأ الأرصدة.",
        inline: true,
      });
      table.setAttribute("data-state", "ready");
      return;
    }
    DS.patchDataTable(content, {
      columns: COLUMNS, items: POSITIONS, keyFn: function (p) { return p.symbol; },
      buildRow: row,
      patchRow: function (tr, p) {
        var cells = row(p);
        COLUMNS.forEach(function (c) { DS.setCellText(tr, c.key, cells[c.key]); });
      },
    });
    table.setAttribute("data-state", "ready");
  }

  /* ═══ التحديث الحيّ يمسّ الخلايا لا الجدول ═══
   *
   * إعادة بناء الجدول مع كل تكّة تُلغي التحديد وتُغلق أيّ قائمة
   * مفتوحة، وتومض الصفوف. فتُكتب الخلايا المتأثّرة وحدها. */
  function paintPrices() {
    POSITIONS.forEach(function (p) {
      var tr = document.querySelector('[data-key="' + CSS.escape(p.symbol) + '"]');
      if (!tr) return;
      var cells = row(p);
      ["price", "value", "pnl"].forEach(function (k) {
        DS.setCellText(tr, k, cells[k]);
      });
    });
    renderSummary();
  }

  function renderHealth(d) {
    var host = document.getElementById("wallet-health");
    if (!host) return;
    if (!d || d.configured === false) { host.innerHTML = ""; return; }
    if (d.safe === true) {
      host.innerHTML = '<div class="ds-text-xs ds-value-success">' +
        "✓ المفتاح للقراءة فقط" +
        (d.ip_restricted ? " · ومقيَّد بعنوان IP" : "") + "</div>";
      return;
    }
    if (d.safe === false) {
      /* ═══ التحذير لا يُخفى ═══
         مفتاحٌ يسمح بالسحب على خادمٍ بلا HTTPS خطرٌ حقيقيّ. */
      host.innerHTML = '<div class="ds-insight ds-insight--risk" role="alert">' +
        '<span class="ds-insight__mark"></span><div class="ds-insight__body">' +
        '<p class="ds-insight__title">هذا المفتاح يستطيع أكثر من القراءة</p>' +
        '<p class="ds-insight__text">' + DS.esc(d.why) + "</p>" +
        '<p class="ds-insight__text ds-text-xs">أنشئ مفتاحاً جديداً ' +
        "بالقراءة وحدها، واحذف هذا من Binance.</p></div></div>";
      return;
    }
    host.innerHTML = '<div class="ds-text-xs ds-text-muted">' +
      "صلاحيات المفتاح غير معروفة: " + DS.esc(d.why || "") + "</div>";
  }

  function feedSymbols() {
    if (typeof window.LiveFeed !== "function") return;
    var syms = POSITIONS.map(function (p) { return p.symbol; });
    if (!syms.length) return;
    if (!window._walletFeed) {
      window._walletFeed = new window.LiveFeed({
        onTick: function (sym, price) {
          if (!price) return;
          PRICES[sym] = price;
          paintPrices();
        },
        onStatus: function (st) {
          if (st === "open") say("بثّ مباشر", "ds-value-success");
          else if (st === "closed") say("انقطع البثّ — الأسعار قديمة",
                                        "ds-value-risk");
        },
      });
    }
    window._walletFeed.setSymbols(syms);
  }

  function load(force) {
    return fetch("/api/wallet/" + (force ? "?refresh=1" : ""),
                 { credentials: "same-origin" })
      .then(function (r) {
        /* الجلسة انتهت: الوسيط يردّ ‎401‎ بدل تحويلٍ إلى HTML */
        if (r.status === 401) { window.location = "/accounts/login/"; return null; }
        return r.json();
      })
      .then(function (d) {
        if (!d) return;
        if (!d.ok) {
          /* ═══ الهيكل العظميّ لا يبقى يدور ═══
           *
           * الملخّص كان يبقى في حالة ``loading`` إلى الأبد حين
           * تفشل القراءة: أربعة مستطيلات رمادية تنبض تحت رسالة
           * خطأ. فيُقرأ «ما زال يحمّل» لا «توقّف» — وينتظر
           * القارئ شيئاً لن يأتي. */
          summary.setAttribute("data-state", "ready");
          summary.querySelector(".ds-widget__content").innerHTML =
            '<p class="small ds-text-muted">لا أرقام — ' +
            DS.esc(d.why || "تعذّرت القراءة") + "</p>";
          table.setAttribute("data-state", "error");
          var box = table.querySelector(".ds-widget__error");
          if (box) { box.hidden = false; box.textContent = d.why || "تعذّر"; }
          return;
        }
        POSITIONS = d.positions || [];
        if (d.truncated) {
          say("عُرض " + POSITIONS.length + " من " + d.assets_total +
              " أصلاً — الباقي مقصوص لحدّ الطلبات", "ds-value-warn");
        }
        renderSummary();
        renderTable();
        feedSymbols();
      })
      .catch(function (e) {
        summary.setAttribute("data-state", "ready");
        table.setAttribute("data-state", "error");
        var box = table.querySelector(".ds-widget__error");
        if (box) { box.hidden = false; box.textContent = String(e).slice(0, 140); }
      });
  }

  function loadHealth() {
    fetch("/api/wallet/health/", { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(renderHealth)
      .catch(function () {});
  }

  function loadOrders() {
    var host = document.getElementById("wallet-orders");
    fetch("/api/wallet/orders/", { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) {
          host.innerHTML = '<span class="ds-text-muted">' +
            DS.esc(d.reason || "تعذّر") + "</span>";
          return;
        }
        if (!d.orders.length) {
          host.innerHTML = '<span class="ds-text-muted">' +
            "لا أوامر معلّقة على Binance.</span>";
          return;
        }
        host.innerHTML = d.orders.map(function (o) {
          return '<div class="d-flex gap-2 align-items-center py-1">' +
            DS.StatusBadge({ label: o.side === "BUY" ? "شراء" : "بيع",
                             tone: o.side === "BUY" ? "success" : "risk" }) +
            "<b>" + DS.esc(o.symbol) + "</b>" +
            '<span class="ds-text-muted">' + DS.esc(o.type) + "</span>" +
            '<span class="ds-num" dir="ltr">' +
            money(o.stop_price || o.price) + "</span>" +
            '<span class="ds-text-xs ds-text-muted">كمّية ' +
            DS.ltr(o.orig_qty) + "</span></div>";
        }).join("");
      })
      .catch(function () {
        host.innerHTML = '<span class="ds-text-muted">تعذّر التحميل</span>';
      });
  }

  // ── تاريخ الصفقات ──
  function showHistory(symbol) {
    var card = document.getElementById("trade-history");
    var body = document.getElementById("hist-body");
    document.getElementById("hist-symbol").textContent = symbol;
    card.hidden = false;
    body.innerHTML = '<span class="ds-text-muted">يحمّل…</span>';
    card.scrollIntoView({ behavior: "smooth", block: "nearest" });

    fetch("/api/wallet/trades/?symbol=" + encodeURIComponent(symbol),
          { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) {
          body.innerHTML = '<span class="down">' + DS.esc(d.reason) + "</span>";
          return;
        }
        var b = d.basis || {};
        body.innerHTML =
          '<div class="ds-text-xs ds-text-muted mb-2">' +
          b.trades + " صفقة · اشتُري " + DS.ltr(b.bought) +
          " · بيع " + DS.ltr(b.sold) +
          " · محقّق " + money(b.realized) +
          " · عمولات " + money(b.fees_quote) + "</div>" +
          '<div class="ds-table-scroll"><table class="ds-table"><thead><tr>' +
          "<th>الوقت</th><th>النوع</th><th class='num'>السعر</th>" +
          "<th class='num'>الكمّية</th><th class='num'>القيمة</th>" +
          "<th class='num'>عمولة</th></tr></thead><tbody>" +
          d.trades.map(function (t) {
            return "<tr><td class='ds-text-xs'>" +
              new Date(t.time).toLocaleString("ar-SA") + "</td><td>" +
              DS.StatusBadge({ label: t.is_buyer ? "شراء" : "بيع",
                               tone: t.is_buyer ? "success" : "risk" }) +
              "</td><td class='num' dir='ltr'>" + money(t.price) +
              "</td><td class='num' dir='ltr'>" + DS.ltr(t.qty) +
              "</td><td class='num' dir='ltr'>" + money(t.quote_qty) +
              "</td><td class='num ds-text-xs' dir='ltr'>" +
              DS.ltr(t.commission) + " " + DS.esc(t.commission_asset) +
              "</td></tr>";
          }).join("") + "</tbody></table></div>";
      });
  }

  // ── حوار القاعدة ──
  var current = { symbol: "", asset: "" };

  function syncDialogKind() {
    var k = document.getElementById("rule-kind").value;
    document.getElementById("rule-price-box").hidden = (k !== "stop" && k !== "target");
    document.getElementById("rule-pct-box").hidden = (k !== "trail");
    document.getElementById("rule-signal-note").hidden = (k !== "signal");
  }

  document.getElementById("rule-kind").addEventListener("change", syncDialogKind);

  document.addEventListener("click", function (e) {
    var b = e.target.closest(".w-rule");
    if (b) {
      current = { symbol: b.dataset.symbol, asset: b.dataset.asset };
      document.getElementById("rule-symbol").textContent = current.symbol;
      document.getElementById("rule-error").textContent = "";
      syncDialogKind();
      dlg.showModal();
      return;
    }
    var h = e.target.closest(".w-hist");
    if (h) showHistory(h.dataset.symbol);
  });

  document.getElementById("hist-close").addEventListener("click", function () {
    document.getElementById("trade-history").hidden = true;
  });

  document.getElementById("rule-form").addEventListener("submit", function (e) {
    if (e.submitter && e.submitter.value === "cancel") return;
    e.preventDefault();
    var kind = document.getElementById("rule-kind").value;
    var body = {
      symbol: current.symbol, asset: current.asset, kind: kind,
      price: parseFloat(document.getElementById("rule-price").value),
      pct: parseFloat(document.getElementById("rule-pct").value),
      note: document.getElementById("rule-note").value,
      active: true,
    };
    window.postJSON("/api/wallet/rule/save/", body)
      .then(function (d) {
        if (d && d.ok) { dlg.close(); load(false); }
        else {
          document.getElementById("rule-error").textContent =
            (d && d.reason) || "تعذّر الحفظ";
        }
      })
      .catch(function (err) {
        document.getElementById("rule-error").textContent =
          String(err).slice(0, 100);
      });
  });

  document.getElementById("wallet-refresh").addEventListener("click", function () {
    say("يحدّث…");
    load(true).then(function () { say(""); loadOrders(); });
  });

  document.getElementById("wallet-check").addEventListener("click", function () {
    say("يفحص…");
    window.postJSON("/api/wallet/check/")
      .then(function (d) {
        if (d && d.ok) {
          say("فُحصت " + d.checked + " قاعدة · أُطلق " + d.fired,
              d.fired ? "ds-value-warn" : "ds-value-success");
          load(false);
        } else say((d && d.reason) || "تعذّر", "ds-value-risk");
      })
      .catch(function (e) { say(String(e).slice(0, 100), "ds-value-risk"); });
  });

  loadHealth();
  load(false);
  loadOrders();
  // الأرصدة تتغيّر ببطء — والسعر يأتي من البثّ لحظةً بلحظة
  EVERY(120000, function () { load(false); });
})();
