/* راسم شموع احتياطي بـ SVG — بلا مكتبة خارجية وبلا شبكة.
 *
 * ═══ لماذا وُجد ═══
 *
 * الشارت كان يعتمد على LightweightCharts من CDN، فإن حجبت الشبكة
 * cdnjs و jsdelivr ظهرت الصفحة فارغة برسالة «تعذّر تحميل مكتبة
 * الرسم» — بينما البيانات كلها وصلت سليمة (400 شمعة وسعر وتحليل).
 *
 * والاعتماد على CDN يناقض المشروع نفسه: البيانات محلية، والنموذج
 * اللغوي محلي، والخادم يُفتح على شبكة محلية قد لا تصل إلى الإنترنت
 * أصلاً. فأداةٌ تعمل بلا اتصال يجب أن **تُرسم** بلا اتصال.
 *
 * ═══ ما يرسمه ═══
 *
 * شموع (فتيل وجسم) · خطوط المؤشرات · مستويات أفقية (دخول · وقف ·
 * هدف · فيبوناتشي) · محور سعر · شبكة خفيفة.
 *
 * وما لا يرسمه: التكبير والتمرير والتفاعل. هذا احتياط لا بديل —
 * وظيفته أن ترى السوق حين تنقطع الشبكة، لا أن يحلّ محلّ المكتبة.
 */
