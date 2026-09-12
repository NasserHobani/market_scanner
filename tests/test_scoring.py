import numpy as np
import pandas as pd
import pytest

from scanner.config import MarketConfig
from scanner.scoring import compute_components, decide, score_series, score_symbol


def make_df(trend: float, n: int = 400) -> pd.DataFrame:
    rng = np.random.default_rng(3)
    base = np.arange(n) * trend + 100
    noise = rng.normal(0, 0.3, n)
    close = base + noise
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + 0.5
    low = np.minimum(open_, close) - 0.5
    volume = rng.uniform(1000, 2000, n)
    idx = pd.date_range("2025-01-01", periods=n, freq="4h", tz="UTC")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=idx
    )


def test_components_are_ternary():
    cfg = MarketConfig()
    comps = compute_components(make_df(0.05), cfg)
    assert set(np.unique(comps.to_numpy())) <= {-1, 0, 1}


def test_score_within_bounds():
    cfg = MarketConfig()
    s = score_series(make_df(0.05), cfg).dropna()
    assert s.between(-100, 100).all()


def test_uptrend_scores_higher_than_downtrend():
    cfg = MarketConfig()
    up = score_series(make_df(0.08), cfg).iloc[-1]
    down = score_series(make_df(-0.08), cfg).iloc[-1]
    assert up > down


def test_decide_thresholds():
    cfg = MarketConfig(strong_threshold=60, normal_threshold=25)
    assert decide(70, cfg) == "شراء قوي"
    assert decide(30, cfg) == "شراء"
    assert decide(0, cfg) == "محايد"
    assert decide(-30, cfg) == "بيع"
    assert decide(-70, cfg) == "بيع قوي"


def test_score_symbol_shape():
    cfg = MarketConfig()
    r = score_symbol(make_df(0.05), "TESTUSDT", "4h", cfg)
    assert r.symbol == "TESTUSDT"
    assert -100 <= r.score <= 100
    row = r.to_row()
    assert "score" in row and "c_obv" in row
