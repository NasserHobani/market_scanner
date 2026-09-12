/**
 * Research lab — statistical confidence leads, because it is the question the
 * page exists to answer.
 */
(function () {
  "use strict";

  var pageData = (function () {
    var el = document.getElementById("page-data");
    try { return el ? JSON.parse(el.textContent) : {}; } catch (e) { return {}; }
  })();
  var qs = pageData.query || "";

  function loadAutomationStatus() {
    return DS.loadWidget({
      id: "w-research-auto",
      url: "/api/research/status/",
      render: ResearchWidgets.renderAutomationStatus,
    });
  }
  loadAutomationStatus();
  EVERY(5000, loadAutomationStatus);

  var PANELS = {
    confidence: {
      id: "w-confidence", url: "/api/widgets/confidence/",
      render: ResearchWidgets.renderConfidence,
    },
    experiments: {
      id: "w-experiments", url: "/api/widgets/experiments/",
      render: ResearchWidgets.renderExperiments,
    },
    baselines: {
      id: "w-baselines", url: "/api/widgets/baselines/",
      render: ResearchWidgets.renderBaselines,
    },
  };

  DS.initTabs({
    tabsSelector: "#research-tabs",
    panelSelector: "#research-panels",
    syncUrl: true,
    onShow: function (name) {
      var p = PANELS[name];
      if (p) DS.loadWidget({ id: p.id, url: p.url + qs, render: p.render });
    },
  });
})();
