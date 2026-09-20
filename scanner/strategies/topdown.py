# -*- coding: utf-8 -*-
"""من الأعلى إلى الأسفل: الأسبوعيّ يأذن · اليوميّ يوافق · الـ4س يوقّت.

    أسبوعيّ صاعد   →  اتّجاهٌ أكبر منك، فلا تقاتله
    يوميّ صاعد     →  والوسط يوافق
    غير ممتدّ      →  ولم يُستهلَك الصعود بعد
    ارتدادٌ ثمّ استئناف على 4س  →  وهنا تدخل

═══ لماذا الارتداد لا الاختراق ═══

الدخول عند القمّة مع اتّجاهٍ صاعد **يعمل** — لكنّ وقفَه بعيد:
تحتاج نزولاً كاملاً إلى آخر قاع لتعرف أنّك مخطئ. والدخول بعد
ارتدادٍ إلى المتوسّط يضع الوقف تحت ذلك الارتداد مباشرةً، فالخطأ
يظهر بسرعة ورخيصاً.

والفرق ليس في نسبة الفوز بل في حجم الخسارة حين تخطئ — وهو ما
يحكم النتيجة على المدى.

═══ وما الذي يُميّز «ارتداداً ثمّ استئنافاً» عن «هبوط»؟ ═══

ثلاثة شروط معاً، وإسقاط أيّها يجعل الشاشة تلتقط السقوط:

    ١) الاتّجاه العلويّ ما زال صاعداً       ← وإلّا فهو انهيار
    ٢) لمس المنطقة ثمّ **أغلق فوقها**       ← لا لمسٌ وحده
    ٣) الارتداد لم يكسر البنية              ← لم ينزل تحت قاعٍ سابق

═══ ولا نظر إلى المستقبل ═══

كل قراءةٍ هنا من آخر شمعة **مغلقة**. والشمعة الجارية تُسقَط قبل
أيّ حساب: «أغلق فوق المتوسّط» تُقال عن شمعةٍ أغلقت فعلاً، لا عن
شمعةٍ قد تنعكس قبل إغلاقها.

═══ وهذا وصفٌ لا حكم ═══

لم يُقَس أثرُ هذا الترتيب على صفقاتك بعد. فالشاشة تعرض وتشرح،
ولا تُنتج توصيةً ولا تدخل تقييم PES. وقياسُه على الصفقات
المحسومة هو ما يقرّر إن كان يستحقّ أكثر من ذلك.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

# ‏قاعدة إعادة التجميع إلى الأسبوعيّ. والأسبوع ينتهي الأحد في
# السوق السعودي والجمعة في الأمريكي — و``1W`` تكفي هنا لأنّ
# المقصود انحيازٌ عامّ لا توقيتٌ دقيق على حدّ الأسبوع.
WEEKLY_RULE = "1W"

#: أقلّ عدد شمعاتٍ أسبوعية يُبنى عليها حكم
MIN_WEEKLY = 30
MIN_DAILY = 60
MIN_H4 = 60

BIAS_UP, BIAS_FLAT, BIAS_DOWN = 1, 0, -1


def _closed(df: pd.DataFrame | None) -> pd.DataFrame | None:
    """بلا الشمعة الجارية — قيمُها تتغيّر حتى تُغلق."""
    if df is None or len(df) < 2:
        return None
    return df.iloc[:-1]


def to_weekly(d1: pd.DataFrame) -> pd.DataFrame:
    """أسبوعيّ من اليوميّ — لا طلب شبكة.

    ``label="right"`` مع ``closed="right"``: الشمعة تُنسَب إلى
    نهاية أسبوعها. وهو ما يفعله ``indicators/htf.py`` نفسه، فلا
    يفترق الفريمان في مكانين من النظام.
    """
    from scanner.indicators.htf import AGG

    return d1.resample(WEEKLY_RULE, label="right",
                       closed="right").agg(AGG).dropna()


def _bias(df: pd.DataFrame, *, fast: int = 20, slow: int = 50) -> dict:
    """انحياز فريمٍ واحد: صاعد/محايد/هابط، وبرهانه.

    والميل شرطٌ مستقلّ عن الترتيب: ``EMA20 > EMA50`` تبقى صحيحة
    أسابيع بعد أن يلتفت الاتجاه. و«مكمل بالصعود» تعني أنّ
    المتوسّط ما زال **يرتفع** الآن.
    """
    from scanner.indicators.pine import ema
    from scanner.indicators.trend import slope

    out = {"bias": BIAS_FLAT, "checks": [], "ext_pct": None,
           "close": None, "ema_fast": None, "ema_slow": None}
    if df is None or len(df) < slow + 5:
        out["reason"] = f"شموع غير كافية ({0 if df is None else len(df)})"
        return out

    close = df["close"].astype(float)
    ef, es = ema(close, fast), ema(close, slow)
    c = float(close.iloc[-1])
    f, s = float(ef.iloc[-1]), float(es.iloc[-1])

    above = c > s
    stacked = f > s
    rising = slope(ef, 5) > 0        # المتوسّط ما زال يصعد الآن

    out["checks"] = [
        {"name": f"الإغلاق فوق EMA{slow}", "ok": bool(above)},
        {"name": f"EMA{fast} فوق EMA{slow}", "ok": bool(stacked)},
        {"name": f"EMA{fast} ما زال يرتفع", "ok": bool(rising)},
    ]
    ups = sum(1 for x in out["checks"] if x["ok"])
    # ═══ الثلاثة أو لا شيء ═══
    #
    # اثنان من ثلاثة يمرّر اتّجاهاً يلتفت: السعر فوق المتوسّط
    # والترتيب سليم، والميل انعكس — وهي صورة القمّة بالضبط.
    out["bias"] = (BIAS_UP if ups == 3
                   else BIAS_DOWN if ups == 0 else BIAS_FLAT)
    out["ext_pct"] = round((c - f) / f * 100, 2) if f else None
    out["close"], out["ema_fast"], out["ema_slow"] = (
        round(c, 8), round(f, 8), round(s, 8))
    return out


def _pullback_resume(h4: pd.DataFrame, p: dict) -> dict:
    """ارتدادٌ إلى المنطقة ثمّ استئناف — على الـ4س.

    ═══ «المنطقة» ليست خطّاً واحداً ═══

    ‏EMA20 أو خطّ Supertrend، أيّهما لامسه السعر. والاكتفاء بواحدٍ
    منهما يفوّت نصف الارتدادات: بعضها يرتدّ من المتوسّط وبعضها من
    الخطّ، وكلاهما ارتدادٌ صحيح.
    """
    from scanner.indicators.pine import ema
    from scanner.indicators.trend import supertrend_state

    cfg = (p or {}).get("topdown") or {}
    look = int(cfg.get("pullback_lookback", 12))
    touch_pct = float(cfg.get("touch_pct", 1.5))

    out: dict[str, Any] = {"ok": False, "reason": "", "checks": [],
                           "touched_bars_ago": None, "zone": None,
                           "stop_hint": None, "risk_pct": None}
    df = _closed(h4)
    if df is None or len(df) < MIN_H4:
        out["reason"] = "شموع 4س غير كافية"
        return out

    min_drop = float(cfg.get("min_pullback_pct", 2.0))

    close = df["close"].astype(float)
    low = df["low"].astype(float)
    high = df["high"].astype(float)
    e20 = ema(close, 20)
    st = supertrend_state(h4)      # يُسقط الجارية بنفسه

    c = float(close.iloc[-1])
    e = float(e20.iloc[-1])
    st_line = st["line"] if st["usable"] and st["direction"] > 0 else None

    # ═══════════════════════════════════════════════════════
    #  الارتداد يُقاس من قمّةٍ، لا من قربٍ عابرٍ للمتوسّط
    # ═══════════════════════════════════════════════════════
    #
    # النسخة الأولى سألت: «هل لمس السعر المنطقة في آخر ١٢ شمعة؟»
    # ومرّ عليها صعودٌ مستقيم بلا ارتدادٍ قطّ — لأنّ EMA20 يتخلّف
    # عن سعرٍ يصعد باطّراد بنسبةٍ ثابتة، فيبقى القاعُ ملامساً له
    # كل شمعة. فكانت الشاشة تسمّي القمّة «ارتداداً».
    #
    # وأمسكه الفحص «والقمّة بلا ارتداد تُرفَض» — وكان محقّاً.
    #
    # فالقياس الآن من **قمّة النافذة**: كم نزل السعر عنها؟ وما لم
    # ينزل ``min_pullback_pct`` فلا ارتداد هناك مهما قارب المتوسّط.
    win = min(look, len(df) - 2)
    hi_win = high.iloc[-win:]
    peak_pos = int(hi_win.to_numpy().argmax())     # موضعه داخل النافذة
    peak_high = float(hi_win.iloc[peak_pos])
    bars_after_peak = win - 1 - peak_pos

    # ما بعد القمّة وحده هو الارتداد. والقمّة إن كانت آخر شمعة
    # فلم يبدأ ارتدادٌ بعد.
    after = low.iloc[-(bars_after_peak + 1):] if bars_after_peak > 0 else None
    pull_low = float(after.min()) if after is not None else float(low.iloc[-1])
    drop_pct = ((peak_high - pull_low) / peak_high * 100.0) if peak_high else 0.0
    dipped = bars_after_peak > 0 and drop_pct >= min_drop

    # واللمس يُسأل عن **قاع الارتداد** لا عن أيّ شمعة
    zone_used = None
    for z, name in ((st_line, "Supertrend"), (e, "EMA20")):
        if z and pull_low <= z * (1 + touch_pct / 100.0):
            zone_used, zone_val = name, z
            break
    else:
        zone_val = None

    # والإغلاق فوق المنطقة **التي لامسها** — لا فوق الاثنتين معاً.
    # اشتراطُ الأعلى منهما يرفض ارتداداً سليماً من الأدنى.
    above_zone = zone_val is not None and c > zone_val
    resumed = c > float(close.iloc[-2])

    # ═══ البنية: قاع الارتداد فوق القاع الذي سبق القمّة ═══
    #
    # النسخة الأولى قارنت «أدنى ١٢ شمعة» بـ«أدنى ٢٤ قبلها». وفي
    # صعودٍ مطّرد يكون الأقدم دائماً أدنى، فيسقط الفحص على كل
    # ارتدادٍ سليم. والمقصود: هل كسر الارتدادُ آخر قاعٍ **قبل**
    # القمّة؟ فذاك هو كسر البنية.
    before = low.iloc[-(win + look * 2):-(bars_after_peak + 1)] \
        if bars_after_peak > 0 and len(df) > win + look * 2 else None
    prior_low = float(before.min()) if before is not None and len(before) \
        else None
    structure_ok = prior_low is None or pull_low > prior_low

    out["checks"] = [
        {"name": f"ارتدّ عن قمّته ≥{min_drop:.0f}٪", "ok": bool(dipped)},
        {"name": "ولمس المنطقة", "ok": zone_used is not None},
        {"name": "وأغلق فوقها", "ok": bool(above_zone)},
        {"name": "واستأنف صعوده", "ok": bool(resumed)},
        {"name": "ولم يكسر القاع السابق", "ok": bool(structure_ok)},
    ]
    out["ok"] = all(x["ok"] for x in out["checks"])
    out["touched_bars_ago"] = bars_after_peak if dipped else None
    out["zone"] = zone_used
    out["drop_pct"] = round(drop_pct, 2)

    # ═══ الوقف تحت قاع الارتداد ═══
    #
    # وضعُه على المتوسّط بالضبط يجعله يُضرَب بأيّ اختراقٍ كاذب.
    # وتحت القاع: هناك يكون الرأي قد بطل فعلاً.
    if pull_low > 0:
        out["stop_hint"] = round(pull_low, 8)
        out["risk_pct"] = round((c - pull_low) / c * 100, 2) if c else None
    if not out["ok"]:
        out["reason"] = " · ".join(x["name"] for x in out["checks"]
                                   if not x["ok"])
    return out


def analyze(frames: dict, *, params: dict | None = None) -> dict:
    """الحكم الكامل لرمزٍ واحد. لا يرمي — يعيد ``ok`` وسبباً.

    ``frames`` يحمل ``1d`` و``4h``. والأسبوعيّ يُجمَّع هنا.
    """
    p = params or {}
    cfg = (p.get("topdown") or {})
    max_ext_w = float(cfg.get("max_ext_weekly_pct", 25.0))
    max_ext_d = float(cfg.get("max_ext_daily_pct", 12.0))

    d1_raw, h4 = frames.get("1d"), frames.get("4h")
    d1 = _closed(d1_raw)
    if d1 is None or len(d1) < MIN_DAILY:
        return {"ok": False, "stage": "daily", "reason": "شموع يومية غير كافية"}

    wk = _closed(to_weekly(d1_raw)) if d1_raw is not None else None
    if wk is None or len(wk) < MIN_WEEKLY:
        return {"ok": False, "stage": "weekly",
                "reason": f"شموع أسبوعية غير كافية "
                          f"({0 if wk is None else len(wk)}/{MIN_WEEKLY})"}

    # الأسبوعيّ بمتوسّطاتٍ أقصر: ٥٠ أسبوعاً ≈ سنة، و٢٠٠ تحتاج أربع
    w = _bias(wk, fast=10, slow=30)
    d = _bias(d1, fast=20, slow=50)

    ext_w = w.get("ext_pct")
    ext_d = d.get("ext_pct")
    extended = ((ext_w is not None and ext_w > max_ext_w)
                or (ext_d is not None and ext_d > max_ext_d))

    entry = _pullback_resume(h4, p)

    stages = [
        {"key": "weekly", "label": "الأسبوعيّ صاعد",
         "ok": w["bias"] == BIAS_UP},
        {"key": "daily", "label": "اليوميّ صاعد", "ok": d["bias"] == BIAS_UP},
        {"key": "not_extended", "label": "غير ممتدّ", "ok": not extended},
        {"key": "entry", "label": "ارتدادٌ ثمّ استئناف (4س)",
         "ok": bool(entry["ok"])},
    ]
    # ═══ أوّل مرحلةٍ سقطت ═══
    #
    # «لا يُطابق» بلا سبب تجعل الشاشة صندوقاً مغلقاً. وذكرُ أوّل
    # ما سقط يجعلها تعلّم: رمزٌ سقط عند «غير ممتدّ» يُراقَب،
    # ورمزٌ سقط عند «الأسبوعيّ» لا يُنظَر إليه أصلاً.
    failed = next((s for s in stages if not s["ok"]), None)

    return {
        "ok": failed is None,
        "stage": "ready" if failed is None else failed["key"],
        "reason": "" if failed is None else failed["label"],
        "stages": stages,
        "weekly": w,
        "daily": d,
        "entry": entry,
        "extended": bool(extended),
        "ext_weekly_pct": ext_w,
        "ext_daily_pct": ext_d,
        "weekly_bars": int(len(wk)),
    }


__all__ = ["analyze", "to_weekly", "WEEKLY_RULE",
           "BIAS_UP", "BIAS_FLAT", "BIAS_DOWN"]
