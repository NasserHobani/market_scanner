/* صفحة البتكوين: شارت حيّ مربوط بالتحليل.
 *
 * ثلاث قواعد تحكم هذا الملف:
 *
 * ١. الشارت والتحليل لا يفترقان. تبديل الفريم يعيد تحميل الاثنين من
 *    نداء واحد (‏/api/chart/) — فلا تظهر شموع 1h بجانب قراءة 4h. هذا
 *    الخلط أخطر من غياب المعلومة لأنه يبدو متّسقاً.
 *
 * ٢. البثّ الحيّ يحدّث **الشمعة الجارية فقط**. التحليل لا يُعاد حسابه
 *    مع كل تكّة: قرارات هذا المشروع كلها على شموع مغلقة، وتحديث
 *    القراءة لحظياً يوهم بأن الإشارة تتغيّر كل ثانية.
 *
 * ٣. لا نداء ثقيل عند الرسم. النماذج ورأي المستشار خلف أزرار صريحة.
 */
(function () {
  "use strict";

  var cfgEl = document.getElementById("btc-config");
  var CFG = {};
  try { CFG = JSON.parse(cfgEl ? cfgEl.textContent : "{}"); } catch (e) { CFG = {}; }

  var tf = CFG.timeframe || "4h";
  var symbol = CFG.symbol || "BTCUSDT";
  var market = CFG.market || "crypto";
  var verdicts = CFG.verdicts || {};

  var priceEl = document.getElementById("chart-price");
  var feedEl = document.getElementById("chart-feed");
  var noteEl = document.getElementById("chart-note");
  var legendEl = document.getElementById("chart-legend");
  var boxEl = document.getElementById("chart-analysis");
  var stateEl = document.getElementById("btc-state");

  var lastClose = null;

  function fmt(v, d) {
    if (v === null || v === undefined || v !== v) return "—";
    return window.Fmt ? window.Fmt.price(v) : Number(v).toFixed(d === undefined ? 2 : d);
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  /* ═══ الرقم بمقياسه ═══
   *
   * ‏«19.4» وحدها لا تقول أمِن عشرةٍ هي أم من مئة، ولا أين العتبة.
   * و«sub» هنا هو السقف أو الحدّ — يُعرض تحت الرقم دائماً. */
  function cell(label, value, cls, sub) {
    return '<div class="col-6 col-md-3">' +
      '<div class="muted">' + label + "</div>" +
      '<div class="fs-6 ' + (cls || "") + '">' + value + "</div>" +
      (sub ? '<div class="small dim">' + sub + "</div>" : "") +
      "</div>";
  }

  /* شريط تقدّم بعلامة عتبة — الرقم يُرى موضعُه لا قيمتُه وحدها */
  function bar(val, max, mark, cls) {
    if (val === null || val === undefined || val !== val) return "";
    var p = Math.max(0, Math.min(100, (val / max) * 100));
    var m = Math.max(0, Math.min(100, (mark / max) * 100));
    return '<div style="position:relative;height:4px;border-radius:2px;' +
      'background:var(--ds-surface-2);margin-top:4px">' +
      '<div style="height:100%;border-radius:2px;width:' + p.toFixed(1) +
      '%;background:var(--' + (cls === "up" ? "up" : cls === "down"
        ? "down" : "dim") + ')"></div>' +
      '<div style="position:absolute;top:-2px;height:8px;width:1px;' +
      'inset-inline-start:' + m.toFixed(1) + '%;background:var(--ds-line)">' +
      "</div></div>";
  }

  /* ═══ الحكم أوّلاً ═══
   *
   * ثمانية أرقام صحيحة لا تقول ماذا أفعل. والقارئ يجمعها ذهنياً
   * كل مرّة — فيرى الدرجة خضراء ويظنّ الإشارة قائمة، والمانع
   * مكتوبٌ في زاويةٍ أخرى. فالحكم يُقال في سطرٍ واحد أعلى الكلّ. */
  function paintVerdict(d) {
    var host = document.getElementById("btc-verdict");
    if (!host) return;
    var v = d.verdict;
    if (!v) { host.innerHTML = ""; return; }
    var tone = v.level === "strong" ? "up" : v.level === "ok" ? "up" : "down";
    host.innerHTML =
      '<div class="d-flex align-items-start gap-3 flex-wrap" ' +
      'style="padding:12px 14px;border-radius:8px;' +
      'border:1px solid var(--ds-line);' +
      'border-inline-start:4px solid var(--' + tone + ')">' +
      '<div class="fs-5 ' + tone + '">' + esc(v.headline) + "</div>" +
      '<div class="small muted" style="flex:1;min-width:14rem">' +
      esc(v.why) + "</div></div>";
  }

  function paintAnalysis(d) {
    if (!boxEl) return;
    var sc = d.scales || {};
    var htf = d.htf === 1 ? '<span class="up">صاعد</span>'
      : d.htf === -1 ? '<span class="down">هابط</span>'
        : '<span class="dim">مختلط</span>';
    var v = verdicts[tf];
    var model;
    if (!v) {
      model = '<span class="dim">لم يُقيَّم لهذا الفريم</span>';
    } else if (!v.usable) {
      /* الرقم موجود لكنّه مرفوض. إخفاؤه يترك المستخدم يظنّ أن النموذج
         لم يعمل؛ وعرضه بلا حكم يجعله يبدو توقّعاً معتمداً. */
      model = '<span class="down">لا يتفوّق على خطّ الأساس</span>' +
        '<div class="small muted">دقّة ' + fmt(v.accuracy, 1) + "% مقابل " +
        fmt(v.baseline, 1) + "% — لا يُستعمل</div>";
    } else {
      var p = v.prob_up;
      model = '<span class="' + (p > 50 ? "up" : "down") + '">' +
        fmt(p, 1) + "% صعود</span>" +
        '<div class="small muted">دقّة ' + fmt(v.accuracy, 1) + "% مقابل أساس " +
        fmt(v.baseline, 1) + "%</div>";
    }

    /* ═══ «3/» ═══
     *
     * ‏``confluence`` **مصفوفة** أسباب لا عدد. و``[] + "/3"`` في
     * جافاسكربت = ``"/3"`` — فظهر «3/» في العربية، رقمٌ بلا معنى.
     * والمقام «3» كان مكتوباً باليد بينما الحدّ الحقيقيّ
     * ``min_confluence`` = 2: الشاشة تعرض مقياساً والمانع يحسب
     * بآخر، والقارئ لا يملك ما يكشف الفرق. */
    var need = sc.confluence_min || 0;
    var got = (d.confluence || []).length;
    var confCls = !need ? "dim" : got >= need ? "up" : "warn";

    var smax = sc.score_max || 100;
    var normal = sc.score_normal === undefined ? 25 : sc.score_normal;
    var scoreCls = d.score >= (sc.score_strong || 60) ? "up"
      : d.score >= normal ? "warn" : "dim";

    var rsiCls = d.rsi >= (sc.rsi_high || 70) ? "down"
      : d.rsi <= (sc.rsi_low || 30) ? "up" : "dim";
    var rvolCls = d.rvol >= (sc.rvol_high || 1.5) ? "up" : "dim";

    boxEl.innerHTML =
      cell("الدرجة", fmt(d.score, 1) + ' <span class="small dim">/ ' +
           smax + "</span>" + bar(d.score, smax, normal, scoreCls),
           scoreCls, "العتبة " + normal) +
      cell("الالتقاء", got + ' <span class="small dim">/ ' + need +
           "</span>", confCls,
           need ? "الحدّ الأدنى للدخول" : "بلا حدّ مضبوط") +
      cell("الفريم الأعلى", htf, "", "يومي مقابل فريم العرض") +
      cell("RSI", fmt(d.rsi, 1), rsiCls,
           "تشبّع فوق " + (sc.rsi_high || 70)) +
      cell("الحجم النسبي", fmt(d.rvol, 2) + "×", rvolCls,
           "مقابل متوسّطه — لافت فوق " + (sc.rvol_high || 1.5)) +
      cell("ATR%", fmt(d.atr_pct, 2) + "٪", "",
           "مدى الشمعة من السعر") +
      cell("التوصية", (d.recommendation && d.recommendation.headline)
           || "لا توصية") +
      cell("توقّع النموذج (" + tf + ")", model);
  }

  /* ─────────────────── السياق: تموضع · أحداث · أخبار */

  function paintContext(d) {
    paintPositioning(d.positioning || {});
    paintEvents(d.events || [], d.calendar || {});
    paintNews(d.headlines || [], d.news_error, d.news_note);
  }

  var POS_TONE = {
    crowded_long: "down", heating: "warn",
    neutral: "dim", reset: "up", unknown: "dim"
  };

  function paintPositioning(p) {
    var host = document.getElementById("btc-positioning");
    if (!host) return;
    if (!p.ok) {
      host.innerHTML = '<div class="small muted">' +
        esc(p.why || "غير متاح") + "</div>";
      return;
    }
    var tone = POS_TONE[p.state] || "dim";
    host.innerHTML =
      '<div class="fs-6 ' + tone + '">' + esc(p.label) + "</div>" +
      '<div class="small muted mb-2">' + esc(p.why) + "</div>" +
      '<div class="row g-2">' +
      cell("التمويل", fmt(p.funding, 4) + "٪", tone,
           "سنوياً " + fmt(p.funding_annual_pct, 1) + "٪") +
      cell("مئين التمويل",
           p.funding_pctile === null ? "—" : fmt(p.funding_pctile, 0),
           tone, p.funding_samples + " دفعة") +
      cell("المراكز المفتوحة — يوم",
           p.oi_change_1d === null ? "—" : fmt(p.oi_change_1d, 1) + "٪", "") +
      cell("المراكز المفتوحة — أسبوع",
           p.oi_change_7d === null ? "—" : fmt(p.oi_change_7d, 1) + "٪", "") +
      "</div>" +
      /* الحدّ يُعلَن مع البيانات: نسبةٌ بلا سياقٍ تاريخيّ توحي
         بسياقٍ لا وجود له */
      '<div class="small dim mt-2">' + esc(p.oi_note) + "</div>" +
      '<div class="small dim">لا يدخل الدرجة — وصفُ مخاطرة لا إشارة اتجاه.' +
      "</div>";
  }

  var EV_TONE = { fomc: "down", cpi: "warn", halving: "up" };

  function paintEvents(list, health) {
    var host = document.getElementById("btc-events");
    if (!host) return;
    var warn = "";
    /* ═══ الصمت هو العطب ═══
     *
     * تقويمٌ نفدت مواعيده يعرض قائمةً فارغة — تُقرأ «لا أحداث
     * قادمة»، وهو ادّعاء كاذب. فالفرق بين «لا حدث» و«لا أعرف»
     * يُقال صراحة. */
    if (health && (health.ok === false || health.warn)) {
      warn = '<div class="small down mb-2">' + esc(health.why) + "</div>";
    }
    if (!list.length) {
      host.innerHTML = warn + '<div class="small muted">' +
        (health && health.ok === false ? "" : "لا أحداث خلال ٤٥ يوماً.") +
        "</div>";
      return;
    }
    host.innerHTML = warn + list.map(function (e) {
      var tone = EV_TONE[e.kind] || "dim";
      return '<div class="d-flex align-items-center gap-2 py-1">' +
        '<span class="badge text-bg-secondary">' + esc(e.kind_label) +
        "</span>" +
        '<span class="' + tone + '">' + esc(e.title) + "</span>" +
        '<span class="small muted" style="margin-inline-start:auto" dir="ltr">' +
        esc(e.date) + "</span>" +
        '<span class="small ' + (e.days <= 3 ? "down" : "dim") + '">بعد ' +
        e.days + " يوماً" + (e.approx ? " ≈" : "") + "</span></div>";
    }).join("");
  }

  function paintNews(items, err, note) {
    var host = document.getElementById("btc-news");
    if (!host) return;
    if (!items.length) {
      host.innerHTML = '<div class="small muted">' +
        esc(err || "لم تصل عناوين") + "</div>";
      return;
    }
    host.innerHTML = items.map(function (n) {
      return '<div class="py-1">' +
        '<a href="' + esc(n.link) + '" target="_blank" rel="noopener">' +
        esc(n.title) + "</a>" +
        '<div class="small dim">' + esc(n.source) + " · " +
        esc(n.date) + "</div></div>";
    }).join("") +
      '<div class="small dim mt-2">' + esc(note || "") + "</div>";
  }

  function loadContext() {
    fetch("/api/btc/context/")
      .then(function (r) { return r.json(); })
      .then(paintContext)
      .catch(function (e) {
        var h = document.getElementById("btc-positioning");
        if (h) h.innerHTML = '<div class="small muted">' +
          esc(String(e).slice(0, 120)) + "</div>";
      });
  }

  /* ─────────────────── شارت TradingView
   *
   * الراسم المحلي كان بديلاً رديئاً: بلا أدوات رسم ولا مؤشرات ولا
   * حفظ. وTradingView يصل من شبكتك (المحجوب هو cdnjs لا هو)، فيُستعمل
   * الأصل بدل تقليده.
   *
   * الثمن صريح: الويدجت **إطار معزول**، فلا يمكن رسم مستويات تحليلك
   * داخله. ولذلك تُعرض تحته أرقاماً قابلة للنسخ — تعويض لا تمويه.
   */
  var TV_INTERVAL = { "15m": "15", "1h": "60", "4h": "240", "1d": "D" };
  var tvWidget = null;

  function mountTradingView() {
    var host = document.getElementById("tv-chart");
    if (!host) return false;
    if (typeof TradingView === "undefined" || !TradingView.widget) {
      // النطاق محجوب: نكشف الراسم المحلي بدل ترك فراغ
      host.classList.add("d-none");
      var fb = document.getElementById("tv-fallback");
      if (fb) fb.classList.remove("d-none");
      return false;
    }
    host.innerHTML = "";
    try {
      tvWidget = new TradingView.widget({
        container_id: "tv-chart",
        // BINANCE هو مصدر شموعنا نفسه — أي شارت آخر يعني رقمين
        // مختلفين للسعر نفسه على الشاشة ذاتها
        symbol: "BINANCE:" + symbol,
        interval: TV_INTERVAL[tf] || "60",
        timezone: "Asia/Riyadh",
        theme: "dark",
        style: "1",
        locale: "ar_AE",
        autosize: true,
        hide_side_toolbar: false,
        allow_symbol_change: false,
        withdateranges: true,
        details: false,
        studies: []
      });
      return true;
    } catch (e) {
      host.classList.add("d-none");
      var f2 = document.getElementById("tv-fallback");
      if (f2) f2.classList.remove("d-none");
      return false;
    }
  }

  /* ─────────────────── لوحة المستويات
   *
   * ترتيب مقصود: خطة الصفقة أولاً (دخول · وقف · هدف) لأنها ما يُنفَّذ،
   * ثم بقية الطبقات. والسعر الحالي مرجع لكل مستوى — «‏64,620‏» وحدها
   * لا تقول إن كانت فوقك أم تحتك.
   */
  var LAYER_AR = {
    plan: "خطة الصفقة", fib: "فيبوناتشي", structure: "بنية السوق",
    pa: "مناطق العرض والطلب", patterns: "نماذج سعرية",
    channel: "القناة", waves: "موجات إليوت", other: "أخرى"
  };

  function paintLevels(d) {
    var box = document.getElementById("levels-box");
    if (!box) return;
    var rows = [];
    var reco = d.recommendation || {};
    if (reco.entry) rows.push({ layer: "plan", title: "الدخول",
                                price: reco.entry, color: "var(--dim)" });
    if (reco.stop) rows.push({ layer: "plan", title: "الوقف",
                               price: reco.stop, color: "var(--down)" });
    (reco.targets || []).forEach(function (t, i) {
      rows.push({ layer: "plan", title: "الهدف " + (i + 1),
                  price: t, color: "var(--up)" });
    });
    (d.levels || []).forEach(function (lv) {
      if (typeof lv.price === "number") rows.push(lv);
    });
    if (!rows.length) {
      box.innerHTML = '<div class="col-12 muted">لا مستويات لهذا الفريم.</div>';
      return;
    }

    var groups = {};
    rows.forEach(function (r) {
      var k = r.layer || "other";
      (groups[k] = groups[k] || []).push(r);
    });
    var order = ["plan", "fib", "structure", "pa", "patterns", "channel",
                 "waves", "other"];
    var html = "";
    order.forEach(function (k) {
      var list = groups[k];
      if (!list || !list.length) return;
      html += '<div class="col-12 col-md-6 col-lg-4"><div class="mb-1 muted">' +
        (LAYER_AR[k] || k) + "</div>";
      list.slice(0, 8).forEach(function (r) {
        var away = lastClose
          ? ((r.price - lastClose) / lastClose * 100) : null;
        var side = away === null ? "" :
          (away > 0 ? '<span class="up">↑ ' : '<span class="down">↓ ') +
          Math.abs(away).toFixed(2) + "%</span>";
        html += '<div class="d-flex align-items-center gap-2 py-1">' +
          '<button class="btn btn-sm btn-outline-secondary py-0 px-1 lvl-copy"' +
          ' data-price="' + r.price + '" title="انسخ">⧉</button>' +
          '<span dir="ltr" style="font-variant-numeric:tabular-nums">' +
          fmt(r.price) + "</span>" +
          '<span class="muted">' + (r.title || "") + "</span>" +
          side + "</div>";
      });
      html += "</div>";
    });
    box.innerHTML = html;

    box.querySelectorAll(".lvl-copy").forEach(function (b) {
      b.addEventListener("click", function () {
        var v = b.getAttribute("data-price");
        var done = function () {
          var old = b.textContent;
          b.textContent = "✓";
          setTimeout(function () { b.textContent = old; }, 1200);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(v).then(done, function () {});
        } else {
          // متصفّح بلا clipboard أو صفحة بلا HTTPS: بديل قديم يعمل
          var ta = document.createElement("textarea");
          ta.value = v; document.body.appendChild(ta); ta.select();
          try { document.execCommand("copy"); done(); } catch (e) {}
          document.body.removeChild(ta);
        }
      });
    });
  }

  function load() {
    if (noteEl) noteEl.textContent = "يحمّل…";
    var url = "/api/chart/" + market + "/" + symbol + "/?tf=" + encodeURIComponent(tf);
    fetch(url, { headers: { "X-Requested-With": "fetch" } })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.error) {
          if (noteEl) noteEl.textContent = d.error;
          return;
        }
        // الراسم المحلي يُرسم فقط إن كان هو المعروض (‏TradingView محجوب)
        var fb = document.getElementById("tv-fallback");
        if (fb && !fb.classList.contains("d-none")
            && window.AnalysisChart && AnalysisChart.render) {
          AnalysisChart.render("chart", d, {});
        }
        lastClose = d.close;
        if (priceEl) priceEl.textContent = fmt(d.close);
        if (legendEl) {
          legendEl.textContent = (d.candles ? d.candles.length : 0) +
            " شمعة · آخر إغلاق " + fmt(d.close);
        }
        paintVerdict(d);
        paintAnalysis(d);
        paintLevels(d);
        if (noteEl) {
          noteEl.textContent = d.blocker ? ("مانع: " + d.blocker) : "";
        }
      })
      .catch(function (e) {
        if (noteEl) noteEl.textContent = String(e).slice(0, 140);
      });
  }

  /* ── تبديل الفريم ── */
  document.querySelectorAll(".btn-tf").forEach(function (b) {
    b.addEventListener("click", function () {
      document.querySelectorAll(".btn-tf").forEach(function (x) {
        x.classList.remove("active");
      });
      b.classList.add("active");
      tf = b.getAttribute("data-tf");
      // العنوان يحمل الفريم: إعادة التحميل أو مشاركة الرابط تُبقي ما تراه
      try {
        var u = new URL(window.location);
        u.searchParams.set("tf", tf);
        history.replaceState(null, "", u);
      } catch (e) { /* متصفّح قديم: لا ضرر */ }
      // الشارت والتحليل يتبدّلان معاً — وإلا ظهرت قراءة فريم فوق
      // شموع فريم آخر، وهو خلط يبدو متّسقاً
      mountTradingView();
      load();
    });
  });

  /* ── البثّ الحيّ: الشمعة الجارية وحدها ── */
  if (typeof window.LiveFeed === "function") {
    var feed = new window.LiveFeed({
      onTick: function (sym, price) {
        if (sym !== symbol || !price) return;
        if (priceEl) {
          priceEl.textContent = fmt(price);
          priceEl.className = "small " +
            (lastClose === null ? "" : price >= lastClose ? "up" : "down");
        }
        if (window.AnalysisChart && AnalysisChart.updateLatest) {
          AnalysisChart.updateLatest("chart", {
            time: Math.floor(Date.now() / 1000), close: price,
            open: price, high: price, low: price
          });
        }
      },
      onStatus: function (st) {
        if (!feedEl) return;
        var map = { open: ["بثّ مباشر", "var(--up)"],
                    connecting: ["يتصل…", "var(--dim)"],
                    closed: ["انقطع البثّ", "var(--down)"] };
        var v = map[st] || map.closed;
        feedEl.textContent = v[0];
        feedEl.style.color = v[1];
        if (st === "open") stopPolling(); else startPolling();
      }
    });
    feed.setSymbols([symbol]);
  } else {
    startPolling();
  }

  /* ── احتياط حين يُحجب بثّ بينانس ──
   *
   * الشبكة التي تمنع CDN تمنع WebSocket غالباً. لكن **الخادم يصل**
   * إلى المنصّة — هو من يجلب الشموع أصلاً — فيُسأل هو بدل المنصّة.
   *
   * الفارق أن هذا سعر آخر شمعة مخزَّنة لا سعر لحظي، فالتسمية تقول
   * «من الخادم» لا «بثّ مباشر». إخفاء الفرق يجعل رقماً عمره دقيقة
   * يبدو لحظياً — وهو ما يبني عليه المستخدم قراراً خاطئاً.
   */
  var pollTimer = null;

  function startPolling() {
    if (pollTimer) return;
    pollOnce();
    pollTimer = setInterval(pollOnce, 20000);
  }

  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  function pollOnce() {
    fetch("/api/chart/" + market + "/" + symbol + "/latest/?tf=" +
          encodeURIComponent(tf))
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.candle) return;
        if (priceEl) {
          priceEl.textContent = fmt(d.candle.close);
          priceEl.className = "small " +
            (lastClose === null ? ""
              : d.candle.close >= lastClose ? "up" : "down");
        }
        if (feedEl) {
          feedEl.textContent = "من الخادم (لا بثّ مباشر)";
          feedEl.style.color = "var(--dim)";
        }
        if (window.AnalysisChart && AnalysisChart.updateLatest) {
          AnalysisChart.updateLatest("chart", d.candle);
        }
      })
      .catch(function () { /* الخادم أيضاً لا يصل: نبقي آخر ما عُرض */ });
  }

  /* ── الأزرار الثقيلة: بنداء صريح لا عند الرسم ── */
  function say(text, cls) {
    if (!stateEl) return;
    stateEl.textContent = text || "";
    stateEl.className = "small align-self-center " + (cls || "muted");
  }

  function run(btn, url, busy, done) {
    if (!btn) return;
    btn.addEventListener("click", function () {
      btn.disabled = true;
      var label = btn.textContent;
      btn.textContent = busy;
      say("قد يستغرق دقيقة…");
      window.postJSON(url)
        .then(function (d) {
          btn.disabled = false;
          btn.textContent = label;
          if (d && d.ok) {
            say(done, "up");
            setTimeout(function () { location.reload(); }, 900);
          } else {
            say((d && d.reason) || "تعذّر", "down");
          }
        })
        .catch(function (e) {
          btn.disabled = false;
          btn.textContent = label;
          say(String(e).slice(0, 120), "down");
        });
    });
  }

  /* رأي المستشار: يبدأ ويُستعلَم، ولا يُنتظَر داخل الطلب.
   *
   * قِيس أن المراجعة تستغرق 116 ثانية بالوسيط، ومع إعادتين ومهلة 300
   * ثانية يبلغ أسوأ انتظار تسعمئة. الطلب المتزامن ينقطع قبلها فيظهر
   * «لا نتيجة» — والنموذج يكون قد عمل فعلاً. */
  var opinionBtn = document.getElementById("btc-opinion");
  var pollJob = null;

  function watchOpinion() {
    if (pollJob) return;
    pollJob = setInterval(function () {
      fetch("/api/btc/opinion/status/")
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d) return;
          if (d.state === "running") {
            say("يراجع… " + (d.elapsed || 0) + " ثانية");
            return;
          }
          clearInterval(pollJob); pollJob = null;
          if (opinionBtn) {
            opinionBtn.disabled = false;
            opinionBtn.textContent = "اطلب رأياً جديداً";
          }
          if (d.state === "done") {
            say("وصل الرأي بعد " + (d.elapsed || 0) + " ثانية", "up");
            setTimeout(function () { location.reload(); }, 800);
          } else if (d.state === "failed") {
            say(d.error || "تعذّرت المراجعة", "down");
          }
        })
        .catch(function () { /* انقطاع عابر: نُبقي الاستعلام */ });
    }, 3000);
  }

  if (opinionBtn) {
    opinionBtn.addEventListener("click", function () {
      opinionBtn.disabled = true;
      opinionBtn.textContent = "يراجع في الخلفية…";
      say("بدأت المراجعة…");
      window.postJSON("/api/btc/opinion/")
        .then(function (d) {
          if (d && d.ok) watchOpinion();
          else {
            opinionBtn.disabled = false;
            opinionBtn.textContent = "اطلب رأياً جديداً";
            say((d && d.reason) || "تعذّر البدء", "down");
          }
        })
        .catch(function (e) {
          opinionBtn.disabled = false;
          opinionBtn.textContent = "اطلب رأياً جديداً";
          say(String(e).slice(0, 120), "down");
        });
    });
  }

  // مراجعة بدأت في زيارة سابقة وما زالت تعمل: نلتقطها بلا ضغط زرّ
  fetch("/api/btc/opinion/status/")
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (d && d.state === "running") {
        if (opinionBtn) {
          opinionBtn.disabled = true;
          opinionBtn.textContent = "يراجع في الخلفية…";
        }
        watchOpinion();
      }
    })
    .catch(function () {});

  run(document.getElementById("btc-refresh"), "/api/btc/refresh/",
      "يعيد الحساب…", "أُعيد الحساب");

  mountTradingView();
  load();
  // السياق بعد الشارت: ثلاث شبكاتٍ لا تُؤخّر أوّل شمعة
  loadContext();
})();