(function (global) {
  "use strict";

  var NS = "http://www.w3.org/2000/svg";
  var PAD = { top: 12, right: 8, bottom: 20, left: 58 };
  var STATE = {};

  function el(name, attrs) {
    var node = document.createElementNS(NS, name);
    for (var k in attrs) {
      if (Object.prototype.hasOwnProperty.call(attrs, k)) {
        node.setAttribute(k, attrs[k]);
      }
    }
    return node;
  }

  function css(name, fallback) {
    try {
      var v = getComputedStyle(document.documentElement)
        .getPropertyValue(name).trim();
      return v || fallback;
    } catch (e) { return fallback; }
  }

  function niceTicks(lo, hi, count) {
    if (!(hi > lo)) return [lo];
    var span = hi - lo;
    var raw = span / Math.max(1, count);
    var mag = Math.pow(10, Math.floor(Math.log10(raw)));
    var norm = raw / mag;
    var step = (norm >= 5 ? 10 : norm >= 2 ? 5 : norm >= 1 ? 2 : 1) * mag;
    var out = [];
    for (var v = Math.ceil(lo / step) * step; v <= hi; v += step) out.push(v);
    return out.length ? out : [lo, hi];
  }

  function fmtPrice(v) {
    if (global.Fmt && global.Fmt.price) return global.Fmt.price(v);
    var a = Math.abs(v);
    return v.toFixed(a >= 1000 ? 0 : a >= 1 ? 2 : 6);
  }

  /* الشمعة الجارية قد تكون أعلى أو أدنى من كل التاريخ المعروض، فالمدى
     يُحسب من المعروض كله لا من التاريخ وحده — وإلا خرجت خارج الإطار. */
  function bounds(candles, lines, levels) {
    var lo = Infinity, hi = -Infinity;
    candles.forEach(function (c) {
      if (c.low < lo) lo = c.low;
      if (c.high > hi) hi = c.high;
    });
    (lines || []).forEach(function (ln) {
      (ln.points || ln.data || []).forEach(function (p) {
        var v = p.value !== undefined ? p.value : p[1];
        if (typeof v === "number") {
          if (v < lo) lo = v;
          if (v > hi) hi = v;
        }
      });
    });
    (levels || []).forEach(function (lv) {
      var v = lv.price !== undefined ? lv.price : lv.value;
      if (typeof v === "number") {
        if (v < lo) lo = v;
        if (v > hi) hi = v;
      }
    });
    if (!isFinite(lo) || !isFinite(hi) || hi <= lo) return null;
    var pad = (hi - lo) * 0.06;
    return { lo: lo - pad, hi: hi + pad };
  }

  function draw(container, data, opts) {
    opts = opts || {};
    var off = opts.hidden || {};
    var visible = function (item) { return !off[item.layer || "other"]; };

    var candles = (data.candles || []).filter(function (c) {
      return c && typeof c.close === "number";
    });
    if (!candles.length) {
      container.innerHTML = '<div class="empty">لا شموع لعرضها</div>';
      return null;
    }

    var lines = (data.lines || []).filter(visible);
    var levels = (data.levels || []).filter(visible);
    var b = bounds(candles, lines, levels);
    if (!b) {
      container.innerHTML = '<div class="empty">مدى الأسعار غير صالح</div>';
      return null;
    }

    var w = Math.max(320, container.clientWidth || 800);
    var h = Math.max(220, container.clientHeight || 420);
    var iw = w - PAD.left - PAD.right;
    var ih = h - PAD.top - PAD.bottom;

    var n = candles.length;
    var step = iw / n;
    var body = Math.max(1, Math.min(12, step * 0.65));

    var y = function (p) {
      return PAD.top + (b.hi - p) / (b.hi - b.lo) * ih;
    };
    var x = function (i) { return PAD.left + (i + 0.5) * step; };

    var up = css("--up", "#26a69a");
    var down = css("--down", "#ef5350");
    var dim = css("--dim", "#7a8290");
    var grid = css("--border", "#2a2f3a");

    var svg = el("svg", {
      width: "100%", height: h, viewBox: "0 0 " + w + " " + h,
      role: "img", "aria-label": "شارت شموع احتياطي"
    });

    // الشبكة ومحور السعر
    niceTicks(b.lo, b.hi, 6).forEach(function (v) {
      var yy = y(v);
      svg.appendChild(el("line", {
        x1: PAD.left, x2: w - PAD.right, y1: yy, y2: yy,
        stroke: grid, "stroke-width": 1, opacity: 0.5
      }));
      var t = el("text", {
        x: PAD.left - 6, y: yy + 4, fill: dim, "font-size": 11,
        "text-anchor": "end", direction: "ltr"
      });
      t.textContent = fmtPrice(v);
      svg.appendChild(t);
    });

    // الشموع
    candles.forEach(function (c, i) {
      var cx = x(i);
      var rising = c.close >= c.open;
      var color = rising ? up : down;
      svg.appendChild(el("line", {
        x1: cx, x2: cx, y1: y(c.high), y2: y(c.low),
        stroke: color, "stroke-width": 1
      }));
      var top = y(Math.max(c.open, c.close));
      var bot = y(Math.min(c.open, c.close));
      svg.appendChild(el("rect", {
        x: cx - body / 2, y: top, width: body,
        height: Math.max(1, bot - top), fill: color
      }));
    });

    // خطوط المؤشرات — تُحاذى بالفهرس لا بالوقت، فطولها قد يقلّ عن
    // الشموع (متوسط 200 مثلاً يبدأ متأخراً)
    lines.forEach(function (ln) {
      var pts = ln.points || ln.data || [];
      var offset = Math.max(0, n - pts.length);
      var d = "";
      pts.forEach(function (p, i) {
        var v = p.value !== undefined ? p.value : p[1];
        if (typeof v !== "number" || isNaN(v)) return;
        d += (d ? " L" : "M") + x(i + offset) + " " + y(v);
      });
      if (d) {
        svg.appendChild(el("path", {
          d: d, fill: "none", stroke: ln.color || dim,
          "stroke-width": ln.width || 1.2, opacity: 0.9
        }));
      }
    });

    // المستويات الأفقية
    levels.forEach(function (lv) {
      var v = lv.price !== undefined ? lv.price : lv.value;
      if (typeof v !== "number") return;
      var yy = y(v);
      svg.appendChild(el("line", {
        x1: PAD.left, x2: w - PAD.right, y1: yy, y2: yy,
        stroke: lv.color || dim, "stroke-width": 1,
        "stroke-dasharray": "4 3", opacity: 0.9
      }));
      if (lv.title) {
        var t = el("text", {
          x: w - PAD.right - 4, y: yy - 3, fill: lv.color || dim,
          "font-size": 10, "text-anchor": "end"
        });
        t.textContent = lv.title;
        svg.appendChild(t);
      }
    });

    container.innerHTML = "";
    container.appendChild(svg);
    return { svg: svg, candles: candles, bounds: b, opts: opts, data: data };
  }

  /* ── التحكّم: تكبير بالعجلة وتمرير بالسحب ──
   *
   * الراسم الأول كان يعرض كل الشموع دفعة واحدة بلا تحكّم، فأربعمئة
   * شمعة على 4h تعني أن كل شمعة عرضها بضع بكسلات — يُرى الشكل العام
   * ولا يُقرأ أي تفصيل. والقراءة التفصيلية هي الغرض.
   *
   * النافذة (‏from..to‏) حالة مستقلّة عن البيانات، فتبقى بين إعادات
   * الرسم — تكبيرك لا يضيع مع كل تحديث سعر.
   */
  function clampWindow(h) {
    var n = h.all.length;
    var span = Math.max(MIN_BARS, Math.min(n, h.to - h.from));
    if (h.from < 0) h.from = 0;
    h.to = h.from + span;
    if (h.to > n) { h.to = n; h.from = Math.max(0, n - span); }
  }

  var MIN_BARS = 20;

  function attachControls(containerId, container) {
    var dragging = false, startX = 0, startFrom = 0;

    container.addEventListener("wheel", function (e) {
      var h = STATE[containerId];
      if (!h || !h.all) return;
      e.preventDefault();
      var span = h.to - h.from;
      // نقطة المؤشّر تبقى ثابتة أثناء التكبير — وإلا قفز الشارت
      var rect = container.getBoundingClientRect();
      var frac = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
      if (document.dir === "rtl" || document.documentElement.dir === "rtl") {
        frac = 1 - frac;
      }
      var anchor = h.from + span * frac;
      var next = Math.round(span * (e.deltaY > 0 ? 1.2 : 1 / 1.2));
      next = Math.max(MIN_BARS, Math.min(h.all.length, next));
      h.from = Math.round(anchor - next * frac);
      h.to = h.from + next;
      clampWindow(h);
      redraw(containerId);
    }, { passive: false });

    container.addEventListener("mousedown", function (e) {
      var h = STATE[containerId];
      if (!h || !h.all) return;
      dragging = true; startX = e.clientX; startFrom = h.from;
      container.style.cursor = "grabbing";
    });
    window.addEventListener("mousemove", function (e) {
      if (!dragging) return;
      var h = STATE[containerId];
      if (!h || !h.all) return;
      var span = h.to - h.from;
      var perPx = span / Math.max(1, container.clientWidth);
      var dx = (e.clientX - startX) * perPx;
      h.from = Math.round(startFrom + dx);   // RTL: السحب يميناً يرجع
      h.to = h.from + span;
      clampWindow(h);
      redraw(containerId);
    });
    window.addEventListener("mouseup", function () {
      dragging = false;
      container.style.cursor = "";
    });
    container.addEventListener("dblclick", function () {
      var h = STATE[containerId];
      if (!h || !h.all) return;
      h.from = 0; h.to = h.all.length;      // نقرتان = العودة للكل
      redraw(containerId);
    });
  }

  function redraw(containerId) {
    var h = STATE[containerId];
    if (!h) return;
    var container = document.getElementById(containerId);
    if (!container) return;
    var view = Object.assign({}, h.data,
                             { candles: h.all.slice(h.from, h.to) });
    var next = draw(container, view, h.opts);
    if (next) {
      next.all = h.all; next.from = h.from; next.to = h.to;
      next.bound = h.bound;
      STATE[containerId] = next;
    }
  }

  function render(containerId, data, opts) {
    var container = document.getElementById(containerId);
    if (!container) return null;
    var prev = STATE[containerId];
    var all = (data.candles || []).filter(function (c) {
      return c && typeof c.close === "number";
    });
    // النافذة السابقة تُحفظ إن كانت البيانات هي نفسها طولاً — تبديل
    // الفريم يجلب عدداً مختلفاً فيُعاد الضبط، والتحديث الحيّ لا يُعيده
    var from = 0, to = all.length;
    if (prev && prev.all && prev.all.length === all.length) {
      from = prev.from; to = prev.to;
    } else if (all.length > 150) {
      from = all.length - 150;              // افتراضياً آخر 150 شمعة
    }
    var view = Object.assign({}, data, { candles: all.slice(from, to) });
    var handle = draw(container, view, opts);
    if (handle) {
      handle.all = all; handle.from = from; handle.to = to;
      handle.bound = prev && prev.bound;
    }
    STATE[containerId] = handle;
    if (handle && !handle.bound) {
      handle.bound = true;
      attachControls(containerId, container);
      var timer = null;
      var onResize = function () {
        clearTimeout(timer);
        timer = setTimeout(function () { redraw(containerId); }, 120);
      };
      if (global.ResizeObserver) {
        new ResizeObserver(onResize).observe(container);
      } else if (global.addEventListener) {
        global.addEventListener("resize", onResize);
      }
    }
    return handle;
  }

  /* تحديث الشمعة الأخيرة بلا إعادة رسم كل شيء: البثّ يصل كل ثانية،
     وإعادة بناء SVG كامل عندها تُثقل المتصفّح بلا فائدة. */
  function updateLatest(containerId, candle) {
    var handle = STATE[containerId];
    if (!handle || !candle || typeof candle.close !== "number") return false;
    // الشمعة الأخيرة في **كل** البيانات لا في النافذة المعروضة: من
    // يتصفّح الماضي يجب ألّا يرى سعر اللحظة يُكتب فوق شمعة قديمة
    if (handle.all && handle.to < handle.all.length) {
      var tail = handle.all[handle.all.length - 1];
      if (tail) {
        tail.close = candle.close;
        tail.high = Math.max(tail.high, candle.close);
        tail.low = Math.min(tail.low, candle.close);
      }
      return true;
    }
    var last = handle.candles[handle.candles.length - 1];
    if (!last) return false;
    last.close = candle.close;
    last.high = Math.max(last.high, candle.close);
    last.low = Math.min(last.low, candle.close);
    // خارج المدى المرسوم: لا مفرّ من إعادة الرسم وإلا خرجت الشمعة
    if (candle.close > handle.bounds.hi || candle.close < handle.bounds.lo) {
      STATE[containerId] = draw(document.getElementById(containerId),
                                handle.data, handle.opts);
      return true;
    }
    var svg = handle.svg;
    var rects = svg.querySelectorAll("rect");
    var lines = svg.querySelectorAll("line");
    if (!rects.length) return false;
    var rect = rects[rects.length - 1];
    var wick = lines[lines.length - 1];
    var b = handle.bounds;
    var h = svg.viewBox.baseVal.height;
    var ih = h - PAD.top - PAD.bottom;
    var y = function (p) { return PAD.top + (b.hi - p) / (b.hi - b.lo) * ih; };
    var rising = last.close >= last.open;
    var color = rising ? css("--up", "#26a69a") : css("--down", "#ef5350");
    var top = y(Math.max(last.open, last.close));
    var bot = y(Math.min(last.open, last.close));
    rect.setAttribute("y", top);
    rect.setAttribute("height", Math.max(1, bot - top));
    rect.setAttribute("fill", color);
    if (wick) {
      wick.setAttribute("y1", y(last.high));
      wick.setAttribute("y2", y(last.low));
      wick.setAttribute("stroke", color);
    }
    return true;
  }

  global.FallbackChart = { render: render, updateLatest: updateLatest,
                           available: true };
})(window);
