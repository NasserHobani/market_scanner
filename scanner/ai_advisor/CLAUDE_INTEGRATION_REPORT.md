# AIA-03 Engineering Report — Claude Provider Integration

## 1. Executive Summary

Sprint AIA-03 integrates Anthropic Claude as the first production AI Advisor provider. The implementation lives entirely within the existing provider abstraction — no changes to the Decision Engine, Prediction, Research, Optimization, or Advisor orchestration logic.

Claude connects through `scanner/ai_advisor/providers/claude_provider.py`, configured via a new AI Advisor settings group, with API keys loaded exclusively from the `ANTHROPIC_API_KEY` environment variable. The Settings page displays provider status and includes a Test Connection button.

## 2. Provider Architecture

```
Decision Package
    ↓
Prompt Builder (versioned)
    ↓
ProviderRegistry.get("claude")
    ↓
ClaudeProvider.analyze()
    ↓
Anthropic API (via SDK)
    ↓
JSON Response
    ↓
ResponseParser → ResponseValidator → AdvisorReview
    ↓
Evaluation → Learning (unchanged)
```

The platform never imports Anthropic outside the provider module. All other code uses `LLMProvider` abstraction.

## 3. Claude Integration

**File:** `scanner/ai_advisor/providers/claude_provider.py`

| Method | Purpose |
|--------|---------|
| `analyze()` | Send prompt, receive JSON, retry on transient failures |
| `health()` | Provider status, latency, error rate |
| `model_name()` | Current model from settings |
| `provider_name()` | Returns `"claude"` |
| `supported_features()` | JSON mode, shadow mode, grounding, etc. |
| `test_connection()` | Minimal JSON health check |

**Factory:** `scanner/ai_advisor/provider_factory.py` creates configured instances.

**Model catalog:** `data/ai_provider_models.json` — models never hardcoded in provider code.

## 4. Settings Integration

New group in `scanner/settings_schema.py`: **مستشار الذكاء الاصطناعي (AI Advisor)**

| Field | Key | Default |
|-------|-----|---------|
| Enable Claude | `ai_claude_enabled` | false |
| Default Provider | `ai_default_provider` | mock |
| Claude Model | `ai_claude_model` | from catalog |
| Temperature | `ai_temperature` | 0.2 |
| Max Tokens | `ai_max_tokens` | 4096 |
| Timeout | `ai_timeout` | 60s |
| Retry Count | `ai_retry_count` | 2 |
| Shadow Mode | `ai_shadow_mode` | true |
| Memory | `ai_memory_enabled` | true |
| Evaluation | `ai_evaluation_enabled` | true |
| Learning | `ai_learning_enabled` | true |
| Prompt Version | `ai_prompt_version` | advisor_prompt_v1 |
| Strict JSON | `ai_strict_json` | true |
| Grounding Required | `ai_grounding_required` | true |
| Allow Experiments | `ai_allow_experiments` | true |
| Max Evidence Items | `ai_max_evidence_items` | 10 |
| Save Raw Responses | `ai_save_raw_responses` | false |
| Health Check Interval | `ai_health_check_interval` | 300s |

Persisted through existing `appsettings` / `Setting` model. No `.env` values in code.

## 5. Health Monitoring

`HealthState` tracks per-provider:

- `healthy` — last request succeeded
- `latency_ms` — last request latency
- `last_success` / `last_failure` — ISO timestamps
- `average_response_time_ms` — rolling average
- `error_rate` — failures / total requests (%)
- `provider_version` — provider code version

Settings page displays: provider, model, status, latency, last success, shadow/evaluation/learning flags.

## 6. Retry Strategy

| Condition | Retry? |
|-----------|--------|
| Timeout | Yes |
| Rate limit (429) | Yes |
| Server error (5xx) | Yes |
| Connection failure | Yes |
| Invalid JSON | Yes (once) |
| Validation error | No (post-parse) |
| Disabled provider | No |
| Missing API key | No |

Max attempts = `retry_count + 1` (default 3).

## 7. JSON Validation

1. System prompt enforces JSON-only when `ai_strict_json` is enabled
2. `ResponseParser` extracts JSON (handles fences as fallback)
3. On `JSONDecodeError`, retry once before rejecting
4. `ResponseValidator` handles grounding (unchanged)

## 8. Security

| Rule | Implementation |
|------|----------------|
| API key from env only | `os.environ["ANTHROPIC_API_KEY"]` |
| Never in UI | `config_to_public_dict()` excludes key |
| Never logged | `advisor_logging.py` strips key references |
| Never serialized | Not in settings DB, not in memory records |
| No prompt logging | Only metadata: provider, model, event_id, latency |
| No package logging | Decision Package never logged |

## 9. Configuration

**Config loader:** `scanner/ai_advisor/provider_config.py`

**Model catalog:** `scanner/ai_advisor/models_catalog.py` + `data/ai_provider_models.json`

**Dependencies:** `requirements-ai.txt` (`anthropic>=0.39.0`)

To enable:
```bash
pip install -r requirements-ai.txt
export ANTHROPIC_API_KEY=sk-ant-...
# Enable Claude in Settings → AI Advisor
```

## 10. Testing

```
python tests_ai_claude_provider.py
```

Mock Anthropic SDK via `_client_factory` injection. Tests cover:
- Provider interface (analyze, health, model_name, provider_name, supported_features)
- Configuration loading and public dict safety
- JSON parsing and JSON retry
- Timeout retry
- Disabled provider error
- Test connection
- No API key handling
- Provider factory
- Settings schema fields
- Registry integration

## 11. Risks

| Risk | Mitigation |
|------|------------|
| API costs from retries | Retry capped at `retry_count`; JSON retry only once |
| Key exposure in logs | Structured logging strips key patterns |
| Model deprecation | Models in JSON config, not code |
| SDK not installed | Clear error message; optional dependency |
| Provider outage | Health check + error rate tracking; fallback to mock provider |

## 12. Future Multi-Provider

Architecture already supports:
- `ProviderRegistry` with runtime registration
- `review_multi()` for parallel provider dispatch
- `data/ai_provider_models.json` extensible to OpenAI, Gemini, etc.
- Settings `ai_default_provider` choice field
- Benchmark/leaderboard from AIA-01.5 for provider comparison

Next sprints: OpenAI provider, provider routing based on evaluation scores, automatic failover.

## 13. Test Results

- `tests_ai_claude_provider.py` — all passed
- `tests_ai_advisor.py` — all passed (unchanged behavior via mock)
- `tests_ai_advisor_evaluation.py` — all passed
- `tests_ai_learning.py` — all passed
- `manage.py check` — no issues

Claude remains an Advisor in Shadow Mode. The trading engine is the single source of truth.
