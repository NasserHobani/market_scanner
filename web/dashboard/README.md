# Sprint PX-01 — Product Experience & UI Modernization

Engineering report for the front-end rebuild of the CS Edge web surface.
No trading logic, scanner algorithm, AI module, optimizer, research engine,
database schema or API contract was changed by this sprint.

---

## 1. Executive summary

CS Edge was an engineering dashboard: one page fetched one large bundle,
rendered a wall of tables, and left the trader to work out what any of it
meant. This sprint rebuilt the presentation layer on top of the existing APIs
so the product answers questions instead of dumping data.

Four things changed structurally.

**Every page now owns exactly one question.** The dashboard answers "can I
trust the system right now?", trades answers "what needs my attention?", AI
answers "why did it recommend that?", analytics answers "where does the
performance come from?", research answers "is this edge real or luck?",
optimization answers "which parameter set wins?", and the watchlist answers
"which opportunity is closest to triggering?". Nothing appears on a page that
does not serve its question.

**A real design system replaced ad-hoc markup.** `design-system.css`
(31 KB of tokens and component rules) and `ds-components.js` (26 KB of
renderers) provide 16 UI components and 8 formatting/behaviour helpers. Every
screen is now assembled from them; there is no page-local card, badge, bar or
table implementation left in the redesigned pages.

**Loading became per-widget instead of per-page.** The dashboard used to wait
on a single `/api/dashboard/` bundle. It now issues seven independent widget
requests, each with its own skeleton, its own error state, and its own refresh
cadence. A slow AI query no longer holds the equity curve hostage. Measured on
a warm cache: HTML in 12 ms, DOM ready in 36 ms, all seven widgets painted by
296 ms — against a 1-second budget.

**Tables gave way to visual encodings where the data allowed it.** Confidence
bars, distribution bars, heatmaps, proximity bars, trend indicators, status
badges and timelines now carry information that used to be numeric columns.
Tables survive only where the row count genuinely demands one — the scanner,
the trade lists, the watchlist — and even there each cell renders a component
rather than a raw string.

The dashboard fits in 1920×1080 with zero scroll. All 28 test scripts pass and
`manage.py check` is clean.

---

## 2. Screens redesigned

| Screen | Question it answers | What it became |
| --- | --- | --- |
| Dashboard (`/`) | Can I trust the system right now? | Zero-scroll operations grid: health hero + 4 KPIs, verdict insight, three system-status cards, equity curve, alert timeline, top-5 open trades |
| Trades (`/trades/`) | What is running and what needs intervention? | Exposure summary, three status tabs with per-tab column sets, nine-tab investigation drawer |
| AI (`/ai/`) | Why does the system recommend what it recommends? | Composite readiness score, decision-component confidence bars, module status list, weakest-link callout, four tabs. No raw JSON anywhere |
| Analytics (`/analytics/`) | Where does performance come from? | Rolling expectancy and equity charts, factor contribution, performance splits as heatmap + distribution grid |
| Research (`/research/`) | Is this edge real or is it luck? | Statistical confidence bars, expectancy interval cards, experiments, baseline comparison, export |
| Optimization (`/optimization/`) | Which parameter set gives the best expectancy? | Summary strip, leaderboard, accepted/rejected partitions, walk-forward distribution, run history — plus an instructional empty state with a copy-the-command button |
| Watchlist (`/watches/`) | Which opportunity is closest to triggering? | Summary strip (watched / about to trigger / closest distance / triggered), proximity-bar table, recently-triggered card |
| Scanner (`/scanner/`) | What opportunities exist now? | Design-system page header and summary metrics over the existing screener table |
| Settings (`/settings/`) | What constraints does the system run under? | Design-system page header over the existing sectioned form |

---

## 3. Components created

Rendering components in `ds-components.js`:

`SectionHeader`, `SectionCard`, `MetricCard`, `StatGrid`, `StatusBadge`,
`TrendIndicator`, `ConfidenceBar`, `ConfidenceList`, `InsightCard`,
`EmptyState`, `LoadingSkeleton`, `DataTable`, `Heatmap`, `Distribution`,
`Timeline`, `List`.

