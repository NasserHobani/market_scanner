/**
 * CS Edge Design System — component factories.
 *
 * Every screen composes its UI from these functions so that a visual change
 * happens in one place. Each factory returns an HTML string; callers assign it
 * to a container. Values are escaped unless a field is documented as HTML.
 */
(function (global) {
  "use strict";

  // ── Primitives ───────────────────────────────────────────────────────────

  function esc(v) {
    if (v === null || v === undefined) return "";
    return String(v)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function num(v) {
    return v === null || v === undefined || v === "" || isNaN(v) ? null : Number(v);
  }

  /**
   * Wraps a run of Latin text in a directional isolate.
   *
   * The whole UI is RTL, so an unisolated "-0.75R" is reordered by the bidi
   * algorithm and displays as "0.75R-" — the sign lands on the wrong side and
   * a loss can read as a gain. Every formatted number goes through this.
   */
  function ltr(s) {
    return "\u2066" + s + "\u2069";
  }

  function fmtR(v) {
    var n = num(v);
    if (n === null) return "—";
    return ltr((n >= 0 ? "+" : "\u2212") + Math.abs(n).toFixed(2) + "R");
  }

  /** R as a magnitude — for drawdown, where a "+" would read as a gain. */
  function fmtRAbs(v) {
    var n = num(v);
    if (n === null) return "—";
    return ltr(Math.abs(n).toFixed(2) + "R");
  }

  function fmtPct(v, digits) {
    var n = num(v);
    if (n === null) return "—";
    return ltr(n.toFixed(digits === undefined ? 1 : digits) + "%");
  }

  function fmtNum(v, digits) {
    var n = num(v);
    if (n === null) return "—";
    return ltr(digits === undefined ? String(n) : n.toFixed(digits));
  }

  /** Maps a signed value to a semantic tone. */
  function toneForValue(v) {
    var n = num(v);
    if (n === null) return "muted";
    if (n > 0) return "success";
    if (n < 0) return "risk";
    return "muted";
  }

  /** Maps a 0–100 score to a semantic tone using shared platform thresholds. */
  function toneForScore(score) {
    var n = num(score);
    if (n === null) return "muted";
    if (n >= 70) return "success";
    if (n >= 45) return "warn";
    return "risk";
  }

  function clamp(v, lo, hi) {
    return Math.max(lo, Math.min(hi, num(v) === null ? lo : Number(v)));
  }

  // ── SectionHeader ────────────────────────────────────────────────────────

  /**
   * @param {{title:string, note?:string, link?:{href:string,label:string}}} o
   */
  function SectionHeader(o) {
    return '<div class="ds-section-header">' +
      "<h2>" + esc(o.title) + "</h2>" +
      (o.note ? '<span class="ds-section-header__note">' + esc(o.note) + "</span>" : "") +
      (o.link ? '<a class="ds-section-header__link" href="' + esc(o.link.href) + '">' +
        esc(o.link.label) + "</a>" : "") +
      "</div>";
  }

  // ── SectionCard ──────────────────────────────────────────────────────────

  /**
   * @param {{title?:string, meta?:string, body:string, tight?:boolean,
   *          flush?:boolean, className?:string}} o body is trusted HTML.
   */
  function SectionCard(o) {
    var cls = "ds-card" + (o.tight ? " ds-card--tight" : "") +
      (o.flush ? " ds-card--flush" : "") + (o.className ? " " + o.className : "");
    var head = o.title
      ? '<div class="ds-card__head"><h3 class="ds-card__title">' + esc(o.title) + "</h3>" +
        (o.meta ? '<span class="ds-card__meta">' + esc(o.meta) + "</span>" : "") + "</div>"
      : "";
    return '<div class="' + cls + '">' + head + o.body + "</div>";
  }

  // ── MetricCard ───────────────────────────────────────────────────────────

  /**
   * @param {{label:string, value:string, tone?:string, size?:'hero'|'lg'|'sm',
   *          foot?:string, valueTone?:string}} o
   */
  function MetricCard(o) {
    var cls = "ds-metric";
    if (o.tone) cls += " ds-metric--" + o.tone;
    if (o.size) cls += " ds-metric--" + o.size;
    var valueCls = "ds-metric__value" +
      (o.valueTone ? " ds-value-" + o.valueTone : "");
    return '<div class="' + cls + '">' +
      '<span class="ds-metric__label">' + esc(o.label) + "</span>" +
      '<span class="' + valueCls + '">' + esc(o.value) + "</span>" +
      (o.foot ? '<span class="ds-metric__foot">' + o.foot + "</span>" : "") +
      "</div>";
  }

  /**
   * @param {Array} cards MetricCard option objects.
   * @param {number} [cols] Fixed column count; omit for auto-fit.
   */
  function StatGrid(cards, cols) {
    var cls = "ds-stat-grid" + (cols ? " ds-stat-grid--" + cols : "");
    return '<div class="' + cls + '">' + cards.map(MetricCard).join("") + "</div>";
  }

  // ── StatusBadge ──────────────────────────────────────────────────────────

  /**
   * @param {{label:string, tone?:string, dot?:boolean}} o
   */
  function StatusBadge(o) {
    return '<span class="ds-badge ds-badge--' + (o.tone || "neutral") + '">' +
      (o.dot ? '<span class="ds-badge__dot"></span>' : "") +
      esc(o.label) + "</span>";
  }

  // ── TrendIndicator ───────────────────────────────────────────────────────

  /**
   * @param {{value:number, text?:string}} o
   */
  function TrendIndicator(o) {
    var n = num(o.value);
    var dir = n === null || n === 0 ? "flat" : n > 0 ? "up" : "down";
    var arrow = dir === "up" ? "▲" : dir === "down" ? "▼" : "▬";
    return '<span class="ds-trend ds-trend--' + dir + '">' +
      '<span class="ds-trend__arrow">' + arrow + "</span>" +
      esc(o.text !== undefined ? o.text : fmtR(n)) + "</span>";
  }

  // ── ConfidenceBar ────────────────────────────────────────────────────────

  /**
   * Renders an internal confidence score as a readable bar. This is the only
   * approved way to surface model confidence — never print the raw object.
   * @param {{label:string, value:number, tone?:string, note?:string,
   *          suffix?:string}} o value is 0–100.
   */
  function ConfidenceBar(o) {
    var pct = clamp(o.value, 0, 100);
    var tone = o.tone || (num(o.value) === null ? "muted" : toneForScore(pct));
    var text = num(o.value) === null ? "غير متاح"
      : ltr(Math.round(pct) + (o.suffix !== undefined ? o.suffix : "%"));
    return '<div class="ds-confidence">' +
      '<span class="ds-confidence__label">' + esc(o.label) + "</span>" +
      '<span class="ds-confidence__track" role="meter" aria-valuenow="' + Math.round(pct) +
        '" aria-valuemin="0" aria-valuemax="100" aria-label="' + esc(o.label) + '">' +
        '<span class="ds-confidence__fill ds-confidence__fill--' + tone +
        '" style="width:' + pct + '%"></span></span>' +
      '<span class="ds-confidence__value ds-value-' + tone + '">' + esc(text) + "</span>" +
      (o.note ? '<span class="ds-confidence__note">' + esc(o.note) + "</span>" : "") +
      "</div>";
  }

  function ConfidenceList(items) {
    return '<div class="ds-confidence-list">' + items.map(ConfidenceBar).join("") + "</div>";
  }

  // ── InsightCard ──────────────────────────────────────────────────────────

  /**
   * @param {{title:string, text:string, tone?:string}} o
   */
  function InsightCard(o) {
    return '<div class="ds-insight ds-insight--' + (o.tone || "info") + '">' +
      '<span class="ds-insight__mark"></span>' +
      '<div class="ds-insight__body">' +
        '<p class="ds-insight__title">' + esc(o.title) + "</p>" +
        '<p class="ds-insight__text">' + esc(o.text) + "</p>" +
      "</div></div>";
  }

  // ── EmptyState ───────────────────────────────────────────────────────────

  /**
   * @param {{icon?:string, title:string, text?:string, steps?:string[],
   *          actions?:Array<{href?:string,label:string,primary?:boolean,id?:string}>,
   *          meta?:string, inline?:boolean}} o
   */
  function EmptyState(o) {
    if (!o) return "";
    var steps = (o.steps || []).map(function (s, i) {
      return '<li class="ds-empty__step">' +
        '<span class="ds-empty__step-num">' + (i + 1) + "</span>" + esc(s) + "</li>";
    }).join("");
    var actions = (o.actions || []).map(function (a) {
      var cls = "ds-btn" + (a.primary ? " ds-btn--primary" : "");
      return a.href
        ? '<a class="' + cls + '" href="' + esc(a.href) + '">' + esc(a.label) + "</a>"
        : '<button type="button" class="' + cls + '"' +
          (a.id ? ' id="' + esc(a.id) + '"' : "") + ">" + esc(a.label) + "</button>";
    }).join("");
    return '<div class="ds-empty' + (o.inline ? " ds-empty--inline" : "") + '">' +
      '<span class="ds-empty__icon" aria-hidden="true">' + esc(o.icon || "○") + "</span>" +
      '<h3 class="ds-empty__title">' + esc(o.title) + "</h3>" +
      (o.text ? '<p class="ds-empty__text">' + esc(o.text) + "</p>" : "") +
      (steps ? '<ol class="ds-empty__steps">' + steps + "</ol>" : "") +
      (actions ? '<div class="ds-empty__actions">' + actions + "</div>" : "") +
      (o.meta ? '<span class="ds-empty__meta">' + esc(o.meta) + "</span>" : "") +
      "</div>";
  }

  // ── LoadingSkeleton ──────────────────────────────────────────────────────

  /**
   * @param {'metrics'|'chart'|'rows'|'cards'|'text'|'confidence'} kind
   * @param {number} [count]
   */
  function LoadingSkeleton(kind, count) {
    var n = count || 3;
    var out = [];
    var i;
    switch (kind) {
      case "metrics":
        for (i = 0; i < n; i++) out.push('<div class="ds-skel ds-skel-metric"></div>');
        return '<div class="ds-stat-grid">' + out.join("") + "</div>";
      case "chart":
        return '<div class="ds-skel ds-skel-chart"></div>';
      case "cards":
        for (i = 0; i < n; i++) out.push('<div class="ds-skel ds-skel-card"></div>');
        return '<div class="ds-grid-2">' + out.join("") + "</div>";
      case "confidence":
        for (i = 0; i < n; i++) {
          out.push('<div class="ds-confidence">' +
            '<span class="ds-skel ds-skel-text w80" style="margin:0"></span>' +
            '<span class="ds-skel" style="height:8px;border-radius:4px"></span>' +
            '<span class="ds-skel ds-skel-text" style="width:2.5rem;margin:0"></span></div>');
        }
        return out.join("");
      case "text":
        return '<div class="ds-skel ds-skel-text w80"></div>' +
          '<div class="ds-skel ds-skel-text w60"></div>' +
          '<div class="ds-skel ds-skel-text w40"></div>';
      default: // rows
        for (i = 0; i < n; i++) out.push('<div class="ds-skel ds-skel-row"></div>');
        return out.join("");
    }
  }

  // ── Table ────────────────────────────────────────────────────────────────

  /**
   * @param {{columns:Array<{key:string,label:string,align?:string,width?:string}>,
   *          rows:Array<Object>, rowAttrs?:function, scroll?:boolean}} o
   *          Cell values are trusted HTML so callers can embed badges/bars.
   */
  function DataTable(o) {
    var head = o.columns.map(function (c) {
      var cls = (c.align === "end" ? "num" : "") +
        (c.sortable ? " ds-th-sortable" : "");
      return "<th" + (c.width ? ' style="width:' + c.width + '"' : "") +
        (cls ? ' class="' + cls.trim() + '"' : "") +
        (c.sortable ? ' data-sort-key="' + esc(c.key) + '"' : "") + ">" +
        esc(c.label) +
        (c.sortable ? '<span class="ds-th-sort" aria-hidden="true"></span>' : "") +
        "</th>";
    }).join("");
    var body = o.rows.map(function (r, i) {
      var attrs = o.rowAttrs ? o.rowAttrs(r, i) : "";
      var cells = o.columns.map(function (c) {
        var v = r[c.key];
        return "<td" + (c.align === "end" ? ' class="num"' : "") +
          ' data-cell="' + esc(c.key) + '">' +
          (v === undefined || v === null ? "—" : v) + "</td>";
      }).join("");
      return "<tr " + attrs + ">" + cells + "</tr>";
    }).join("");
    var table = '<table class="ds-table"><thead><tr>' + head + "</tr></thead><tbody>" +
      body + "</tbody></table>";
    return o.scroll === false ? table : '<div class="ds-table-scroll">' + table + "</div>";
  }

  /**
   * Incrementally sync a table: patch existing rows, insert new at position,
   * remove stale rows — no full innerHTML rebuild on poll.
   *
   * @param {HTMLElement} container
   * @param {{columns:Array, items:Array, keyFn:function, buildRow:function,
   *          patchRow:function, toolbar?:string, emptyHtml?:string,
   *          onWire?:function}} o
   */
  function patchDataTable(container, o) {
    var items = o.items || [];
    var keyFn = o.keyFn || function (it) { return it.id; };
    var table = container.querySelector("table.ds-table");
    var tbody = table ? table.querySelector("tbody") : null;

    if (!items.length) {
      if (o.emptyHtml) container.innerHTML = o.emptyHtml;
      return null;
    }

    if (!tbody) {
      var rows = items.map(function (it, i) { return o.buildRow(it, i); });
      container.innerHTML = (o.toolbar || "") + DataTable({
        columns: o.columns,
        rows: rows,
        rowAttrs: function (r) { return r._attrs || ""; },
      });
      tbody = container.querySelector("tbody");
      if (o.onWire) o.onWire(container);
      return tbody;
    }

    var existing = {};
    Array.prototype.forEach.call(
      tbody.querySelectorAll("tr[data-key]"),
      function (tr) { existing[tr.getAttribute("data-key")] = tr; }
    );

    var desired = items.map(function (it) { return String(keyFn(it)); });

    Object.keys(existing).forEach(function (id) {
      if (desired.indexOf(id) < 0) existing[id].remove();
    });

    items.forEach(function (it, i) {
      var key = String(keyFn(it));
      var tr = existing[key];
      if (tr) {
        o.patchRow(tr, it, i);
        var at = tbody.children[i];
        if (at !== tr) tbody.insertBefore(tr, at || null);
      } else {
        var row = o.buildRow(it, i);
        var html = "<tr " + (row._attrs || "") + ">";
        o.columns.forEach(function (c) {
          var v = row[c.key];
          html += "<td" + (c.align === "end" ? ' class="num"' : "") +
            ' data-cell="' + esc(c.key) + '">' +
            (v === undefined || v === null ? "—" : v) + "</td>";
        });
        html += "</tr>";
        var wrap = document.createElement("tbody");
        wrap.innerHTML = html;
        tr = wrap.firstChild;
        tbody.insertBefore(tr, tbody.children[i] || null);
        existing[key] = tr;
        tr.style.transition = "background .8s";
        tr.style.background = "rgba(106,169,255,.12)";
        setTimeout(function () { tr.style.background = ""; }, 1200);
      }
    });

    return tbody;
  }

  function setCellText(tr, key, html) {
    var cell = tr.querySelector('[data-cell="' + key + '"]');
    if (cell && cell.innerHTML !== html) cell.innerHTML = html;
  }

  // ── Heatmap ──────────────────────────────────────────────────────────────

  /**
   * @param {Array<{label:string, value:number, sub?:string}>} cells
   *        Cell background intensity scales with |value| relative to the max.
   */
  function Heatmap(cells) {
    var max = cells.reduce(function (m, c) {
      return Math.max(m, Math.abs(num(c.value) || 0));
    }, 0) || 1;
    return '<div class="ds-heatmap">' + cells.map(function (c) {
      var v = num(c.value) || 0;
      var intensity = Math.min(.32, (Math.abs(v) / max) * .32);
      var rgb = v > 0 ? "61,220,151" : v < 0 ? "255,107,107" : "148,157,178";
      return '<div class="ds-heat-cell" style="background:rgba(' + rgb + "," + intensity + ')">' +
        '<span class="ds-heat-cell__label">' + esc(c.label) + "</span>" +
        '<span class="ds-heat-cell__value ds-value-' + toneForValue(v) + '">' +
          esc(c.text !== undefined ? c.text : fmtR(v)) + "</span>" +
        (c.sub ? '<span class="ds-heat-cell__sub">' + esc(c.sub) + "</span>" : "") +
        "</div>";
    }).join("") + "</div>";
  }

  // ── Distribution ─────────────────────────────────────────────────────────

  /**
   * @param {Array<{label:string, value:number, text?:string, tone?:string,
   *                max?:number}>} rows
   */
  function Distribution(rows) {
    var max = rows.reduce(function (m, r) {
      return Math.max(m, Math.abs(num(r.value) || 0));
    }, 0) || 1;
    return '<div class="ds-dist">' + rows.map(function (r) {
      var v = Math.abs(num(r.value) || 0);
      var pct = (v / max) * 100;
      var tone = r.tone || toneForValue(r.value);
      var color = tone === "success" ? "var(--ds-success)"
        : tone === "risk" ? "var(--ds-risk)"
        : tone === "warn" ? "var(--ds-warn)"
        : tone === "info" ? "var(--ds-info)" : "var(--ds-text-faint)";
      return '<div class="ds-dist__row">' +
        '<span class="ds-dist__label">' + esc(r.label) + "</span>" +
        '<span class="ds-dist__track"><span class="ds-dist__fill" style="width:' +
          pct + "%;background:" + color + '"></span></span>' +
        '<span class="ds-dist__value ds-value-' + tone + '">' +
          esc(r.text !== undefined ? r.text : fmtR(r.value)) + "</span></div>";
    }).join("") + "</div>";
  }

  // ── Timeline ─────────────────────────────────────────────────────────────

  /**
   * @param {Array<{title:string, meta?:string, tone?:string}>} items
   */
  function Timeline(items) {
    return '<ul class="ds-timeline">' + items.map(function (it) {
      return '<li class="ds-timeline__item ds-timeline__item--' + (it.tone || "info") + '">' +
        '<span class="ds-timeline__dot"></span>' +
        '<div class="ds-timeline__title">' + esc(it.title) + "</div>" +
        (it.meta ? '<div class="ds-timeline__meta">' + esc(it.meta) + "</div>" : "") +
        "</li>";
    }).join("") + "</ul>";
  }

  // ── List ─────────────────────────────────────────────────────────────────

  /**
   * @param {Array<{title:string, sub?:string, end?:string, attrs?:string}>} rows
   *        `end` is trusted HTML so it can hold a badge or trend indicator.
   */
  function List(rows) {
    return '<div class="ds-list">' + rows.map(function (r) {
      return '<div class="ds-list__row' + (r.attrs ? " is-clickable" : "") + '" ' +
        (r.attrs || "") + ">" +
        '<div class="ds-list__main">' +
          '<div class="ds-list__title">' + esc(r.title) + "</div>" +
          (r.sub ? '<div class="ds-list__sub">' + esc(r.sub) + "</div>" : "") +
        "</div>" +
        (r.end ? '<div class="ds-list__end">' + r.end + "</div>" : "") +
        "</div>";
    }).join("") + "</div>";
  }

  // ── Widget shell: independent async loading ─────────────────────────────

  /**
   * Loads one widget without blocking any other. A failure is contained inside
   * the widget's own shell and offers a retry, so a single bad endpoint can
   * never take down a page.
   *
   * @param {{id:string, url:string, render:function(HTMLElement, Object),
   *          onError?:function}} o
   */
  function loadWidget(o) {
    var shell = document.getElementById(o.id);
    if (!shell) return Promise.resolve();
    var content = shell.querySelector(".ds-widget__content");
    var errBox = shell.querySelector(".ds-widget__error");
    shell.setAttribute("data-state", "loading");

    return fetch(o.url, { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data && data.error) throw new Error(data.error);
        o.render(content, data);
        content.classList.add("ds-fade-in");
        shell.setAttribute("data-state", "ready");
      })
      .catch(function (err) {
        if (errBox) {
          errBox.innerHTML =
            '<div class="ds-widget__error-body">' +
              '<div class="ds-widget__error-title">تعذّر تحميل هذا القسم</div>' +
              '<div class="ds-widget__error-text">' + esc(err.message || "خطأ غير معروف") + "</div>" +
            "</div>" +
            '<button type="button" class="ds-btn ds-btn--sm">إعادة المحاولة</button>';
          var retry = errBox.querySelector("button");
          if (retry) retry.onclick = function () { loadWidget(o); };
        }
        shell.setAttribute("data-state", "error");
        if (o.onError) o.onError(err);
      });
  }

  /** Renders a widget shell with its own skeleton and error region. */
  function widgetShell(id, skeletonHtml) {
    return '<div class="ds-widget" id="' + esc(id) + '" data-state="loading">' +
      '<div class="ds-widget__skeleton">' + skeletonHtml + "</div>" +
      '<div class="ds-widget__error"></div>' +
      '<div class="ds-widget__content"></div></div>';
  }

  // ── Tabs controller (page tabs and drawer tabs share this) ──────────────

  /**
   * Wires an accessible tab list: click, arrow keys, Home/End, and an optional
   * lazy callback fired the first time each panel becomes visible.
   *
   * @param {{tabsSelector:string, panelSelector?:string,
   *          onShow?:function(string), syncUrl?:boolean, initial?:string}} o
   */
  function initTabs(o) {
    var list = document.querySelector(o.tabsSelector);
    if (!list) return null;
    var tabs = Array.prototype.slice.call(list.querySelectorAll("[data-tab]"));
    var panelScope = o.panelSelector
      ? document.querySelector(o.panelSelector) : document;
    if (!panelScope) panelScope = document;
    var panels = Array.prototype.slice.call(
      panelScope.querySelectorAll("[data-tab-panel]"));
    if (!tabs.length) return null;

    var seen = {};

    function activate(name, focus) {
      tabs.forEach(function (t) {
        var on = t.getAttribute("data-tab") === name;
        t.classList.toggle("active", on);
        t.setAttribute("aria-selected", on ? "true" : "false");
        t.setAttribute("tabindex", on ? "0" : "-1");
        if (on && focus) t.focus();
      });
      panels.forEach(function (p) {
        p.classList.toggle("active", p.getAttribute("data-tab-panel") === name);
      });
      if (o.syncUrl) {
        var url = new URL(window.location.href);
        url.searchParams.set("tab", name);
        history.replaceState(null, "", url.toString());
      }
      if (o.onShow && !seen[name]) {
        seen[name] = true;
        o.onShow(name);
      }
    }

    list.setAttribute("role", "tablist");
    tabs.forEach(function (tab, idx) {
      tab.setAttribute("role", "tab");
      tab.addEventListener("click", function () {
        activate(tab.getAttribute("data-tab"));
      });
      tab.addEventListener("keydown", function (e) {
        var next = null;
        if (e.key === "ArrowLeft") next = tabs[(idx + 1) % tabs.length];
        else if (e.key === "ArrowRight") next = tabs[(idx - 1 + tabs.length) % tabs.length];
        else if (e.key === "Home") next = tabs[0];
        else if (e.key === "End") next = tabs[tabs.length - 1];
        if (next) {
          e.preventDefault();
          activate(next.getAttribute("data-tab"), true);
        }
      });
    });

    var start = o.initial ||
      new URL(window.location.href).searchParams.get("tab") ||
      tabs[0].getAttribute("data-tab");
    if (!tabs.some(function (t) { return t.getAttribute("data-tab") === start; })) {
      start = tabs[0].getAttribute("data-tab");
    }
    activate(start);
    return { activate: activate };
  }

  // ── Drawer controller ───────────────────────────────────────────────────

  /**
   * Focus-trapping slide-over. Restores focus to the trigger on close and
   * closes on Escape, which keeps it usable from the keyboard alone.
   */
  function createDrawer(drawerId, backdropId) {
    var drawer = document.getElementById(drawerId);
    var backdrop = document.getElementById(backdropId);
    if (!drawer) return { open: function () {}, close: function () {} };
    var lastFocus = null;

    function focusables() {
      return Array.prototype.slice.call(drawer.querySelectorAll(
        'button:not([disabled]), a[href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      )).filter(function (el) { return el.offsetParent !== null; });
    }

    function onKey(e) {
      if (e.key === "Escape") { close(); return; }
      if (e.key !== "Tab") return;
      var items = focusables();
      if (!items.length) return;
      var first = items[0];
      var last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault(); last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault(); first.focus();
      }
    }

    function open() {
      lastFocus = document.activeElement;
      drawer.classList.add("open");
      drawer.setAttribute("aria-hidden", "false");
      if (backdrop) backdrop.classList.add("open");
      document.body.style.overflow = "hidden";
      document.addEventListener("keydown", onKey);
      var items = focusables();
      if (items.length) items[0].focus();
    }

    function close() {
      drawer.classList.remove("open");
      drawer.setAttribute("aria-hidden", "true");
      if (backdrop) backdrop.classList.remove("open");
      document.body.style.overflow = "";
      document.removeEventListener("keydown", onKey);
      if (lastFocus && lastFocus.focus) lastFocus.focus();
    }

    if (backdrop) backdrop.addEventListener("click", close);
    return { open: open, close: close, el: drawer };
  }

  global.DS = {
    esc: esc,
    num: num,
    ltr: ltr,
    fmtR: fmtR,
    fmtRAbs: fmtRAbs,
    fmtPct: fmtPct,
    fmtNum: fmtNum,
    toneForValue: toneForValue,
    toneForScore: toneForScore,
    SectionHeader: SectionHeader,
    SectionCard: SectionCard,
    MetricCard: MetricCard,
    StatGrid: StatGrid,
    StatusBadge: StatusBadge,
    TrendIndicator: TrendIndicator,
    ConfidenceBar: ConfidenceBar,
    ConfidenceList: ConfidenceList,
    InsightCard: InsightCard,
    EmptyState: EmptyState,
    LoadingSkeleton: LoadingSkeleton,
    DataTable: DataTable,
    patchDataTable: patchDataTable,
    setCellText: setCellText,
    Heatmap: Heatmap,
    Distribution: Distribution,
    Timeline: Timeline,
    List: List,
    loadWidget: loadWidget,
    widgetShell: widgetShell,
    initTabs: initTabs,
    createDrawer: createDrawer,
  };
})(window);
