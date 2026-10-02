# -*- coding: utf-8 -*-
"""دراسة رمزٍ واحد — أين دخل الناجحون، ومتى.

═══ الخطوات ═══

    ١. وسمُ كل شمعةٍ بالحاجزين: هل بلغ ‎2×ATR‎ قبل ‎1×ATR‎؟
    ٢. مناطق الارتداد التاريخية، وكلّ لمسةٍ بنتيجتها
    ٣. شروط المنصّة — مكتوبةٌ سلفاً — كلٌّ بنسبته وفاصله
    ٤. تقسيمٌ زمنيّ: اكتشافٌ ثمّ تحقّق

═══ وما تمتنع عنه ═══

لا تبحث عن عتبةٍ مثلى. ولا تجرّب تركيباتٍ حتى تجد واحدةً تلمع.
الشروط هي حالات المنصّة نفسها، وعددُها ثابتٌ معروف — فالتصحيح
الإحصائيّ له معنى، والنتيجة قابلةٌ للتكذيب.

ولا تقول «ادخل هنا». تقول: هذه المنطقة لُمست إحدى عشرة مرّة،
صمدت في سبعٍ منها، وفاصل ذلك ‎[35–86]‎. والقرار بعد ذلك لصاحبه.

═══ وحدُّها الصريح ═══

رمزٌ واحد وتاريخٌ واحد. ومئتا شمعةٍ ليست عيّنةً تُبنى عليها
قاعدة، والسوق يغيّر نظامه فما صحّ في ٢٠٢٤ قد لا يصحّ اليوم.
فالفواصل معروضةٌ دائماً — وهي التي تقول كم تعرف فعلاً.
"""
from __future__ import annotations

from .conditions import evaluate as evaluate_conditions
from .labels import DEFAULTS, label_forward, rate
from .zones import build as build_zones

__all__ = ["study", "DEFAULTS", "label_forward", "rate",
           "build_zones", "evaluate_conditions"]


def study(market: str, symbol: str, timeframe: str = "4h", *,
          target_atr: float = 2.0, stop_atr: float = 1.0,
          horizon: int = 24) -> dict:
    """الدراسة الكاملة — أو سببُ التعذّر.

    تقرأ الشموع المخزّنة فقط: لا جلبَ شبكيّ، فالدراسة لا تنتظر
    مزوّداً ولا تُثقل حدّ الطلبات.
    """
    from scanner import storage

    df = storage.load(market, symbol, timeframe)
    if df is None or len(df) < 250:
        return {"ok": False,
                "why": f"شموع غير كافية ({0 if df is None else len(df)}) — "
                       f"يلزم ٢٥٠ على {timeframe}. زامن الرمز أوّلاً."}

    daily = storage.load(market, symbol, "1d") if timeframe != "1d" else None

    labels = label_forward(df, target_atr=target_atr, stop_atr=stop_atr,
                           horizon=horizon)
    if not labels.get("ok"):
        return {"ok": False, "why": labels.get("why", "تعذّر الوسم")}

    overall = rate(labels["label"])
    zones = build_zones(df, labels)
    conds = evaluate_conditions(df, labels, daily=daily)

    amb = labels["ambiguous_n"]
    notes = [
        f"النجاح = بلوغ {target_atr:g}×ATR قبل {stop_atr:g}×ATR خلال "
        f"{horizon} شمعة. وما لم يُحسم في الأفق لا يُحتسب — لا ربحاً "
        "ولا خسارة.",
    ]
    if amb:
        share = 100.0 * amb / max(1, labels["settled"])
        notes.append(
            f"‏{amb} حالة ({share:.0f}٪) بلغت الحاجزين في شمعةٍ واحدة — "
            "والترتيب فيها مجهول، فعُدّت خسارة. وإن كثُرت فالأفق أو "
            "الحاجزان لا يناسبان هذا الفريم.")
    notes.append(
        "رمزٌ واحد وتاريخٌ واحد. والفواصل معروضة لأنّها هي التي تقول "
        "كم تعرف — لا النسبة وحدها.")

    return {
        "ok": True,
        "symbol": symbol, "market": market, "timeframe": timeframe,
        "candles": len(df),
        "from": str(df.index[0])[:16], "to": str(df.index[-1])[:16],
        "last_close": float(df["close"].iloc[-1]),
        "params": labels["params"],
        "baseline": overall,
        "zones": zones[:12],
        "conditions": conds,
        "daily_available": daily is not None and len(daily) > 60,
        "notes": notes,
    }