Behaviour helpers:

- `loadWidget({id, url, render})` — fetch a widget's data, swap skeleton for
  content, catch and display its own error without touching the rest of the
  page.
- `widgetShell` — the skeleton/content/error markup contract.
- `initTabs({tabsSelector, panelSelector, syncUrl, onShow})` — accessible tabs
  that lazy-load a panel the first time it is opened and can mirror the active
  tab into the URL.
- `createDrawer(id, backdropId)` — focus-trapping drawer with Escape-to-close.

Formatting helpers: `esc`, `num`, `ltr`, `fmtR`, `fmtRAbs`, `fmtPct`,
`fmtNum`, `toneForValue`, `toneForScore`.

`ltr` deserves a note. The interface is right-to-left, so an unisolated
`-1.00R` renders as `1.00R-` and `-0.1` on a chart axis renders as `0.1-`.
Every numeric formatter now wraps its output in Unicode isolate characters
(U+2066 / U+2069), and both chart libraries' tick callbacks do the same.

---

## 4. Components removed

| Removed | Replaced by |
| --- | --- |
| `static/dashboard/platform.js` | `ds-components.js` |
| `templates/dashboard/widgets/shell.html` | the `ds-widget` skeleton/content/error pattern |
| `templates/dashboard/index.html` | `scanner.html` (the scanner is no longer the landing page) |
| Bootstrap `alert`/`card`/`badge` usage on redesigned pages | `InsightCard`, `SectionCard`, `StatusBadge` |
| Page-local table renderers on watches and trades | `DataTable` |
| The blocking `/api/dashboard/` bundle call from the dashboard page | seven independent widget endpoints (the endpoint itself is untouched and still served) |

---

## 5. Pages improved

Beyond the nine screens above, the shared shell changed:

- Navigation is grouped by workflow (operate → investigate → improve) with
  separators, `aria-current` on the active item, and Settings demoted to an
  icon in the status area so the primary row holds only the eight workflow
  destinations.
- A skip link jumps to `#main`.
- Timeframe chips are suppressed on pages that do not filter by timeframe.
- Static assets are cache-busted by file mtime through a new `{% asset %}`
  template tag, so a CSS change is visible on reload without a hard refresh.

---

## 6. Loading optimizations

- **Independent widgets.** Each widget is a `ds-widget` element with three
  states (`loading` / `ready` / `error`) driven by `data-state`. `loadWidget`
  owns the transition. One widget failing paints one error box.
- **Skeletons, not spinners.** Every widget ships a skeleton whose shape
  matches its eventual content (`ds-skel-metric`, `ds-skel-row`,
  `ds-skel-chart`), so nothing reflows when data lands.
- **Staged dispatch.** The dashboard fires its above-the-fold widgets on the
  next animation frame and defers the rest to `requestIdleCallback`, so the
  trust panel paints before the alert feed competes for the network.
- **Lazy tabs.** Analytics, research, optimization, AI and trades fetch a
  tab's data the first time that tab is opened, and never again on re-entry.
  Opening the analytics page costs one request, not three.
- **Scoped polling.** Trades refreshes only the visible tab every 5 s; the
  dashboard refreshes only open trades every 5 s. Hidden tabs cost nothing.

---

## 7. Responsive improvements

- The dashboard's `ops-grid` uses named grid areas and collapses from a
  three-column operations layout to two columns under 1400 px and one column
  under 992 px.
- `analytics-grid`, `ai-grid`, `research-grid`, `splits-grid` and
  `trades-summary` all use `repeat(auto-fit, minmax(...))` or explicit
  breakpoints; there are no fixed pixel widths in the redesigned pages.
- Tables live in `.ds-table-scroll` (horizontal and vertical scroll, capped at
  60 vh) with sticky headers, so a wide table scrolls inside its card instead
  of stretching the document.
- The drawer is `min(560px, 100vw)` wide and scrolls per panel, not as a whole.
- Verified at 1920×1080, 1366×768 and 834×1112: no horizontal document
  overflow on any page, and the nav collapses to a toggle on tablet.

---

