/* بثّ الأسعار اللحظي من WebSocket بينانس — مباشرة إلى المتصفح.
 *
 * لماذا من المتصفح لا من الخادم: البث عام ولا يحتاج مفتاحاً، فتمريره عبر
 * الخادم يضيف تأخيراً وحملاً بلا فائدة. الخادم يبقى مسؤولاً عن الإشارات وحدها.
 *
 * الحدّ الفاصل المهم: هذا الملف يحدّث الأسعار فقط. لا يحسب درجة ولا يغيّر
 * قراراً. الإشارة تبقى عند إغلاق الشمعة كما هي.
 */
(function (global) {
  "use strict";

  var HOSTS = [
    "wss://stream.binance.com:9443/stream?streams=",
    "wss://data-stream.binance.vision/stream?streams="
  ];
  var MAX_STREAMS = 200;

  function LiveFeed(options) {
    options = options || {};
    this.onTick = options.onTick || function () {};
    this.onStatus = options.onStatus || function () {};
    this.symbols = [];
    this.ws = null;
    this.hostIndex = 0;
    this.retries = 0;
    this.closedByUs = false;
    this.last = {};
    this.watchLifecycle();
  }

  LiveFeed.prototype.setSymbols = function (symbols) {
    var next = symbols
      .filter(function (s) { return /USDT$/.test(s); })
      .slice(0, MAX_STREAMS)
      .sort();
    if (next.join(",") === this.symbols.join(",")) return;
    this.symbols = next;
    this.connect();
  };

  LiveFeed.prototype.connect = function () {
    if (!this.symbols.length) { this.onStatus("idle"); return; }
    this.close();
    this.closedByUs = false;

    var streams = this.symbols.map(function (s) {
      return s.toLowerCase() + "@miniTicker";
    }).join("/");

    var url = HOSTS[this.hostIndex % HOSTS.length] + streams;
    var self = this;
    this.onStatus("connecting");

    try {
      this.ws = new WebSocket(url);
    } catch (e) {
      this.scheduleReconnect();
      return;
    }

    this.ws.onopen = function () {
      self.retries = 0;
      self.onStatus("live");
    };

    this.ws.onmessage = function (event) {
      var payload;
      try { payload = JSON.parse(event.data); } catch (e) { return; }
      var d = payload.data || payload;
      if (!d || !d.s) return;

      var price = parseFloat(d.c);
      var open = parseFloat(d.o);
      if (!isFinite(price)) return;

      var prev = self.last[d.s];
      self.last[d.s] = price;
      self.onTick({
        symbol: d.s,
        price: price,
        changePct: isFinite(open) && open > 0 ? (price - open) / open * 100 : null,
        direction: prev === undefined ? 0 : (price > prev ? 1 : price < prev ? -1 : 0),
        high: parseFloat(d.h),
        low: parseFloat(d.l)
      });
    };

    this.ws.onerror = function () { self.onStatus("error"); };

    this.ws.onclose = function () {
      if (self.closedByUs) return;
      // تبديل المضيف عند الفشل المتكرر — أحدهما قد يكون محجوباً على شبكتك
      self.hostIndex += 1;
      self.scheduleReconnect();
    };
  };

  LiveFeed.prototype.scheduleReconnect = function () {
    var self = this;
    this.retries += 1;
    var delay = Math.min(30000, 1000 * Math.pow(2, Math.min(this.retries, 5)));
    this.onStatus("reconnecting");
    setTimeout(function () { self.connect(); }, delay);
  };

  LiveFeed.prototype.close = function () {
    this.closedByUs = true;
    if (this.ws) {
      try { this.ws.close(); } catch (e) { /* تجاهل */ }
      this.ws = null;
    }
  };

  LiveFeed.prototype.isAlive = function () {
    return this.ws && this.ws.readyState === WebSocket.OPEN;
  };

  /* المتصفح يجمّد الصفحة عند التنقّل (Back-Forward Cache) فيُغلق الاتصال.
     عند العودة تبدو الأسعار حيّة وهي متوقفة — لذا نعيد الوصل صراحةً
     عند استعادة الصفحة أو عودتها للواجهة. */
  LiveFeed.prototype.watchLifecycle = function () {
    var self = this;
    var revive = function () {
      if (self.symbols.length && !self.isAlive()) {
        self.retries = 0;
        self.connect();
      }
    };
    global.addEventListener("pageshow", function (e) {
      if (e.persisted) revive();
    });
    global.addEventListener("online", revive);
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "visible") revive();
    });
  };

  global.LiveFeed = LiveFeed;
})(window);
