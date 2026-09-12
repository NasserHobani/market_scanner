/**
 * AI Advisor Explainability — manual analysis, review drawer, timeline.
 * AIA-05 additive UI layer; uses existing Claude pipeline via /api/ai/*
 */
(function (global) {
  "use strict";

  var DS = global.DS;
  if (!DS) return;

  var drawerEl = null;
  var backdropEl = null;
  var drawerCtrl = null;
  var pollTimer = null;
  var UI_LANG_KEY = "ai_ui_lang";
  var currentReviewState = null;
  var currentManualState = null;

  function getUiLang() {
    try {
      var v = localStorage.getItem(UI_LANG_KEY);
      return v === "en" ? "en" : "ar";
    } catch (e) { return "ar"; }
  }

  function setUiLang(lang) {
    try { localStorage.setItem(UI_LANG_KEY, lang === "en" ? "en" : "ar"); } catch (e) { /* ignore */ }
  }

  function langSelectorHtml() {
    var lang = getUiLang();
    return '<div class="ai-lang-switch" role="group" aria-label="Language">' +
      '<button type="button" class="ai-lang-btn' + (lang === "ar" ? " is-active" : "") +
      '" data-lang="ar">العربية</button>' +
      '<span class="ai-lang-sep">|</span>' +
      '<button type="button" class="ai-lang-btn' + (lang === "en" ? " is-active" : "") +
      '" data-lang="en">English</button></div>';
  }

  function wireLangSwitch(root, onSwitch) {
    if (!root) return;
    root.querySelectorAll(".ai-lang-btn").forEach(function (btn) {
      btn.onclick = function () {
        var l = btn.getAttribute("data-lang");
        setUiLang(l);
        root.querySelectorAll(".ai-lang-btn").forEach(function (b) {
          b.classList.toggle("is-active", b.getAttribute("data-lang") === l);
        });
        if (onSwitch) onSwitch();
      };
    });
  }

  function getPresentation(source) {
    if (!source) return null;
    var lang = getUiLang();
    var pres = source.presentations;
    if (pres && pres[lang]) return pres[lang];
    if (pres && pres.ar) return pres.ar;
    return null;
  }

  function setWidgetReady(widgetId) {
    var shell = document.getElementById(widgetId);
    if (shell) shell.setAttribute("data-state", "ready");
  }

  function ensureDrawer() {
    if (drawerEl) return;
    backdropEl = document.createElement("div");
    backdropEl.id = "ai-review-backdrop";
    backdropEl.className = "ds-drawer-backdrop";
    backdropEl.setAttribute("aria-hidden", "true");

    drawerEl = document.createElement("aside");
    drawerEl.id = "ai-review-drawer";
    drawerEl.className = "ds-drawer ds-drawer--wide";
    drawerEl.setAttribute("aria-hidden", "true");
    drawerEl.setAttribute("role", "dialog");
    drawerEl.innerHTML =
      '<div class="ds-drawer__head">' +
        '<div class="ds-drawer__title-row">' +
          '<div class="ai-drawer-head-text">' +
            '<h2 class="ds-drawer__title" id="ai-drawer-title">مراجعة الذكاء</h2>' +
            '<p class="ai-drawer-sub" id="ai-drawer-sub"></p>' +
          "</div>" +
          '<button type="button" class="ds-drawer__close" id="ai-drawer-close" aria-label="إغلاق">×</button>' +
        "</div>" +
      "</div>" +
      '<div class="ds-drawer__body" id="ai-drawer-body"></div>' +
      '<div class="ds-drawer__foot" id="ai-drawer-foot"></div>';

    document.body.appendChild(backdropEl);
    document.body.appendChild(drawerEl);
    drawerCtrl = DS.createDrawer("ai-review-drawer", "ai-review-backdrop");
    document.getElementById("ai-drawer-close").onclick = function () { drawerCtrl.close(); };
  }

  var AGREEMENT_LABEL = {
    agree: "متفق مع النظام",
    disagree: "مختلف مع النظام",
    partial: "متفق جزئيًا",
    unknown: "غير محدد",
  };

  function agreementTone(a) {
    a = (a || "").toLowerCase();
    if (a === "agree") return "success";
    if (a === "disagree") return "risk";
    return "warn";
  }

  function agreementLabel(a) {
    return AGREEMENT_LABEL[(a || "").toLowerCase()] || a || "—";
  }

  function fmtCost(v) {
    var n = DS.num(v);
    return n === null ? "—" : DS.ltr("$" + n.toFixed(4));
  }

  function fmtMs(v) {
    var n = DS.num(v);
    if (n === null) return "—";
    if (n >= 1000) return (n / 1000).toFixed(1) + " ث";
    return Math.round(n) + " ms";
  }

  function fmtInt(v) {
    var n = DS.num(v);
    return n === null ? "—" : Math.round(n).toLocaleString("en");
  }

  /** Claude replies in English; isolate it so RTL bidi keeps it readable. */
  function ltrBlock(text) {
    return '<p class="ai-ltr">' + DS.esc(text || "") + "</p>";
  }

  function metricGrid(items) {
    return '<div class="ai-metrics">' + items.map(function (m) {
      return '<div class="ai-metric">' +
        '<span class="ai-metric__label">' + DS.esc(m.label) + "</span>" +
        '<span class="ai-metric__value" dir="ltr">' + DS.esc(m.value) + "</span>" +
        (m.hint ? '<span class="ai-metric__hint">' + DS.esc(m.hint) + "</span>" : "") +
        "</div>";
    }).join("") + "</div>";
  }

  function sectionGroup(title) {
    return '<div class="ai-section-label">' + DS.esc(title) + "</div>";
  }

  /** @param {number} [count] Shown as a pill so a section's weight is visible closed. */
  function collapsible(title, bodyHtml, open, count) {
    var pill = count === undefined || count === null
      ? ""
      : '<span class="ai-collapse__count">' + count + "</span>";
    return '<details class="ai-collapse"' + (open ? " open" : "") + ">" +
      "<summary><span class=\"ai-collapse__title\">" + DS.esc(title) + "</span>" +
      pill + "</summary>" +
      '<div class="ai-collapse__body">' + bodyHtml + "</div></details>";
  }

  function evidenceList(items, kind) {
    if (!items || !items.length) return '<p class="ai-empty">لا عناصر.</p>';
    var mod = kind === "against" ? " ai-evidence--against" : " ai-evidence--support";
    return '<ul class="ai-evidence-list">' + items.map(function (ev) {
      var id = ev.evidence_id || "";
      var head = ev.href
        ? '<a href="' + DS.esc(ev.href) + '" class="ai-ev-link">' + DS.esc(id) + "</a>"
        : '<span class="ai-ev-link">' + DS.esc(id) + "</span>";
      return '<li class="ai-evidence' + mod + '">' +
        '<div class="ai-evidence__head">' + head +
        '<span class="ai-ev-section">' + DS.esc(ev.label || ev.section || "") + "</span></div>" +
        '<p class="ai-evidence__note ai-ltr">' + DS.esc(ev.note || "") + "</p></li>";
    }).join("") + "</ul>";
  }

  function bulletList(items, tone) {
    if (!items || !items.length) return '<p class="ai-empty">لا عناصر.</p>';
    var cls = "ai-bullets" + (tone === "risk" ? " ai-bullets--risk" : "");
    return '<ul class="' + cls + '">' + items.map(function (x) {
      return '<li class="ai-ltr">' + DS.esc(x) + "</li>";
    }).join("") + "</ul>";
  }

  function reasoningBlock(text) {
    var body = (text || "").trim();
    var chunks = body ? body.split(/\n{2,}/) : [];
    if (chunks.length <= 1 && body.length > 400) {
      chunks = body.replace(/([.!?])\s+/g, "$1\n\n").split(/\n{2,}/);
    }
    var paras = chunks.length
      ? chunks.map(function (p) {
          return '<p class="ai-reasoning-p">' + DS.esc(p.trim()) + "</p>";
        }).join("")
      : '<p class="ai-empty">لا يوجد نص تفكير.</p>';
    return '<div class="ai-reasoning-wrap" data-reasoning="1">' +
      '<div class="ai-reasoning-actions">' +
        '<button type="button" class="ds-btn ds-btn--sm ai-expand-btn">توسيع الكل</button>' +
        '<button type="button" class="ds-btn ds-btn--sm ai-copy-btn">نسخ</button>' +
      "</div>" +
      '<div class="ai-reasoning-full ai-ltr" id="ai-reasoning-text">' + paras + "</div></div>";
  }

  function wireReasoningActions(root, rawText) {
    var wrap = root.querySelector("[data-reasoning]");
    var box = root.querySelector("#ai-reasoning-text");
    var copy = root.querySelector(".ai-copy-btn");
    var expand = root.querySelector(".ai-expand-btn");
    if (wrap) wrap._rawReasoning = rawText || "";
    if (copy) {
      copy.onclick = function () {
        if (!navigator.clipboard) return;
        var raw = (wrap && wrap._rawReasoning) || (box && box.textContent) || "";
        navigator.clipboard.writeText(raw).then(function () {
          copy.textContent = "نُسخ ✓";
          setTimeout(function () { copy.textContent = "نسخ"; }, 2000);
        });
      };
    }
    if (expand && box) {
      expand.onclick = function () {
        var open = box.classList.toggle("is-expanded");
        expand.textContent = open ? "طيّ" : "توسيع الكل";
      };
    }
  }

  function signalList(signals, tone) {
    if (!signals || !signals.length) return "";
    var mod = tone === "neg" ? " ai-signals--neg" : " ai-signals--pos";
    return '<ul class="ai-signals' + mod + '">' + signals.map(function (s) {
      var icon = tone === "neg" ? "✗" : "✓";
      var text = typeof s === "string" ? s : (s.text || "");
      var href = typeof s === "object" && s.href;
      var link = href
        ? '<a href="' + DS.esc(s.href) + '" class="ai-ev-statement-link">' + DS.esc(text) + "</a>"
        : DS.esc(text);
      var ev = typeof s === "object" && s.evidence_id
        ? ' <span class="ai-ev-id" dir="ltr">(' + DS.esc(s.evidence_id) + ")</span>"
        : "";
      return "<li>" + icon + " " + link + ev + "</li>";
    }).join("") + "</ul>";
  }

  function simpleBullets(items, tone) {
    if (!items || !items.length) return "";
    return '<ul class="ai-bullets' + (tone === "risk" ? " ai-bullets--risk" : "") + '">' +
      items.map(function (x) {
        return "<li>" + DS.esc(x) + "</li>";
      }).join("") + "</ul>";
  }

  function renderTechnicalEvidence(p, review) {
    var tech = (p && p.technical) || {};
    var body = reasoningBlock(tech.reasoning || (review && review.reasoning) || "");
    body += evidenceList(tech.supporting_evidence || (review && review.supporting_evidence) || [], "support");
    body += evidenceList(tech.contradicting_evidence || (review && review.contradicting_evidence) || [], "against");
    var diag = tech.package_diagnostics || (review && review.package_diagnostics) || {};
    if (diag.package_version || diag.evidence_count != null) {
      body += '<div class="ai-pkg-strip">' +
        (diag.package_version
          ? '<span>Package <b dir="ltr">' + DS.esc(String(diag.package_version)) + "</b></span>" : "") +
        (diag.evidence_count != null
          ? "<span>Evidence <b>" + DS.esc(String(diag.evidence_count)) + "</b></span>" : "") +
        "</div>";
    }
    var val = tech.validation || {};
    if (val.grounding_score != null || val.hallucination_score != null) {
      body += '<p class="ds-text-xs ds-text-muted">Grounding ' +
        DS.esc(String(val.grounding_score != null ? val.grounding_score : "—")) +
        " · Hallucination " +
        DS.esc(String(val.hallucination_score != null ? val.hallucination_score : "—")) +
        "</p>";
    }
    if (tech.provider || tech.model) {
      body += '<p class="ds-text-xs ds-text-muted" dir="ltr">' +
        DS.esc(tech.provider || "") + " · " + DS.esc(tech.model || "") + "</p>";
    }
    return collapsible(tech.title || "الأدلة التقنية", body, false);
  }

  function renderPresentationBlock(p, review) {
    if (!p) {
      return '<p class="ai-empty">' + (getUiLang() === "ar"
        ? "لا يوجد عرض محلي — يُعرض النص الأصلي أدناه."
        : "No localized presentation — showing original text below.") + "</p>";
    }
    var isEn = p.language === "en";
    var L = function (ar, en) { return isEn ? en : ar; };
    var html = '<div class="ai-presentation" dir="' + (isEn ? "ltr" : "rtl") + '">';

    html += '<div class="ai-pres-header">';
    html += '<h3 class="ai-pres-title">🧠 ' + DS.esc(p.title) + "</h3>";
    if (p.symbol) {
      html += '<p class="ai-pres-meta"><span dir="ltr">' + DS.esc(p.symbol) +
        (p.timeframe ? " · " + DS.esc(p.timeframe) : "") + "</span></p>";
    }
    html += "</div>";

    html += '<div class="ai-pres-top">';
    html += '<div class="ai-pres-agreement">' +
      DS.StatusBadge({ label: p.agreement_label, tone: p.agreement_tone, dot: true }) +
      "</div>";
    html += '<div class="ai-pres-confidence">' +
      '<span class="ai-pres-confidence__label">' + DS.esc(p.confidence_label) + "</span>" +
      '<span class="ai-pres-confidence__value ds-value-' + p.agreement_tone + '">' +
      DS.esc(p.confidence_display) + "</span></div>";
    html += "</div>";

    html += '<div class="ai-pres-section"><h4 class="ai-pres-section__title">' +
      L("القرار الحالي", "Current recommendation") + "</h4>" +
      '<p class="ai-pres-verdict__value">' + DS.esc(p.advisor_decision || p.final_verdict || "") +
      "</p></div>";
    html += DS.StatGrid([
      { label: L("الاتجاه الحالي", "Current view"), value: p.current_market_view || "—" },
      { label: L("النظرة 3–7 أيام", "3–7 day outlook"), value: p.near_term_outlook || "—" },
      { label: L("ثقة المستشار", "Advisor confidence"), value: p.advisor_confidence_display || p.confidence_display },
      { label: L("قرار المنصة", "Platform"), value: p.platform_decision || "—" },
    ], 4);

    if (p.disagreement) {
      var d = p.disagreement;
      html += '<div class="ai-pres-card ai-pres-card--warn">';
      html += "<h4>" + DS.esc(d.title) + "</h4>";
      html += '<dl class="ds-kv">';
      html += "<dt>" + DS.esc((d.labels && d.labels.platform) || L("قرار المنصة", "Platform")) +
        "</dt><dd>" + DS.esc(d.platform_decision || "") + "</dd>";
      html += "<dt>" + DS.esc((d.labels && d.labels.claude) || L("رأي المستشار", "Advisor")) +
        "</dt><dd>" + DS.esc(d.claude_opinion || "") + "</dd>";
      html += "</dl>";
      if (d.why && d.why.length) {
        html += "<h5>" + DS.esc((d.labels && d.labels.why) || L("لماذا؟", "Why?")) + "</h5>";
        html += simpleBullets(d.why, "risk");
      }
      if (d.key_point) {
        html += "<h5>" + DS.esc((d.labels && d.labels.key) || L("أهم نقطة خلاف", "Key disagreement")) +
          "</h5><p>" + DS.esc(d.key_point) + "</p>";
      }
      if (d.watch_for) {
        html += "<h5>" + DS.esc((d.labels && d.labels.watch) || L("ماذا نراقب؟", "What to watch")) +
          "</h5><p>" + DS.esc(d.watch_for) + "</p>";
      }
      html += "</div>";
    }

    if (p.partial) {
      var pt = p.partial;
      html += '<div class="ai-pres-card ai-pres-card--warn">';
      html += "<h4>" + DS.esc(pt.title) + "</h4>";
      if (pt.agrees_with && pt.agrees_with.length) {
        html += "<h5>" + L("ما يتفق عليه المستشار", "What the advisor agrees with") + "</h5>";
        html += simpleBullets(pt.agrees_with);
      }
      if (pt.disagrees_with && pt.disagrees_with.length) {
        html += "<h5>" + L("ما يختلف فيه", "What the advisor disagrees with") + "</h5>";
        html += simpleBullets(pt.disagrees_with, "risk");
      }
      if (pt.why) html += "<p>" + DS.esc(pt.why) + "</p>";
      html += "</div>";
    }

    if (p.executive_summary) {
      html += '<div class="ai-pres-section"><h4 class="ai-pres-section__title">' +
        L("النظرة العامة", "Overview") + "</h4>" +
        '<p class="ai-pres-summary">' + DS.esc(p.executive_summary) + "</p></div>";
    }
    if (p.actionable_advice) {
      html += '<div class="ai-pres-section"><h4 class="ai-pres-section__title">' +
        L("ماذا أفعل الآن؟", "What should I do now?") + "</h4>" +
        "<p>" + DS.esc(p.actionable_advice) + "</p></div>";
    }
    if (p.positive_signals && p.positive_signals.length) {
      html += '<div class="ai-pres-section"><h4 class="ai-pres-section__title">' +
        L("أهم الإشارات الإيجابية", "Positive signals") + "</h4>" +
        signalList(p.positive_signals, "pos") + "</div>";
    }
    if (p.negative_signals && p.negative_signals.length) {
      html += '<div class="ai-pres-section"><h4 class="ai-pres-section__title">' +
        L("إشارات سلبية / تعارض", "Negative signals") + "</h4>" +
        signalList(p.negative_signals, "neg") + "</div>";
    }
    var sc = p.scenarios || {};
    if (sc.bullish || sc.base || sc.bearish) {
      html += '<div class="ai-pres-section"><h4 class="ai-pres-section__title">' +
        L("تحليل السيناريوهات", "Scenario analysis") + "</h4>";
      if (sc.bullish) {
        html += "<h5>" + L("السيناريو الصاعد", "Bullish scenario") + "</h5><p>" +
          DS.esc(sc.bullish) + "</p>";
      }
      if (sc.base) {
        html += "<h5>" + L("السيناريو الأساسي", "Base scenario") + "</h5><p>" +
          DS.esc(sc.base) + "</p>";
      }
      if (sc.bearish) {
        html += "<h5>" + L("السيناريو الهابط", "Bearish scenario") + "</h5><p>" +
          DS.esc(sc.bearish) + "</p>";
      }
      html += "</div>";
    }
    if (p.missing_information && p.missing_information.length) {
      html += '<div class="ai-pres-section"><h4 class="ai-pres-section__title">' +
        L("معلومات ناقصة", "Missing information") + "</h4>" +
        simpleBullets(p.missing_information) + "</div>";
    }
    if (p.main_risks && p.main_risks.length) {
      html += '<div class="ai-pres-section ai-pres-section--risk"><h4 class="ai-pres-section__title">' +
        L("أهم المخاطر", "Key risks") + "</h4>" +
        simpleBullets(p.main_risks, "risk") + "</div>";
    }
    if (p.what_to_watch && p.what_to_watch.length) {
      html += '<div class="ai-pres-section"><h4 class="ai-pres-section__title">' +
        L("ماذا أراقب الآن؟", "What to watch") + "</h4>" +
        simpleBullets(p.what_to_watch) + "</div>";
    }
    if (p.invalidation_conditions && p.invalidation_conditions.length) {
      html += '<div class="ai-pres-section"><h4 class="ai-pres-section__title">' +
        L("متى يتغير رأيي؟", "When would the view change?") + "</h4>" +
        simpleBullets(p.invalidation_conditions) + "</div>";
    } else if (p.what_could_change) {
      html += '<div class="ai-pres-section"><h4 class="ai-pres-section__title">' +
        L("متى يتغير رأيي؟", "When would the view change?") + "</h4>" +
        '<p class="ai-pres-change">' + DS.esc(p.what_could_change) + "</p></div>";
    }
    if (p.data_quality_note) {
      html += '<div class="ai-pres-section"><h4 class="ai-pres-section__title">' +
        L("جودة البيانات", "Data quality") + "</h4>" +
        "<p>" + DS.esc(p.data_quality_note) + "</p></div>";
    }

    html += '<div class="ai-pres-section"><h4 class="ai-pres-section__title">' +
      L("الثقات المنفصلة", "Separate confidences") + "</h4>" +
      DS.StatGrid([
        { label: L("ثقة المنصة", "Platform confidence"), value: p.platform_confidence_display || "—" },
        { label: L("الاحتمال الإحصائي", "Statistical probability"), value: p.prediction_probability_display || "—" },
        { label: L("ثقة المستشار", "Advisor confidence"), value: p.advisor_confidence_display || p.confidence_display },
      ], 3) + "</div>";

    html += '<div class="ai-pres-verdict"><h4 class="ai-pres-section__title">' +
      L("الخلاصة / القرار", "Conclusion") + "</h4>" +
      '<p class="ai-pres-verdict__value">' + DS.esc(p.final_verdict || "") + "</p>" +
      '<p class="ds-text-muted">' + L("النظرة خلال 3–7 أيام", "3–7 day outlook") + ": " +
      DS.esc(p.near_term_outlook || "—") + "</p></div>";

    html += "</div>";
    html += renderTechnicalEvidence(p, review);
    return html;
  }

  function drawerLangBar() {
    return '<div class="ai-drawer-lang">' + langSelectorHtml() + "</div>";
  }

  function exportBar(reviewId) {
    var base = "/api/ai/reviews/" + encodeURIComponent(reviewId) + "/export/?format=";
    return '<a class="ds-btn" href="' + base + 'json" download>JSON</a>' +
      '<a class="ds-btn" href="' + base + 'markdown" download>Markdown</a>' +
      '<a class="ds-btn" href="' + base + 'pdf" download>PDF</a>';
  }

  function formatFusionBlock(review) {
    var f = review.fusion || {};
    if (!f || !f.fusion_state) {
      return '<p class="ai-empty">لا يوجد دمج تنبؤ — التنبؤ غير متاح أو لم تُسجّل مراجعة بعد.</p>';
    }
    var predAvail = f.prediction_available;
    var prob = f.prediction_probability;
    var probStr = prob != null ? DS.fmtPct(Number(prob) * 100, 1) : "—";
    return '<dl class="ds-kv">' +
      "<dt>المنصة</dt><dd>" + DS.esc(f.platform_action || "—") + "</dd>" +
      "<dt>ثقة المنصة</dt><dd>" + (f.platform_confidence != null
        ? DS.fmtPct(Number(f.platform_confidence) * 100, 1) : "—") + "</dd>" +
      "<dt>LightGBM</dt><dd>" + (predAvail ? DS.esc(f.prediction_label || "WIN/LOSS") : "UNAVAILABLE") + "</dd>" +
      "<dt>احتمال إحصائي</dt><dd>" + probStr + "</dd>" +
      "<dt>تقييم LLM</dt><dd>" + DS.esc(f.llm_prediction_assessment || f.llm_agreement || "—") + "</dd>" +
      "<dt>ثقة LLM</dt><dd>" + (f.llm_confidence != null ? DS.fmtNum(f.llm_confidence, 0) + "%" : "—") + "</dd>" +
      "<dt>حالة الدمج</dt><dd><strong>" + DS.esc(f.fusion_state || "—") + "</strong></dd>" +
      "</dl>";
  }

  function paintReviewDrawer(review) {
    var body = document.getElementById("ai-drawer-body");
    var rid = review.review_id || "";
    var p = getPresentation(review);
    var typeLabel = review.review_type === "manual" ? "يدوي" : "تلقائي";

    var metrics = metricGrid([
      { label: "المزوّد", value: review.provider || "—" },
      { label: "النموذج", value: review.model || "—" },
      { label: "زمن الاستجابة", value: fmtMs(review.latency_ms), hint: "Latency" },
      { label: "التوكنات", value: fmtInt(review.total_tokens),
        hint: "مدخل " + fmtInt(review.prompt_tokens) + " · مخرج " + fmtInt(review.completion_tokens) },
      { label: "التكلفة", value: (function () {
          var n = DS.num(review.estimated_cost);
          return n === null ? "—" : "$" + n.toFixed(4);
        })() },
      { label: "التأريض", value: (DS.fmtNum(review.grounding_score, 1) || "—"),
        hint: "هلوسة " + (DS.fmtNum(review.hallucination_score, 1) || "0") },
    ]);

    body.innerHTML =
      drawerLangBar() +
      renderPresentationBlock(p, review) +
      '<div class="ai-drawer-meta-badges">' +
        DS.StatusBadge({ label: typeLabel, tone: "neutral" }) +
        DS.StatusBadge({
          label: review.status === "accepted" || review.review_status === "accepted"
            ? "مقبول" : (review.review_status || "مكتمل"),
          tone: "info",
        }) +
        (review.timestamp
          ? '<span class="ds-text-xs ds-text-muted">' +
            DS.esc(String(review.timestamp).slice(0, 19).replace("T", " ")) + " UTC</span>"
          : "") +
      "</div>" +
      metrics +
      sectionGroup("دمج التنبؤ") +
      collapsible("دمج التنبؤ", formatFusionBlock(review), true) +
      sectionGroup(getUiLang() === "ar" ? "بعد الصفقة" : "Post-trade") +
      collapsible(getUiLang() === "ar" ? "نتيجة الصفقة" : "Trade result",
        formatTradeResult(review.trade_result), false) +
      collapsible(getUiLang() === "ar" ? "التقييم" : "Evaluation",
        formatEval(review.evaluation), false) +
      collapsible(getUiLang() === "ar" ? "التعلّم" : "Learning",
        formatLearning(review.learning), false) +
      collapsible(getUiLang() === "ar" ? "التجربة المقترحة" : "Suggested experiment",
        formatExperiment(review.suggested_experiment), false);

    document.getElementById("ai-drawer-foot").innerHTML =
      '<span class="ai-drawer-foot__hint">تصدير المراجعة</span>' + exportBar(rid);
    wireLangSwitch(body, function () { paintReviewDrawer(currentReviewState); });
    wireReasoningActions(body, (p && p.technical && p.technical.reasoning) || review.reasoning || "");
  }

  function renderReviewDrawer(review) {
    ensureDrawer();
    currentReviewState = review;
    currentManualState = null;
    var sym = review.symbol || "مراجعة";
    var rid = review.review_id || "";

    document.getElementById("ai-drawer-title").textContent = sym;
    var sub = document.getElementById("ai-drawer-sub");
    if (sub) {
      sub.innerHTML =
        '<span dir="ltr">' + DS.esc(rid) + "</span>" +
        (review.market ? " · " + DS.esc(review.market) : "") +
        (review.timeframe ? " · " + DS.esc(review.timeframe) : "") +
        (sym && review.market
          ? ' · <a class="ai-drawer-sym-link" href="/symbol/' +
            DS.esc(review.market) + "/" + encodeURIComponent(sym) +
            '/?tf=' + encodeURIComponent(review.timeframe || "4h") + '">صفحة الرمز</a>'
          : "");
    }
    paintReviewDrawer(review);
    drawerCtrl.open();
  }

  function formatTradeResult(tr) {
    tr = tr || {};
    if (!tr.outcome) return '<p class="ai-empty">لم تُغلق الصفقة بعد.</p>';
    var yesNo = function (v) { return v === true ? "نعم" : v === false ? "لا" : "—"; };
    return '<dl class="ds-kv">' +
      "<dt>النتيجة</dt><dd>" + DS.esc(tr.outcome) + "</dd>" +
      "<dt>العائد</dt><dd>" + DS.fmtR(tr.r_multiple) + "</dd>" +
      "<dt>وافق Claude؟</dt><dd>" + yesNo(tr.claude_agreed) + "</dd>" +
      "<dt>هل كان صائباً؟</dt><dd>" + yesNo(tr.claude_correct) + "</dd>" +
      "<dt>وُلّد درس؟</dt><dd>" + yesNo(tr.learning_generated) + "</dd>" +
      "</dl>";
  }

  function formatExperiment(exp) {
    if (!exp || !exp.hypothesis) return '<p class="ai-empty">لا تجربة مقترحة.</p>';
    return '<dl class="ds-kv">' +
      "<dt>الفرضية</dt><dd class=\"ai-ltr\">" + DS.esc(exp.hypothesis) + "</dd>" +
      "<dt>الطريقة</dt><dd class=\"ai-ltr\">" + DS.esc(exp.method || "") + "</dd>" +
      "<dt>المتوقّع</dt><dd class=\"ai-ltr\">" + DS.esc(exp.expected_outcome || "") + "</dd>" +
      "</dl>";
  }

  function formatEval(ev) {
    if (!ev) return '<p class="ai-empty">لا يوجد تقييم بعد — يُنشأ بعد إغلاق الصفقة.</p>';
    return '<dl class="ds-kv">' +
      "<dt>نتيجة الصفقة</dt><dd>" + DS.esc(ev.trade_result || "—") + "</dd>" +
      "<dt>اتفاق المستشار</dt><dd>" + agreementLabel(ev.advisor_agreement) + "</dd>" +
      "<dt>كان صائباً</dt><dd>" + (ev.advisor_correct ? "نعم" : "لا") + "</dd>" +
      "<dt>تحذير مفيد</dt><dd>" + (ev.useful_warning ? "نعم" : "لا") + "</dd>" +
      "</dl>";
  }

  function formatLearning(lr) {
    if (!lr || !lr.lessons || !lr.lessons.length) {
      return '<p class="ai-empty">لا دروس مرتبطة بعد.</p>';
    }
    return bulletList(lr.lessons.map(function (l) { return l.title || l.lesson_id || ""; }));
  }

  function renderCompareBlock(compare) {
    if (!compare) return "";
    var plat = compare.platform_decision || "—";
  function agreeLabel(a) {
    if (!a) return "—";
    return a.toLowerCase() === "agree" ? "موافق" : (a.toLowerCase() === "disagree" ? "غير موافق" : a);
  }
    return '<div class="ai-compare-grid">' +
      '<div class="ai-compare-platform"><strong>قرار المنصة</strong><div class="ai-compare-value">' +
        DS.esc(plat) + "</div></div>" +
      '<div class="ai-compare-side"><strong>Claude</strong>' +
        "<div>" + agreeLabel(compare.claude && compare.claude.agreement) + " · " +
        DS.fmtNum(compare.claude && compare.claude.confidence, 0) + "%</div>" +
        "<div class=\"ds-text-xs ds-text-muted\">" +
        DS.fmtNum(compare.claude && compare.claude.latency_ms, 0) + " ms · $" +
        Number((compare.claude && compare.claude.estimated_cost) || 0).toFixed(4) +
        "</div></div>" +
      '<div class="ai-compare-side"><strong>Qwen</strong>' +
        "<div>" + agreeLabel(compare.ollama && compare.ollama.agreement) + " · " +
        DS.fmtNum(compare.ollama && compare.ollama.confidence, 0) + "%</div>" +
        "<div class=\"ds-text-xs ds-text-muted\">" +
        DS.fmtNum(compare.ollama && compare.ollama.latency_ms, 0) + " ms · $0</div></div>" +
      "</div>";
  }

  function paintManualDrawer(data) {
    var body = document.getElementById("ai-drawer-body");
    var m = data.manual || {};
    var met = data.metrics || {};
    var report = data.report || {};
    var compareHtml = data.compare ? renderCompareBlock(data.compare) : "";
    var reviewLike = report.review_id ? report : {
      presentations: data.presentations,
      review_id: data.review_id,
      symbol: data.symbol,
      timeframe: data.timeframe,
      reasoning: (m.detailed_analysis || {}).full_reasoning,
      supporting_evidence: m.positive_signals,
      contradicting_evidence: m.negative_signals,
      package_diagnostics: data.package_diagnostics,
    };
    if (!reviewLike.presentations && data.presentations) {
      reviewLike.presentations = data.presentations;
    }
    var p = getPresentation(reviewLike);

    body.innerHTML =
      drawerLangBar() +
      compareHtml +
      renderPresentationBlock(p, reviewLike) +
      '<div class="ai-drawer-meta-badges">' +
        DS.StatusBadge({ label: "يدوي", tone: "neutral" }) +
        (data.cached
          ? DS.StatusBadge({ label: "من الذاكرة المؤقتة", tone: "warn" })
          : DS.StatusBadge({ label: "جديد", tone: "info" })) +
      "</div>" +
      metricGrid([
        { label: "زمن الاستجابة", value: fmtMs(met.latency_ms) },
        { label: "التوكنات", value: fmtInt(met.total_tokens),
          hint: "مدخل " + fmtInt(met.prompt_tokens) + " · مخرج " + fmtInt(met.completion_tokens) },
        { label: "التكلفة", value: (function () {
            var n = DS.num(met.estimated_cost);
            return n === null ? "—" : "$" + n.toFixed(4);
          })() },
        { label: "السيناريو", value: m.expected_scenario || "—" },
      ]) +
      collapsible(getUiLang() === "ar" ? "مناطق الدخول والوقف والهدف" : "Entry / stop / target",
        '<dl class="ds-kv">' +
          "<dt>" + (getUiLang() === "ar" ? "الدخول" : "Entry") + "</dt><dd>" +
          DS.esc(m.suggested_entry_zone || "—") + "</dd>" +
          "<dt>" + (getUiLang() === "ar" ? "الوقف" : "Stop") + "</dt><dd>" +
          DS.esc(m.suggested_stop_zone || "—") + "</dd>" +
          "<dt>" + (getUiLang() === "ar" ? "الهدف" : "Target") + "</dt><dd>" +
          DS.esc(m.suggested_target_zone || "—") + "</dd>" +
        "</dl>", false) +
      collapsible(getUiLang() === "ar" ? "هل أنتظر؟" : "Should I wait?",
        ltrBlock(m.should_wait), false);

    document.getElementById("ai-drawer-foot").innerHTML = data.review_id
      ? '<button type="button" class="ds-btn ds-btn--primary" id="ai-open-full-review">' +
        (getUiLang() === "ar" ? "عرض التحليل الكامل" : "Full review") + "</button>" +
        exportBar(data.review_id)
      : "";
    var fullBtn = document.getElementById("ai-open-full-review");
    if (fullBtn) fullBtn.onclick = function () { openReview(data.review_id); };
    wireLangSwitch(body, function () { paintManualDrawer(currentManualState); });
    wireReasoningActions(body, (m.detailed_analysis || {}).full_reasoning || "");
  }

  function renderManualAnalysis(data) {
    ensureDrawer();
    currentManualState = data;
    currentReviewState = null;
    document.getElementById("ai-drawer-title").textContent = data.symbol || "تحليل يدوي";
    var subEl = document.getElementById("ai-drawer-sub");
    if (subEl) {
      subEl.innerHTML = data.review_id
        ? '<span dir="ltr">' + DS.esc(data.review_id) + "</span> · تحليل يدوي"
        : "تحليل يدوي";
    }
    paintManualDrawer(data);
    renderLastAnalysisStrip(data);
    drawerCtrl.open();
  }

  function openReview(reviewId) {
    fetch("/api/ai/reviews/" + encodeURIComponent(reviewId) + "/")
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.ok && d.review) renderReviewDrawer(d.review);
      });
  }

  function renderLiveCard(el, live) {
    setWidgetReady("w-live-review");
    if (!live) {
      el.innerHTML = DS.SectionCard({ title: "مراجعة مباشرة",
        body: '<p class="ds-text-muted">لا توجد مراجعة حديثة بعد. تظهر هنا فور انتهاء Claude من مراجعة إشارة.</p>' });
      return;
    }
    var pres = getPresentation(live) || {};
    var agreeLbl = pres.agreement_label || agreementLabel(live.agreement);
    var reason = pres.executive_summary || live.reason || "";
    el.innerHTML = DS.SectionCard({
      title: "مراجعة مباشرة",
      meta: live.timestamp ? live.timestamp.slice(0, 19) : "",
      body:
        '<div class="ai-live-card">' +
          '<div class="ai-live-card__head">' +
            "<strong>" + DS.esc(live.symbol) + "</strong>" +
            (live.timeframe ? '<span class="ds-text-xs ds-text-muted" dir="ltr">' +
              DS.esc(live.timeframe) + "</span>" : "") +
            DS.StatusBadge({ label: agreeLbl, tone: agreementTone(live.agreement), dot: true }) +
            '<span class="ds-text-xs ds-text-muted">' +
              (pres.confidence_label || "درجة ثقة Claude") + " " +
              DS.fmtNum(live.confidence, 0) + "%</span>" +
          "</div>" +
          (pres.final_verdict
            ? '<p class="ai-live-card__verdict">' + DS.esc(pres.final_verdict) + "</p>"
            : "") +
          '<p class="ai-live-card__reason">' + DS.esc(reason) + "</p>" +
          '<div class="ai-live-card__meta">' +
            fmtMs(live.latency_ms) + " · " + fmtInt(live.total_tokens) + " توكن · " +
            fmtCost(live.estimated_cost) +
          "</div>" +
          (live.review_id
            ? '<button type="button" class="ds-btn ds-btn--sm ai-open-review" data-id="' +
              DS.esc(live.review_id) + '">التفاصيل</button>'
            : "") +
        "</div>",
    });
    var btn = el.querySelector(".ai-open-review");
    if (btn) btn.onclick = function () { openReview(btn.getAttribute("data-id")); };
  }

  function renderHistoryTable(el, data, onPage) {
    var items = (data && data.items) || [];
    var lang = getUiLang();
    var rows = items.map(function (r) {
      var typeLabel = r.review_type === "manual" ? "يدوي" : "تلقائي";
      var verdict = r.verdict || r.verdict_ar || (r.decision || "").toUpperCase();
      var agreeLbl = r.agreement_label || agreementLabel(r.agreement);
      return "<tr class=\"ai-hist-row\" data-id=\"" + DS.esc(r.review_id) + "\">" +
        "<td dir=\"ltr\">" + DS.esc((r.timestamp || "").slice(0, 16).replace("T", " ")) + "</td>" +
        "<td><strong>" + DS.esc(r.pair || r.symbol) + "</strong></td>" +
        "<td dir=\"ltr\">" + DS.esc(r.timeframe || "—") + "</td>" +
        "<td>" + DS.esc(verdict) + "</td>" +
        "<td>" + DS.StatusBadge({
          label: agreeLbl,
          tone: agreementTone(r.agreement),
        }) + "</td>" +
        "<td dir=\"ltr\">" + DS.fmtNum(r.confidence, 0) + "%</td>" +
        "<td>" + DS.esc(r.provider || "") + "</td>" +
        "<td>" + DS.esc(lang === "ar" ? "العربية" : "English") + "</td>" +
        "<td>" + DS.esc(typeLabel) + "</td>" +
        "</tr>";
    }).join("");

    var pager = "";
    if (data && data.pages > 1) {
      pager = '<div class="ai-pager">';
      for (var p = 1; p <= Math.min(data.pages, 20); p++) {
        pager += '<button type="button" class="ds-btn ds-btn--sm ai-page-btn' +
          (p === data.page ? " is-active" : "") + '" data-page="' + p + '">' + p + "</button> ";
      }
      pager += "</div>";
    }

    el.innerHTML =
      '<div class="ai-search-bar">' +
        '<input type="search" id="ai-review-search" placeholder="بحث: رمز، معرّف، مزوّد…" class="ds-input">' +
        '<select id="ai-review-type" class="ds-input"><option value="">كل الأنواع</option>' +
        '<option value="automatic">تلقائي</option><option value="manual">يدوي</option></select>' +
      "</div>" +
      '<div class="table-wrap"><table class="table data-table"><thead><tr>' +
      "<th>الوقت</th><th>الرمز</th><th>الفريم</th><th>القرار</th><th>اتفاق</th><th>ثقة</th>" +
      "<th>مزوّد</th><th>اللغة</th><th>نوع</th>" +
      "</tr></thead><tbody>" + (rows || '<tr><td colspan="9">لا مراجعات</td></tr>') +
      "</tbody></table></div>" + pager;

    el.querySelectorAll(".ai-hist-row").forEach(function (row) {
      row.style.cursor = "pointer";
      row.onclick = function () { openReview(row.getAttribute("data-id")); };
    });
    el.querySelectorAll(".ai-page-btn").forEach(function (btn) {
      btn.onclick = function () { onPage(parseInt(btn.getAttribute("data-page"), 10)); };
    });
    var search = document.getElementById("ai-review-search");
    var typeSel = document.getElementById("ai-review-type");
    function doSearch() {
      var q = search ? search.value : "";
      var t = typeSel ? typeSel.value : "";
      fetch("/api/ai/reviews/?page=1&q=" + encodeURIComponent(q) +
        "&type=" + encodeURIComponent(t))
        .then(function (r) { return r.json(); })
        .then(function (d) { if (d.ok) renderHistoryTable(el, d, onPage); });
    }
    if (search) search.onchange = doSearch;
    if (typeSel) typeSel.onchange = doSearch;
  }

  function runManualAnalysis(opts) {
    opts = opts || {};
    ensureDrawer();
    document.getElementById("ai-drawer-title").textContent = "جاري التحليل…";
    document.getElementById("ai-drawer-body").innerHTML =
      '<div class="ai-loading"><div class="ai-loading__spinner"></div>' +
      '<p class="ai-loading__text">الذكاء الاصطناعي يحلّل ' + DS.esc(opts.symbol || "") +
      "…<br>قد يستغرق ذلك حتى دقيقة.</p></div>";
    document.getElementById("ai-drawer-foot").innerHTML = "";
    drawerCtrl.open();

    var body = new URLSearchParams();
    body.set("symbol", opts.symbol || "");
    body.set("market", opts.market || "crypto");
    if (opts.timeframe) body.set("timeframe", opts.timeframe);

    function fail(msg) {
      document.getElementById("ai-drawer-title").textContent = "تعذّر التحليل";
      document.getElementById("ai-drawer-body").innerHTML =
        '<div class="ai-drawer-hero"><p class="ai-drawer-hero__summary ds-value-risk">' +
        DS.esc(msg) + "</p></div>";
    }

    return window.postJSON("/api/ai/manual-analysis/", body).then(function (data) {
      if (!data.ok) {
        fail(data.message || data.error || "فشل التحليل");
        return data;
      }
      renderManualAnalysis(data);
      return data;
    }).catch(function (err) {
      fail(String((err && err.message) || err));
      return { ok: false };
    });
  }

  function injectAnalyzeButton(container, opts) {
    if (!container || container.querySelector(".ai-analyze-btn")) return;
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ds-btn ai-analyze-btn";
    btn.textContent = "حلّل بالذكاء";
    btn.onclick = function () { runManualAnalysis(opts); };
    container.appendChild(btn);
  }

  function startLivePolling(el, intervalMs) {
    function tick() {
      fetch("/api/ai/reviews/live/", { credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d.ok) {
            renderLiveCard(el, d.live);
            return;
          }
          el.innerHTML = DS.SectionCard({
            title: "مراجعة مباشرة",
            body: '<p class="ds-text-muted">' + DS.esc(d.error || "تعذّر تحميل المراجعة.") + "</p>",
          });
          setWidgetReady("w-live-review");
        })
        .catch(function () {
          el.innerHTML = DS.SectionCard({
            title: "مراجعة مباشرة",
            body: '<p class="ds-text-muted">تعذّر الاتصال بالخادم.</p>',
          });
          setWidgetReady("w-live-review");
        });
    }
    tick();
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(tick, intervalMs || 15000);
  }

  function openLessonDrawer(lesson) {
    if (!lesson) return;
    ensureDrawer();
    document.getElementById("ai-drawer-title").textContent =
      lesson.title_ar || lesson.title || "درس التعلّم";
    document.getElementById("ai-drawer-sub").textContent =
      (lesson.failure_type || lesson.pattern_type || "") +
      (lesson.provider ? " · " + lesson.provider : "");

    var examples = lesson.trade_examples || [];
    var evidence = lesson.evidence || lesson.supporting_evidence || [];
    var conf = lesson.confidence_summary || {};

    document.getElementById("ai-drawer-body").innerHTML =
      collapsible("summary", "الملخص", 0,
        '<p class="ai-ltr">' + DS.esc(lesson.description_ar || lesson.description || "") + "</p>" +
        (lesson.description && lesson.description_ar
          ? '<p class="ds-text-xs ds-text-muted ai-ltr" style="margin-top:.5rem">' +
            DS.esc(lesson.description) + "</p>"
          : "")) +
      collapsible("pattern", "النمط", 0,
        DS.StatGrid([
          { label: "النوع", value: lesson.title_ar || "—", size: "sm" },
          { label: "العيّنة", value: String(lesson.sample_size || 0), size: "sm" },
          { label: "الثقة", value: conf.avg != null ? conf.avg + "%" : "—", size: "sm" },
        ], 3)) +
      collapsible("evidence", "الأدلة", evidence.length,
        evidence.length
          ? '<ul class="ai-bullets">' + evidence.map(function (e) {
              return "<li dir=\"ltr\">" + DS.esc(e) + "</li>";
            }).join("") + "</ul>"
          : '<p class="ds-text-muted">لا أدلة مسجّلة.</p>') +
      collapsible("trades", "الصفقات المتأثرة", examples.length,
        examples.length
          ? '<div class="table-wrap"><table class="table"><thead><tr>' +
            "<th>الصفقة</th><th>الرمز</th><th>النتيجة</th><th>R</th><th>اتفاق</th><th>ثقة</th>" +
            "</tr></thead><tbody>" +
            examples.map(function (ex) {
              return "<tr><td dir=\"ltr\">" + DS.esc(ex.trade_id || "") + "</td>" +
                "<td dir=\"ltr\">" + DS.esc(ex.symbol || "") + "</td>" +
                "<td>" + DS.esc(ex.outcome || "") + "</td>" +
                "<td dir=\"ltr\">" + (ex.r_multiple != null ? DS.fmtR(ex.r_multiple) : "—") + "</td>" +
                "<td>" + DS.esc(ex.agreement || "") + "</td>" +
                "<td dir=\"ltr\">" + (ex.confidence != null ? ex.confidence + "%" : "—") + "</td></tr>";
            }).join("") +
            "</tbody></table></div>"
          : '<p class="ds-text-muted">لا صفقات مرتبطة.</p>') +
      collapsible("recommendation", "التوصية", 0,
        DS.InsightCard({
          tone: lesson.recommendation_strength === "insufficient" ? "warn" : "info",
          title: lesson.recommendation_ar || lesson.recommendation || "—",
          text: lesson.recommendation_strength === "insufficient"
            ? "لا تغيّر الاستراتيجية أو العتبات بناءً على عيّنة صغيرة."
            : "راجع الأدلة والصفقات قبل أي تعديل على المستشار.",
        }));

    document.getElementById("ai-drawer-foot").innerHTML =
      '<span class="ds-text-xs ds-text-muted">أول رصد: ' +
      DS.esc((lesson.first_seen || "").slice(0, 16).replace("T", " ")) +
      " · آخر تحديث: " +
      DS.esc((lesson.last_seen || "").slice(0, 16).replace("T", " ")) + "</span>";
    drawerCtrl.open();
  }

  function renderLastAnalysisStrip(data) {
    var el = document.getElementById("ai-last-analysis");
    if (!el || !data || !data.ok) return;
    var pres = getPresentation(data.report || data) || getPresentation(data) || {};
    var ts = (data.report && data.report.timestamp) || "";
    el.classList.remove("d-none");
    el.innerHTML =
      '<div class="card-body ai-last-strip">' +
        '<div class="ai-last-strip__head">' +
          '<h2 class="h6 mb-0">آخر تحليل</h2>' +
          '<button type="button" class="btn btn-sm btn-outline-primary" id="ai-strip-full">' +
          'عرض التفاصيل</button>' +
        "</div>" +
        '<div class="ai-last-strip__grid">' +
          '<div><span class="muted small">القرار</span><div>' +
          DS.esc(pres.advisor_decision || pres.final_verdict || "—") + "</div></div>" +
          '<div><span class="muted small">النظرة</span><div>' +
          DS.esc(pres.near_term_outlook || "—") + "</div></div>" +
          '<div><span class="muted small">الاتجاه</span><div>' +
          DS.esc(pres.current_market_view || "—") + "</div></div>" +
          '<div><span class="muted small">ثقة المستشار</span><div dir="ltr">' +
          DS.esc(pres.advisor_confidence_display || pres.confidence_display || "—") + "</div></div>" +
          '<div><span class="muted small">الوقت</span><div dir="ltr">' +
          DS.esc(String(ts).slice(0, 19).replace("T", " ") || "—") + "</div></div>" +
        "</div>" +
        (pres.executive_summary
          ? '<p class="small mt-2 mb-0">' + DS.esc(String(pres.executive_summary).slice(0, 280)) + "</p>"
          : "") +
      "</div>";
    var btn = document.getElementById("ai-strip-full");
    if (btn) {
      btn.onclick = function () {
        if (data.report && data.report.review_id) renderReviewDrawer(data.report);
        else if (data.review_id) openReview(data.review_id);
        else renderManualAnalysis(data);
      };
    }
  }

  global.AIExplain = {
    openReview: openReview,
    openLessonDrawer: openLessonDrawer,
    renderReviewDrawer: renderReviewDrawer,
    renderManualAnalysis: renderManualAnalysis,
    renderLiveCard: renderLiveCard,
    renderHistoryTable: renderHistoryTable,
    runManualAnalysis: runManualAnalysis,
    renderLastAnalysisStrip: renderLastAnalysisStrip,
    injectAnalyzeButton: injectAnalyzeButton,
    startLivePolling: startLivePolling,
  };
})(window);
