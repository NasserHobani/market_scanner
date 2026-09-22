# -*- coding: utf-8 -*-
"""استراتيجياتٌ يبنيها المستخدم — شروطٌ على ما حُسب، لا حسابٌ جديد.

═══ الفكرة ═══

المسح يحسب لكل رمز عشرات القيم ويحفظها. والاستراتيجية هنا ليست
حساباً جديداً بل **مرشِّحاً** على تلك القيم:

    درجة PES ≥ 60  ·  التقاء الزخم ≥ 7  ·  Supertrend صاعد

فالفرز ثوانٍ لا دقائق، ونتيجتُه متّسقة مع بقيّة الشاشات: الرقم
الذي يفرز هو الرقم المعروض في صفحة الرمز، لا حسابٌ ثانٍ قد
يختلف عنه بسطرٍ واحد.

═══ ولماذا سجلٌّ للحقول ═══

``FIELDS`` يذكر لكل حقل: من أين يُقرأ، ونوعه، واسمه العربي،
ومداه. فالواجهة تُبنى منه — لا تُكتب باليد. وإضافةُ حقلٍ جديد
سطرٌ واحد هنا، ويظهر في القائمة وفي الفرز معاً.

والنسخة اليدوية كانت ستحتاج تعديلين في مكانين، ويُنسى أحدهما —
فيُعرَض حقلٌ لا يُفرَز به، أو يُفرَز بحقلٍ لا يُعرَض.

═══ والغائب لا يُطابِق ═══

رمزٌ بلا قيمةٍ لهذا الحقل لا يجتاز الشرط. والبديل — عدُّه ناجحاً
— يُدخل في النتيجة رموزاً لم تُفحَص أصلاً، وهو أسوأ أنواع
الخطأ: قائمةٌ تبدو أطول فتبدو الاستراتيجية أنجح.

═══ وكل الشروط تجتمع ═══

لا «أو» ولا مجموعات. شرطٌ واحد لا يتحقّق يُسقط الرمز. والعدد
المتحقّق يُحفظ للعرض — كي ترى من اقترب — لكنّه **لا يجعله
مطابقاً**.
"""
from __future__ import annotations

from typing import Any, Callable

# ═══════════════════════════════════════════════════════════════
#  العمليات
# ═══════════════════════════════════════════════════════════════
#
# ``between`` يأخذ قيمتين، والباقي واحدة. و``in`` للقوائم النصّية
# مثل المرحلة.

OPS: dict[str, dict] = {
    ">=": {"label": "أكبر من أو يساوي", "arity": 1, "kinds": ("number",)},
    "<=": {"label": "أصغر من أو يساوي", "arity": 1, "kinds": ("number",)},
    ">": {"label": "أكبر من", "arity": 1, "kinds": ("number",)},
    "<": {"label": "أصغر من", "arity": 1, "kinds": ("number",)},
    "==": {"label": "يساوي", "arity": 1, "kinds": ("number", "enum", "bool")},
    "!=": {"label": "لا يساوي", "arity": 1, "kinds": ("number", "enum", "bool")},
    "between": {"label": "بين", "arity": 2, "kinds": ("number",)},
    "in": {"label": "واحدٌ من", "arity": "list", "kinds": ("enum",)},
}


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None          # ‏NaN لا تُطابق شيئاً


def _st_dir(row: dict) -> str | None:
    """اتّجاه Supertrend نصّاً — أو ``None`` إن لم يُحسب.

    والتمييز بين «هابط» و«غير محسوب» لازم: صفرٌ يعني أنّ المؤشّر
    لم يستقرّ بعد (شموع غير كافية)، وعدُّه هبوطاً يُسقط رمزاً لم
    يُفحَص أصلاً.
    """
    d = _num((row.get("supertrend") or {}).get("direction"))
    if d is None or d == 0:
        return None
    return "up" if d > 0 else "down"


