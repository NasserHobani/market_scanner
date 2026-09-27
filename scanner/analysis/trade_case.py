# -*- coding: utf-8 -*-
"""الحجّة قبل الدخول — ما يدعم الصفقة وما يضعفها، بأرقامك أنت.

═══ لماذا وجهان لا وجه ═══

كل شاشةٍ في هذه المنصّة تعرض **أسباب الدخول**: عوامل موجبة، ونقاطاً
مجتمعة، ودرجةً تصعد. ولا واحدةٌ منها تعرض ما يضعف الصفقة.

وهذا ليس نقصَ ميزة بل انحيازاً مبنيّاً: قائمةُ أسبابٍ من جانبٍ
واحد تُقرأ تأكيداً مهما كان محتواها، فيدخل القارئ وهو يظنّ أنّه
فحص. والفحصُ الحقيقيّ أن يُرى الجانبان معاً ثمّ يُوزَن.

ولهذا **لا تُعاد حجّةٌ من طرفٍ واحد أبداً**: إن لم يوجد ما يضعف
الصفقة قيل ذلك صراحةً ووُسم بأنّه نادر ويستحقّ الشكّ.

═══ ولا يُتنبَّأ بشيء ═══

لا «احتمال نجاح ٧٢٪». النموذج الوحيد الذي حاول ذلك في هذه المنصّة
(LightGBM) لم يتجاوز خطّ الأساس، فأُخفي احتماله. والمعيار نفسه
يُطبَّق هنا: ما يُعرَض **نسبةُ نجاح وسمٍ في سجلّك** بفاصل ثقة
وعدد — لا تنبّؤ بهذه الصفقة.

والفرق ليس لفظياً: «‏٦٨٪ من صفقاتك الموسومة بالاختراق نجحت (ن=٣١،
الفاصل ٥٠–٨٢)» قابلٌ للتحقّق والتكذيب. و«احتمال نجاحها ٦٨٪» ليس
كذلك.

═══ والمادّة ١٧ تُطبَّق هنا أيضاً ═══

‏EMA و ADX و Supertrend تقيس **الاتّجاه**. واجتماعها ثلاثُ نقاطٍ
في عمود «يدعم» ليس ثلاثة شهود بل شاهدٌ واحد بثلاثة أسماء — وهو
بالضبط العطب الذي عولج في وحدة الأدلّة من قبل: ثلاثة «أسباب»
بأرقامٍ متطابقة كانت الصفقات الثمانية عشر نفسها.

فالحجج تُجمَّع بالعائلة، وتُعدّ العائلة مرّة.
"""
from __future__ import annotations

import math
from typing import Any

__all__ = ["build", "FAMILIES", "family_of", "tag_rate"]

#: العائلة لكل عامل — والاسم كما يخرج من محرّك التسجيل
FAMILIES: dict[str, str] = {
    # الاتّجاه: ثلاثة أسماء لشاهدٍ واحد
    "daily_trend": "trend", "h4_trend": "trend", "supertrend": "trend",
    "adx": "trend", "ema": "trend", "trend": "trend",
    # الزخم
    "rsi": "momentum", "momentum_confluence": "momentum",
    "macd": "momentum", "stoch": "momentum", "divergence": "momentum",
    # الحجم والتراكم
    "volume": "volume", "obv": "volume", "rvol": "volume",
    "cmf": "volume", "mfi": "volume", "delta": "volume",
    # البنية والموقع
    "compression": "structure", "resistance": "structure",
    "fib": "structure", "pattern": "structure", "channel": "structure",
}

FAMILY_LABELS = {
    "trend": "الاتّجاه",
    "momentum": "الزخم",
    "volume": "الحجم والتراكم",
    "structure": "البنية والموقع",
    "other": "أخرى",
}

#: أقلّ عدد قبل عرض نسبةٍ بلا وسم «العيّنة قصيرة»
MIN_N = 12
Z95 = 1.959963985


