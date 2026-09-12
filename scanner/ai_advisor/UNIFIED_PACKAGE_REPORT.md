# AIA-04 Unified Decision Package — Engineering Report

## 1. Executive Summary

Sprint AIA-04 replaces the minimal scan-row context with a **Unified Decision Package** that aggregates outputs from all platform layers (Knowledge, Reasoning, Similarity, Research, Feature Intelligence, Prediction, Optimization, Decision AI) before Claude review. The package is immutable, evidence-traceable, deterministically compressed, token-optimized, and validated before API invocation. Claude remains in Shadow Mode — reviewer only.

## 2. New Files

| File | Purpose |
|------|---------|
| `scanner/ai_advisor/unified_package.py` | `UnifiedDecisionPackage`, `EvidenceTrace`, `UnifiedPackageBuilder` |
| `scanner/ai_advisor/layer_adapters.py` | Map engine outputs → unified sections |
| `scanner/ai_advisor/layer_collectors.py` | Collect from existing services (no engine changes) |
| `scanner/ai_advisor/package_compression.py` | Deterministic compression |
| `scanner/ai_advisor/token_optimizer.py` | Priority-based token pruning |
| `scanner/ai_advisor/package_validator.py` | Pre-Claude package validation |
| `scanner/ai_advisor/package_cache.py` | Fingerprint cache for unchanged recommendations |
| `scanner/ai_advisor/unified_pipeline.py` | Build → compress → optimize → validate orchestration |
| `tests_ai_unified_package.py` | 28 unit tests |

## 3. Modified Files

| File | Change |
|------|--------|
| `scanner/ai_advisor/advisor_engine.py` | Builds unified package via pipeline; legacy builder preserved |
| `scanner/ai_advisor/advisor_service.py` | `build_package()` returns `UnifiedDecisionPackage`; diagnostics in UI |
| `scanner/ai_advisor/prompt_builder.py` | Serializes `UnifiedDecisionPackage` |
| `scanner/ai_advisor/runtime.py` | Uses `collect_platform_layers()` for full context |
| `scanner/ai_advisor/response_validator.py` | Accepts unified package (duck-typed) |
| `scanner/ai_advisor/review.py` | Type union for package |
| `scanner/ai_advisor/__init__.py` | Exports unified types |
| `web/dashboard/static/dashboard/dashboard-page.js` | Package diagnostics section |

## 4. UnifiedDecisionPackage Architecture

```
Platform Layers (read-only service calls)
        │
        ▼
layer_collectors.collect_platform_layers()
        │
        ▼
UnifiedPackageBuilder.build()
        │
        ▼
package_compression.compress()
        │
        ▼
token_optimizer.optimize()
        │
        ▼
package_validator.validate()
        │
        ▼
UnifiedDecisionPackage (immutable)
        │
        ▼
PromptBuilder → Claude → ResponseValidator
```

`UnifiedDecisionPackage` sections: `recommendation`, `knowledge`, `reasoning`, `similarity`, `research`, `feature_intelligence`, `prediction`, `optimization`, `decision_ai`, `evidence_index`, `metadata`, `diagnostics`.

## 5. Section Definitions

| Section | Contents |
|---------|----------|
| **Recommendation** | action, direction, confidence, grade, entry, stop, r_target, expectancy, risk |
| **Knowledge** | market_regime, market_structure, knowledge_facts, patterns, trend_summary |
| **Reasoning** | reasoning_chain, evidence, confidence, contradictions, warnings |
| **Similarity** | historical_matches, win_rate, average_r, similar_cases, confidence |
| **Research** | experiment_summary, research_confidence, comparison_results, hypothesis_evidence |
| **Feature Intelligence** | top_features, quality, drift, redundancy, stability |
| **Prediction** | model_output, probability, calibration, uncertainty |
| **Optimization** | optimized_parameters, confidence, walk-forward, baseline comparison |
| **Decision AI** | fused_confidence, guardrails, warnings, contradictions |

## 6. Package Generation Flow

1. Scan triggers `review_scan_candidates()` with ready recommendations.
2. `collect_platform_layers()` calls `KnowledgeService`, `ReasoningService`, `SimilarityService`, Research, Feature Intelligence, Prediction, Optimization, `DecisionAIService`.
3. `build_unified_package()` assembles, compresses, optimizes, validates.
4. Cache hit skips rebuild when recommendation fingerprint unchanged.
5. `AIAdvisorService.review_trade()` sends validated package to Claude.

## 7. Compression Strategy

Deterministic only — no AI summarization:

- Remove empty/unavailable sections
- Deduplicate evidence by `section.field=value`
- Merge repeated knowledge facts
- Truncate oversized statistics dicts (>500 bytes)

## 8. Token Optimization Strategy

Priority order (never remove Critical):

| Priority | Sections |
|----------|----------|
| Critical (0) | recommendation, reasoning, decision_ai, evidence_index |
| High (1) | metadata, knowledge |
| Medium (2) | similarity, prediction |
| Low (3) | research, feature_intelligence, optimization |

Default budget: 12,000 tokens (~4 chars/token estimate). Low-priority sections marked `pruned: true` when exceeded.

## 9. Evidence Traceability Model

Each `EvidenceTrace` includes:

- `evidence_id` — grounding reference for Claude
- `source_layer` — originating platform layer
- `section` / `field` — package location
- `timestamp` — collection time
- `confidence` — layer confidence when available
- `reference` — trace path (e.g. `knowledge.market_regime`)

Claude responses must cite `evidence_id` + `section` or validation fails.

## 10. Grounding Validation Flow

1. `PackageValidator` — pre-Claude: completeness, evidence, size, version
2. `ResponseValidator` — post-Claude: evidence_ids in package, section references valid
3. Grounding score: `100 - failures×25 - hallucinations×50`

## 11. Dashboard Integration

Widget `w-ai` diagnostics section displays:

- Package Version
- Package Size (bytes)
- Token Estimate
- Compression Ratio
- Evidence Count
- Sections Included / Removed count

Via `package_diagnostics` in `AIAdvisorService.to_ui_summary()`.

## 12. Performance Measurements

| Metric | Before (minimal) | After (unified) |
|--------|------------------|-----------------|
| Layer collection | ~0 ms (inline dict) | ~50–500 ms (service calls) |
| Package build | <1 ms | ~1–2 ms |
| Cached rebuild | N/A | <1 ms (cache hit) |
| Evidence items | 3–8 | 15–40+ |
| Package size | ~1–2 KB | ~4–15 KB (compressed) |

Uncached pipeline measured at **~1.1 ms** build time in tests (excluding service I/O).

## 13. Test Results

| Suite | Result |
|-------|--------|
| `tests_ai_unified_package.py` | 28/28 |
| `tests_ai_advisor.py` | 47/47 |
| `tests_ai_advisor_runtime.py` | 22/22 |
| `tests_ai_claude_provider.py` | 35/35 |
| `tests_ai_advisor_evaluation.py` | 44/44 |
| `tests_ai_learning.py` | 58/58 |

**Total: 234/234 passed**

## 14. Known Technical Debt (document only)

1. Layer collectors use best-effort service calls with fallbacks — not full orchestration pipeline context.
2. Research/optimization collectors may return sparse data when no experiment history exists.
3. Token budget and cost rates remain hardcoded — should be settings-driven.
4. Cache is file-based with 1-hour TTL — no distributed invalidation.
5. `DecisionPackage` retained for legacy tests; production path uses unified package only.
6. No per-layer timeout isolation — slow service delays package build.
