# -*- coding: utf-8 -*-
"""ماذا حُلِّل فعلاً من السوق — وما الذي غاب ولماذا.

═══ الفجوة التي كانت صامتة ═══

المسار ثلاث مراحل، وكلٌّ يقرأ من غير ما يقرأ منه الآخر:

    اكتشاف   ``resolve_symbols``      من المنصّة  ← ٤٨٧ رمزاً
    مزامنة   ``sync_pair``            تنزّل الشموع ← ٢١٠ نجحت
    تحليل    ``stored_symbols``       من **القرص** ← ٢١٠ حُلِّلت

فالتحليل لا يرى إلّا ما نُزّل. والرمز المكتشَف الذي لم تصله
المزامنة بعدُ **غير موجود** بالنسبة للشاشة: لا صفّ له، ولا سطر
يقول إنّه ناقص.

وظهر أثرُها على خادمٍ جديد: عشرة رموزٍ حُلِّلت من سوقٍ فيه مئات،
والشاشة تعرض عشرة صفوفٍ سليمة تماماً. لا خطأ، ولا صفر، ولا شيء
يدلّ — فبدا النظام يعمل وهو يرى ٢٪ من السوق.

═══ ولماذا تقريرٌ لا إصلاحٌ تلقائيّ ═══

جعلُ التحليل يجلب ما ينقصه يخلط مسؤوليتين: يصير المسح شبكياً،
فتتضاعف مدّته وتُضرب حدود المنصّات، ويفشل التحليل كلّه لانقطاعٍ
في رمزٍ واحد.

فالمزامنة تبقى مهمّةً مستقلّة، والتحليل **يعلن** ما لم يصله. وعددٌ
معلَن أنفع من إصلاحٍ صامت: يقول لك أنّ المزامنة متأخّرة، وهو
تشخيصٌ يخصّها لا يخصّ التحليل.
"""
from __future__ import annotations

import logging

log = logging.getLogger("scanner.analysis.coverage")


def report(market: str, analyzed: list[str], *, timeframe: str = "4h") -> dict:
    """يقارن ما حُلِّل بما اكتُشف. لا يرمي — يعيد ``known: False``.

    ``analyzed`` هي الرموز التي دخلت التحليل فعلاً، لا التي على
    القرص: بينهما المحظور والمعطوب، وخلطُهما يجعل التقرير يكذب
    في الاتجاه المطمئن.
    """
    out = {
        "known": False,
        "analyzed": len(analyzed),
        "discovered": None,
        "awaiting_sync": [],
        "awaiting_count": 0,
        "coverage_pct": None,
        "reason": "",
    }
    try:
        from scanner.market_sync import get_service

        universe = list(get_service().resolve_symbols(market))
    except Exception as exc:  # noqa: BLE001
        # ═══ فشل الاكتشاف لا يُسقط المسح ═══
        #
        # التقرير خدمةٌ فوق التحليل لا شرطٌ له. وانقطاعُ شبكةٍ
        # لحظةَ المسح يجب ألّا يمحو نتائج مئتي رمزٍ حُسبت فعلاً.
        out["reason"] = f"تعذّر معرفة كون السوق: {str(exc)[:120]}"
        log.warning("تعذّرت تغطية %s: %s", market, str(exc)[:120])
        return out

    done = set(analyzed)
    waiting = [s for s in universe if s not in done]
    out.update(
        known=True,
        discovered=len(universe),
        awaiting_sync=waiting[:50],      # عيّنة للعرض لا القائمة كلّها
        awaiting_count=len(waiting),
        coverage_pct=(round(len(done & set(universe)) / len(universe) * 100, 1)
                      if universe else None),
        timeframe=timeframe,
    )
    return out


def describe(cov: dict) -> str:
    """سطرٌ عربيّ للسجلّ والشاشة."""
    if not cov.get("known"):
        return cov.get("reason") or "التغطية غير معروفة"
    if not cov.get("awaiting_count"):
        return f"حُلِّل السوق كاملاً ({cov['analyzed']} رمزاً)"
    return (f"حُلِّل {cov['analyzed']} من {cov['discovered']} "
            f"({cov['coverage_pct']}٪) · {cov['awaiting_count']} "
            f"بلا شموع بعد")


__all__ = ["report", "describe"]
