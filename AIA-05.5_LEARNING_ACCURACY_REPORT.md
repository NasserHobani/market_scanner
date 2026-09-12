# AIA-05.5 — Learning Accuracy, Failure Classification & Lesson Deduplication

## 1. Root causes

| Issue | Root cause |
|-------|------------|
| Generic **"other failure"** lessons | `LessonGenerator._from_failures` only checked `hallucination`, `missed_warning`, and `agree+lost`; `false_warning`, `partial`, and `disagree+win` fell through to `other_failure`. |
| Duplicate lessons | `LearningEngine.run_cycle` called `LessonRepository.save()` (append-only) with no fingerprint; two settlements 2ms apart created two identical lessons. |
| **Correct disagreement** treated as failure | Grouping used `advisor_correct=False` only; disagree+loss is correct but was lumped with failures when pattern detection ran on raw flags. |
| Partial always "incorrect" without type | `EvaluationEngine` set `advisor_correct=False` for partial but did not expose `evaluation_type` / `failure_type`. |
| Unhelpful Learning UI | `ai-page.js` rendered only English `title` in a bullet list. |

## 2. Failure classification matrix

| Condition | `evaluation_type` | `failure_type` | `advisor_correct` | `is_failure` |
|-----------|-------------------|----------------|-------------------|--------------|
| Hallucination | hallucination | hallucination | false | yes |
| Partial + loss | partial_on_loss | partial_on_loss | false | yes |
| Partial + win | partial_on_win | partial_on_win | false | yes |
| No risks + big loss (non-partial) | missed_warning | missed_warning | false | yes |
| Disagree + win | incorrect_disagreement | incorrect_disagreement | false | yes |
| Disagree + loss | correct_disagreement | — | **true** | **no** |
| Agree + loss | wrong_agreement | wrong_agreement | false | yes |
| Risks + win (not disagree) | false_warning | false_warning | varies | yes |
| Agree + win | agree_success | — | true | no |
| Unclassified incorrect | other_failure | other_failure | false | yes |

**Secondary (when `is_failure`):** `high_confidence_wrong` if confidence ≥ 80; `low_confidence_wrong` if confidence < 60.

## 3. Evaluation semantics

`EvaluationEngine.evaluate_closed_trade` now adds:

- `outcome` — `win` / `loss` / `neutral`
- `evaluation_type` — primary semantic label
- `failure_type` — nullable; null for successes including `correct_disagreement`
- `secondary_type` — confidence severity
- `is_advisor_failure` — explicit failure flag for learning

Partial agreement remains `advisor_correct=false` but is classified as `partial_on_loss` or `partial_on_win`, not generic incorrect.

## 4. Deduplication algorithm

1. **Fingerprint:** `sha256(failure_type|provider|market|timeframe|strategy)[:20]` → `lfp_*`
2. **Before save:** `LessonRepository.find_by_fingerprint(fp)`
3. **If exists:** `_merge_lesson()` — increment `sample_size`, union `evidence`, `trade_examples`, `affected_symbols`, update `last_seen`
4. **If new:** append to `learning_lessons.jsonl`
5. **list_all():** returns latest record per fingerprint + legacy rows without fingerprint (backward compatible)

## 5. Concurrency handling

`learning_cycle_lock()` uses atomic `O_CREAT|O_EXCL` lock file at `data/.learning_cycle.lock` (Windows + Unix). `LearningEngine.run_cycle(persist=True)` wraps all lesson/proposal/hypothesis/report writes in this lock.

## 6. Sample-size policy (`lesson_thresholds.py`)

| Sample size | Strength | Recommendation (AR) |
|-------------|----------|------------------------|
| ≤ 1 | insufficient | أدلة غير كافية |
| 2 | insufficient | أدلة غير كافية |
| 3–9 | emerging | نمط ناشئ |
| 10–19 | recurring | نمط متكرر |
| ≥ 20 | strong | نمط قوي ومتكرر |

`KnowledgeProposals` skips proposals when `recommendation_strength == insufficient`.

## 7. UI changes

- **Learning tab:** Rich cards with Arabic pattern, description, sample, win rate, avg R, provider, symbols, recommendation badge.
- **Lesson drawer:** `AIExplain.openLessonDrawer()` — summary, pattern, evidence, affected trades table, recommendation.
- **CSS:** `.ai-learning-card*` styles in `platform.css`.

## 8. Before / after examples

**Before (stored):**
```json
{"title": "Recurring AI failure: other failure", "sample_size": 2}
```

**After (same trades):**
```json
{
  "failure_type": "incorrect_disagreement",
  "title_ar": "اعتراض خاطئ",
  "title": "Claude disagreed with trades that subsequently won",
  "description_ar": "اعترض المستشار على الإشارة لكن الصفقة ربحت.",
  "recommendation_ar": "أدلة غير كافية — لا تغيّر الإعدادات بناءً على هذه الحالة وحدها",
  "fingerprint": "lfp_..."
}
```

## 9. Tests

| Suite | Result |
|-------|--------|
| `tests_ai_learning_aia055.py` | 26/26 |
| `tests_ai_learning.py` | 58/58 |
| `tests_ai_advisor_evaluation.py` | 44/44 |

## 10. Modified files

| File | Change |
|------|--------|
| `scanner/ai_learning/failure_classifier.py` | **NEW** — classification logic |
| `scanner/ai_learning/failure_labels.py` | **NEW** — AR/EN labels |
| `scanner/ai_learning/lesson_fingerprint.py` | **NEW** — deterministic fingerprints |
| `scanner/ai_learning/lesson_thresholds.py` | **NEW** — sample thresholds |
| `scanner/ai_learning/learning_lock.py` | **NEW** — file lock |
| `scanner/ai_learning/lesson_generator.py` | Rich lessons, specific types |
| `scanner/ai_learning/lesson_repository.py` | `upsert`, merge, dedup list |
| `scanner/ai_learning/learning_engine.py` | Lock + upsert |
| `scanner/ai_learning/knowledge_proposals.py` | New pattern types, insufficient gate |
| `scanner/ai_learning/reflection_report.py` | `lesson_cards` for UI |
| `scanner/ai_advisor/evaluation/evaluation_engine.py` | Semantic fields |
| `scanner/ai_advisor/production_hooks.py` | Pass `symbol` to evaluation |
| `web/dashboard/static/dashboard/ai-page.js` | Learning cards UI |
| `web/dashboard/static/dashboard/ai-advisor-explain.js` | Lesson drawer |
| `web/dashboard/static/dashboard/platform.css` | Learning card styles |
| `tests_ai_learning_aia055.py` | **NEW** — sprint tests |

## 11. Backward compatibility

- Old lessons without `fingerprint` still load via `list_all()`.
- `failure_type=other_failure` remains valid for unclassified cases.
- New fields are additive; `schema_version` bumped to `1.1.0` for new lessons only.
- Historical JSONL rows are **not** rewritten.

## 12. Remaining limitations

- Existing duplicate lessons in `data/learning_lessons.jsonl` are deduplicated at **read** time only; raw file still contains legacy duplicates until manually compacted.
- Lesson drawer loads from in-memory card data (no separate API endpoint).
- `false_warning` as primary type applies when `false_warning` flag is set without `disagree`; `disagree+win` uses `incorrect_disagreement`.
- Concurrent processes on different machines would need shared lock storage (single-node file lock assumed).
