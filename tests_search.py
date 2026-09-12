# -*- coding: utf-8 -*-
"""اختبارات نطاق البحث — بلا Django ولا شبكة.

    python tests_search.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scanner import search as S

results: list[tuple[bool, str, str]] = []


def check(name, cond, extra=""):
    results.append((bool(cond), name, str(extra)))


# ─────────────────── محوّلات مُقلَّدة تسجّل من سُئل ومتى

class FakeAdapter:
    def __init__(self, rows, delay=0.0, error=None):
        self.rows, self.delay, self.error = rows, delay, error
        self.calls = 0

    def search(self, query):
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise self.error
        return [dict(r) for r in self.rows]


def registry(**adapters):
    """سجلّ محوّلات وهمي.

    المصدر غير المذكور يُملأ بمحوّل صامت بلا نتائج بدل رفع خطأ: إضافة
    مصدر جديد إلى ``SOURCES`` كانت تُفشل كل اختبار على نطاق «الكل»
    لسبب لا علاقة له بما يقيسه. الاختبار الذي ينكسر لتغيير غير ذي صلة
    يُدرّب على تجاهل الأحمر.
    """
    def resolve(name):
        if name not in adapters:
            return FakeAdapter([])
        return adapters[name]
    return resolve


CRYPTO = [{"symbol": "BTCUSDT", "name": "BTC", "market": "crypto"},
          {"symbol": "BTCDOWNUSDT", "name": "BTCDOWN", "market": "crypto"}]
STOCKS = [{"symbol": "AAPL", "name": "Apple", "market": "us"},
          {"symbol": "2222.SR", "name": "أرامكو", "market": "saudi"}]


# ─────────────────── تطبيع النطاق

check("نطاق معروف يُقبل", S.normalize_scope("crypto") == "crypto")
check("نطاق مجهول يعود للافتراضي", S.normalize_scope("xyz") == "all")
check("فارغ يعود للافتراضي", S.normalize_scope("") == "all")
check("الافتراضي البديل يُحترم",
      S.normalize_scope(None, fallback="saudi") == "saudi")
check("افتراضي بديل تالف يعود للكل",
      S.normalize_scope(None, fallback="تالف") == "all")

# ─────────────────── اختيار المصادر

check("العملات ← بينانس وحده", S.sources_for("crypto") == ("binance",))
# الأمريكي مصدران: alpaca يطابق ما يستطيع الماسح جلبه فعلاً، و yahoo
# احتياط حين تغيب المفاتيح — فالبحث يعمل قبل ضبطها لا بعدها.
check("الأمريكي ← ألباكا ثم ياهو احتياطاً",
      S.sources_for("us") == ("alpaca", "yahoo"), S.sources_for("us"))
check("والأولوية لألباكا", S.sources_for("us")[0] == "alpaca")
check("السعودي ← ياهو وحده", S.sources_for("saudi") == ("yahoo",))
check("الكل ← المصادر بلا تكرار رغم اشتراك ياهو في سوقين",
      S.sources_for("all") == ("binance", "alpaca", "yahoo"),
      S.sources_for("all"))
check("ولا مصدر مكرَّر",
      len(S.sources_for("all")) == len(set(S.sources_for("all"))))

# ─────────────────── جوهر المطلب: المصدر البطيء لا يُسأل أصلاً

binance = FakeAdapter(CRYPTO)
yahoo = FakeAdapter(STOCKS, delay=1.0)
out = S.run("BTC", "crypto", registry(binance=binance, yahoo=yahoo))
check("بحث العملات لا يستدعي ياهو إطلاقاً",
      yahoo.calls == 0 and binance.calls == 1,
      f"binance={binance.calls} yahoo={yahoo.calls}")
check("ولا ينتظر تأخيره", out["elapsed"] < 0.5, f"{out['elapsed']}ث")
check("ويعيد نتائج العملات", len(out["results"]) == 2)

binance = FakeAdapter(CRYPTO, delay=1.0)
yahoo = FakeAdapter(STOCKS)
out = S.run("AAPL", "us", registry(binance=binance, yahoo=yahoo))
check("بحث الأسهم لا يستدعي بينانس", binance.calls == 0 and yahoo.calls == 1)

# ─────────────────── الترشيح بعد الجلب

out = S.run("x", "us", registry(binance=FakeAdapter([]), yahoo=FakeAdapter(STOCKS)))
syms = [r["symbol"] for r in out["results"]]
check("الأمريكي يستبعد السعودي رغم مجيئهما معاً من ياهو",
      syms == ["AAPL"], syms)

out = S.run("x", "saudi", registry(binance=FakeAdapter([]), yahoo=FakeAdapter(STOCKS)))
check("السعودي يستبعد الأمريكي",
      [r["symbol"] for r in out["results"]] == ["2222.SR"])

out = S.run("x", "all", registry(binance=FakeAdapter(CRYPTO),
                                 yahoo=FakeAdapter(STOCKS)))
check("الكل لا يرشّح شيئاً", len(out["results"]) == 4, len(out["results"]))

# ─────────────────── التوازي

SLOW = 0.6
binance = FakeAdapter(CRYPTO, delay=SLOW)
yahoo = FakeAdapter(STOCKS, delay=SLOW)
out = S.run("x", "all", registry(binance=binance, yahoo=yahoo))
check("«الكل» يسأل المصدرين بالتوازي لا بالتتابع",
      out["elapsed"] < SLOW * 1.7, f"{out['elapsed']}ث لمصدرين × {SLOW}ث")
check("والاثنان سُئلا فعلاً", binance.calls == 1 and yahoo.calls == 1)

# ─────────────────── الأعطال

out = S.run("x", "all", registry(binance=FakeAdapter(CRYPTO),
                                 yahoo=FakeAdapter([], error=RuntimeError("انقطاع"))))
check("سقوط مصدر لا يمنع نتائج الآخر",
      len(out["results"]) == 2 and len(out["failures"]) == 1,
      f"{len(out['results'])} نتيجة · {out['failures']}")

out = S.run("x", "crypto", registry(binance=FakeAdapter([], error=RuntimeError("حدّ")),
                                    yahoo=FakeAdapter(STOCKS)))
check("مصدر وحيد ساقط ← لا نتائج مع سبب",
      out["results"] == [] and "حدّ" in out["failures"][0], out["failures"])

out = S.run("x", "all", registry(binance=FakeAdapter(CRYPTO),
                                 yahoo=FakeAdapter(STOCKS, delay=1.0)),
            timeout=0.2)
check("مصدر بطيء يُقطع بمهلة ولا يعلّق الصفحة",
      len(out["results"]) == 2 and "تجاوز" in out["failures"][0],
      f"{out['results']} · {out['failures']}")


class NoSearch:
    pass


out = S.run("x", "crypto", registry(binance=NoSearch(), yahoo=FakeAdapter([])))
check("محوّل بلا دالة بحث يُتخطّى بلا خطأ",
      out["results"] == [] and out["failures"] == [], out["failures"])

# ─────────────────── إزالة التكرار والحدّ

dup = FakeAdapter([{"symbol": "AAPL", "market": "us"},
                   {"symbol": "AAPL", "market": "us"},
                   {"symbol": None, "market": "us"}])
out = S.run("x", "us", registry(binance=FakeAdapter([]), yahoo=dup))
check("التكرار يُزال والرمز الفارغ يُتخطّى",
      [r["symbol"] for r in out["results"]] == ["AAPL"],
      [r.get("symbol") for r in out["results"]])

many = FakeAdapter([{"symbol": f"S{i}", "market": "us"} for i in range(50)])
out = S.run("x", "us", registry(binance=FakeAdapter([]), yahoo=many))
check("الحدّ الأقصى يُحترم", len(out["results"]) == S.MAX_RESULTS,
      len(out["results"]))

# ─────────────────── استعلام فارغ لا يستدعي شيئاً

binance = FakeAdapter(CRYPTO)
out = S.run("   ", "all", registry(binance=binance, yahoo=FakeAdapter(STOCKS)))
check("استعلام فارغ لا يسأل أي مصدر",
      binance.calls == 0 and out["results"] == [] and out["elapsed"] == 0.0)

# ─────────────────── التقرير

bad = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not bad else f"✗ فشل {len(bad)} من {len(results)}")
sys.exit(1 if bad else 0)