def family_of(key: str) -> str:
    k = str(key or "").strip().lower()
    if k in FAMILIES:
        return FAMILIES[k]
    for name, fam in FAMILIES.items():
        if name in k:
            return fam
    return "other"


def _wilson(k: int, n: int) -> tuple[float, float, float]:
    if n <= 0:
        return (0.0, 0.0, 100.0)
    p = k / n
    d = 1 + Z95 * Z95 / n
    c = (p + Z95 * Z95 / (2 * n)) / d
    h = Z95 * math.sqrt(p * (1 - p) / n + Z95 * Z95 / (4 * n * n)) / d
    return (round(100 * p, 1), round(100 * max(0.0, c - h), 1),
            round(100 * min(1.0, c + h), 1))


def tag_rate(tag: str, settled: list[dict]) -> dict | None:
    """نسبة نجاح صفقاتك التي حملت هذا الوسم.

    ``None`` إن لم يظهر الوسم قطّ — ولا يُخترع رقم.
    """
    from scanner.postmortem.separation import extract_tags

    hits = [t for t in settled
            if tag in extract_tags(t.get("factors") or t.get("reasons"))]
    if not hits:
        return None
    won = sum(1 for t in hits if str(t.get("status")) == "won")
    p, lo, hi = _wilson(won, len(hits))
    return {"tag": tag, "n": len(hits), "won": won,
            "rate": p, "lo": lo, "hi": hi,
            # ═══ العيّنة القصيرة تُوسَم لا تُخفى ═══
            #
            # «٣ من ٤ = ٧٥٪» رقمٌ صحيح ومضلّل. وإخفاؤه يحرم القارئ
            # ممّا يعرفه، وعرضُه بلا وسمٍ يوهمه بدقّةٍ لا توجد.
            "thin": len(hits) < MIN_N}


def _baseline(settled: list[dict]) -> dict:
    won = sum(1 for t in settled if str(t.get("status")) == "won")
    n = len(settled)
    p, lo, hi = _wilson(won, n)
    return {"n": n, "won": won, "rate": p, "lo": lo, "hi": hi}


