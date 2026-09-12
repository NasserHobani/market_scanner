from .base import MarketAdapter
from .binance import BinanceAdapter


def _binance_lib():
    from .binance_lib import BinanceLibAdapter

    return BinanceLibAdapter


def _yahoo():
    from .yahoo import YahooAdapter

    return YahooAdapter


def _alpaca():
    from .alpaca import AlpacaAdapter

    return AlpacaAdapter


def _sahmk():
    from .sahmk import SahmkAdapter

    return SahmkAdapter


# الاستيراد كسول: binance_lib يحتاج حزمة خارجية، ولا نريد كسر المشروع بدونها
ADAPTERS = {
    "binance": lambda: BinanceAdapter,
    "binance_lib": _binance_lib,
    "yahoo": _yahoo,
    "alpaca": _alpaca,
    "sahmk": _sahmk,
}


def get_adapter(name: str) -> MarketAdapter:
    if name not in ADAPTERS:
        raise ValueError(f"محوّل غير معروف: {name}. المتاح: {list(ADAPTERS)}")
    return ADAPTERS[name]()()