def _macd(row: dict) -> dict | None:
    """كتلة MACD المحفوظة — أو ``None`` إن لم تُحسب.

    والتمييز لازم: ``bool(missing)`` يساوي «لا»، فشرطُ «التقاطع
    = لا» كان سيطابق كل رمزٍ لم يُحسب له MACD أصلاً. وهو أسوأ
    أنواع الخطأ — قائمةٌ تبدو أطول فتبدو الاستراتيجية أنجح.
    """
    m = row.get("momentum") or {}
    m = m.get("macd") if isinstance(m, dict) else None
    return m if isinstance(m, dict) and m.get("ok") else None


def _macd_flag(key: str):
    def read(row: dict):
        m = _macd(row)
        return None if m is None else bool(m.get(key))
    return read


def _macd_slope(row: dict) -> float | None:
    m = _macd(row)
    return None if m is None else _num(m.get("slope_pct"))


def _stoch_timing(row: dict) -> bool | None:
    """توقيت StochRSI — و``None`` لصفٍّ قديم لا يحمله.

    ``m.get(key, False)`` كان سيُعيد «لا» لصفٍّ مُسح قبل إضافة
    الحقل، فيطابق شرط «التوقيت = لا» رمزاً لم يُفحَص.
    """
    m = row.get("momentum")
    if not isinstance(m, dict) or "stoch_timing" not in m:
        return None
    return bool(m.get("stoch_timing"))


def _factor_pct(row: dict, key: str) -> float | None:
    """حصّة عاملٍ من سقفه — ٪.

    والنسبة لا النقاط: وزن العامل يتغيّر من إعدادٍ لآخر، فشرطٌ
    على «نقاط الحجم ≥ 12» يصير معنىً مختلفاً بعد تعديل الأوزان
    بلا أن ينتبه أحد. والنسبة تبقى نسبةً.
    """
    for f in row.get("factors") or []:
        if f.get("key") == key:
            mx = _num(f.get("max")) or 0.0
            pts = _num(f.get("points"))
            if mx > 0 and pts is not None:
                return round(pts / mx * 100.0, 1)
            return None
    return None


# ═══════════════════════════════════════════════════════════════
#  سجلّ الحقول
# ═══════════════════════════════════════════════════════════════
#
# ``get`` يقرأ من صفّ مسح ‏PES. وكلّها محفوظة بعد كل دورة، فلا
# قراءة قرصٍ ولا حساب.

