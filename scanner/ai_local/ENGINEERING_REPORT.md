# AIA-06 Engineering Report — Local AI Foundation

**Sprint:** AIA-06  
**Date:** 2026-08-10  
**Final Status:** `NOT READY` (local AI disabled; Ollama not running on verification host)

---

## 1. Files Created

| Path | Purpose |
|------|---------|
| `scanner/ai_local/__init__.py` | Public exports |
| `scanner/ai_local/config.py` | Local AI configuration |
| `scanner/ai_local/interfaces.py` | Future training hooks |
| `scanner/ai_local/model_registry.py` | Qwen3 model registry |
| `scanner/ai_local/ollama_provider.py` | Ollama LLMProvider |
| `scanner/ai_local/health.py` | Ollama health checks |
| `scanner/ai_local/history.py` | Append-only `local_ai_history.jsonl` |
| `scanner/ai_local/comparisons.py` | Compare mode persistence |
| `scanner/ai_local/metrics.py` | Local metrics aggregation |
| `scanner/ai_local/benchmark.py` | Claude vs Qwen leaderboard |
| `scanner/ai_local/routing.py` | Execution mode routing |
| `scanner/ai_local/runtime.py` | Runtime status helpers |
| `scanner/ai_local/README.md` | Package documentation |
| `web/dashboard/ai_local_views.py` | REST API endpoints |
| `scripts/verify_local_ai.py` | Real runtime verification |
| `tests_ai_local.py` | Infrastructure tests |
| `tests_ai_ollama_provider.py` | Ollama provider tests |
| `tests_ai_model_registry.py` | Model registry tests |
| `tests_ai_compare_mode.py` | Compare mode tests |

## 2. Files Modified

| Path | Change |
|------|--------|
| `scanner/ai_advisor/provider_factory.py` | `create_ollama_provider()` |
| `scanner/ai_advisor/provider_registry.py` | Register Ollama |
| `scanner/ai_advisor/token_cost.py` | $0 API cost for local models |
| `scanner/ai_advisor/runtime.py` | Route via `execute_review()` |
| `scanner/ai_advisor/models_catalog.py` | Ollama model catalog |
| `scanner/ai_advisor/explainability/manual_analysis_service.py` | Compare mode payload |
| `scanner/settings_schema.py` | Local AI settings group |
| `data/ai_provider_models.json` | Ollama provider + models |
| `web/dashboard/urls.py` | `/api/ai/local/*` routes |
| `web/dashboard/views.py` | `_local_ai_status()` for settings |
| `web/dashboard/templates/dashboard/settings.html` | Local AI status card |
| `web/dashboard/templates/dashboard/ai.html` | النماذج tab |
| `web/dashboard/static/dashboard/ai-page.js` | Models leaderboard UI |
| `web/dashboard/static/dashboard/ai-advisor-explain.js` | Compare drawer |
| `web/dashboard/static/dashboard/design-system.css` | Compare/models styles |

## 3. Architecture

```
UnifiedDecisionPackage (built once)
        |
        +------------------+
        |                  |
        v                  v
ClaudeProvider       OllamaProvider
        |                  |
        v                  v
    Claude API          Ollama /api/chat
        |                  |
        +--------+---------+
                 |
                 v
          ResponseValidator
                 |
                 v
          Evaluation Engine (unchanged)
```

**Execution modes:** `claude_only` (default) | `local_only` | `local_first` | `compare`

**Shadow mode:** Platform decisions never modified. Compare mode is observational only.

## 4. Configuration

| Setting | Default | Notes |
|---------|---------|-------|
| `ai_local_enabled` | `false` | Must be explicitly enabled |
| `ai_ollama_enabled` | `false` | |
| `ai_ollama_base_url` | `http://127.0.0.1:11434` | |
| `ai_local_model` | `qwen3:8b` | Also `qwen3:4b` |
| `ai_execution_mode` | `claude_only` | Production unchanged |

## 5. Ollama Setup

```bash
# Install from https://ollama.com
ollama pull qwen3:8b
ollama serve   # usually auto-starts

# Verify
curl http://127.0.0.1:11434/api/tags
python scripts/verify_local_ai.py
```

Enable in Settings → الذكاء المحلي:
1. تفعيل الذكاء المحلي
2. تفعيل Ollama
3. Choose execution mode
4. Test Ollama button

## 6. Supported Models

| Model | Context | Provider |
|-------|---------|----------|
| `qwen3:4b` | 32K | Ollama |
| `qwen3:8b` | 32K | Ollama |

Registry is extensible via `scanner/ai_local/model_registry.py`.

## 7. Test Results

| Suite | Result |
|-------|--------|
| `tests_ai_model_registry.py` | 10/10 |
| `tests_ai_ollama_provider.py` | 9/9 |
| `tests_ai_compare_mode.py` | 13/13 |
| `tests_ai_local.py` | 16/16 |
| `tests_ai_advisor.py` | 47/47 |
| `tests_ai_claude_provider.py` | 35/35 |
| `tests_ai_advisor_runtime.py` | 22/22 |

All existing tests remain green.

## 8. Real Verification Result

```
STATUS: NOT READY
Reason: ai_local_enabled is False — enable in settings.
Ollama: not running on verification host (connection refused).
```

To reach `VERIFIED`:
1. Enable local AI in settings
2. Start Ollama with qwen3 model pulled
3. Run `python scripts/verify_local_ai.py`

## 9. Claude vs Qwen Comparison Example

When `execution_mode = compare`, both providers receive the **same** `UnifiedDecisionPackage`:

```
Package fingerprint: pkg_a1b2c3d4...
Platform decision:   BUY (unchanged)

Claude:  agree · 82% · 1400ms · $0.06
Qwen:    agree · 76% ·  800ms · $0.00

Stored in: data/local_ai_comparisons.jsonl
```

No winner selected — observational only.

## 10. Known Limitations

- GPU/memory monitoring is optional, not a hard dependency
- Real Qwen inference not verified on this host (Ollama offline)
- Compare UI shows data only after compare-mode reviews exist
- Training/fine-tuning intentionally not implemented (future sprint)

## 11. Resource Requirements

| Resource | qwen3:4b | qwen3:8b |
|----------|----------|----------|
| RAM | ~4 GB | ~8 GB |
| GPU | Optional (faster) | Recommended |
| Disk | ~2.5 GB | ~5 GB |
| API cost | $0 | $0 |

Local inference has compute cost even when API cost is $0.

## 12. Recommended Next Sprint

1. Enable compare mode in staging; collect 100+ paired reviews
2. Trade outcome correlation (Claude vs Qwen agreement vs PnL)
3. Teacher pipeline hooks: Claude → validated review → training dataset
4. QLoRA fine-tuning on high-quality examples
5. Auto-escalation tuning from benchmark data

---

**Acceptance checklist:**

- [x] Ollama provider implemented
- [x] Qwen models in registry
- [x] Provider abstraction compatible
- [x] Local metrics + history
- [x] Compare mode (same package)
- [x] Execution modes configurable
- [x] Claude unchanged (default claude_only)
- [x] API + UI (النماذج tab)
- [x] Tests pass (mocked Ollama)
- [x] Verification script exists
- [ ] Real Qwen review verified (blocked: Ollama offline + settings disabled)
