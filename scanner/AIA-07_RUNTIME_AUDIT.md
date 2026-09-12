# AIA-07 — Runtime Audit Report

**Audit date:** 2026-08-10  
**Overall status:** CONFIGURED (training works; no model promoted to ACTIVE)

## Executive Summary

Runtime evidence shows the **learning loop is operational** but **prediction was never trained in production until this sprint**. The Evaluation tab showing Claude 0% on 3 samples is **not statistically meaningful** — now surfaced as `INSUFFICIENT` / `EARLY_SIGNAL`.

| Finding | Root cause | Resolution |
|---------|-----------|------------|
| "No trained prediction models" | No `data/predictive/` artifacts; training was manual-only | `PredictionTrainingOrchestrator` + trade dataset builder |
| Lessons ≠ model training | Learning only writes JSONL artifacts | Explicit lifecycle labels (`Lesson recorded`) |
| 0% Claude accuracy misleading | 3 evaluations, UI lacked sample context | `sample_reliability.py` + Evaluation tab fix |
| Model not active after training | Quality gates: OOS accuracy 45% < baseline 52% | Correct — `NOT_PROMOTED` |

---

## Runtime Truth Table

| Component | Implemented | Production-called | Automatic | Real data | Last execution | Artifact | Consumed downstream | Status |
|-----------|-------------|-------------------|-----------|-----------|----------------|----------|---------------------|--------|
| Trade settlement | ✅ | ✅ `trades.py` | ✅ | 201 closed | Live | DB | Evaluation, Learning | **WORKING** |
| Scan → Recommendation | ✅ | ✅ scan command | ✅ | Live | Live | ScanResult | Knowledge | **WORKING** |
| UnifiedDecisionPackage | ✅ | ✅ advisor runtime | On review | Live | Live | advisor memory | Claude/Qwen | **WORKING** |
| Claude/Qwen review | ✅ | ✅ routing.py | On scan/settle | Live | VERIFIED | history jsonl | Evaluation | **WORKING** |
| Review persistence | ✅ | ✅ | ✅ | Live | Live | advisor_memory | Evaluation | **WORKING** |
| Evaluation | ✅ | ✅ production_hooks | On trade close | **3 evals** | Last settle | advisor_evaluations.jsonl | Learning | **WORKING** (low N) |
| Failure classification | ✅ | ✅ failure_classifier | ✅ | 3 evals | Same | evaluations | Lessons | **WORKING** |
| Learning lessons | ✅ | ✅ LearningService | On settle | **7 lessons** | Last settle | learning_lessons.jsonl | UI, Research | **WORKING** |
| Knowledge proposals | ✅ | ✅ | ✅ | 5 proposals | Last cycle | learning_proposals.jsonl | None (advisory) | **ARTIFACT ONLY** |
| Research hypotheses | ✅ | ✅ | ✅ | 9 hypotheses | Last cycle | learning_hypotheses.jsonl | Research orchestrator | **WORKING** |
| Quant Research | ✅ | ✅ orchestrator | On settle | 6 jobs | rex completed | jobs.jsonl, experiments | Learning reports | **WORKING** |
| Prediction dataset | ✅ **NEW** | ✅ trade_dataset | On train | **201 eligible** | 2026-08-10 | datasets/registry.jsonl | Training | **WORKING** |
| Model training | ✅ **NEW** | ✅ orchestrator | On N trades | 201 rows | 2026-08-10 | mdl_2097ebe89fb14b7b | Registry | **WORKING** |
| Model registry | ✅ | ✅ | On train | 1 model | 2026-08-10 | registry.jsonl | Inference | **WORKING** |
| Quality gates | ✅ **NEW** | ✅ | On train | Real metrics | 2026-08-10 | job metrics | Promotion | **WORKING** |
| Active prediction | ✅ | ✅ layer_collectors | On review | None active | — | — | UDP | **NOT PROMOTED** |
| Prediction → Claude | ✅ | ✅ adapt_prediction | On review | unavailable reason | Live | UDP prediction layer | Advisor prompt | **ADVISORY** |

---

## Root Cause: Why Prediction Tab Was Empty

1. **No training orchestration** — `PredictiveService.train()` existed but was never called in production
2. **No `data/predictive/models/` directory** — zero persisted models
3. **Feature snapshot join gap** — only 3/201 trades have `feature_snapshot_id`; legacy `load_from_django()` returned empty
4. **UI showed binary empty state** — hid dataset eligibility and real reasons

**Fix:** `trade_dataset.py` builds from pre-trade trade fields (score, grade, factors, confidence) — 201/201 eligible.

---

## Real Training Results (2026-08-10)

```
Dataset: 201 eligible trades (dsfp fingerprint persisted)
Model:   mdl_2097ebe89fb14b7b
Test:    accuracy 45.2% vs baseline 51.6%
Status:  NOT_PROMOTED (correct — does not beat naive baseline)
Active:  none (requires explicit promotion)
```

---

## Learning Lifecycle States

Lessons now display **"دُرِّس مُسجَّل"** (Lesson recorded), not "AI learned".

```
OBSERVED → EVALUATED → LEARNED_AS_LESSON → HYPOTHESIS_CREATED → RESEARCHED
→ VALIDATED → CANDIDATE_FOR_PROMOTION → APPROVED → DEPLOYED
```

No stage auto-deploys to trading.

---

## Evaluation Sample Reliability

| Evaluations | State | UI label |
|-------------|-------|----------|
| 0 | NO_DATA | لا بيانات |
| 1–2 | INSUFFICIENT | عيّنة غير كافية |
| 3–9 | EARLY_SIGNAL | إشارة مبكرة |
| 10–19 | EMERGING | ناشئ |
| 20–49 | MEANINGFUL | عيّنة ذات معنى |
| 50+ | STRONG_SAMPLE | عيّنة قوية |

**Current:** 3 evaluations → `EARLY_SIGNAL` — 0% accuracy must not be interpreted as model failure.

---

## Closed Loop Status

```
Closed Trade (201) ✅
  → Evaluation (3 — low coverage) ⚠️
  → Learning (7 lessons) ✅
  → Hypotheses (9) ✅
  → Research (6 jobs) ✅
  → Prediction Dataset (201 eligible) ✅ NEW
  → Training (1 model, NOT_PROMOTED) ✅ NEW
  → Active Prediction (none) ⏸️
  → UDP → Claude/Qwen (prediction unavailable reason) ✅
  → Evaluation (continues) ✅
```

---

## Verification Commands

```bash
# Full lifecycle check
python scripts/verify_ai_learning_prediction.py

# Unit tests
python tests_ai_learning_prediction.py
python tests_ai_learning.py
python tests_ai_advisor_evaluation.py

# Manual training
python -c "
import django, os, sys
os.environ['DJANGO_SETTINGS_MODULE']='config.settings'
sys.path[:0]=['.','web']
django.setup()
from scanner.predictive.training_orchestrator import PredictionTrainingOrchestrator
print(PredictionTrainingOrchestrator().run_manual().to_dict())
"

# Promote only after human review
curl -X POST http://localhost:8000/api/prediction/promote/mdl_XXXX/
```

---

## Safety Confirmation

- ✅ No trading execution changes
- ✅ No automatic strategy deployment  
- ✅ No look-ahead features in dataset
- ✅ Quality gates block weak models
- ✅ Lessons ≠ model training (explicit labels)
- ✅ Prediction advisory only until promoted

**Final status: CONFIGURED** — training pipeline verified; await model that beats baseline for ACTIVE promotion.
