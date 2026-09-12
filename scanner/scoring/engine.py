"""محرك التسجيل — نفس منطق مؤشر VDM، منقولاً إلى Python.

كل مكوّن يعطي -1 أو 0 أو +1، ثم يُجمع بأوزانه ويُطبّع إلى نطاق -100..+100.
المحرك لا يعرف من أي سوق جاءت البيانات — يستقبل DataFrame موحّداً فقط.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..config import MarketConfig
from ..indicators import pine, volume as vol
from ..indicators import volume_profile as vprof
from ..indicators.htf import htf_bias
from ..indicators.structure import (
    build_structure, detect_channel, detect_divergence, fib_confluence, fib_levels,
)


@dataclass
class ScoreResult:
    symbol: str
    timeframe: str
    timestamp: pd.Timestamp
    close: float
    score: float
    decision: str
    components: dict[str, int] = field(default_factory=dict)
    context: dict = field(default_factory=dict)
    confluence: list[str] = field(default_factory=list)
    htf: int = 0
    ready: bool = False
    blocker: str = ""
    recommendation: dict = field(default_factory=dict)

    def to_row(self) -> dict:
        row = {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp,
            "close": self.close,
            "score": round(self.score, 1),
            "decision": self.decision,
            "confluence": len(self.confluence),
            "action": self.recommendation.get("action", "none"),
            "headline": self.recommendation.get("headline", "—"),
            "entry": self.recommendation.get("entry"),
            "stop": self.recommendation.get("stop"),
            "rr": self.recommendation.get("rr"),
            "reasons": " · ".join(self.confluence) if self.confluence else "—",
            "htf": self.htf,
            "ready": self.ready,
            "blocker": self.blocker,
        }
        row.update({f"c_{k}": v for k, v in self.components.items()})
        row.update({k: v for k, v in self.context.items()})
        return row


def _sign(condition_up: pd.Series, condition_down: pd.Series) -> pd.Series:
    out = pd.Series(0, index=condition_up.index, dtype="int64")
    out[condition_up.fillna(False)] = 1
    out[condition_down.fillna(False)] = -1
    return out


def compute_components(df: pd.DataFrame, cfg: MarketConfig) -> pd.DataFrame:
    p = cfg.params
    out = pd.DataFrame(index=df.index)

    obv_series = vol.obv(df)
    obv_ma = pine.sma(obv_series, p.obv_ma_len)
    out["obv"] = _sign(obv_series > obv_ma, obv_series < obv_ma)

    # ═══ VWAP الذي له معنى على هذا الفريم ═══
    #
    # كان ``session_vwap`` وحده — والجلسة فيه يومٌ تقويميّ. وهذا
    # صحيح داخل اليوم، وينهار على الفريم اليومي: كل شمعة جلسةٌ
    # وحدها، فيصير VWAP مساوياً لـ ``(H+L+C)/3`` لتلك الشمعة.
    #
    # القياس على بياناتك:
    #
    #     crypto 1d   VWAP == (H+L+C)/3 في 100.0٪ من الشموع
    #     saudi  1d   VWAP == (H+L+C)/3 في  95.6٪ من الشموع
    #     crypto 15m  VWAP == (H+L+C)/3 في   1.2٪ من الشموع
    #
    # فالمكوّن يحمل وزناً كاملاً ويقيس «أين أغلق داخل مداه» لا «أين
    # السعر من متوسّط ما دفعه المتداولون». والسوق السعودي كلّه
    # يُمسَح على ``1d``.
    #
    # ولا يُحذف بل يُصلَح: القياس على ١١٥ صفقة محسومة قال إنّ
    # ``above_vwap_20`` أقوى ما فصل الرابح عن الخاسر (d=+0.65،
    # ‏56٪ فوزاً فوقه مقابل 43٪ أساساً) — أي أن VWAP **الصحيح**
    # يستحقّ وزنه، والمعطوب هو الذي لم يكن يستحقّه.
    vwap = vprof.smart_vwap(df, p.vwap_len)
    out["vwap"] = _sign(df["close"] > vwap, df["close"] < vwap)

    cmf_series = vol.cmf(df, p.cmf_len)
    out["cmf"] = _sign(cmf_series > p.cmf_thresh, cmf_series < -p.cmf_thresh)

    mfi_series = vol.mfi(df, p.mfi_len)
    out["mfi"] = _sign(mfi_series > p.mfi_high, mfi_series < p.mfi_low)

    ad = vol.ad_line(df)
    ad_smooth = pine.sma(ad, p.ad_smooth_len)
    out["ad"] = _sign(ad > ad_smooth, ad < ad_smooth)

    rv = vol.rvol(df, p.rvol_len)
    spike = rv > p.rvol_mult
    direction = _sign(df["close"] > df["open"], df["close"] < df["open"])
    out["spike"] = (direction * spike.fillna(False).astype(int)).astype("int64")

    hist = vol.obv_macd(obv_series, p.obv_fast, p.obv_slow, p.obv_signal)
    out["obv_macd"] = _sign(hist > 0, hist < 0)

    rsi_series = pine.rsi(df["close"], p.rsi_len)
    out["rsi"] = _sign(rsi_series > p.rsi_high, rsi_series < p.rsi_low)

    ema_f = pine.ema(df["close"], p.ema_fast)
    ema_s = pine.ema(df["close"], p.ema_slow)
    out["trend"] = _sign(ema_f > ema_s, ema_f < ema_s)

    delta = vol.delta_approx(df)
    out["delta"] = _sign(delta > p.delta_thresh, delta < -p.delta_thresh)

    # فيبوناتشي والدايفرجنس يُحسبان على آخر شمعة فقط (يعتمدان على الهيكل)
    # لذا يُملآن في score_symbol؛ هنا نتركهما صفراً للسلاسل التاريخية
    out["fib"] = 0
    out["div"] = 0

    out.attrs["raw"] = {
        "rsi": rsi_series,
        "cmf": cmf_series,
        "mfi": mfi_series,
        "rvol": rv,
        "atr": pine.atr(df, p.atr_len),
        "delta": delta,
    }
    return out


def score_series(df: pd.DataFrame, cfg: MarketConfig) -> pd.Series:
    comps = compute_components(df, cfg)
    w = cfg.weights
    total = w.total()
    if total == 0:
        return pd.Series(0.0, index=df.index)
    weighted = (
        comps["obv"] * w.obv
        + comps["vwap"] * w.vwap
        + comps["cmf"] * w.cmf
        + comps["mfi"] * w.mfi
        + comps["ad"] * w.ad
        + comps["spike"] * w.spike
        + comps["obv_macd"] * w.obv_macd
        + comps["rsi"] * w.rsi
        + comps["trend"] * w.trend
        + comps["delta"] * w.delta
        + comps["fib"] * w.fib
        + comps["div"] * w.div
    )
    return weighted / total * 100.0


def decide(score: float, cfg: MarketConfig) -> str:
    if score >= cfg.strong_threshold:
        return "شراء قوي"
    if score >= cfg.normal_threshold:
        return "شراء"
    if score <= -cfg.strong_threshold:
        return "بيع قوي"
    if score <= -cfg.normal_threshold:
        return "بيع"
    return "محايد"


def score_symbol(df: pd.DataFrame, symbol: str, timeframe: str, cfg: MarketConfig) -> ScoreResult:
    p = cfg.params
    comps = compute_components(df, cfg)
    raw = comps.attrs["raw"]
    last_i = len(df) - 1
    close = float(df["close"].iloc[-1])
    atr_val = float(raw["atr"].iloc[-1])
    atr_series = raw["atr"].dropna()
    atr_percentile = None
    if len(atr_series) >= 20 and not np.isnan(atr_val):
        # Point-in-time: rank of current ATR among bars available at decision only
        window = atr_series.iloc[-min(len(atr_series), 100):]
        atr_percentile = float((window <= atr_val).sum() / len(window))

    # ---------- الهيكل: فيبوناتشي من آخر موجة حقيقية، لا من نافذة عامة ----------
    reasons: list[str] = []
    fib_score = 0
    fib_ratio = None
    channel_kind = "—"
    channel_zone = "—"

    structure = build_structure(df, p.zigzag_len, p.min_swing_atr, p.atr_len)
    trend_now = int(comps["trend"].iloc[-1])

    if structure.structure_high > structure.structure_low and not np.isnan(atr_val):
        levels = fib_levels(structure.structure_high, structure.structure_low)
        hit, fib_ratio = fib_confluence(close, levels, atr_val * p.fib_tol_atr)
        if hit:
            fib_score = trend_now
            reasons.append(f"فيبو {fib_ratio:.3f}".rstrip("0").rstrip("."))

        eq = (structure.structure_high + structure.structure_low) / 2
        if close < eq:
            reasons.append("خصم")

        channel = detect_channel(
            df, structure, atr_val,
            flat_atr=p.ch_flat_atr, tol_atr=p.ch_tol_atr, min_bars=p.ch_min_bars,
            min_touches=p.ch_min_touches, min_contain=p.ch_min_contain,
        )
        if channel is not None:
            channel_kind = channel.kind
            channel_zone = channel.zone_at(last_i, close)
            if channel_zone == "buy" and channel.kind in ("rising", "flat"):
                reasons.append("قاع القناة")

    # ---------- الدايفرجنس ----------
    bull_div, bear_div = detect_divergence(
        df,
        {"obv": vol.obv(df), "rsi": raw["rsi"]},
        pivot_len=p.div_pivot_len, max_bars=p.div_max_bars,
    )
    div_score = 1 if (bull_div and not bear_div) else -1 if (bear_div and not bull_div) else 0
    if bull_div:
        reasons.append("دايفرجنس صاعد")

    # ---------- إعادة حساب الدرجة بعد إدراج فيبو والدايفرجنس ----------
    comps.loc[df.index[-1], "fib"] = fib_score
    comps.loc[df.index[-1], "div"] = div_score
    w = cfg.weights
    total = w.total()
    last_comps = {k: int(comps[k].iloc[-1]) for k in comps.columns}
    weighted = (
        last_comps["obv"] * w.obv + last_comps["vwap"] * w.vwap + last_comps["cmf"] * w.cmf
        + last_comps["mfi"] * w.mfi + last_comps["ad"] * w.ad + last_comps["spike"] * w.spike
        + last_comps["obv_macd"] * w.obv_macd + last_comps["rsi"] * w.rsi
        + last_comps["trend"] * w.trend + last_comps["delta"] * w.delta
        + last_comps["fib"] * w.fib + last_comps["div"] * w.div
    )
    score = 0.0 if total == 0 else weighted / total * 100.0

    # ---------- فلتر الفريم الأعلى وجاهزية الشراء ----------
    htf, htf_text = htf_bias(df, timeframe, p.ema_fast, p.ema_slow, p.htf_mode)

    blocker = ""
    if cfg.require_htf and htf != 1:
        blocker = "ضد الفريم الأعلى"
    elif len(reasons) < cfg.min_confluence:
        blocker = f"التقاء ناقص ({len(reasons)}/{cfg.min_confluence})"
    elif score < cfg.normal_threshold:
        blocker = "الدرجة دون العتبة"
    ready = blocker == ""

    return ScoreResult(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=df.index[-1],
        close=close,
        score=float(score),
        decision=decide(float(score), cfg),
        components=last_comps,
        context={
            "rsi": round(float(raw["rsi"].iloc[-1]), 1),
            "rvol": round(float(raw["rvol"].iloc[-1]), 2),
            "atr_pct": round(atr_val / close * 100.0, 2) if close else float("nan"),
            "atr_percentile": None if atr_percentile is None else round(atr_percentile, 4),
            "delta": round(float(raw["delta"].iloc[-1]), 2),
            "htf_text": htf_text,
            "channel": channel_kind,
            "ch_zone": channel_zone,
        },
        confluence=reasons,
        htf=htf,
        ready=ready,
        blocker=blocker,
    )


def score_with_recommendation(df: pd.DataFrame, symbol: str, timeframe: str,
                              cfg: MarketConfig) -> ScoreResult:
    """التسجيل + التوصية الكاملة (شموع، نماذج، إليوت).

    مفصولة عن score_symbol لأنها أثقل: الماسح السريع لمئات الرموز لا
    يحتاجها، وصفحة الرمز الواحد تحتاجها.
    """
    from ..analysis.recommend import build as _build

    result = score_symbol(df, symbol, timeframe, cfg)
    try:
        reco = _build(df, cfg, result.score, result.htf, result.confluence)
        result.recommendation = reco.as_dict()
    except Exception as exc:  # noqa: BLE001
        result.recommendation = {"action": "none", "headline": "تعذّر التحليل",
                                 "error": str(exc)[:200]}
    return result
