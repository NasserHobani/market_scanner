/**
 * Analytics page — each tab fetches on first open and never again unless the
 * user reloads, so switching tabs stays instant.
 */
(function () {
  "use strict";

  var pageData = (function () {
    var el = document.getElementById("page-data");
    try { return el ? JSON.parse(el.textContent) : {}; } catch (e) { return {}; }
  })();
  var qs = pageData.query || "";

  var PANELS = {
    trends: { id: "w-trends", url: "/api/widgets/trends/", render: ResearchWidgets.renderTrends },
    factors: { id: "w-factors", url: "/api/widgets/factors/", render: ResearchWidgets.renderFactors },
    splits: { id: "w-splits", url: "/api/widgets/splits/", render: ResearchWidgets.renderSplits },
  };

  DS.initTabs({
    tabsSelector: "#analytics-tabs",
    panelSelector: "#analytics-panels",
    syncUrl: true,
    onShow: function (name) {
      var p = PANELS[name];
      if (p) DS.loadWidget({ id: p.id, url: p.url + qs, render: p.render });
    },
  });
})();
