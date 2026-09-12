/**
 * Dashboard widget loader — independent parallel loading with skeletons,
 * lazy below-fold widgets, per-widget refresh intervals, and timing logs.
 */
(function (global) {
  "use strict";

  var registry = {};
  var timers = {};

  function log(widgetId, msg, data) {
    var prefix = "[Widget " + widgetId + "]";
    if (data !== undefined) {
      console.info(prefix, msg, data);
    } else {
      console.info(prefix, msg);
    }
  }

  function skeletonCards(n) {
    var html = '<div class="row g-2">';
    for (var i = 0; i < n; i++) {
      html += '<div class="col-6 col-md-3 col-lg-2"><div class="skel skel-card"></div></div>';
    }
    return html + "</div>";
  }

  function skeletonTable(rows) {
    var html = "";
    for (var i = 0; i < rows; i++) {
      html += '<div class="skel skel-table-row"></div>';
    }
    return html;
  }

  function defaultSkeleton(type) {
    if (type === "cards") return skeletonCards(6);
    if (type === "chart") return '<div class="skel skel-chart"></div>';
    if (type === "table") return skeletonTable(5);
    return '<div class="skel skel-line w75"></div><div class="skel skel-line w50"></div>';
  }

  function setState(el, state) {
    el.setAttribute("data-state", state);
  }

  function timingBadge(timing) {
    if (!timing) return "";
    var parts = [];
    if (timing.total_ms !== undefined) parts.push(timing.total_ms + "ms");
    if (timing.cache_hit) parts.push("cached");
    return '<span class="widget-timing">' + parts.join(" · ") + "</span>";
  }

  function loadWidget(id) {
    var cfg = registry[id];
    if (!cfg) return Promise.resolve();
    var el = document.getElementById(id);
    if (!el) return Promise.resolve();

    setState(el, "loading");
    var fetchStart = performance.now();

    return fetch(cfg.url, { credentials: "same-origin" })
      .then(function (res) {
        var apiMs = Math.round(performance.now() - fetchStart);
        return res.json().then(function (data) {
          return { data: data, apiMs: apiMs, ok: res.ok };
        });
      })
      .then(function (result) {
        var renderStart = performance.now();
        var content = el.querySelector(".widget-content");
        var errEl = el.querySelector(".widget-error");

        if (!result.ok || result.data.error) {
          setState(el, "error");
          if (errEl) {
            errEl.textContent = result.data.error || "تعذّر تحميل هذا القسم";
            errEl.style.display = "block";
          }
          log(id, "error", { apiMs: result.apiMs, error: result.data.error });
          if (cfg.onError) cfg.onError(el, result.data);
          return;
        }

        if (cfg.render && content) {
          cfg.render(content, result.data);
        }
        var timingEl = el.querySelector(".widget-timing-host");
        if (timingEl) {
          timingEl.innerHTML = timingBadge(result.data._timing);
        }
        setState(el, "ready");
        if (errEl) errEl.style.display = "none";

        var renderMs = Math.round(performance.now() - renderStart);
        var totalMs = Math.round(performance.now() - fetchStart);
        log(id, "loaded", {
          apiMs: result.apiMs,
          renderMs: renderMs,
          totalMs: totalMs,
          server: result.data._timing || null,
        });
        if (cfg.onLoad) cfg.onLoad(el, result.data);
      })
      .catch(function (err) {
        setState(el, "error");
        var errEl = el.querySelector(".widget-error");
        if (errEl) {
          errEl.textContent = "تعذّر الاتصال بالخادم";
          errEl.style.display = "block";
        }
        log(id, "fetch failed", err.message);
        if (cfg.onError) cfg.onError(el, { error: err.message });
      });
  }

  function scheduleRefresh(id) {
    var cfg = registry[id];
    if (!cfg || !cfg.interval) return;
    if (timers[id]) clearInterval(timers[id]);
    timers[id] = setInterval(function () { loadWidget(id); }, cfg.interval);
  }

  function register(id, config) {
    registry[id] = config;
  }

  function boot(options) {
    options = options || {};
    var eager = [];
    var lazy = [];

    Object.keys(registry).forEach(function (id) {
      var cfg = registry[id];
      if (cfg.lazy) {
        lazy.push(id);
      } else {
        eager.push(id);
      }
    });

    // Load eager widgets in parallel
    var promises = eager.map(function (id) { return loadWidget(id); });
    Promise.all(promises).then(function () {
      eager.forEach(scheduleRefresh);
    });

    // Lazy-load below-fold widgets via IntersectionObserver
    if (lazy.length && "IntersectionObserver" in window) {
      var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          var id = entry.target.id;
          observer.unobserve(entry.target);
          loadWidget(id).then(function () { scheduleRefresh(id); });
        });
      }, { rootMargin: "200px" });

      lazy.forEach(function (id) {
        var el = document.getElementById(id);
        if (el) observer.observe(el);
      });
    } else {
      lazy.forEach(function (id) {
        loadWidget(id).then(function () { scheduleRefresh(id); });
      });
    }

    if (options.onReady) options.onReady();
  }

  function refresh(id) {
    return loadWidget(id);
  }

  function refreshAll() {
    return Promise.all(Object.keys(registry).map(loadWidget));
  }

  global.DashboardWidgets = {
    register: register,
    boot: boot,
    refresh: refresh,
    refreshAll: refreshAll,
    load: loadWidget,
    defaultSkeleton: defaultSkeleton,
    INTERVALS: {
      OPEN_TRADES: 5000,
      DASHBOARD_CARDS: 30000,
      HEALTH: 60000,
      EQUITY: 60000,
      PERFORMANCE: 300000,
    },
  };
})(window);
