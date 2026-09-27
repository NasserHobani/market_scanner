# -*- coding: utf-8 -*-
"""قواعد الخروج على المراكز الحقيقية — تنبيهٌ لا تنفيذ.

═══ ثلاثة مصادر للتنبيه ═══

    وقف/هدف   سعرٌ تكتبه أنت لكل رمز
    تراجع     نسبةٌ من أعلى نقطةٍ بلغها **بعد** تفعيل القاعدة
    إشارة     تحليل المنصّة نفسه تغيّر على رمزٍ تملكه

والثلاثة تُنتج رسالة. ولا يوجد في المشروع كلّه سطرٌ يرسل أمراً
إلى Binance — المادّة ١٣ §٣٣.

═══ والتكرار هو العطب المتوقَّع ═══

قاعدةٌ تُفحَص كل دقيقة وسعرٌ بقي تحت الوقف ساعةً = ستّون رسالة.
فيُحفَظ ``fired_at`` ولا يُعاد الإطلاق قبل ``COOLDOWN`` — والقاعدة
لا تُطفأ تلقائياً: إطفاؤها قرارٌ يخصّ صاحبها، ونحن لا نعرف أباع
أم لا.

═══ والقمّة تُحفَظ ولا تُحسب ═══

«أعلى سعر» محسوبٌ من الشموع يعطي قمّة التاريخ كلّه — فتنبيه
التراجع إمّا لا يقع أبداً أو يقع فوراً. والقمّة هنا تبدأ من لحظة
التفعيل وتُحدَّث في كل دورة.
"""
from __future__ import annotations

import logging

log = logging.getLogger("dashboard.wallet_monitor")

#: لا يُعاد التنبيه نفسه قبل هذه المدّة
COOLDOWN_MINUTES = 180

#: حالات المنصّة التي تعني «الحركة انتهت»
EXIT_STATES = ("ALREADY_EXPANDED", "LATE_MOMENTUM")

__all__ = ["evaluate", "run_once", "COOLDOWN_MINUTES", "EXIT_STATES"]


def _pct(a: float, b: float) -> float:
    return (a - b) / b * 100.0 if b else 0.0


def evaluate(rule, price: float, *, peak: float | None = None,
             signal: dict | None = None) -> dict:
    """هل تتحقّق هذه القاعدة عند هذا السعر؟

    دالّةٌ نقيّة: لا قاعدة بيانات ولا شبكة — فتُختبَر بلا إطار،
    وهي المنطق الذي يقرّر متى تُرسَل رسالة.
    """
    kind = rule.kind
    if not rule.active or price is None or price <= 0:
        return {"hit": False, "why": "غير فعّالة أو بلا سعر"}

    if kind == "stop":
        if rule.price is None:
            return {"hit": False, "why": "بلا سعر وقف"}
        hit = price <= rule.price
        return {"hit": hit, "level": rule.price,
                "why": (f"السعر {price:.8g} بلغ الوقف {rule.price:.8g}"
                        if hit else
                        f"فوق الوقف بـ{_pct(price, rule.price):.2f}٪")}

    if kind == "target":
        if rule.price is None:
            return {"hit": False, "why": "بلا سعر هدف"}
        hit = price >= rule.price
        return {"hit": hit, "level": rule.price,
                "why": (f"السعر {price:.8g} بلغ الهدف {rule.price:.8g}"
                        if hit else
                        f"دون الهدف بـ{_pct(rule.price, price):.2f}٪")}

    if kind == "trail":
        if not rule.pct or rule.pct <= 0:
            return {"hit": False, "why": "بلا نسبة تراجع"}
        top = peak if peak is not None else rule.peak
        # ═══ بلا قمّةٍ لا تراجع ═══
        #
        # أوّل دورةٍ بعد التفعيل تضع القمّة ولا تُطلق. وحسابُ
        # التراجع من قمّةٍ فارغة يقارن بصفرٍ فيتحقّق دائماً.
        if not top or top <= 0:
            return {"hit": False, "why": "القمّة لم تُسجَّل بعد"}
        drop = _pct(top, price)          # كم نزل عن القمّة
        hit = drop >= rule.pct
        level = top * (1 - rule.pct / 100.0)
        return {"hit": hit, "level": level, "peak": top, "drop_pct": drop,
                "why": (f"تراجع {drop:.2f}٪ من القمّة {top:.8g} — "
                        f"والحدّ {rule.pct:g}٪"
                        if hit else
                        f"تراجع {drop:.2f}٪ من {top:.8g} (الحدّ "
                        f"{rule.pct:g}٪)")}

    if kind == "signal":
        # ═══ تحليل المنصّة ═══
        #
        # ولا يُخترع هنا شيء: الحالات نفسها التي تعرضها بقيّة
        # الشاشات. ومعيارٌ ثانٍ بمعنىً مختلف يجعل الشاشتين
        # تتناقضان على الرمز نفسه.
        if not signal:
            return {"hit": False, "why": "لا تحليل محفوظ لهذا الرمز"}
        reasons = []
        if str(signal.get("state") or "") in EXIT_STATES:
            reasons.append(f"المرحلة صارت {signal.get('state')}")
        st = (signal.get("supertrend") or {}).get("direction")
        if st is not None and st < 0:
            reasons.append("‏Supertrend انقلب هابطاً")
        if signal.get("already_expanded"):
            reasons.append("ارتفع بالفعل — مانع المطاردة")
        return {"hit": bool(reasons), "why": " · ".join(reasons)
                or "التحليل لم يتغيّر"}

    return {"hit": False, "why": f"نوع غير معروف: {kind}"}


