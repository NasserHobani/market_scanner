"""إعدادات المحرك. كل سوق يُعاير مستقلاً — لا تُوحَّد العتبات بين الأسواق."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Weights:
    obv: float = 1.0
    vwap: float = 1.0
    cmf: float = 1.2
    mfi: float = 1.0
    ad: float = 1.0
    spike: float = 1.3
    obv_macd: float = 1.2
    rsi: float = 0.7
    trend: float = 0.8
    delta: float = 1.4
    fib: float = 1.0
    div: float = 1.3

    def total(self) -> float:
        return sum(asdict(self).values())


@dataclass
class Params:
    obv_ma_len: int = 20
    cmf_len: int = 20
    # نافذة VWAP المتدحرج على الفريم اليومي فأعلى. عشرون
    # جلسة عرفٌ شائع، وهي قابلة للمعايرة بالقياس لا بالذوق.
    vwap_len: int = 20
    cmf_thresh: float = 0.05
    mfi_len: int = 14
    mfi_high: int = 60
    mfi_low: int = 40
    ad_smooth_len: int = 5
    rvol_len: int = 20
    rvol_mult: float = 1.5
    obv_fast: int = 12
    obv_slow: int = 26
    obv_signal: int = 9
    rsi_len: int = 14
    rsi_high: int = 55
    rsi_low: int = 45
    ema_fast: int = 50
    ema_slow: int = 200
    atr_len: int = 14
    delta_thresh: float = 0.15

    # الهيكل وفيبوناتشي
    zigzag_len: int = 10
    min_swing_atr: float = 1.0
    fib_tol_atr: float = 0.3

    # الدايفرجنس
    div_pivot_len: int = 5
    div_max_bars: int = 60

    # القناة السعرية
    ch_flat_atr: float = 0.5
    ch_tol_atr: float = 0.35
    ch_min_bars: int = 30
    ch_min_touches: int = 4
    ch_min_contain: float = 75.0

    # الفريم الأعلى
    htf_mode: str = "both"          # both | ema | price


@dataclass
class MarketConfig:
    name: str = "crypto"
    adapter: str = "binance"
    timeframes: list[str] = field(default_factory=lambda: ["4h"])
    symbols: list[str] = field(default_factory=list)
    universe: str = "auto"            # auto = كل أزواج USDT، list = القائمة أدناه
    min_quote_volume: float = 5_000_000
    top_n: int | None = None
    workers: int = 8
    candles: int = 1500
    strong_threshold: float = 60.0
    normal_threshold: float = 25.0
    max_candidates: int = 10
    min_confluence: int = 2
    min_votes: float = 1.2      # الحد الأدنى لمجموع أدلة التوصية
    account_size: float = 1000.0
    risk_pct: float = 1.0
    news_feeds: list[str] = field(default_factory=list)
    outlook_days: int = 7
    require_htf: bool = True

    # ═══ توقيت السوق ═══
    #
    # ``feed_delay_minutes`` مهلة بثّ الاشتراك. الاشتراك المجاني
    # يتأخّر خمس عشرة دقيقة، فلا يُعدّ ذلك تأخّراً في النظام. من
    # رقّى اشتراكه إلى بثّ لحظي فليجعلها صفراً.
    #
    # ``holidays`` أيّام الإغلاق الرسمية بصيغة YYYY-MM-DD. بدونها
    # تُحسَب الإجازة جلسةً مفتوحة — انزياحٌ بمقدار يوم واحد، لا
    # بمقدار أسبوع كما كان قبل وعي الجلسات.
    feed_delay_minutes: float | None = None
    holidays: list[str] = field(default_factory=list)

    # ═══ محوّل الاكتشاف منفصلاً عن محوّل الشموع ═══
    #
    # سؤالان مختلفان لا سؤال واحد: **من في السوق؟** و**ما شموع هذا
    # الرمز؟** وقد يجيب عنهما مصدران مختلفان.
    #
    # السوق السعودي مثالٌ حيّ: ``/companies/`` عند سهمك مجاني ويعطي
    # تاسي ونمو كاملين، بينما الشموع التاريخية تحتاج باقة Starter.
    # وياهو يعطي شموع ``NNNN.SR`` مجاناً ولا يكتشف شيئاً. فربطُ
    # السؤالين بمحوّل واحد كان يجبر على اختيار أحد النقصين.
    #
    # فارغاً: المحوّل نفسه يجيب عن السؤالين — وهو حال الكريبتو.
    universe_adapter: str = ""

    # إدارة الصفقة (تُستخدم في الاختبار التاريخي وفي خطة الصفقة)
    rr_ratio: float = 2.0
    min_rr: float = 1.5
    tp1_r: float = 1.0
    tp1_pct: int = 50
    trail_atr: float = 1.5
    weights: Weights = field(default_factory=Weights)
    params: Params = field(default_factory=Params)


def load_market(path: str | Path) -> MarketConfig:
    raw: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    weights = Weights(**raw.pop("weights", {}) or {})
    params = Params(**raw.pop("params", {}) or {})
    cfg = MarketConfig(weights=weights, params=params, **raw)

    # توقيت السوق يُطبَّق عند التحميل: الجلسات جدولٌ عام في
    # ``scanner.sessions``، وملف السوق يُعدّله. ولو تُرك التطبيق
    # لمن يستعمل النضارة لاختلف حكم مسارين على الرمز نفسه.
    if cfg.feed_delay_minutes is not None or cfg.holidays:
        try:
            from . import sessions

            sessions.configure(
                cfg.name,
                feed_delay_seconds=(None if cfg.feed_delay_minutes is None
                                    else int(float(cfg.feed_delay_minutes) * 60)),
                holidays=list(cfg.holidays) if cfg.holidays else None,
            )
        except Exception:  # noqa: BLE001
            pass
    return cfg
