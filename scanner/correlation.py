# -*- coding: utf-8 -*-
"""الارتباط بين الرموز — واختيار صفقات متزامنة مستقلّة فعلاً.

═══ ما قِيس ═══

على 352 رمزاً على فريم 1h، ارتباط العائد بعائد البتكوين:

    المئين 25 : +0.26      42٪ فوق 0.50
    الوسيط    : +0.46      6٪  فوق 0.70
    المئين 75 : +0.58      31٪ تحت 0.30

والكبار متطابقون تقريباً: ETH ‎+0.89‎ · SOL ‎+0.84‎ · XRP ‎+0.84‎ ·
LINK ‎+0.85‎، وبيتا بين 1.04 و1.24 — أي أنها تتحرّك مع البتكوين
وأشدّ منه.

═══ لماذا يهمّ ═══

عدد الرهانات المستقلّة فعلياً حين تفتح ``n`` صفقة بارتباط متوسط ``ρ``:

    n_eff = n ÷ [1 + (n−1)·ρ]

وعند ρ = 0.46:

    3 صفقات  ⇒ 1.56 رهاناً · مخاطرة ×1.39 من المتوقّع
    10 صفقات ⇒ 1.95 رهاناً · مخاطرة ×2.27
    20 صفقة  ⇒ 2.05 رهاناً · مخاطرة ×3.12

أي أن الصفقة الحادية عشرة لا تضيف تنويعاً — تضيف حجماً. ومن يظنّ
أنه يخاطر بـ ‎1R‎ عشرين مرة، يخاطر في الحقيقة بما يقارب ‎6R‎ دفعة
واحدة على حركة واحدة.

وفي سجلّ المستخدم: الصفقات المفتوحة في اللحظة نفسها تتّفق في نتيجتها
**59٪** من الوقت (‏50٪ يعني استقلالاً تامّاً).

═══ لماذا الاختيار بالارتباط أفضل من عدّ ═══

الحدّ العددي يعامل رمزين ارتباطهما 0.9 كرمزين ارتباطهما 0.05. والأول
صفقة واحدة مكرّرة، والثاني صفقتان حقيقيتان. فالاختيار هنا يبني
مجموعة يبقى الارتباط داخلها تحت عتبة معلنة — فيتّسع العدد حين تكون
الفرص مستقلّة، ويضيق حين تكون نسخاً.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# قِيس أن الوسيط 0.46، فالعتبة تحته قليلاً: تسمح بالمستقلّ نسبياً
# وتمنع النسخ. رقم معلن قابل للضبط لا ثابت مقدّس.
MAX_PAIR_CORR = 0.55
MIN_BARS = 200          # دونها الارتباط ضجيج لا قياس


def returns(df: pd.DataFrame) -> pd.Series | None:
    """عوائد الإغلاق بفهرس واعٍ بالمنطقة — أو ``None`` إن قصُرت."""
    if df is None or len(df) < MIN_BARS or "close" not in df.columns:
        return None
    idx = df.index
    if getattr(idx, "tz", None) is None:
        try:
            idx = idx.tz_localize("UTC")
        except (TypeError, AttributeError):
            return None
    s = pd.Series(df["close"].to_numpy(dtype="float64"), index=idx)
    return s.pct_change().dropna()


def pair_corr(a: pd.Series | None, b: pd.Series | None) -> float | None:
    """ارتباط سلسلتين على الفترة المشتركة وحدها.

    ``join="inner"`` ضروري: رمزان بتاريخين مختلفين يعطيان ارتباطاً
    زائفاً لو حُوذي أحدهما بأصفار. والمشترك القصير يُرفض بـ ``None``
    بدل رقم لا يُعتمد عليه.
    """
    if a is None or b is None:
        return None
    j = pd.concat([a, b], axis=1, join="inner").dropna()
    if len(j) < MIN_BARS:
        return None
    v = j.iloc[:, 0].corr(j.iloc[:, 1])
    return None if pd.isna(v) else float(v)


def effective_bets(n: int, rho: float) -> float:
    """عدد الرهانات المستقلّة المكافئ لـ ``n`` صفقة بارتباط ``rho``."""
    if n <= 0:
        return 0.0
    rho = max(-0.99, min(0.99, float(rho)))
    denom = 1.0 + (n - 1) * rho
    return n / denom if denom > 0 else float(n)


def risk_multiple(n: int, rho: float) -> float:
    """كم تتضخّم المخاطرة الفعلية مقارنةً بافتراض الاستقلال."""
    if n <= 0:
        return 0.0
    rho = max(-0.99, min(0.99, float(rho)))
    return float(np.sqrt(max(0.0, 1.0 + (n - 1) * rho)))


def select_uncorrelated(candidates: list, series: dict, *,
                        max_pair: float = MAX_PAIR_CORR,
                        limit: int | None = None) -> tuple[list, list]:
    """يختار مجموعة يبقى الارتباط بين أفرادها تحت ``max_pair``.

    ``candidates`` مرتّبة بالأفضلية مسبقاً — الأول يُقبل دائماً، وكل
    تالٍ يُقبل إن لم يرتبط بأيٍّ من المقبولين فوق العتبة. خوارزمية
    جشِعة لا مثلى، وهذا مقصود: المثلى تحتاج حلّ مسألة تجميع كاملة عند
    كل مسح، والجشِعة تحفظ ترتيب الجودة وهو ما نريد.

    الرمز الذي **لا يُعرف** ارتباطه يُقبل: تاريخه قصير أو غائب، ورفضه
    عقوبة على نقص بيانات لا على تشابه. يعيد (المقبول، المرفوض مع سببه).
    """
    kept: list = []
    kept_keys: list[str] = []
    dropped: list[tuple] = []

    for item in candidates:
        key = _key(item)
        me = series.get(key)
        worst = 0.0
        clash = ""
        for other in kept_keys:
            c = pair_corr(me, series.get(other))
            if c is not None and abs(c) > abs(worst):
                worst, clash = c, other
        if clash and abs(worst) > max_pair:
            dropped.append((item, clash, worst))
            continue
        kept.append(item)
        kept_keys.append(key)
        if limit and len(kept) >= limit:
            break
    return kept, dropped


def _key(item) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, (tuple, list)) and item:
        return _key(item[0])
    for attr in ("symbol", "sym"):
        v = getattr(item, attr, None)
        if v:
            return str(v)
    if isinstance(item, dict):
        return str(item.get("symbol") or item.get("sym") or "")
    return str(item)


def average_corr(keys: list[str], series: dict) -> float | None:
    """متوسط الارتباط الزوجي داخل مجموعة — لعرضه لا لاتخاذ قرار."""
    vals = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            c = pair_corr(series.get(keys[i]), series.get(keys[j]))
            if c is not None:
                vals.append(c)
    return float(np.mean(vals)) if vals else None