## 8. Performance improvements

Measured in-browser on the dashboard with a warm widget cache:

| Metric | Value |
| --- | --- |
| HTML response complete | 12 ms |
| DOMContentLoaded | 36 ms |
| Slowest widget request | 229 ms (`health`) |
| All seven widgets painted | 296 ms |
| Requests to first meaningful paint | 1 (the HTML) |

Contributing changes:

- Splitting one bundle into seven parallel requests means total wall time is
  the slowest widget (229 ms), not the sum of all of them.
- Lazy tabs removed two of three requests from the analytics page load and
  four of five from optimization.
- Chart.js instances are destroyed before re-render, so the 5-second refresh
  loop does not leak canvases.
- A single delegated listener per table replaced one listener per row; the
  272-row waiting-trades table attaches two listeners, not 272.
- `{% asset %}` stamps URLs with the file mtime, which lets static assets be
  served with long cache lifetimes without stale-asset risk.

---

## 9. Files added

| File | Purpose |
| --- | --- |
| `static/dashboard/design-system.css` | Tokens, component styles, accessibility rules |
| `static/dashboard/ds-components.js` | Component renderers and behaviour helpers |
| `static/dashboard/dashboard-page.js` | Dashboard widget wiring |
| `static/dashboard/trades-page.js` | Trades tables and the investigation drawer |
| `static/dashboard/ai-page.js` | AI centre rendering |
| `static/dashboard/optimization-page.js` | Optimization tabs and empty state |
| `static/dashboard/analytics-page.js` | Analytics tab wiring |
| `static/dashboard/research-page.js` | Research tab wiring |
| `static/dashboard/watches-page.js` | Watchlist rendering |
| `templates/dashboard/dashboard.html` | Operations dashboard |
| `templates/dashboard/trades.html` | Trades page and drawer markup |
| `templates/dashboard/ai.html` | AI centre |
| `templates/dashboard/analytics.html` | Analytics |
| `templates/dashboard/research.html` | Research lab |
| `templates/dashboard/optimization.html` | Optimization |
| `templates/dashboard/scanner.html` | Scanner (was `index.html`) |
| `templatetags/assets.py` | `{% asset %}` mtime cache-busting tag |

## 10. Files modified

| File | Change |
| --- | --- |
| `templates/dashboard/base.html` | Workflow navigation, skip link, design-system includes, `{% asset %}` |
| `templates/dashboard/watches.html` | Rebuilt on the design system |
| `templates/dashboard/settings.html` | Design-system page header |
| `static/dashboard/platform.css` | Reduced to page-specific layout plus compatibility shims |
| `static/dashboard/research-widgets.js` | Renderers moved onto design-system components; bidi-safe chart axes |
| `views.py` | `tf_in_page` context flag so the dashboard hides timeframe chips (presentation only) |
| `widgets.py` | `build_health` now surfaces `win_rate` and `total_r` that `health_panel` already computed but did not return |

## 11. Design system summary

**Tokens** (`:root` in `design-system.css`): semantic colours (`--ds-success`,
`--ds-risk`, `--ds-warn`, `--ds-info`, each with a `-dim` fill and a `-line`
border variant), three surface elevations, four text weights, an eight-step
type scale, a seven-step spacing scale, three radii, two shadows and one
easing curve.

**Colour discipline.** Green means a realised gain or a passing check, red
means loss or risk, amber means caution or a pending state, blue means
neutral information. Colour is never decorative; `toneForValue` and
`toneForScore` derive the tone from the number so the mapping cannot drift
between pages.

**Typography.** One family, eight sizes, hierarchy carried by size and weight
rather than colour. Numbers use `font-variant-numeric: tabular-nums` so
columns align.

**Motion.** Three animations only — a 180 ms fade-in on widget content, a
220 ms slide on the drawer, and the skeleton shimmer. All of them collapse to
nothing under `prefers-reduced-motion`.

**Accessibility.** Visible `:focus-visible` rings on every interactive
element, `role="tab"`/`aria-selected` on tab strips, `role="meter"` with
`aria-valuenow` on confidence bars, `aria-current` on the active nav item, a
skip link, keyboard-activatable table rows (`tabindex="0"`, Enter/Space), and
Escape-to-close on the drawer.

