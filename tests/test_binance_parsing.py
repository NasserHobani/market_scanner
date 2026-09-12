"""اختبار التحليل على حمولة حقيقية من Binance.

الصفوف أدناه منسوخة حرفياً من استجابة
data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=4h
حتى يبقى الاختبار صالحاً بلا اتصال بالشبكة.
"""
import pandas as pd

from scanner.adapters.binance import BinanceAdapter

REAL_PAYLOAD = [
    [1786075200000, "64289.99000000", "64463.75000000", "64166.00000000", "64319.84000000",
     "1378.76331000", 1786089599999, "88693539.60203640", 221813,
     "649.87887000", "41809418.54644790", "0"],
    [1786089600000, "64319.84000000", "65213.33000000", "64304.22000000", "65029.98000000",
     "2365.76634000", 1786103999999, "153395685.62826650", 319893,
     "1085.53286000", "70399708.42939560", "0"],
    [1786104000000, "65029.98000000", "65280.60000000", "65029.97000000", "65104.00000000",
     "349.18888000", 1786118399999, "22751995.92951020", 57985,
     "177.76851000", "11580422.26191300", "0"],
]


def test_parses_real_payload():
    df = BinanceAdapter.to_frame(REAL_PAYLOAD, drop_unclosed=False)
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert len(df) == 3
    assert str(df.index.tz) == "UTC"
    assert df.index.is_monotonic_increasing
    assert df["close"].iloc[-1] == 65104.0
    assert df["high"].iloc[1] == 65213.33
    assert df.dtypes.unique().tolist() == ["float64"]


def test_ohlc_relationships_hold():
    df = BinanceAdapter.to_frame(REAL_PAYLOAD, drop_unclosed=False)
    assert (df["high"] >= df[["open", "close"]].max(axis=1)).all()
    assert (df["low"] <= df[["open", "close"]].min(axis=1)).all()


def test_candle_spacing_matches_timeframe():
    df = BinanceAdapter.to_frame(REAL_PAYLOAD, drop_unclosed=False)
    gaps = df.index.to_series().diff().dropna().unique()
    assert len(gaps) == 1 and gaps[0] == pd.Timedelta(hours=4)


def test_open_equals_previous_close_on_continuous_data():
    df = BinanceAdapter.to_frame(REAL_PAYLOAD, drop_unclosed=False)
    assert df["open"].iloc[1] == df["close"].iloc[0]


def test_unclosed_candle_is_dropped():
    future = [r[:] for r in REAL_PAYLOAD]
    future[-1][0] = int(pd.Timestamp.now("UTC").timestamp() * 1000)
    future[-1][6] = future[-1][0] + 4 * 3600 * 1000  # تُغلق في المستقبل
    kept = BinanceAdapter.to_frame(future, drop_unclosed=True)
    assert len(kept) == 2
