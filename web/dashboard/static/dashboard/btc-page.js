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

  function cell(label, value, cls) {
    return '<div class="col-6 col-md-3">' +
      '<div class="muted">' + label + "</div>" +
      '<div class="fs-6 ' + (cls || "") + '">' + value + "</div></div>";
  }

  function paintAnalysis(d) {
    if (!boxEl) return;
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

    boxEl.innerHTML =
      cell("الدرجة", fmt(d.score, 1),
           d.score >= 25 ? "up" : d.score <= -25 ? "down" : "dim") +
      cell("الفريم الأعلى", htf) +
      cell("الالتقاء", (d.confluence === undefined ? "—" : d.confluence + "/3")) +
      cell("ATR%", fmt(d.atr_pct, 2)) +
      cell("RSI", fmt(d.rsi, 1)) +
      cell("الحجم النسبي", fmt(d.rvol, 2)) +
      cell("التوصية", (d.recommendation && d.recommendation.headline) || "لا توصية") +
      cell("توقّع النموذج (" + tf + ")", model);
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
})();
