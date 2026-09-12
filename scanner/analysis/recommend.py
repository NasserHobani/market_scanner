"""نظام التوصيات: شراء الآن، أو شراء لاحقاً عند مستوى محدد.

الفرق بين الحالتين ليس شكلياً:
  • «الآن» تعني أن كل الشروط مستوفاة على شمعة مغلقة، والدخول بسعر السوق.
  • «لاحقاً» تعني أن التحليل يدعم الشراء لكن الموقع غير مناسب — السعر بعيد
    عن مستوى دعم، أو ينقص تأكيد. فنعطيك أمراً معلّقاً بسعر محدد وشرط.

الحالة الثالثة، وهي الأكثر صدقاً وأقلّها شعبية: «لا توصية».
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..config import MarketConfig
from ..formatting import price as _fmt
from ..indicators.pine import atr
from ..indicators.structure import (
    build_structure, detect_channel, fib_confluence, fib_levels,
)
from . import candles as candle_mod
from . import elliott as elliott_mod
from . import patterns as pattern_mod
from . import price_action as pa_mod
from ..ml import runtime as ml_runtime

NOW = "now"
PENDING = "pending"
NONE = "none"


@dataclass
class Recommendation:
    action: str                     # now | pending | none
    side: str                       # buy | sell | —
    entry: float | None = None
    stop: float | None = None
    targets: list[float] = field(default_factory=list)
    rr: float | None = None
    trigger: str = ""               # شرط التفعيل للأوامر المعلّقة
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    confidence: float = 0.0
    analysis: dict = field(default_factory=dict)
    votes: float = 0.0
    breakdown: list[dict] = field(default_factory=list)
    grade: str = "—"                  # A ممتازة · B جيدة · C مقبولة
    invalidation: float | None = None  # المستوى الذي تسقط عنده التوصية
    valid_until: str = ""              # صلاحية زمنية
    vetoes: list[str] = field(default_factory=list)
    size: dict = field(default_factory=dict)

    @property
    def headline(self) -> str:
        if self.action == NOW:
            return "شراء الآن" if self.side == "buy" else "بيع الآن"
        if self.action == PENDING:
            return "شراء عند الارتداد" if self.side == "buy" else "بيع عند الرفض"
        return "لا توصية"

    def as_dict(self) -> dict:
        return {
            "action": self.action, "side": self.side, "headline": self.headline,
            "entry": self.entry, "stop": self.stop, "targets": self.targets,
            "rr": round(self.rr, 2) if self.rr else None,
            "trigger": self.trigger, "reasons": self.reasons,
            "warnings": self.warnings, "confidence": round(self.confidence, 2),
            "analysis": self.analysis,
            "votes": round(self.votes, 2), "breakdown": self.breakdown,
            "grade": self.grade, "invalidation": self.invalidation,
            "valid_until": self.valid_until, "vetoes": self.vetoes,
            "size": self.size,
        }


def build(df: pd.DataFrame, cfg: MarketConfig, score: float, htf: int,
          confluence: list[str]) -> Recommendation:
    p = cfg.params
    close = float(df["close"].iloc[-1])
    a = float(atr(df, p.atr_len).iloc[-1])
    if not np.isfinite(a) or a <= 0:
        return Recommendation(NONE, "—", warnings=["تعذّر حساب التذبذب"])

    structure = build_structure(df, p.zigzag_len, p.min_swing_atr, p.atr_len)
    candle = candle_mod.summarize(df, atr_len=p.atr_len)
    chart_patterns = pattern_mod.detect(structure, df, a)
    pattern_view = pattern_mod.summarize(chart_patterns)
    wave = elliott_mod.count(structure, close)
    action = pa_mod.analyze(df, structure, p.atr_len)
    channel = detect_channel(df, structure, a, flat_atr=p.ch_flat_atr,
                             tol_atr=p.ch_tol_atr, min_bars=p.ch_min_bars,
                             min_touches=p.ch_min_touches, min_contain=p.ch_min_contain)

    analysis = {
        "candles": candle["patterns"],
        "candle_score": candle["score"],
        "chart_patterns": pattern_view["patterns"][:3],
        "pattern_score": pattern_view["score"],
        "elliott": wave.as_dict() if wave else None,
        "price_action": action.as_dict(),
        "channel": None if channel is None else {
            "kind": channel.kind, "zone": channel.zone_at(len(df) - 1, close),
            "touches": channel.touches,
        },
    }

    reasons = list(confluence)
    warnings: list[str] = []

    # ── وزن الأدلة ──
    votes = 0.0
    breakdown: list[dict] = []

    def vote(label: str, value: float, detail: str = "") -> None:
        nonlocal votes
        votes += value
        breakdown.append({"label": label, "value": round(value, 2), "detail": detail})

    if score >= cfg.normal_threshold:
        vote("الدرجة الموزونة", 1.0, f"{score:.0f}")
        reasons.append(f"الدرجة {score:.0f}")
    elif score <= -cfg.normal_threshold:
        vote("الدرجة الموزونة", -1.0, f"{score:.0f}")
    else:
        vote("الدرجة الموزونة", 0.0, f"{score:.0f} — دون العتبة")

    # ``require_htf`` كان معرّفاً في الإعدادات ويحكم ``ready`` والاختبار
    # الخلفي القديم، بينما هذا المحرّك — الذي يُنتج الصفقات فعلاً —
    # يتجاهله ويصوّت ويعترض بلا شرط. والقياس على 230 صفقة أعطى هذا
    # العامل أسوأ توقّع بين الثمانية (‏−0.20R على 157 صفقة)، فوجب أن
    # يكون إطفاؤه ممكناً وأن يُقاس أثره.
    use_htf = bool(getattr(cfg, "require_htf", True))

    if not use_htf:
        vote("الفريم الأعلى", 0.0, "معطّل بالإعدادات")
    elif htf == 1:
        vote("الفريم الأعلى", 0.8, "صاعد")
    elif htf == -1:
        vote("الفريم الأعلى", -0.8, "هابط")
        warnings.append("الفريم الأعلى هابط")
    else:
        vote("الفريم الأعلى", 0.0, "مختلط")

    if candle["score"] == 1:
        vote("نماذج الشموع", 0.6, "، ".join(candle["bullish"][:2]))
        reasons.append("شمعة: " + "، ".join(candle["bullish"][:2]))
    elif candle["score"] == -1:
        vote("نماذج الشموع", -0.6, "، ".join(candle["bearish"][:2]))
        warnings.append("شمعة هابطة: " + "، ".join(candle["bearish"][:2]))
    else:
        vote("نماذج الشموع", 0.0, "لا شيء مؤثر")

    if pattern_view["score"] == 1:
        vote("النموذج السعري", 0.7, pattern_view["best"]["arabic"])
        reasons.append("نموذج: " + pattern_view["best"]["arabic"])
    elif pattern_view["score"] == -1:
        vote("النموذج السعري", -0.7, pattern_view["best"]["arabic"])
        warnings.append("نموذج هابط: " + pattern_view["best"]["arabic"])
    else:
        vote("النموذج السعري", 0.0, "لا نموذج واضح")

    if wave is not None:
        if wave.direction == 1 and wave.current_wave in (3, 5):
            vote("موجات إليوت", 0.5, wave.label)
            reasons.append(f"إليوت: {wave.label}")
        elif wave.direction == 1 and wave.current_wave == 0:
            vote("موجات إليوت", -0.3, "تصحيح بعد دافعة صاعدة")
            warnings.append("إليوت: تصحيح بعد دافعة صاعدة")
        elif wave.direction == -1 and wave.current_wave in (3, 5):
            vote("موجات إليوت", -0.5, wave.label)
            warnings.append(f"إليوت: {wave.label}")
        else:
            vote("موجات إليوت", 0.0, wave.label)
    else:
        vote("موجات إليوت", 0.0, "لا عدّ صالح")

    if confluence:
        vote("عناصر الالتقاء", 0.4 * len(confluence), " · ".join(confluence))
    else:
        vote("عناصر الالتقاء", 0.0, "لا شيء")

    # حركة السعر بوزن مرتفع: هي أقرب المدارس لقراءة نية السوق
    if action.score == 1:
        vote("حركة السعر", 1.0, " · ".join(action.notes[:2]) or action.trend)
        reasons.extend(action.notes[:2])
    elif action.score == -1:
        vote("حركة السعر", -1.0, " · ".join(action.notes[:2]) or action.trend)
        warnings.extend(action.notes[:2])
    else:
        vote("حركة السعر", 0.0, f"هيكل {action.trend}")

    # اصطياد السيولة السفلي الحديث: أقوى إشارة انعكاس في هذه المدرسة
    fresh_sweep = [x for x in action.sweeps
                   if x["direction"] == 1 and x["index"] >= len(df) - 10]
    if fresh_sweep:
        vote("اصطياد سيولة سفلية", 0.6, f"عند {fresh_sweep[-1]['level']:,.6g}")
        reasons.append("اصطياد سيولة سفلية حديث")

    # مصوّت ML اختياري: لا يعمل إلا إذا اجتاز بوابة OOS في ملف النموذج.
    if bool(getattr(cfg, "ml_vote_enabled", False)):
        ml = ml_runtime.vote(score, htf, confluence, action.score)
        if ml is None:
            vote("تصويت النموذج", 0.0, "غير متاح أو لم يجتز البوابة")
        else:
            prob, w = ml
            vote("تصويت النموذج", w, f"احتمال الربح {prob:.2f}")

    # ── مستويات الدخول ──
    levels = fib_levels(structure.structure_high, structure.structure_low)
    tol = a * p.fib_tol_atr
    at_level, ratio = fib_confluence(close, levels, tol)

    swing_low = structure.structure_low
    # ── النقض القاطع ──
    # المجموع وحده يخدع: درجة عالية جداً قد تغطّي على تناقض جوهري.
    # هذه الحالات تمنع التوصية مهما بلغ المجموع.
    vetoes: list[str] = []
    if use_htf and htf == -1:
        vetoes.append("الفريم الأعلى هابط — لا شراء ضد التيار الأكبر")
    if action.score == -1 and pattern_view["score"] == -1:
        vetoes.append("حركة السعر والنموذج كلاهما هابط")
    if wave is not None and wave.direction == -1 and wave.current_wave == 3:
        vetoes.append("الموجة الثالثة الهابطة — أعنف موجات البيع")
    if candle["score"] == -1 and action.score == -1:
        vetoes.append("شمعة هابطة داخل هيكل هابط")

    confidence = float(min(1.0, max(0.0, votes / 4.0)))
    min_votes = float(getattr(cfg, "min_votes", 1.2))

    if votes >= min_votes * 1.6 and not vetoes:
        grade = "A"
    elif votes >= min_votes * 1.2 and len(warnings) <= 1:
        grade = "B"
    else:
        grade = "C"

    bars_left = _bars_to_close(df)
    common = {"confidence": confidence, "analysis": analysis,
              "votes": votes, "breakdown": breakdown, "vetoes": vetoes,
              "grade": grade if votes >= min_votes else "—",
              "valid_until": bars_left}

    if vetoes:
        warnings.extend(vetoes)
        return Recommendation(NONE, "—", reasons=reasons, warnings=warnings, **common)

    # ── القرار ──
    if votes < min_votes:
        warnings.append(f"مجموع الأدلة {votes:.1f} دون الحد {min_votes}")
        return Recommendation(NONE, "—", reasons=reasons, warnings=warnings, **common)

    # مسار «شراء الآن» كان يشترط فريماً أعلى صاعداً؛ إطفاء الفلتر يجب
    # أن يرفع الشرط وإلا بقي معطّلاً نصف تعطيل
    if at_level and candle["score"] == 1 and (htf == 1 or not use_htf):
        entry = close
        stop = min(swing_low, entry - a * 1.5) - a * 0.25
        risk = entry - stop
        if risk <= 0:
            return Recommendation(NONE, "—", warnings=["الوقف غير منطقي"], **common)
        targets = _targets(entry, risk, structure, chart_patterns, wave)
        rr = (targets[0] - entry) / risk if targets else None
        if rr is None or rr < cfg.min_rr:
            warnings.append(f"العائد/المخاطرة {rr:.2f} دون الحد" if rr else "لا هدف واضح")
            return Recommendation(NONE, "—", reasons=reasons, warnings=warnings, **common)
        reasons.append(f"السعر عند فيبو {ratio:.3f}".rstrip("0").rstrip("."))
        return Recommendation(
            NOW, "buy", entry, stop, targets, rr, "", reasons, warnings,
            invalidation=stop, size=_position(cfg, entry, stop), **common)

    # التحليل يدعم الشراء لكن الموقع غير مناسب → أمر معلّق.
    # نجرّب كل الدعوم المرشّحة لا الأقرب وحده: الأقرب قد يعطي عائداً
    # ضعيفاً فتُرفض التوصية كلها، بينما دعم أعمق قليلاً يعطي صفقة سليمة.
    candidates: list[tuple[float, str]] = []
    for lvl in levels.values():
        if lvl < close:
            candidates.append((float(lvl), "فيبوناتشي"))
    if channel is not None:
        low_line, _ = channel.bounds_at(len(df) - 1)
        if low_line < close:
            candidates.append((float(low_line), "قاع القناة"))
    for zone in action.zones:
        if zone.kind in ("demand", "fvg_bull") and zone.top < close:
            candidates.append((float(zone.top), zone.arabic))
    for lvl in action.equal_levels:
        if lvl["direction"] == 1 and lvl["price"] < close:
            candidates.append((float(lvl["price"]), lvl["kind"]))
    if not np.isnan(swing_low) and swing_low < close:
        candidates.append((float(swing_low), "قاع هيكلي"))

    if not candidates:
        warnings.append("لا يوجد دعم واضح تحت السعر")
        return Recommendation(NONE, "—", reasons=reasons, warnings=warnings, **common)

    # الأقرب أولاً — الدخول البعيد قد لا يتحقق أصلاً
    candidates.sort(key=lambda c: -c[0])
    rejected: list[str] = []
    best = None

    for level, source in candidates:
        distance = (close - level) / close * 100
        if distance > 12:
            rejected.append(f"{source}: بعيد {distance:.1f}%")
            continue
        stop_c = min(swing_low, level - a * 1.2) - a * 0.25
        risk_c = level - stop_c
        if risk_c <= 0:
            continue
        targets_c = _targets(level, risk_c, structure, chart_patterns, wave)
        if not targets_c:
            continue
        rr_c = (targets_c[0] - level) / risk_c
        if rr_c < cfg.min_rr:
            rejected.append(f"{source}: عائد {rr_c:.2f}")
            continue
        best = (level, stop_c, targets_c, rr_c, source, distance)
        break

    if best is None:
        warnings.append("كل الدعوم المرشّحة عائدها دون الحد: " + " · ".join(rejected[:3]))
        return Recommendation(NONE, "—", reasons=reasons, warnings=warnings, **common)

    entry, stop, targets, rr, source, distance = best
    reasons.append(f"الدخول عند {source}")
    trigger = (f"انتظر نزول السعر إلى {_fmt(entry)} "
               f"(أدنى بـ {distance:.1f}%) مع شمعة انعكاس صاعدة")

    return Recommendation(
        PENDING, "buy", entry, stop, targets, rr, trigger, reasons, warnings,
        invalidation=stop, size=_position(cfg, entry, stop), **common)

def _bars_to_close(df: pd.DataFrame) -> str:
    """صلاحية التوصية: تُراجَع عند إغلاق الشمعة القادمة."""
    if len(df) < 2:
        return ""
    step = df.index[-1] - df.index[-2]
    return (df.index[-1] + step).strftime("%Y-%m-%d %H:%M UTC")


def _position(cfg: MarketConfig, entry: float, stop: float) -> dict:
    """حجم المركز من رأس المال ونسبة المخاطرة."""
    capital = float(getattr(cfg, "account_size", 1000.0))
    risk_pct = float(getattr(cfg, "risk_pct", 1.0))
    risk_per_unit = entry - stop
    if risk_per_unit <= 0:
        return {}
    amount = capital * risk_pct / 100.0
    qty = amount / risk_per_unit
    return {"capital": capital, "risk_pct": risk_pct,
            "risk_amount": round(amount, 2), "qty": qty,
            "value": round(qty * entry, 2)}


def _targets(entry: float, risk: float, structure, chart_patterns, wave) -> list[float]:
    """الأهداف من مصادر حقيقية أولاً، ثم مضاعفات المخاطرة."""
    out: list[float] = []

    for pat in chart_patterns:
        if pat.direction == 1 and pat.target and pat.target > entry:
            out.append(float(pat.target))
            break

    if wave is not None and wave.direction == 1 and wave.next_target \
            and wave.next_target > entry:
        out.append(float(wave.next_target))

    if structure.structure_high > entry:
        out.append(float(structure.structure_high))

    out.extend([entry + risk * 2, entry + risk * 3])
    out = sorted({round(v, 10) for v in out if v > entry})
    return out[:3]
