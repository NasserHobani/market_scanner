/* لوحتا الزخم تحت الشارت — StochRSI و MACD.
 *
 * ═══ لماذا شارتات منفصلة لا سلاسل فوق السعر ═══
 *
 * ‏StochRSI مقياسه ٠–١٠٠، و MACD بوحدة السعر. ووضعهما على محور
 * السعر يسحق أحدهما في خطٍّ مسطّح عند الحافّة.
 *
 * والثمن أن محاور الزمن الثلاثة تصير مستقلّة: تكبّر الشارت
 * الأعلى فلا يتحرّك ما تحته، فتقارن زخم أمس بسعر اليوم. ولهذا
 * تُربط المحاور في الاتّجاهين أدناه.
 *
 * ═══ وهما عرضٌ لا قرار ═══
 *
 * لا يدخلان النقاط ولا التوصية — ويُكتب ذلك في الشاشة صراحةً.
 * فمؤشّرٌ مرسوم في الصفحة يُفترَض أنّه يؤثّر، وسكوتُ الواجهة
 * يجعل القارئ ينسب إليهما قراراً لم يصنعاه.
 */
(function (global) {
  "use strict";

  var LIVE = null;          // ما رُسم آخر مرّة — يُنظَّف قبل الرسم التالي
  var HEIGHT = 132;

  var COL = {
    k: "#5aa9ff", d: "#ffb454",
    band: "rgba(139,147,167,.35)", zero: "rgba(139,147,167,.5)",
    macd: "#5aa9ff", signal: "#ff6b6b",
    grid: "#1e2432", axis: "#242a3a", text: "#8b93a7"
  };

  function baseOptions(el) {
    return {
      layout: { background: { color: "transparent" }, textColor: COL.text,
                fontFamily: "system-ui, 'Segoe UI', Tahoma, sans-serif" },
      grid: { vertLines: { color: COL.grid }, horzLines: { color: COL.grid } },
      rightPriceScale: { borderColor: COL.axis },
      /* الزمن مخفيّ في اللوحة الأولى وظاهر في الأخيرة وحدها:
         ثلاثة أشرطة تواريخ متطابقة تأكل ارتفاعاً بلا فائدة. */
      timeScale: { borderColor: COL.axis, timeVisible: true,
                   secondsVisible: false, visible: false },
      crosshair: { mode: 1 },
      handleScale: true, handleScroll: true,
      height: HEIGHT, width: el.clientWidth,
      localization: { locale: "ar" }
    };
  }

  function lineOpts(color, width) {
    return { color: color, lineWidth: width || 2, priceLineVisible: false,
             lastValueVisible: true, crosshairMarkerVisible: true, title: "" };
  }

  /* ═══ ربط المحاور ═══
   *
   * كل شارت يبثّ تغيّر نطاقه ويستقبل تغيّر الآخرين. وبلا حارسٍ
   * يبثّ المستقبِلُ بدوره فيعود إلى الأوّل — حلقة لا تنتهي تجمّد
   * الصفحة. فالحارس يقول: أنا الآن أطبّق لا أُبادر.
   */
  function link(charts) {
    var applying = false;
    var unsubs = [];
    charts.forEach(function (src) {
      var handler = function (range) {
        if (applying || !range) return;
        applying = true;
        charts.forEach(function (dst) {
          if (dst === src) return;
          try { dst.timeScale().setVisibleLogicalRange(range); }
          catch (e) { /* شارتٌ أُزيل بين البثّ والتطبيق */ }
        });
        applying = false;
      };
      src.timeScale().subscribeVisibleLogicalRangeChange(handler);
      unsubs.push(function () {
        try { src.timeScale().unsubscribeVisibleLogicalRangeChange(handler); }
        catch (e) { /* أُزيل مع الشارت */ }
      });
    });
    return unsubs;
  }

  function destroy() {
    if (!LIVE) return;
    global.removeEventListener("resize", LIVE.onResize);
    if (LIVE.ro) LIVE.ro.disconnect();
    (LIVE.unsubs || []).forEach(function (fn) { fn(); });
    LIVE.charts.forEach(function (c) {
      try { c.remove(); } catch (e) { /* أُزيل مع innerHTML */ }
    });
    LIVE = null;
  }

  function setText(id, html) {
    var el = document.getElementById(id);
    if (el) el.innerHTML = html;
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  /* القراءة المكتوبة — من آخر شمعة **مغلقة**، والخطوط تُرسم إلى
     الجارية. والفرق يُقال صراحةً كي لا يُظنّ الرقم مخالفاً للرسم. */
  function reading(state, extra) {
    if (!state || state.text == null) return "—";
    var h = '<span class="fw-semibold">' + esc(state.text) + "</span>";
    if (extra) h += ' <span class="muted">· ' + esc(extra) + "</span>";
    if (state.note) {
      h += '<div class="small mt-1" style="color:#ffb454">⚠ '
         + esc(state.note) + "</div>";
    }
    return h;
  }

  function render(osc) {
    destroy();

    var wrap = document.getElementById("oscillators");
    if (!wrap) return null;

    if (!osc || !osc.ok) {
      wrap.classList.add("d-none");
      setText("osc-stoch-read", "—");
      setText("osc-macd-read", "—");
      var why = (osc && osc.reason) || "غير متاح";
      setText("osc-note", esc(why));
      return null;
    }
    wrap.classList.remove("d-none");

    var s = osc.stoch_rsi || {}, m = osc.macd || {};

    setText("osc-stoch-read",
            reading(s.state, "‏%K " + (s.state && s.state.k != null ? s.state.k : "—")
                             + " · %D " + (s.state && s.state.d != null ? s.state.d : "—")));
    setText("osc-macd-read", reading(m.state, m.state && m.state.hist != null
                                     ? "المدرّج " + m.state.hist : ""));
    setText("osc-note",
            esc((osc.disclaimer || "") + " · القراءة من آخر شمعة مغلقة"
                + (s.params ? " · " + s.params : "")
                + (m.params ? " · MACD " + m.params : "")));

    var elS = document.getElementById("osc-stoch");
    var elM = document.getElementById("osc-macd");
    if (!elS || !elM) return null;

    /* المكتبة من CDN وقد لا تصل على شبكةٍ محلية. والقراءة أعلاه
       كُتبت بالفعل — فالمعلومة موجودة والرسم وحده الغائب. */
    if (typeof LightweightCharts === "undefined") {
      elS.innerHTML = elM.innerHTML =
        '<div class="empty small">تعذّر تحميل مكتبة الرسم — القراءة أعلاه</div>';
      return null;
    }

    elS.innerHTML = ""; elM.innerHTML = "";

    // ── StochRSI ──
    var cS = LightweightCharts.createChart(elS, baseOptions(elS));
    var kS = cS.addLineSeries(lineOpts(COL.k));
    var dS = cS.addLineSeries(lineOpts(COL.d, 1));
    kS.setData(s.k || []);
    dS.setData(s.d || []);

    /* النطاق مثبّت ٠–١٠٠: بلا تثبيت يتمدّد المحور على القيم
       الظاهرة، فيبدو ٤٥ ملامساً للسقف ويُقرأ «تشبّع شرائي». */
    [0, 100].forEach(function (v) {
      kS.createPriceLine({ price: v, color: "transparent", lineWidth: 1,
                           axisLabelVisible: false, title: "" });
    });
    [[s.overbought || 80, "80"], [s.oversold || 20, "20"]].forEach(function (b) {
      kS.createPriceLine({ price: b[0], color: COL.band, lineWidth: 1,
                           lineStyle: 2, axisLabelVisible: true, title: b[1] });
    });

    // ── MACD ──
    var optM = baseOptions(elM);
    optM.timeScale.visible = true;   // شريط التواريخ في الأخيرة وحدها
    var cM = LightweightCharts.createChart(elM, optM);
    /* المدرّج أوّلاً كي تُرسم الخطوط فوقه لا تحته */
    var hM = cM.addHistogramSeries({ priceFormat: { type: "price" },
                                     priceLineVisible: false,
                                     lastValueVisible: false });
    hM.setData(m.hist || []);
    var lM = cM.addLineSeries(lineOpts(COL.macd));
    var sM = cM.addLineSeries(lineOpts(COL.signal, 1));
    lM.setData(m.line || []);
    sM.setData(m.signal || []);
    lM.createPriceLine({ price: 0, color: COL.zero, lineWidth: 1,
                         lineStyle: 2, axisLabelVisible: false, title: "" });

    var charts = [cS, cM];

    /* يُربط بشارت السعر أيضاً إن كان حيّاً — وهو الهدف كلّه:
       تمرير السعر يمرّر الزخم معه. */
    var main = global.AnalysisChart && global.AnalysisChart.chartOf
      ? global.AnalysisChart.chartOf("chart") : null;
    if (main) charts.push(main);

    var unsubs = link(charts);

    /* المزامنة الأولى: نتبع نطاق شارت السعر لا العكس — هو من
       نفّذ fitContent، ولوحتان تبدآن بنطاقٍ مختلف تُقرآن خطأً
       قبل أوّل تمرير. */
    try {
      var r = (main || cM).timeScale().getVisibleLogicalRange();
      if (r) charts.forEach(function (c) { c.timeScale().setVisibleLogicalRange(r); });
      else charts.forEach(function (c) { c.timeScale().fitContent(); });
    } catch (e) {
      charts.forEach(function (c) { c.timeScale().fitContent(); });
    }

    var onResize = function () {
      cS.applyOptions({ width: elS.clientWidth });
      cM.applyOptions({ width: elM.clientWidth });
    };
    onResize();
    global.addEventListener("resize", onResize);

    var ro = null;
    if (typeof ResizeObserver === "function") {
      ro = new ResizeObserver(onResize);
      ro.observe(elS);
    }

    LIVE = { charts: [cS, cM], unsubs: unsubs, onResize: onResize, ro: ro };
    return LIVE;
  }

  global.Oscillators = { render: render, destroy: destroy };
})(window);
