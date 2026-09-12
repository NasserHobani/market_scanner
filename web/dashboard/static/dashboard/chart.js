/* رسم الشارت وطبقات التحليل فوقه.
 *
 * TradingView المدمج لا يقبل رسماً برمجياً — لا واجهة لإضافة خطوط أو
 * علامات. لذلك نرسم شارتنا بـ lightweight-charts (من TradingView أيضاً،
 * مفتوحة المصدر) ونضع عليها ما حسبه الخادم.
 */
(function (global) {
  "use strict";

  var STYLE = { solid: 0, dotted: 1, dashed: 2 };

  var LIVE = {};   // معرّف الحاوية ← الشارت الحيّ ومستمعاته

  function render(containerId, data, opts) {
    opts = opts || {};
    var off = opts.hidden || {};
    var visible = function (item) { return !off[item.layer || "other"]; };
    var el = document.getElementById(containerId);
    if (!el) return null;
    if (typeof LightweightCharts === "undefined") {
      /* المكتبة من CDN، وشبكة محلية قد لا تصل إليها. البيانات وصلت
         سليمة في هذه الحالة (شموع وسعر وتحليل)، فعرض رسالة فارغة
         بدل رسمها إهدار لمعلومة موجودة.
         الراسم الاحتياطي بـ SVG خالص: أبسط بكثير وبلا تفاعل، لكنه
         يُري السوق حين تنقطع الشبكة — وهذا هو المطلوب. */
      if (global.FallbackChart) {
        var mark = el.parentElement
          && el.parentElement.querySelector("[data-chart-mode]");
        if (mark) {
          mark.textContent = "رسم احتياطي — المكتبة الخارجية لم تصل";
        }
        return global.FallbackChart.render(containerId, data, opts);
      }
      el.innerHTML = '<div class="empty">تعذّر تحميل مكتبة الرسم — تحقّق من الاتصال</div>';
      return null;
    }
    /* كل استدعاء سابق ترك شارتاً حيّاً ومستمعاً لـ resize، و drawChart
       يُستدعى مع كل تبديل طبقة — فتتراكم المستمعات على شارتات محذوفة.
       ننظّف ما قبله قبل البناء. */
    var prev = LIVE[containerId];
    if (prev) {
      global.removeEventListener("resize", prev.onResize);
      if (prev.ro) prev.ro.disconnect();
      try { prev.chart.remove(); } catch (e) { /* أُزيل مع innerHTML */ }
      delete LIVE[containerId];
    }
    el.innerHTML = "";

    /* الارتفاع من CSS لا من رقم ثابت: على الجوال يحدّده clamp() في
       base.html، وتمرير 480 هنا كان يجعل الشارت يتجاوز حاويته. */
    var boxHeight = function () {
      return opts.height || el.clientHeight || 480;
    };

    var chart = LightweightCharts.createChart(el, {
      layout: { background: { color: "transparent" }, textColor: "#8b93a7",
                fontFamily: "system-ui, 'Segoe UI', Tahoma, sans-serif" },
      grid: { vertLines: { color: "#1e2432" }, horzLines: { color: "#1e2432" } },
      rightPriceScale: { borderColor: "#242a3a" },
      timeScale: { borderColor: "#242a3a", timeVisible: true, secondsVisible: false },
      crosshair: { mode: 1 },
      height: boxHeight(),
      localization: { locale: "ar" }
    });

    var candles = chart.addCandlestickSeries({
      upColor: "#3ddc97", downColor: "#ff6b6b",
      borderUpColor: "#3ddc97", borderDownColor: "#ff6b6b",
      wickUpColor: "#3ddc97", wickDownColor: "#ff6b6b"
    });
    candles.setData(data.candles || []);

    if (data.volume && data.volume.length) {
      var vol = chart.addHistogramSeries({
        priceFormat: { type: "volume" }, priceScaleId: "vol"
      });
      chart.priceScale("vol").applyOptions({
        scaleMargins: { top: 0.85, bottom: 0 }
      });
      vol.setData(data.volume);
    }

    // الخطوط: زيجزاج، موجات، حدود القناة
    (data.lines || []).filter(visible).forEach(function (line) {
      if (!line.points || line.points.length < 2) return;
      var series = chart.addLineSeries({
        color: line.color, lineWidth: line.width || 1,
        lineStyle: STYLE[line.style] || 0,
        priceLineVisible: false, lastValueVisible: false,
        crosshairMarkerVisible: false, title: ""
      });
      series.setData(line.points);
    });

    // المستويات الأفقية: فيبوناتشي، أعناق النماذج، الدخول والوقف والأهداف
    (data.levels || []).filter(visible).forEach(function (lv) {
      candles.createPriceLine({
        price: lv.price, color: lv.color, lineWidth: 1,
        lineStyle: STYLE[lv.style] || 2,
        axisLabelVisible: true, title: lv.title
      });
    });

    // علامات نماذج الشموع + أرقام موجات إليوت
    var markers = (data.markers || []).filter(visible).map(function (m) {
      return { time: m.time, position: m.position, color: m.color,
               shape: m.shape, text: m.text };
    });
    if (!off.waves && data.waves && data.waves.labels && data.waves.labels.length) {
      data.waves.labels.forEach(function (w) {
        markers.push({ time: w.time, position: w.position || "inBar",
                       color: w.color, shape: "circle", text: w.text });
      });
    }
    markers.sort(function (a, b) { return a.time - b.time; });
    if (markers.length) candles.setMarkers(markers);

    chart.timeScale().fitContent();

    var resize = function () {
      chart.applyOptions({ width: el.clientWidth, height: boxHeight() });
    };
    resize();
    global.addEventListener("resize", resize);

    /* تغيّر العرض بلا تغيّر النافذة: طيّ القائمة، دوران الجهاز،
       أو ظهور شريط تمرير. resize وحده لا يلتقطها. */
    var ro = null;
    if (typeof ResizeObserver === "function") {
      ro = new ResizeObserver(resize);
      ro.observe(el);
    }

    var handle = { chart: chart, candles: candles, onResize: resize, ro: ro };
    LIVE[containerId] = handle;
    return handle;
  }

  function updateLatest(containerId, candle) {
    /* تحديث الشمعة الأخيرة فقط — بلا إعادة تحميل التاريخ */
    var handle = LIVE[containerId];
    // الرسم جرى بالاحتياطي: التحديث يجب أن يمرّ إليه هو، وإلّا تجمّدت
    // الشمعة الجارية وبدا البثّ معطّلاً وهو يعمل
    if (!handle && global.FallbackChart) {
      return global.FallbackChart.updateLatest(containerId, candle);
    }
    if (!handle || !handle.candles || !candle) return false;
    var t = candle.time;
    if (typeof t === "string") {
      t = Math.floor(Date.parse(t) / 1000);
    }
    if (!t || isNaN(t)) return false;
    try {
      handle.candles.update({
        time: t,
        open: candle.open,
        high: candle.high,
        low: candle.low,
        close: candle.close,
      });
      return true;
    } catch (e) {
      return false;
    }
  }

  /* شارت السعر الحيّ لحاويةٍ ما، أو null.
   *
   * تحتاجه لوحتا الزخم لتربطا محور زمنهما بمحوره. والمرجع يُطلب
   * عند كل رسم لا يُحتفظ به: render يهدم الشارت ويبنيه من جديد
   * مع كل تبديل طبقة، فمرجعٌ محفوظ يصير معلّقاً على شارتٍ محذوف
   * — فتتوقّف المزامنة بلا خطأ يظهر. */
  function chartOf(containerId) {
    var h = LIVE[containerId];
    return h ? h.chart : null;
  }

  global.AnalysisChart = { render: render, updateLatest: updateLatest,
                           chartOf: chartOf };
})(window);
