# AIA-03 Runtime Integration Report — Claude Execution Layer

## 1. Executive Summary

Sprint AIA-03 Runtime Integration connects the configured Claude provider to the live scan/recommendation workflow. `AIAdvisorService.review()` now executes during every scan pass for ready recommendations, persists successful reviews to memory and history, and exposes real runtime metrics on the dashboard.

Claude failures never interrupt trading or scanning. Rejected validations are not persisted.

## 2. Files Created

| File | Purpose |
|------|---------|
| `scanner/ai_advisor/runtime.py` | Scan hook — `review_recommendation()`, `review_scan_candidates()` |
| `scanner/ai_advisor/runtime_state.py` | Persistent status: disconnected/connected/running/failed/disabled |
| `scanner/ai_advisor/runtime_history.py` | Append-only `data/advisor_history.jsonl` |
| `scanner/ai_advisor/token_cost.py` | Token cost estimation |
| `tests_ai_advisor_runtime.py` | Runtime unit tests |
| `data/advisor_runtime_state.json` | Created at runtime |
| `data/advisor_history.jsonl` | Created at runtime |

## 3. Files Modified

| File | Change |
|------|--------|
| `scanner/ai_advisor/advisor_engine.py` | Load provider from settings; token metrics; save only accepted reviews |
| `scanner/ai_advisor/advisor_service.py` | Runtime UI model with status, tokens, cost, grounding |
| `scanner/ai_advisor/providers/claude_provider.py` | Capture `last_usage` from API response |
| `scanner/ai_advisor/advisor_logging.py` | Runtime log events |
| `web/dashboard/management/commands/scan.py` | Invoke advisor for ready recommendations after scan |
| `web/dashboard/static/dashboard/dashboard-page.js` | Dashboard widget shows advisor runtime metrics |
| `web/dashboard/views.py` | Test connection sets `connected` state |

## 4. Integration Point

**`web/dashboard/management/commands/scan.py`** — after scan results are saved:

```python
from scanner.ai_advisor.runtime import review_scan_candidates
review_scan_candidates(advisor_items)  # ready recommendations only
```

Each ready symbol triggers:
1. `build_layer_outputs()` — Decision Package summaries only
2. `AIAdvisorService.review_trade()` — Claude API via configured provider
3. Memory + history persistence on validation success

## 5. Claude Runtime Flow

```
Scan completes → ready recommendation
    ↓
runtime.review_recommendation()
    ↓
AIAdvisorService.review_trade()
    ↓
AdvisorEngine.review() [provider from settings]
    ↓
ClaudeProvider.analyze() → Anthropic API
    ↓
ResponseParser → ResponseValidator
    ↓
If accepted → advisor_memory.jsonl + advisor_history.jsonl
    ↓
AdvisorRuntimeState → status: running
    ↓
Widget API → Dashboard
```

## 6. Sample Request (API key redacted)

```json
{
  "model": "claude-sonnet-4-6",
  "max_tokens": 4096,
  "temperature": 0.2,
  "system": "You are the CS Edge AI Advisor operating in Shadow Mode... Respond with valid JSON only.",
  "messages": [
    {
      "role": "user",
      "content": "<Decision Package JSON — summaries only, no OHLC>"
    }
  ]
}
```

Header: `x-api-key: [REDACTED — from ANTHROPIC_API_KEY env]`

## 7. Sample Response

```json
{
  "agreement": "agree",
  "confidence": 78,
  "summary": "Evidence layers align with platform decision.",
  "reasoning": "Trend and recommendation support the buy setup.",
  "supporting_evidence": [
    {"evidence_id": "ev_trend", "section": "market_context", "field": "trend_direction", "note": "bullish"}
  ],
  "contradicting_evidence": [],
  "risks": ["Sample size may be insufficient"],
  "missing_information": [],
  "suggested_experiment": null,
  "shadow_mode_acknowledged": true
}
```

## 8. Token Accounting

Captured from Anthropic `response.usage`:
- `prompt_tokens` (input_tokens)
- `completion_tokens` (output_tokens)
- `total_tokens`

Stored in `advisor_history.jsonl` and `advisor_runtime_state.json`.

## 9. Cost Calculation Method

`token_cost.estimate_cost(model, prompt_tokens, completion_tokens)`:

```
cost = (prompt_tokens / 1M × input_rate) + (completion_tokens / 1M × output_rate)
```

Rates per model in `token_cost.py` (e.g. Sonnet: $3/$15 per 1M input/output).

## 10. Failure Recovery Strategy

| Failure | Behavior |
|---------|----------|
| Claude API error | Log error, status → `failed`, scan continues |
| Invalid JSON | Retry once, then reject |
| Validation failure | Reject, do not save, log reason |
| Provider disabled | Skip advisor, status → `disabled` |
| No API key | Skip advisor, status → `disconnected` |

Scan/trading never blocked. `try/except` wraps all advisor calls.

## 11. Dashboard Changes

**Widget:** `GET /api/widgets/ai-advisor/` (dashboard `w-ai` card)

Displays:
- Runtime status (يعمل / متصل / غير متصل / فشل / معطّل)
- Provider model
- Last review time
- Latency (ms)
- Total tokens
- Estimated cost ($)
- Grounding score (%)
- Successful review count
- Review ID

No page redesign — existing widget card updated.

## 12. Test Results

| Suite | Result |
|-------|--------|
| `tests_ai_advisor.py` | 47/47 passed |
| `tests_ai_advisor_runtime.py` | 22/22 passed |
| `tests_ai_claude_provider.py` | 35/35 passed |
| `tests_ai_advisor_evaluation.py` | 44/44 passed |
| `tests_ai_learning.py` | 58/58 passed |

## 13. Technical Debt (document only)

1. **Orchestration stage not wired** — advisor runs from scan command, not `AnalysisOrchestrator` pipeline. Future: optional `ai_advisor` stage handler.
2. **Per-symbol API cost** — all ready symbols in a scan pass trigger Claude calls; no batching or rate-limit queue.
3. **Mock provider default** — when `ai_default_provider=mock`, runtime skips; must set `claude` + enable in Settings.
4. **Cost rates hardcoded** — should move to `data/ai_provider_models.json` pricing section.
5. **Trade-close evaluation hook** — evaluation framework exists but not auto-triggered on trade settlement.
6. **AI page (`/ai/`)** — still shows platform modules; advisor detail is on dashboard widget only.