---

## 12. Future UI recommendations

1. **Server-side rendering of the first widget.** The dashboard's health panel
   could be inlined into the HTML response to remove its 229 ms round trip;
   everything else can stay asynchronous.
2. **Symbol and search pages.** These remain on the legacy Bootstrap markup.
   The symbol page in particular is a 500-line chart-heavy template and is the
   natural next migration.
3. **Virtualised tables.** The waiting-trades tab renders 272 rows and the
   watchlist 234. Both are fine today but will not stay fine at 5,000.
4. **A saved-view concept.** Market, timeframe and status filters are re-picked
   on every visit; persisting named filter sets would remove most of that.
5. **Drawer deep links.** `?trade=<id>` would make an investigation shareable.
6. **Density toggle.** A compact mode would let a 1440×900 laptop see the same
   number of rows a 1080p screen sees.

---

## 13. Known limitations

- **Open-trade duration is blank.** `_held_text` needs both an open and a
  close timestamp, and changing it would alter API output, which this sprint
  is not permitted to do. The open-trades table therefore shows entry time and
  omits the duration column rather than printing a column of dashes.
- **Two pytest-based test files do not run.** `tests/test_pine.py` and
  `tests/test_scoring.py` import `pytest`, which is not installed in this
  environment. This predates the sprint and is unrelated to the front end.
- **Symbol, search and performance pages are unmigrated.** They render
  correctly and are reachable, but they still use Bootstrap components rather
  than the design system.
- **The scanner table stays a table.** It is a screener over 315 symbols with
  15 columns; no card or chart encoding improves on that. It received the new
  header and summary metrics but its grid is unchanged.
- **The dev server needs a restart to pick up template edits.** It runs with
  `--noreload` and a cached template loader.
- **Zero-scroll is verified at 1920×1080.** Below roughly 900 px of viewport
  height the dashboard scrolls, by design.

---

## 14. Before vs after

| Dimension | Before | After |
| --- | --- | --- |
| Landing page | Scanner table, 315 rows, 15 columns | Operations dashboard, 8 widgets, zero scroll |
| Dashboard data fetch | One blocking `/api/dashboard/` bundle | Seven independent widget requests |
| Failure mode | One slow query blanks the page | One widget shows an error box; the rest render |
| Loading feedback | Global spinner | Per-widget skeletons shaped like their content |
| Trade investigation | A long scrolling detail panel | Nine-tab drawer, no panel scrolls |
| AI page | Raw JSON and internal object dumps | Confidence bars, status badges, a weakest-link callout |
| Empty states | "لا بيانات" | Explanation, numbered steps, CTA, estimated runtime |
| Tables | Six identical dash-filled columns per tab | Per-tab column sets; every cell is a component |
| RTL numerics | `1.00R-`, `0.1-` on axes | Unicode-isolated throughout, including canvas ticks |
| Component reuse | Per-page markup | 16 shared components, 0 page-local reimplementations |
| Static assets | Browser-cached, stale after edits | mtime-stamped URLs |
| Navigation | Flat list of pages | Workflow groups with `aria-current` and a skip link |

---

## 15. Test results

```
python manage.py check                    → 0 issues
28 test scripts (tests_*.py)              → 28/28 exit 0, 0 failures
  tests_widgets.py, tests_trades.py, tests_trade_filters.py,
  tests_times.py, tests_tracking.py, tests_settlement.py,
  tests_storage.py, tests_settings.py, tests_research_engine.py,
  tests_optimization.py, tests_predictive.py, tests_decision_ai.py,
  tests_feature_intelligence.py, tests_intelligence.py,
  tests_ml_foundation.py, tests_orchestration.py, tests_pipeline.py,
  tests_pipeline_integration.py, tests_similarity.py, tests_reasoning.py,
  tests_knowledge.py, tests_alpaca.py, tests_breakout.py,
  tests_crowding.py, tests_execution.py, tests_lan.py,
  tests_recobt.py, tests_search.py
tests/test_pine.py, tests/test_scoring.py → skipped (pytest not installed)
```

