# AIA-06.1 — Arabic AI Analysis & Explainable Review

## 1. Current problem

Before AIA-06.1, the AI Advisor drawer and symbol manual analysis surfaced Claude’s **raw English summary** as the primary user-facing content. Arabic-speaking users saw unstructured English prose such as:

> The platform's 'none' action decision is well-supported by pervasive data gaps…

This violated explainability goals: no clear agreement label, no structured risks/signals, no Arabic-first UX, and technical reasoning mixed with executive summary.

## 2. Architecture

Pipeline unchanged:

```
UnifiedDecisionPackage → Claude → ResponseParser → ResponseValidator → Accepted Review
                                                                          ↓
                                                              Localized Presentation (ar/en)
```

- **No second Claude call** for translation.
- `build_presentation(review, lang)` and `build_presentations(review)` derive UI payloads from the canonical review dict at read time.
- Client stores both `ar` and `en` in `review.presentations` and switches via `localStorage.ai_ui_lang` without re-fetching.

## 3. Localization strategy

| Layer | Language |
|-------|----------|
| Internal reasoning / technical evidence | English allowed |
| Executive summary, signals, risks, verdict | Arabic (default) or English |
| Identifiers (`review_id`, `evidence_id`, provider, model, symbol, timeframe, tokens, cost) | Never translated |

Rule-based `localize_phrase()` maps common advisor phrases to natural Arabic (not literal MT). English mode keeps original summary text where available.

## 4. Arabic terminology

| Internal | Arabic UI |
|----------|-----------|
| agree | متفق مع النظام |
| disagree | مختلف مع النظام |
| partial | متفق جزئيًا |
| none | انتظار / عدم تداول |
| buy | شراء |
| sell | بيع |
| watch | مراقبة |
| actionable edge | أفضلية تداول واضحة |
| data gaps | البيانات غير مكتملة |

Technical terms (RSI, Prediction, Optimization, BOS, R:R) may remain in English.

## 5. UI changes

- **Language selector** in review drawer: `العربية | English`
- **Structured presentation**: agreement badge, confidence, executive summary, positive/negative signals, missing info, risks, what could change, final verdict
- **Collapsible technical evidence** (`الأدلة التقنية`): original reasoning, evidence IDs, diagnostics
- **Live review card**: localized summary instead of raw English
- **Review history**: Symbol, Timeframe, Verdict, Agreement, Confidence, Provider, Time, Language
- **Symbol page**: `آخر تحليل بواسطة Claude` strip after manual analysis with “عرض التحليل الكامل”

## 6. Evidence preservation

- `evidence_id` values pass through unchanged (`ev_013` stays `ev_013`).
- Signal items retain `href` for deep-links.
- Presentation never invents new evidence IDs.

## 7. Cache behavior

- 10-minute manual analysis cache unchanged.
- Cached payloads enriched on read via `_ensure_presentations()` if older entries lack `presentations`.
- Language toggle re-renders from in-memory `presentations` — **no additional API request**.

## 8. Backward compatibility

- Old reviews without `presentations` get them built dynamically in `get_review()` and manual cache enrichment.
- Canonical review JSON contract unchanged.
- Export (JSON/Markdown/PDF) still uses canonical review object.

## 9. Tests

`tests_ai_explainability_arabic.py` covers:

1. Arabic rendering  
2. English rendering  
3. Agreement labels  
4. Recommendation labels  
5. Confidence preservation  
6. Evidence ID preservation  
7. No hallucinated evidence  
8. Empty section removal  
9. Technical evidence visibility  
10. Manual analysis  
11. Language switching  
12. No duplicate Claude API contract mutation  
13. Cache compatibility  
14. Old review compatibility  
15. RTL layout fields  
16. Long Arabic text  
17. Mixed Arabic/English technical terms  
18. Disagreement rendering  
19. Partial agreement rendering  
20. Missing data rendering  

## 10. Before / after example

**Before (primary view):**

```
ثقة Claude 82%
[English wall of text about pervasive data gaps...]
```

**After (Arabic default):**

```
🧠 تحليل Claude
VETUSDT · 15m
🟢 متفق مع النظام
درجة ثقة Claude: 82%

الخلاصة
قرار النظام بعدم التداول مدعوم بالأدلة الحالية...

الأسباب الرئيسية
✓ البيانات غير مكتملة (ev_013)
✓ معدل نجاح الحالات التاريخية المشابهة 0% (ev_018)

المخاطر
الدخول اعتمادًا على الاتجاه وحده...

القرار النهائي
⏸️ انتظار / عدم تداول

[الأدلة التقنية ▼]
```

## 11. Remaining limitations

- Arabic executive summaries for complex reviews are **rule-assisted**, not full neural translation — quality depends on available structured fields (`risks`, `missing_information`, evidence notes).
- History table language column reflects UI default (`ar`), not per-review stored preference.
- Cached manual analysis files on disk are not rewritten; presentations are computed on read.

---

## Deliverables

### Files created
- `scanner/ai_advisor/explainability/localized_presentation.py`
- `scanner/ai_advisor/explainability/AIA-06.1_ARABIC_EXPLAINABILITY_REPORT.md`
- `tests_ai_explainability_arabic.py`

### Files modified
- `scanner/ai_advisor/explainability/review_timeline_service.py`
- `scanner/ai_advisor/explainability/manual_analysis_service.py`
- `scanner/ai_advisor/explainability/__init__.py`
- `web/dashboard/static/dashboard/ai-advisor-explain.js`
- `web/dashboard/static/dashboard/design-system.css`
- `web/dashboard/templates/dashboard/symbol.html`

### Tests passed
Run:
```bash
python tests_ai_explainability_arabic.py
python tests_ai_explainability.py
```

### Remaining limitations
See section 11 above.