def _signal_for(symbol: str) -> dict | None:
    """آخر صفّ مسحٍ محفوظ لهذا الرمز — من ذاكرة PES لا بحسابٍ جديد."""
    try:
        from scanner.strategies import pes_scan

        for market in ("crypto",):
            cached = pes_scan.load(market)
            for row in (cached or {}).get("rows", []):
                if str(row.get("symbol", "")).upper() == symbol.upper():
                    return row
    except Exception as exc:  # noqa: BLE001
        log.info("تعذّرت قراءة تحليل %s: %s", symbol, str(exc)[:80])
    return None


def run_once() -> dict:
    """دورةٌ واحدة: حدّث القمم، وقيّم القواعد، وأرسل ما تحقّق."""
    from datetime import timedelta

    from django.utils import timezone

    from scanner.adapters import get_adapter

    from .models import WalletRule

    rules = list(WalletRule.objects.filter(active=True))
    if not rules:
        return {"checked": 0, "fired": 0, "reason": "لا قواعد فعّالة"}

    # سعرٌ واحد لكل رمز مهما تعدّدت قواعده
    symbols = sorted({r.symbol.upper() for r in rules})
    prices: dict[str, float] = {}
    adapter = get_adapter("binance")
    for sym in symbols:
        try:
            df = adapter.fetch(sym, "1m", 2)
            if df is not None and len(df):
                prices[sym] = float(df["close"].iloc[-1])
        except Exception as exc:  # noqa: BLE001
            log.info("تعذّر سعر %s: %s", sym, str(exc)[:70])

    now = timezone.now()
    cutoff = now - timedelta(minutes=COOLDOWN_MINUTES)
    fired = []

    for r in rules:
        px = prices.get(r.symbol.upper())
        if px is None:
            continue

        # ═══ القمّة تُحدَّث قبل التقييم ═══
        if r.kind == "trail" and (r.peak is None or px > r.peak):
            r.peak, r.peak_at = px, now
            r.save(update_fields=["peak", "peak_at", "updated_at"])

        res = evaluate(r, px, signal=_signal_for(r.symbol)
                       if r.kind == "signal" else None)
        if not res.get("hit"):
            continue
        # ═══ ولا يُعاد قبل المهلة ═══
        if r.fired_at and r.fired_at > cutoff:
            continue

        r.fired_at, r.fired_price = now, px
        r.fire_count = (r.fire_count or 0) + 1
        r.save(update_fields=["fired_at", "fired_price", "fire_count",
                              "updated_at"])
        fired.append({"symbol": r.symbol, "kind": r.kind,
                      "price": px, "why": res.get("why", "")})
        _notify(r, px, res)

    return {"checked": len(rules), "priced": len(prices),
            "fired": len(fired), "events": fired}


def _notify(rule, price: float, res: dict) -> None:
    """رسالة تيليجرام — ولا ترمي أبداً.

    فشلُ الإرسال يجب ألّا يمنع تقييم بقيّة القواعد: من فقد رسالةً
    أهون ممّن فقد الدورة كلّها.
    """
    label = dict(rule.KINDS).get(rule.kind, rule.kind)
    text = (f"⚠ {rule.symbol} — {label}\n"
            f"السعر: {price:.8g}\n"
            f"{res.get('why', '')}\n"
            f"\nتنبيهٌ فقط — التنفيذ عندك في تطبيق Binance.")
    try:
        from scanner.outputs import telegram

        telegram.send(text)
    except Exception as exc:  # noqa: BLE001
        log.warning("تعذّر إرسال تنبيه %s: %s", rule.symbol, str(exc)[:90])
