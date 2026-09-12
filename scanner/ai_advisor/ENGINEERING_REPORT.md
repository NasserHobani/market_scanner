# Sprint AIA-01 — AI Advisor Framework

## Engineering Report for Principal Software Architects

---

## 1. Executive Summary

Sprint AIA-01 introduces the **AI Advisor Framework** — a new `scanner/ai_advisor/` package that integrates Large Language Models into CS Edge as a **read-only reviewer** operating in **Shadow Mode**.

The platform remains deterministic. The LLM reviews. The platform decides.

No existing production module was modified. Knowledge, Research, Prediction, Optimization, Decision AI, the Trading Engine, and the Risk Engine are untouched. Integration happens exclusively through read-only consumption of their deterministic layer outputs, assembled into a strongly typed **Decision Package** that is the sole input an LLM may receive.

The framework ships with:

- 17 source files across 8 subsystems (package, prompts, providers, validation, memory, scoring)
- 6 stub LLM providers (Claude, OpenAI, Gemini, DeepSeek, OpenRouter, Open Source) with no API keys
- 3 immutable prompt template versions
- Grounding validation that rejects hallucinated evidence references
- Persistent advisor memory (append-only JSONL)
- Advisor Score quality metrics
- Multi-model dispatch architecture (no voting yet)
- UI presentation models exposed via `/api/widgets/ai-advisor/`
- 47 unit tests, all passing

Real LLM API integration is deferred to Sprint AIA-02.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Platform Layers (READ-ONLY)               │
│  Knowledge │ Research │ Similarity │ Prediction │ Decision AI│
└──────────────────────────┬──────────────────────────────────┘
                           │ deterministic dict outputs
                           ▼
              ┌────────────────────────┐
              │ DecisionPackageBuilder │
              │  (sanitizes, indexes)  │
              └───────────┬────────────┘
                          ▼
              ┌────────────────────────┐
              │   DecisionPackage      │  ← ONLY input to LLM
              │   (frozen, typed)      │
              └───────────┬────────────┘
                          ▼
              ┌────────────────────────┐
              │   PromptBuilder      │
              │   (v1, v2, v3)       │
              └───────────┬────────────┘
                          ▼
              ┌────────────────────────┐
              │  ProviderRegistry      │
              │  → LLMProvider.analyze │
              └───────────┬────────────┘
                          ▼
              ┌────────────────────────┐
              │  ResponseParser        │
              │  ResponseValidator     │  ← grounding check
              └───────────┬────────────┘
                          ▼
              ┌────────────────────────┐
              │  ReviewEngine          │
              │  → AdvisorReview       │
              └───────────┬────────────┘
                          ▼
         ┌────────────────┼────────────────┐
         ▼                ▼                ▼
   AdvisorMemory    AdvisorHistory   AdvisorScore
```

**Service facade:** `AIAdvisorService` — single public entry point.

**Shadow Mode invariant:** enforced at three levels:
1. Decision Package sets `shadow_mode: true` and `advisor_may_override: false`
2. Prompt templates include explicit rules forbidding decision overrides
3. Response validator rejects any field matching override patterns

---

## 3. Decision Package Design

`DecisionPackage` is a frozen `@dataclass` containing 14 sections:

| Section | Source Layer | Contains |
|---------|-------------|----------|
| `trade` | Knowledge + Reasoning | symbol, action, direction, grade |
| `market_context` | Knowledge | trend, regime, breadth (summaries only) |
| `knowledge_summary` | Knowledge | grade, score, memory gaps |
| `research_summary` | Research | hypothesis, p-value, effect size |
| `similarity_summary` | Similarity | match count, win rate, average R |
| `prediction_summary` | Prediction | probability, confidence, model ID |
| `feature_intelligence` | Feature Intelligence | drift, top features, quality |
| `optimization_summary` | Optimization | best expectancy, walk-forward |
| `statistics` | Strategy stats | win rate, expectancy, profit factor |
| `risk` | Guardrails + Reasoning | violations, contradictions, warnings |
| `confidence` | Fusion + Reasoning + Prediction | fused score, components |
| `decision` | Reasoning | verdict, action, `platform_authority: true` |
| `execution_metadata` | Built | shadow mode flag, advisor role |
| `evidence_index` | All sections | groundable `EvidenceRef` tuples |

**Forbidden content:** OHLC, candles, DataFrames, CSV, raw indicators. The builder recursively strips keys matching a forbidden set.

**Evidence Index:** Every scalar value and reasoning evidence item is indexed with `{evidence_id, section, field, label, value}`. This index is the grounding authority for response validation.

**Determinism:** Package ID is a SHA-256 hash of the section contents. Same inputs always produce the same package.

---

## 4. Prompt Architecture

Three immutable, versioned templates:

| Version | Focus | Created |
|---------|-------|---------|
| `advisor_prompt_v1` | Agreement and evidence grounding | 2026-08-09 |
| `advisor_prompt_v2` | Risk scrutiny with self-confidence rating | 2026-08-09 |
| `advisor_prompt_v3` | Multi-layer coherence and experiment proposal | 2026-08-09 |

Each template is a frozen `PromptTemplate` with:
- `version`, `created_at`, `description`
- `rules` (tuple of immutable strings)
- `system_prompt` (role definition)
- `instructions` (task-specific guidance)

Templates are stored in a read-only `TEMPLATES` dict. They cannot be modified at runtime.

The rendered `AdvisorPrompt` includes:
- System prompt (advisor role, shadow mode rules)
- User prompt (Decision Package JSON + evidence index + required response schema)
- Metadata (evidence count, build timestamp)

---

## 5. Provider Abstraction

```python
class LLMProvider(ABC):
    def analyze(prompt, *, package) -> dict: ...
    def health() -> dict: ...
    def model_name() -> str: ...