def build(signal: dict, settled: list[dict] | None = None) -> dict:
    """حجّة الصفقة — بوجهيها.

    ``signal`` صفُّ تحليلٍ أو توصية: فيه ``factors`` و``score``
    و``rr`` و``state`` وما إليها.
    """
    settled = [t for t in (settled or [])
               if str(t.get("status")) in ("won", "lost")]
    base = _baseline(settled)

    pro: list[dict] = []
    con: list[dict] = []
    seen_fam: set[str] = set()

    # ── ١) العوامل: الموجب يدعم، والصفر يُضعف ──
    for f in (signal.get("factors") or []):
        key = str(f.get("key") or "")
        pts = f.get("points")
        mx = f.get("max") or 0
        try:
            pts = float(pts)
            mx = float(mx)
        except (TypeError, ValueError):
            continue
        if mx <= 0:
            continue
        share = pts / mx * 100.0
        fam = family_of(key)
        label = str(f.get("label") or key)

        if share >= 60:
            # ═══ عائلةٌ واحدة مرّةً واحدة ═══
            if fam in seen_fam:
                continue
            seen_fam.add(fam)
            pro.append({
                "family": fam, "family_label": FAMILY_LABELS.get(fam, fam),
                "key": key, "label": label, "share": round(share, 0),
                "text": f"{label}: {share:.0f}٪ من سقفه",
            })
        elif share <= 20:
            # والضعيف يُقال — وهو ما كانت الشاشات تُسقطه
            con.append({
                "family": fam, "family_label": FAMILY_LABELS.get(fam, fam),
                "key": key, "label": label, "share": round(share, 0),
                "text": f"{label}: {share:.0f}٪ فقط من سقفه",
            })

    # ── ٢) ما يضعف بنيوياً ──
    score = signal.get("score")
    rr = signal.get("rr")
    fam_count = signal.get("family_count")

    if isinstance(fam_count, (int, float)) and fam_count < 3:
        con.append({"family": "structure", "family_label": "التقاء",
                    "text": f"عائلتان مساهِمتان فقط ({fam_count:.0f}) — "
                            "والقاعدة ١٧ تشترط ثلاثاً. "
                            "واجتماع مؤشّراتٍ تقيس الشيء نفسه ليس تأكيداً."})
    if isinstance(rr, (int, float)) and 0 < rr < 1.5:
        con.append({"family": "risk", "family_label": "المخاطرة",
                    "text": f"العائد/المخاطرة {rr:.2f} — تحتاج نسبة نجاحٍ "
                            f"فوق {100 / (1 + rr):.0f}٪ لمجرّد التعادل، "
                            "قبل الكلفة."})
    if signal.get("already_expanded"):
        con.append({"family": "structure", "family_label": "الموقع",
                    "text": "ارتفع بالفعل — الحركة التي نبحث عن بدايتها "
                            "جرت. والدخول هنا مطاردة."})
    st = (signal.get("supertrend") or {}).get("direction")
    if st is not None and st < 0:
        con.append({"family": "trend", "family_label": "الاتّجاه",
                    "text": "‏Supertrend هابط على فريم المسح."})

    # ── ٣) سجلّك: نسبة كل وسم ──
    from scanner.postmortem.separation import extract_tags

    rates = []
    for tag in extract_tags(signal.get("reasons")
                            or signal.get("factors")):
        r = tag_rate(tag, settled)
        if r:
            rates.append(r)
    rates.sort(key=lambda x: x["rate"])

    # ═══ والوسم الذي يخسر في سجلّك حجّةٌ ضدّه ═══
    for r in rates:
        if r["thin"] or base["n"] < MIN_N:
            continue
        if r["hi"] < base["rate"]:
            con.append({
                "family": "record", "family_label": "سجلّك",
                "text": f"«{r['tag']}» نسبته {r['rate']:.0f}٪ عندك "
                        f"(ن={r['n']}، {r['lo']:.0f}–{r['hi']:.0f}) — "
                        f"دون معدّلك العام {base['rate']:.0f}٪."})
        elif r["lo"] > base["rate"]:
            pro.append({
                "family": "record", "family_label": "سجلّك",
                "text": f"«{r['tag']}» نسبته {r['rate']:.0f}٪ عندك "
                        f"(ن={r['n']}، {r['lo']:.0f}–{r['hi']:.0f}) — "
                        f"فوق معدّلك العام {base['rate']:.0f}٪."})

    # ═══ ولا حجّةٌ من طرفٍ واحد ═══
    #
    # قائمةٌ خالية من الجانب المضادّ تُقرأ «لا شيء يعترض» — وهي
    # في الغالب «لم أفحص». فالفرق يُقال.
    if not con:
        con.append({"family": "", "family_label": "",
                    "text": "لم أجد ما يضعفها في المقاييس المحسوبة. "
                            "وهذا نادر — وغيابُ الاعتراض ليس اعتراضاً "
                            "مفحوصاً: راجع ما لا يقيسه النظام "
                            "(خبرٌ، حدثٌ كلّي، سيولة الرمز)."})
    if not pro:
        pro.append({"family": "", "family_label": "",
                    "text": "لا عامل بلغ ٦٠٪ من سقفه. الدخول هنا بلا "
                            "سندٍ من المقاييس."})

    return {
        "pro": pro, "con": con,
        "families_supporting": sorted(seen_fam),
        "baseline": base,
        "tag_rates": rates,
        # ═══ ولا حكم واحد ═══
        #
        # «ادخل» أو «لا تدخل» يُلغي الغرض: الحجّتان معروضتان كي
        # يوزن القارئ، لا كي يُختصرا في كلمة.
        "verdict": None,
        "note": ("نسبٌ من سجلّك لا تنبّؤ بهذه الصفقة. "
                 f"وسجلّك {base['n']} صفقة محسومة، معدّلها "
                 f"{base['rate']:.0f}٪."),
    }
