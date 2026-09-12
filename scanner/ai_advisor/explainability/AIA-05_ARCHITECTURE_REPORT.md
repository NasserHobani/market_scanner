# AIA-05 — Explainable AI & Manual Analysis
## Principal Software Architect Report

**Sprint:** AIA-05  
**Date:** 2026-08-09  
**Classification:** Additive integration layer — no engine modifications

---

## 1. Executive Summary

Sprint AIA-05 transforms the AI Advisor from a background shadow service into a **fully inspectable explainability platform**. Users can:

- Browse every Claude review in a paginated timeline
- Open a 45%-width investigation drawer with full reasoning (untruncated)
- Click evidence IDs to navigate to originating platform layers
- See live review cards as scans complete
- Manually request AI analysis from Scanner, Symbol, Search, Watches, and Chart contexts
- Export reviews as JSON, Markdown, or PDF
- Track trade outcomes, evaluation, and learning linked to each review

**Design principle:** All new capability sits in an additive `explainability` package and dashboard API/UI layer. The existing `review_recommendation()` → `UnifiedDecisionPackage` → `ClaudeProvider` pipeline is reused without modification.

---

## 2. Architecture

### 2.1 Layer Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        UI Layer (Dashboard)                      │
│  AI Center tabs · Review Drawer · Manual Analysis button          │
│  ai-advisor-explain.js · ai-page.js                               │
└────────────────────────────┬────────────────────────────────────┘
                             │ REST + Widgets
┌────────────────────────────▼────────────────────────────────────┐
│              web/dashboard/ai_explainability_views.py              │
│  GET  /api/ai/reviews/          POST /api/ai/manual-analysis/     │
│  GET  /api/ai/reviews/live/     GET  /api/ai/reviews/:id/export/ │
│  GET  /api/widgets/ai-review-timeline/                           │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│           scanner/ai_advisor/explainability/ (NEW)               │
│  ReviewTimelineService    ManualAnalysisService                    │
│  ReviewMetaStore          review_export · evidence_links          │
│  manual_formatter         symbol_context                          │
└────────────────────────────┬────────────────────────────────────┘
                             │ calls (read-only / wrapper)
┌────────────────────────────▼────────────────────────────────────┐
│           EXISTING PIPELINE (unchanged)                          │
│  runtime.review_recommendation() → AIAdvisorService.review_trade │
│  → UnifiedDecisionPackage → ClaudeProvider → memory + history     │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Stores

| Store | Path | Role |
|-------|------|------|
| `advisor_history.jsonl` | `data/` | Runtime metrics (existing) |
| `advisor_memory.jsonl` | `data/` | Full review + reasoning (existing) |
| `advisor_review_meta.jsonl` | `data/` | **NEW** — review_type, recommendation snapshot, fingerprint |
| `advisor_evaluations.jsonl` | `data/` | Post-trade evaluation (existing) |
| `manual_analysis_cache.json` | `data/` | **NEW** — 10-minute TTL cache |

Automatic reviews default to `review_type=automatic`. Manual reviews write explicit `review_type=manual` to meta store after pipeline completion.

---

## 3. APIs

### 3.1 Review Timeline

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/ai/reviews/` | Paginated list with search/filters |
| GET | `/api/ai/reviews/live/` | Latest review for live card |
| GET | `/api/ai/reviews/<review_id>/` | Full drawer payload |
| GET | `/api/ai/reviews/<review_id>/export/?format=json\|markdown\|pdf` | Download |
| GET | `/api/ai/providers/` | Provider statistics |

**Query parameters (list):** `page`, `page_size`, `q`, `provider`, `agreement`, `type`, `symbol`, `from`, `to`

### 3.2 Manual Analysis

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/ai/manual-analysis/` | On-demand Claude review |

**Input:**
```json
{
  "symbol": "BTCUSDT",
  "market": "crypto",
  "timeframe": "4h",
  "force": false
}
```

**Output:** Full review model + 15-field manual analysis display + metrics

### 3.3 Widgets

| Widget | Endpoint |
|--------|----------|
| AI Review Timeline | `GET /api/widgets/ai-review-timeline/` |

---

## 4. UI Flows

### 4.1 AI Center (`/ai/`)

| Tab | Content |
|-----|---------|
| Overview | Advisor runtime + platform health |
| Live Reviews | Polling live card (12s interval) |
| Review History | Searchable paginated table → drawer |
| Learning | Lessons from closed trades |
| Evaluation | Accuracy metrics |
| Provider Statistics | Per-provider token/cost/latency |
| Prediction / Decision / Features | Existing platform modules (preserved) |

### 4.2 Review Drawer (45% width)

Collapsible sections:
1. Executive Summary
2. Claude Response (full reasoning, copy button, no truncation)
3. Supporting / Contradicting Evidence (clickable `evidence_id` links)
4. Risk Analysis
5. Suggested Experiment
6. Trade Result (outcome, R, Claude correct?, learning generated?)
7. Evaluation
8. Learning

Export footer: JSON · Markdown · PDF

### 4.3 Manual Analysis Flow

```
User clicks "حلّل بالذكاء"
  → Drawer opens with loading animation
  → POST /api/ai/manual-analysis/
  → symbol_context.build_symbol_context() (scores, no OHLC to Claude)
  → review_recommendation() (same as scan)
  → ReviewMetaStore tags review_type=manual
  → 15-field manual_formatter maps response
  → Drawer shows results + link to full review
```

**Button locations:** Symbol page, Scanner row, Watches row, Search analysis, Chart context (symbol page)

### 4.4 Evidence Navigation

`evidence_links.py` maps `evidence_id` prefixes to platform URLs:

| Prefix | Destination |
|--------|-------------|
| `ev_similarity` | Symbol page |
| `ev_prediction` | AI Center → Prediction |
| `ev_research` | Research lab |
| `ev_decision` | AI Center → Decision |
| `ev_feature` | AI Center → Features |

---

## 5. Caching Strategy

| Layer | TTL | Key |
|-------|-----|-----|
| Manual analysis | 10 minutes | `market:symbol:timeframe:fingerprint` |
| Widget cache | Existing TTL_HEALTH | Per widget name + filters |

Cache invalidates when `recommendation_fingerprint()` changes (action, side, grade, confidence, entry, stop, R-target).

`force=true` bypasses cache.

---

## 6. Persistence

### Review Detail Model (drawer)

Every successful review exposes:
- Review ID, timestamp, provider, model
- Latency, prompt/completion/total tokens, estimated cost
- Grounding score, hallucination score
- Agreement, confidence, recommendation
- Summary, full reasoning, evidence lists, risks, missing info, experiment
- Review status, review type (automatic/manual)
- Trade result enrichment (when trade closes)
- Evaluation + learning linkage

### Trade Result Attachment (Part 2)

On trade close, existing `production_hooks.on_trade_settled()` writes evaluation. `ReviewTimelineService.get_review()` joins:
- `AdvisorMemory.later_performance`
- `advisor_evaluations.jsonl`
- `learning_lessons.jsonl` (by evaluation_id)

Displayed in drawer: Outcome, Win/Loss, R, Correct AI?, Did Claude agree?, Learning generated?

---

## 7. Security

| Concern | Mitigation |
|---------|------------|
| API key exposure | Never returned in API; only `api_key_configured` flag |
| CSRF | POST endpoints require Django CSRF token |
| Rate limiting | Manual analysis is user-initiated; cache reduces duplicate Claude calls |
| Shadow mode | Preserved — reviews never modify trading decisions |
| Trading isolation | `review_recommendation()` never raises; scan/trade paths unaffected |
| Export | Review data only; no raw prompts unless `ai_save_raw_responses` enabled |

---

## 8. Testing

| Suite | Tests | Status |
|-------|-------|--------|
| `tests_ai_explainability.py` | 14 | Pass |
| Existing advisor suites | 97+ | Unchanged |

Coverage:
- Fingerprint stability
- Evidence link resolution
- Manual formatter 15-field mapping
- Timeline list/detail/export
- Meta store review_type tagging

---

## 9. Backward Compatibility

| Constraint | Status |
|------------|--------|
| No Scanner changes | ✅ |
| No Knowledge/Research/Prediction/Optimization/Decision AI changes | ✅ |
| No Trading Engine changes | ✅ |
| Existing AI Advisor pipeline unchanged | ✅ |
| Shadow mode preserved | ✅ |
| Existing history/memory format compatible | ✅ (meta is additive file) |

---

## 10. Files Added / Modified

### New Files

```
scanner/ai_advisor/explainability/
  __init__.py
  review_meta.py
  evidence_links.py
  manual_formatter.py
  symbol_context.py
  manual_analysis_service.py
  review_timeline_service.py
  review_export.py
  AIA-05_ARCHITECTURE_REPORT.md

web/dashboard/ai_explainability_views.py
web/dashboard/static/dashboard/ai-advisor-explain.js
tests_ai_explainability.py
```

### Modified (additive only)

```
web/dashboard/urls.py
web/dashboard/widgets.py
web/dashboard/widget_views.py
web/dashboard/templates/dashboard/ai.html
web/dashboard/static/dashboard/ai-page.js
web/dashboard/templates/dashboard/symbol.html
web/dashboard/templates/dashboard/scanner.html
web/dashboard/templates/dashboard/watches.html
web/dashboard/templates/dashboard/search.html
web/dashboard/static/dashboard/app.js
web/dashboard/static/dashboard/watches-page.js
web/dashboard/static/dashboard/design-system.css
web/dashboard/static/dashboard/platform.css
```

---

## 11. Future Roadmap

| Phase | Enhancement |
|-------|-------------|
| AIA-05.1 | WebSocket push for live reviews (replace polling) |
| AIA-05.2 | Package snapshot in drawer (full UnifiedDecisionPackage JSON) |
| AIA-05.3 | Evidence deep-link modal (inline layer preview without navigation) |
| AIA-05.4 | Review comparison (side-by-side automatic vs manual) |
| AIA-05.5 | Rate limiting dashboard + per-user quotas |
| AIA-05.6 | Rich PDF export (styled HTML → PDF via headless browser) |
| AIA-05.7 | Auto-tag automatic reviews in meta store via lightweight post-scan hook |

---

## 12. Acceptance Criteria

| Criterion | Status |
|-----------|--------|
| Every Claude review inspectable | ✅ |
| Readable explanation per recommendation | ✅ |
| Manual analysis generates complete report | ✅ |
| Manual + automatic share same pipeline | ✅ |
| No duplicated prompt logic | ✅ |
| Uses UnifiedDecisionPackage | ✅ |
| No engine modifications | ✅ |
| Shadow mode preserved | ✅ |
| Trading never waits for Claude | ✅ |
| All analyses in history | ✅ |
| Review drawer from every symbol | ✅ |
| 100% backward compatible | ✅ |

---

## 13. Operational Notes

1. **Manual analysis** requires `ANTHROPIC_API_KEY` and `is_advisor_enabled()=True`
2. **First manual analysis** per symbol takes ~30–60s (Claude latency)
3. **Cached results** return instantly for 10 minutes unless recommendation changes
4. **Deep link:** `/ai/?review=adv_xxx` opens drawer on load
5. **Export PDF** uses minimal built-in PDF generator; for print-quality use Markdown export
