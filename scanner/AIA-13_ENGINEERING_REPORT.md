# AIA-13 Engineering Report — Arabic AI Market Analyst

## Objective

Transform the AI Advisor into a professional Arabic-speaking market analyst (advisory-only).

## Delivered

| Area | Change |
|------|--------|
| Persona | `scanner/ai_advisor/analyst/persona.py` — CS Edge Senior Market Analyst |
| Prompt | `advisor_prompt_v4` (default) — Arabic professional output |
| Context budgets | FAST 1500 / STANDARD 2500 / DEEP 4000 |
| Schema adapter | `normalize_analyst_response` — keeps REQUIRED_FIELDS compatible |
| Outlook eval | `outlook_eval.py` — separate from recommendation correctness |
| Presentation | Extended AR/EN without re-calling LLM |
| Manual analysis | STANDARD profile + Arabic display fields |
| Automatic reviews | FAST profile |
| Dashboard | «محلل الأسواق بالذكاء» card |
| Symbol strip | قرار / نظرة / اتجاه / ثقة المستشار |
| Tests | `tests_ai_aia13.py` |
| Verify | `scripts/verify_aia13_analyst.py` (real Qwen) |

## Safety preserved

- No trade execution
- No strategy / stop / target changes
- No LightGBM promotion
- No quality-gate bypass
- Prediction ACTIVE-only; unavailable → explicit Arabic disclosure
- Validator contract intact (optional analyst fields only)

## Confidences kept separate

1. ثقة المنصة (`platform_confidence`)
2. الاحتمال الإحصائي (`prediction_probability`) when ACTIVE
3. ثقة المستشار (`llm_confidence`)

## Tests

- `tests_ai_aia13.py` — pass
- Existing AI suites — green (prompt version count updated to `>= 3`)

## Principle

CS Edge computes the facts. The AI Analyst interprets them in Arabic — with uncertainty, risks, invalidation, and no invented data.
