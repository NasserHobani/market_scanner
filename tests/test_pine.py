"""اختبارات المطابقة مع سلوك Pine.

الفكرة: التأكد أن RSI و ATR يستخدمان تنعيم RMA لا المتوسط البسيط،
لأن هذا بالضبط ما تخطئ فيه أغلب المكتبات الجاهزة.
"""
import numpy as np
import pandas as pd
import pytest

from scanner.indicators import pine, volume as vol


@pytest.fixture
def ohlcv():
    rng = np.random.default_rng(7)
    n = 300
    steps = rng.normal(0, 1, n).cumsum() + 100
    high = steps + rng.uniform(0.2, 1.2, n)
    low = steps - rng.uniform(0.2, 1.2, n)
    close = steps + rng.uniform(-0.4, 0.4, n)
    open_ = np.r_[close[0], close[:-1]]
    volume = rng.uniform(800, 4000, n)
    idx = pd.date_range("2025-01-01", periods=n, freq="4h", tz="UTC")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=idx
    )


def test_rma_matches_wilder_recurrence(ohlcv):
    length = 14
    src = ohlcv["close"]
    out = pine.rma(src, length)
    seed = src.iloc[:length].mean()
    assert out.iloc[length - 1] == pytest.approx(seed)
    expected = (1 / length) * src.iloc[length] + (1 - 1 / length) * seed
    assert out.iloc[length] == pytest.approx(expected)


def test_ema_seeds_with_sma(ohlcv):
    length = 20
    out = pine.ema(ohlcv["close"], length)
    assert out.iloc[: length - 1].isna().all()
    assert out.iloc[length - 1] == pytest.approx(ohlcv["close"].iloc[:length].mean())


def test_rsi_bounds_and_not_sma_based(ohlcv):
    r = pine.rsi(ohlcv["close"], 14).dropna()
    assert ((r >= 0) & (r <= 100)).all()
    # RSI بتنعيم RMA يختلف عن نسخة المتوسط البسيط — نتأكد أنهما ليسا متطابقين
    delta = ohlcv["close"].diff()
    sma_rsi = 100 - 100 / (
        1 + pine.sma(delta.clip(lower=0), 14) / pine.sma((-delta).clip(lower=0), 14)
    )
    assert not np.allclose(r.iloc[-50:], sma_rsi.dropna().iloc[-50:])


def test_atr_is_rma_of_true_range(ohlcv):
    a = pine.atr(ohlcv, 14)
    manual = pine.rma(pine.true_range(ohlcv), 14)
    pd.testing.assert_series_equal(a, manual)


def test_obv_direction(ohlcv):
    o = vol.obv(ohlcv)
    assert len(o) == len(ohlcv)
    assert o.notna().all()


def test_vwap_resets_daily(ohlcv):
    v = vol.session_vwap(ohlcv)
    first_of_day = ohlcv.index.floor("D").to_series().diff().ne(pd.Timedelta(0))
    tp = (ohlcv["high"] + ohlcv["low"] + ohlcv["close"]) / 3
    # أول شمعة في اليوم: VWAP يساوي السعر النموذجي نفسه
    idx = np.where(first_of_day.to_numpy())[0][1]
    assert v.iloc[idx] == pytest.approx(tp.iloc[idx])


def test_pivots_detect_local_extremes():
    s = pd.Series([1, 2, 3, 9, 3, 2, 1, 0, 1, 2], dtype="float64")
    ph = pine.pivot_high(s, 2, 2)
    assert ph.notna().sum() == 1 and ph.dropna().iloc[0] == 9
    pl = pine.pivot_low(s, 2, 2)
    assert pl.dropna().iloc[0] == 0


def test_mfi_bounds(ohlcv):
    m = vol.mfi(ohlcv, 14).dropna()
    assert ((m >= 0) & (m <= 100)).all()