FIELDS: dict[str, dict[str, Any]] = {
    "score": {
        "label": "درجة PES", "kind": "number", "unit": "/100",
        "min": 0, "max": 100, "step": 5,
        "help": "مجموع العوامل الإحدى عشرة. وهي ترتيبٌ لا احتمال.",
        "get": lambda r: _num(r.get("score")),
    },
    "state": {
        "label": "المرحلة", "kind": "enum",
        "choices": ["NONE", "WATCH", "EARLY_MOMENTUM", "PRE_BREAKOUT",
                    "STRONG_PRE_BREAKOUT", "BREAKOUT", "BREAKOUT_RETEST",
                    "ENTRY_READY", "LATE_MOMENTUM", "ALREADY_EXPANDED"],
        "help": "موضع الرمز في تسلسل ما قبل الانفجار.",
        "get": lambda r: r.get("state"),
    },
    "confidence": {
        "label": "الثقة", "kind": "number", "unit": "×",
        "min": 0, "max": 1, "step": 0.05,
        "help": "مُضاعِفٌ يخفضه نظام البتكوين الهابط — للكريبتو وحده.",
        "get": lambda r: _num(r.get("confidence")),
    },
    "family_count": {
        "label": "عدد العائلات المساهِمة", "kind": "number",
        "min": 0, "max": 6, "step": 1,
        "help": "القاعدة ١٧: ثلاثٌ فأكثر شرطُ الترقية. "
                "واجتماع مؤشّرات تقيس الشيء نفسه ليس تأكيداً.",
        "get": lambda r: _num(r.get("family_count")),
    },
    "distance": {
        "label": "البُعد عن المقاومة", "kind": "number", "unit": "٪",
        "min": 0, "max": 50, "step": 0.5,
        "help": "كم يحتاج السعر ليبلغ المقاومة. والصغير أقرب للاختراق.",
        "get": lambda r: _num(r.get("distance")),
    },
    "momentum_score": {
        "label": "التقاء الزخم", "kind": "number", "unit": "/10",
        "min": 0, "max": 10, "step": 1,
        "help": "‏MACD تأكيداً و‏StochRSI توقيتاً. والسابعة قفزةُ التوقيت.",
        "get": lambda r: _num((r.get("momentum") or {}).get("score")),
    },
    # ═══ MACD حالاتٍ لا رقماً ═══
    #
    # كان MACD مدموجاً في «التقاء الزخم» وحدها: رقمٌ من عشرة لا
    # يقول أيّ حالةٍ بلغها. و«المدرَّج صاعد وهو سالب» و«تقاطعٌ صاعد
    # للتوّ» حالتان مختلفتان تماماً في التوقيت، وتذوبان في الرقم
    # نفسه.
    #
    # والمدرَّج نفسه لا يُعرَض شرطاً: قيمته بوحدة السعر، فعتبةٌ
    # تصلح لرمزٍ وتخطئ في آخر. والمعروض ميلُه نسبةً إلى مداه.
    #
    # وهي على فريم ‎4h‎ — الإطار الذي يُقاس عليه الزخم الرئيسي.
    "macd_rising": {
        "label": "‏MACD: المدرَّج صاعد", "kind": "bool",
        "help": "ثلاث شمعاتٍ متتالية صاعدة في المدرَّج. وهي الإشارة "
                "المبكّرة — تسبق التقاطع بشمعاتٍ عدّة.",
        "get": _macd_flag("rising"),
    },
    "macd_early_turn": {
        "label": "‏MACD: تحسّنٌ مبكّر (سالبٌ وصاعد)", "kind": "bool",
        "help": "المدرَّج ما زال تحت الصفر لكنّه يصعد — أنفع حالاته "
                "لاستراتيجية «ما قبل»، وأخطرها إن لم يكتمل.",
        "get": _macd_flag("early_turn"),
    },
    "macd_cross_up": {
        "label": "‏MACD: تقاطعٌ صاعد الآن", "kind": "bool",
        "help": "الخطّ عبر إشارته في الشمعة المغلقة الأخيرة. "
                "تأكيدٌ متأخّر عن الميل، وأقوى منه.",
        "get": _macd_flag("cross_up"),
    },
    "macd_above_signal": {
        "label": "‏MACD: فوق خطّ الإشارة", "kind": "bool",
        "help": "حالةٌ مستمرّة لا لحظة — تصلح شرطَ سياقٍ مع شرط "
                "توقيتٍ آخر.",
        "get": _macd_flag("above_signal"),
    },
    "macd_above_zero": {
        "label": "‏MACD: المدرَّج فوق الصفر", "kind": "bool",
        "help": "الزخم موجب بالفعل. واشتراطه يستبعد الانعكاسات "
                "المبكّرة — وهي ما تبحث عنه هذه المنصّة غالباً.",
        "get": _macd_flag("above_zero"),
    },
    "macd_slope": {
        "label": "‏MACD: ميل المدرَّج", "kind": "number", "unit": "٪",
        "min": -100, "max": 100, "step": 5,
        "help": "الميل نسبةً إلى مدى المدرَّج في ستّين شمعة — لا "
                "بوحدة السعر. فهو قابل للمقارنة بين الرموز: ١٠٪ "
                "فأكثر «صعودٌ واضح».",
        "get": _macd_slope,
    },
    "stoch_timing": {
        "label": "‏StochRSI: تقاطع التوقيت", "kind": "bool",
        "help": "تقاطعٌ صاعد من منطقةٍ ليست مشبَعة. وهو ما يختار "
                "اللحظة — و‏MACD يختار الرمز.",
        "get": _stoch_timing,
    },
    "supertrend_dir": {
        "label": "اتّجاه Supertrend", "kind": "enum",
        "choices": ["up", "down"],
        "labels": {"up": "صاعد", "down": "هابط"},
        "help": "على فريم المسح. والغائب لا يُطابق شيئاً.",
        "get": _st_dir,
    },
    "supertrend_bars": {
        "label": "عمر انقلاب Supertrend", "kind": "number", "unit": "شمعة",
        "min": 0, "max": 200, "step": 1,
        "help": "متى انقلب — وهي المعلومة التي لا يعطيها EMA ولا ADX. "
                "والقليل بدايةُ اتّجاه، والكثير نضجُه.",
        "get": lambda r: _num((r.get("supertrend") or {}).get(
            "bars_since_flip")),
    },
    "already_expanded": {
        "label": "ارتفع بالفعل", "kind": "bool",
        "help": "مانع المطاردة. و«لا» هي ما تريده غالباً.",
        "get": lambda r: bool(r.get("already_expanded")),
    },
    "close": {
        "label": "السعر", "kind": "number",
        "min": 0, "max": 1_000_000, "step": 0.01,
        "help": "لاستبعاد الرموز الرخيصة جداً أو الغالية جداً.",
        "get": lambda r: _num(r.get("close")),
    },
    "fib_room": {
        "label": "المسافة إلى امتداد فيب", "kind": "number", "unit": "٪",
        "min": 0, "max": 100, "step": 1,
        "help": "كم بقي إلى الهدف التالي. ويغيب إن لم توجد موجة صالحة.",
        "get": lambda r: _num((r.get("fib") or {}).get("room_pct")),
    },
    # ═══ العوامل حصصاً ═══
    #
    # نسبةُ كل عامل من سقفه. وهي أدقّ من الدرجة الكلّية: «الحجم
    # ≥ ٨٠٪» شرطٌ على الحجم وحده، والدرجة الكلّية قد تبلغها
    # بعواملَ أخرى تماماً.
    **{
        f"factor_{k}": {
            "label": f"عامل: {lbl}", "kind": "number", "unit": "٪",
            "min": 0, "max": 100, "step": 5,
            "help": "حصّة هذا العامل من سقفه — نسبةً لا نقاطاً، "
                    "فلا يتغيّر معناه بتغيّر الأوزان.",
            "get": (lambda key: lambda r: _factor_pct(r, key))(k),
        }
        for k, lbl in (
            ("compression", "الانضغاط"),
            ("volume", "الحجم"),
            ("obv", "تراكم OBV"),
            ("h4_trend", "اتجاه 4س"),
            ("daily_trend", "الاتجاه اليومي"),
            ("supertrend", "Supertrend"),
            ("resistance", "قرب المقاومة"),
            ("adx", "ADX"),
            ("momentum_confluence", "التقاء الزخم"),
            ("rsi", "RSI"),
        )
    },
}