```

**Registry pattern:** `ProviderRegistry` with runtime `register()` / `get()` / `list_all()`. No hardcoded singletons. Default stubs are registered on first `get_registry()` call.

| Provider ID | Vendor | Status |
|-------------|--------|--------|
| `claude` | Anthropic | Stub |
| `openai` | OpenAI | Stub |
| `gemini` | Google | Stub |
| `deepseek` | DeepSeek | Stub |
| `openrouter` | OpenRouter | Stub |
| `opensource` | Community | Stub |
| `mock` | Test | Mock (configurable response) |

No API keys. No network calls. Stubs return deterministic responses grounded in the package.

---

## 6. Grounding Strategy

Every AI statement must reference the Decision Package. Grounding is enforced at three points:

**1. Prompt level:** The evidence index is included in the user prompt. The LLM is instructed to reference only `evidence_id` values from this index.

**2. Validation level:** `ResponseValidator` checks every `supporting_evidence` and `contradicting_evidence` citation:
- `evidence_id` must exist in `package.evidence_ids()`
- `section` must exist in `package.allowed_sections()`
- Unknown references are recorded as hallucinations and cause rejection

**3. Override prevention:** The validator scans for forbidden fields (`action_override`, `direction_override`, `stop`, `target`) and override language patterns in the response text.

**Rejection policy:** Any response with hallucinations, missing required fields, or override attempts is rejected. Rejected reviews are saved to memory with `rejected: true` and the rejection reason.

---

## 7. Response Validation

Validation pipeline:

```
Raw LLM output
    → ResponseParser (extract JSON, handle fences)
    → ResponseValidator
        ├── Required fields check (10 fields)
        ├── Agreement value check (agree/disagree/partial)
        ├── Confidence range check (0-100)
        ├── Shadow mode acknowledgment check
        ├── Override field scan
        ├── Evidence grounding check
        └── Citation cross-reference
    → ValidationResult {valid, rejected, errors, hallucinations}