Browser verification, per page and per tab, asserting that every widget
reaches `data-state="ready"`, that no panel overflows its container, and that
no rendered text contains `[object Object]`, `undefined`, `NaN` or JSON
punctuation:

| Page | Tabs checked | Result |
| --- | --- | --- |
| Dashboard | — | 8/8 widgets ready, 0 px scroll at 1920×1080 |
| Trades | open, waiting, closed | ready, no leaks |
| Trade drawer | overview, ai, chart, research, prediction, optimization, history, evidence, notes | 9/9 ready, none scrolls |
| AI | overview, prediction, decision, features | ready, no raw JSON |
| Analytics | trends, factors, splits | ready, charts render |
| Research | confidence, experiments, baselines, export | ready |
| Optimization | leaderboard, accepted, rejected, walkforward, history | ready, empty state correct |
| Watchlist | — | ready |
| Scanner, Settings, Symbol | — | render correctly |

Responsive: no horizontal document overflow at 1920×1080, 1366×768 or
834×1112.

---

## 16. Layout descriptions

**Dashboard** — Page header on one line. Then a five-card metric row: an
oversized health score (0–100, tone-coloured, with a status badge and the
sample size) followed by four compact KPIs (expectancy, profit factor, win
rate with its confidence interval, max drawdown). Below that a full-width
verdict insight card in plain language. Then a three-card status row: current
opportunities, AI status, optimization status, each with a "→" link to its
page. The bottom half splits: two-thirds for the cumulative equity curve with
its headline R figure and a stability badge, one-third for a nine-item alert
timeline; under the curve, the top five open trades as a list with status
badges for pending rows and signed R for live ones. Nothing scrolls.

**Trades** — Header with settlement state and two action buttons. Four-card
exposure summary. Source filter chips. Three tabs. The open tab shows symbol,
unrealised R with a direction arrow, grade chip, entry time and entry-factor
chips. The waiting tab drops the realised columns entirely and shows the
signal candle and the factors that triggered the scan. The closed tab shows
result badge, realised R, exit time and holding duration.

**Trade drawer** — Slides in from the inline-end edge over a backdrop. A fixed
header carries the symbol, a status badge and a summary strip (realised flag,
grade, timeframe, status, market). Nine tabs below it, each panel sized to fit
without scrolling; tabs with no per-trade data show an explanatory empty state
pointing at the page that does have it. Repair and settlement buttons pin to
the footer.

**AI centre** — A hero card with the composite readiness score out of 100, a
trust badge and one sentence of interpretation. Two columns: decision
components as labelled confidence bars, each with a one-line explanation of
what the number measures; and the module list with connection badges. A
weakest-link insight card names the component dragging the score down. Three
further tabs cover prediction, decision weights as a distribution, and feature
quality.

**Analytics** — Three expectancy metric cards, a trend insight strip, then the
cumulative equity curve and rolling expectancy chart side by side. The splits
tab shows an overall metric row, then a 2×2 grid of split cards; each card
holds a heatmap of segments (expectancy, sample size, win rate per cell) above
a distribution of total R per segment, and closes with a sentence naming the
best segment.

**Research** — Confidence bars for statistical significance, win-rate interval,
sample adequacy and event independence, each captioned with what it means.
Below them three cards for the expectancy point estimate and its bounds, then
a verdict insight. Further tabs cover experiments, baseline comparison and
export.

**Optimization** — With no runs, the page is a single instructional empty
state: icon, title, explanation, four numbered steps, a "copy the command"
button, a link to the research lab, and an estimated runtime. With runs, it
becomes a summary strip, a leaderboard table with parameter chips, accepted
and rejected partitions, a walk-forward in-sample/out-of-sample distribution,
and run history.

**Watchlist** — Four summary cards (watched, about to trigger, closest
distance, total triggered). The table leads with a proximity bar — full and
green at the entry price, empty and grey at 5% away — followed by direction,
entry, live price, stop, target, R:R, grade and factor chips. A card below
lists recently triggered watches with their trigger price and notification
status.