def field_catalog() -> list[dict]:
    """الحقول للواجهة — بلا الدوالّ.

    والترتيب ثابت: قاموسُ بايثون يحفظ ترتيب الإدخال، فالقائمة
    لا تتبدّل بين تحميلٍ وآخر.
    """
    out = []
    for key, f in FIELDS.items():
        row = {k: v for k, v in f.items() if k != "get"}
        row["key"] = key
        row["ops"] = [o for o, spec in OPS.items()
                      if f["kind"] in spec["kinds"]]
        out.append(row)
    return out


# ═══════════════════════════════════════════════════════════════
#  التقييم
# ═══════════════════════════════════════════════════════════════

def _compare(kind: str, op: str, value, args: list) -> bool:
    if value is None:
        return False                      # الغائب لا يُطابق
    if op == "in":
        return str(value) in {str(a) for a in args}
    if op == "between":
        lo, hi = (_num(args[0]), _num(args[1])) if len(args) > 1 else (None, None)
        v = _num(value)
        return None not in (lo, hi, v) and lo <= v <= hi
    a = args[0] if args else None
    if kind == "number":
        v, t = _num(value), _num(a)
        if v is None or t is None:
            return False
        return {">=": v >= t, "<=": v <= t, ">": v > t, "<": v < t,
                "==": v == t, "!=": v != t}.get(op, False)
    if kind == "bool":
        v = bool(value)
        t = str(a).lower() in ("1", "true", "yes", "نعم")
        return (v == t) if op == "==" else (v != t)
    v, t = str(value), str(a)
    return (v == t) if op == "==" else (v != t)