```

Required JSON schema:

```json
{
  "agreement": "agree|disagree|partial",
  "confidence": 0-100,
  "summary": "string",
  "reasoning": "string",
  "supporting_evidence": [{"evidence_id", "section", "field", "note"}],
  "contradicting_evidence": [{"evidence_id", "section", "field", "note"}],
  "risks": ["string"],
  "missing_information": ["string"],
  "suggested_experiment": {"hypothesis", "method", "expected_outcome"},
  "shadow_mode_acknowledged": true
}
```

---

## 8. Advisor Memory

Persistent, platform-owned memory stored as append-only JSONL at `data/advisor_memory.jsonl`.

Each record captures:

| Field | Purpose |
|-------|---------|
| `record_id` | Unique review identifier |
| `package_id` | Links to Decision Package |
| `event_id` | Trade/event reference |
| `prompt_version` | Which prompt template was used |
| `provider_id` | Which LLM provider |
| `model_name` | Specific model version |
| `response` | Full advisor review dict |
| `accepted` / `rejected` | Validation outcome |
| `rejection_reason` | Why rejected (if applicable) |
| `execution_result` | Trade outcome (populated later) |
| `later_performance` | Post-hoc accuracy assessment |

Memory supports `update_performance()` for retroactive advisor quality measurement.

---

## 9. Advisor Score

Composite quality metric (0-100) computed from:

| Component | Weight | Source |
|-----------|--------|--------|
| Acceptance rate | 30% | accepted / total reviews |
| Helpfulness | 30% | helpful / (helpful + misleading) |
| Engine alignment | 20% | agree / (agree + disagree) |
| Hallucination penalty | 20% | -5 per hallucination, capped at -50 |

Grade mapping: A (≥80), B (≥65), C (≥50), D (≥35), F (<35).

Tracked metrics: total reviews, accepted, rejected, helpful, misleading, hallucination count, agreement with decision engine, agreement with reality.

---

## 10. Security Considerations

1. **No raw market data to LLM.** The Decision Package builder strips forbidden keys. Even if a caller passes OHLC data, it is removed before packaging.

2. **No API keys in codebase.** All providers are stubs. API key management is deferred to AIA-02 with environment-variable injection.

3. **No decision override.** Three-layer enforcement (package, prompt, validator) prevents the LLM from changing platform decisions.

4. **Hallucination rejection.** Unsupported claims are detected and rejected, not displayed to users.

5. **Memory is platform-owned.** Advisor memory is not user-editable. Records are append-only with no delete operation.

6. **Shadow mode is mandatory.** Cannot be disabled without modifying the validator, which requires code change and review.

7. **Provider isolation.** Each provider runs in isolation. A compromised provider response is caught by the validator before reaching the UI.

---

## 11. Future Multi-Model Consensus

The architecture supports sending one Decision Package to multiple providers via `AIAdvisorService.review_multi()`:

```python
reviews = svc.review_multi(package, provider_ids=["claude", "openai", "gemini"])
```

This returns a list of independent `AdvisorReview` objects. Sprint AIA-02 can add:

- **Consensus engine:** majority vote on agreement
- **Confidence weighting:** weight by provider advisor score
- **Disagreement alerts:** flag when providers diverge significantly
- **Provider ranking:** prefer providers with higher reality agreement

The registry, memory, and scoring infrastructure already tracks per-provider metrics to support this.

---

## 12. Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| LLM hallucination despite grounding | High | Validator rejects ungrounded claims; memory tracks hallucination count |
| Prompt injection via layer outputs | Medium | Package builder sanitizes inputs; no free-text fields from external sources |
| Provider API cost at scale | Medium | Shadow mode limits invocations; caching via widget layer |
| Memory file growth | Low | JSONL is append-only; rotation policy needed at scale |
| Stub providers mask integration issues | Medium | AIA-02 must include integration tests with real providers |
| Evidence index incompleteness | Medium | Index covers all scalar fields + reasoning evidence; complex nested claims may lack refs |
| Single-point validator failure | Low | Rejected reviews are logged; platform decisions unaffected |

---

## 13. Suggested Sprint AIA-02

1. **Live provider integration** — Implement real API calls for Claude and OpenAI with environment-variable API keys, retry logic, and timeout handling.

2. **Orchestration stage** — Add optional `ai_advisor` stage to the orchestration workflow after `decision_ai`, using the existing stage handler pattern.

3. **UI integration** — Add "Advisor Review" section to the AI page and trade drawer AI tab, consuming `/api/widgets/ai-advisor/` and per-trade review endpoints.

4. **Multi-model consensus** — Implement `ConsensusEngine` that aggregates reviews from multiple providers with weighted voting.

5. **Performance feedback loop** — After trade settlement, call `memory.update_performance()` to close the advisor quality measurement loop.

6. **Prompt A/B testing** — Use memory records to compare prompt version effectiveness.

7. **Rate limiting and cost controls** — Per-provider invocation limits, daily budget caps, and caching of identical package reviews.

---

## Files Delivered

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 55 | Public exports |
| `interfaces.py` | 35 | Protocol definitions |
| `decision_package.py` | 280 | Package builder + types |
| `prompt_builder.py` | 175 | Versioned prompt templates |
| `providers/base.py` | 75 | Provider ABC |
| `providers/__init__.py` | 95 | Stub provider implementations |
| `provider_registry.py` | 65 | Runtime provider registry |
| `review.py` | 155 | Review engine + types |
| `response_parser.py` | 40 | JSON extraction |
| `response_validator.py` | 120 | Grounding validation |
| `advisor_engine.py` | 115 | Core orchestrator |
| `advisor_service.py` | 105 | Public service facade |
| `memory.py` | 95 | Persistent JSONL memory |
| `history.py` | 40 | History queries |
| `advisor_score.py` | 100 | Quality scoring |
| `README.md` | 85 | Module documentation |
| `tests_ai_advisor.py` | 280 | 47 unit tests |

**Integration (no engine modifications):**

| File | Change |
|------|--------|
| `web/dashboard/widgets.py` | Added `build_ai_advisor_summary()` |
| `web/dashboard/widget_views.py` | Added `api_widget_ai_advisor` |
| `web/dashboard/urls.py` | Added `/api/widgets/ai-advisor/` route |

**Test results:** 47/47 passed. Widget tests green. Django check clean.
