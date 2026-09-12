# AIA-06.1 — Real Ollama/Qwen Verification Report

**Date:** 2026-08-10  
**Final Status:** `VERIFIED`

---

## Environment

| Item | Value |
|------|-------|
| Ollama version | 0.32.5 |
| Ollama endpoint | `http://127.0.0.1:11434` |
| Ollama status | Running (started via `ollama serve`) |
| System RAM | 31.1 GB |
| Model installed | **qwen3:8b** (5.2 GB) |

---

## Application Configuration

| Setting | Value |
|---------|-------|
| `ai_local_enabled` | `true` |
| `ai_ollama_enabled` | `true` |
| `ai_execution_mode` | `compare` |
| `ai_local_model` | `qwen3:8b` |
| `ai_default_provider` | `claude` (unchanged) |
| `ai_timeout` | `300s` (increased for local inference) |

---

## Real Qwen Review (VERIFIED)

| Field | Value |
|-------|-------|
| review_id | `adv_867fbc79e86748bd` |
| provider | `ollama` |
| model | `qwen3:8b` |
| symbol | BTCUSDT |
| timeframe | 4h |
| latency | 54,599 ms |
| prompt_tokens | 2,050 |
| completion_tokens | 787 |
| total_tokens | 2,837 |
| validation | **passed** |
| grounding_score | 100.0 |
| hallucination_score | 0.0 |
| agreement | partial |
| confidence | 65.0 |

Pipeline: `UnifiedDecisionPackage → PromptBuilder → OllamaProvider → Qwen → ResponseParser → ResponseValidator → LocalAIHistory`

---

## Persistence Evidence

**`data/local_ai_history.jsonl`** — 36 real runtime records (not test fixtures).

Verified record example:
```json
{
  "review_id": "adv_867fbc79e86748bd",
  "provider": "ollama",
  "model": "qwen3:8b",
  "validation_passed": true,
  "total_tokens": 2837,
  "latency_ms": 54599.4,
  "grounding_score": 100.0
}
```

**`data/local_ai_comparisons.jsonl`** — 25 comparison records from compare mode.

---

## Claude vs Qwen Benchmark (10 comparisons)

**Evidence strength:** `EMERGING` (n=10, below STRONG threshold)

| Metric | Claude | Qwen | Difference |
|--------|--------|------|------------|
| Validation success | 70% | 60% | — |
| Avg confidence | 53.1% | 56.3% | -3.2 (Claude lower) |
| Avg latency | 38,189 ms | 117,219 ms | Claude faster |
| Avg tokens | 9,961 | 2,921 | — |
| API cost | $0.35 | $0.00 | Infrastructure cost ≠ $0 |
| Agreement match rate | 0% | — | Qwen always `partial` vs Claude `disagree`/`agree` |

**Package fingerprint:** 10/10 identical (`fingerprint_identical: true`)

**Note:** Claude API credit exhausted after comparison #7 (3 comparisons had Claude errors). Platform and Qwen continued normally — failure isolation confirmed.

**No winner declared** — observational benchmark only.

Full results: `data/aia061_benchmark.json`

---

## Performance

| Metric | Value |
|--------|-------|
| First request (cold) | ~60,218 ms |
| Warm request | ~54,599–56,763 ms |
| Benchmark average | 117,219 ms (under sustained load) |
| Tokens/sec (avg) | ~24 tok/s (2821 tokens / 117s) |

GPU monitoring: not required; not measured.

---

## Failure Isolation

Tested with Ollama on dead port (`11435`):
- `local_only`: returns error, does not crash pipeline
- `claude_only`: continues (returns result or graceful failure)
- Scanning/trading/decision engine: unaffected

---

## Integration Fixes (AIA-06.1)

1. `load_local_config()` — fixed `dashboard.appsettings` import path for Django runtime
2. `OllamaProvider` — added `format: json`, `think: false` for Qwen3, thinking-block strip
3. `runtime_status()` — returns `VERIFIED` when validated local review exists
4. `scripts/activate_local_ai.py` — settings activation helper
5. `scripts/run_compare_benchmark.py` — real compare benchmark runner

---

## Tests (all green)

| Suite | Result |
|-------|--------|
| tests_ai_model_registry.py | 10/10 |
| tests_ai_ollama_provider.py | 9/9 |
| tests_ai_compare_mode.py | 13/13 |
| tests_ai_local.py | 16/16 |
| tests_ai_advisor.py | 47/47 |
| tests_ai_claude_provider.py | 35/35 |
| tests_ai_advisor_runtime.py | 22/22 |
| tests_ai_explainability*.py | 63/63 |
| tests_ai_advisor_evaluation.py | 44/44 |
| tests_ai_learning.py | 58/58 |

---

## Recommended Next Step

**AIA-06.2 — Data Collection & Teacher/Student Dataset**

Collect validated triples:
- Claude review + Qwen review + UnifiedDecisionPackage + trade outcome + AIA-05.5 evaluation

Do NOT start LoRA/QLoRA until sample size reaches STRONG threshold (100+ paired evaluations).