def evaluate(row: dict, conditions: list[dict]) -> dict:
    """يقيس صفّاً واحداً على شروط الاستراتيجية.

    ويعيد **تفصيل كل شرط** لا نعم/لا وحدها: البطاقة تعرض أيّها
    تحقّق وأيّها لم يتحقّق وبأيّ قيمة. و«لا يُطابق» بلا سبب
    تجعل الاستراتيجية صندوقاً مغلقاً لا يُحسَّن.
    """
    detail: list[dict] = []
    for c in conditions or []:
        key = c.get("field")
        spec = FIELDS.get(key)
        if spec is None:
            # حقلٌ أُزيل من السجلّ بعد حفظ الاستراتيجية
            detail.append({"field": key, "ok": False, "value": None,
                           "label": key or "?", "why": "حقل غير معروف"})
            continue
        val = spec["get"](row)
        args = c.get("args") or ([c["value"]] if "value" in c else [])
        ok = _compare(spec["kind"], c.get("op", "=="), val, args)
        detail.append({
            "field": key, "label": spec["label"], "ok": bool(ok),
            "value": val, "op": c.get("op"), "args": args,
            "unit": spec.get("unit", ""),
        })
    met = sum(1 for d in detail if d["ok"])
    return {
        "match": bool(detail) and met == len(detail),
        "met": met, "total": len(detail), "conditions": detail,
    }


def matches(row: dict, conditions: list[dict]) -> bool:
    return evaluate(row, conditions)["match"]


def validate(conditions) -> list[str]:
    """أخطاء الاستراتيجية نصّاً — قبل الحفظ لا بعده.

    وحفظُ شرطٍ معطوب يجعله يفشل صامتاً عند كل فرز: لا رمز
    يُطابق، ولا شيء يقول لماذا.
    """
    errs: list[str] = []
    if not isinstance(conditions, list) or not conditions:
        return ["الاستراتيجية بلا شروط"]
    for i, c in enumerate(conditions, 1):
        if not isinstance(c, dict):
            errs.append(f"الشرط {i}: صيغة غير صالحة")
            continue
        key, op = c.get("field"), c.get("op")
        spec = FIELDS.get(key)
        if spec is None:
            errs.append(f"الشرط {i}: حقل غير معروف ({key})")
            continue
        if op not in OPS:
            errs.append(f"الشرط {i}: عملية غير معروفة ({op})")
            continue
        if spec["kind"] not in OPS[op]["kinds"]:
            errs.append(f"الشرط {i}: «{OPS[op]['label']}» لا تنطبق على "
                        f"«{spec['label']}»")
            continue
        args = c.get("args") or ([c["value"]] if "value" in c else [])
        need = OPS[op]["arity"]
        if need == "list" and not args:
            errs.append(f"الشرط {i}: بلا قيم")
        elif isinstance(need, int) and len(args) < need:
            errs.append(f"الشرط {i}: يحتاج {need} قيمة")
    return errs


__all__ = ["FIELDS", "OPS", "field_catalog", "evaluate", "matches",
           "validate"]
