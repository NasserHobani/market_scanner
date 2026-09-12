# -*- coding: utf-8 -*-
"""هويّة المراجعة — الرمز والفريم لا يضيعان.

═══ العطب الذي تحرسه ═══

ظهر عمود «الرمز» فارغاً لأربع مراجعات بينما ``event_id`` بجانبها يقول
``evt_btcusdt_crypto_4h``. وثلاث منها تتشارك معرّف حزمة واحداً
(``udpkg_53e221c965f00303``) — أي أنها **إصابة في ذاكرة الحزم**.

والذاكرة تُفهرَس ببصمة تشمل الرمز، فالإصابة تعني «الأدلّة نفسها»
وهذا صحيح. لكنّ الحزمة المستعادة كانت تحمل أيضاً **هويّة اللحظة التي
بُنيت فيها**، وقد كانت ناقصة. فورثتها كل مراجعة تالية.

وأثره ليس تجميلياً: مراجعة بلا رمز لا تُربط بالصفقة التي راجعتها، فلا
يمكن قياس هل كان المستشار محقّاً على هذا الرمز — وهو أساس تقييمه.

ثلاث حواجز هنا:
  ١. المنبع: الهويّة تُعاد طباعتها على الحزمة المستعادة.
  ٢. العرض: ما نقص يُشتقّ من ``event_id`` بلا كتابة على التاريخ.
  ٣. البيانات الوصفية: تُكتب للمراجعة التلقائية كما لليدوية.
"""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner.ai_advisor.explainability.review_identity import (  # noqa: E402
    identity_from, parse_event_id,
)

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


# ── تفكيك المعرّف ──
check("رمز بسيط", parse_event_id("evt_btcusdt_crypto_4h") == ("BTCUSDT", "crypto", "4h"))
check("فريم من رقمين", parse_event_id("evt_xlmusdt_crypto_15m") == ("XLMUSDT", "crypto", "15m"))
check("سوق أمريكي", parse_event_id("evt_nvda_us_15m") == ("NVDA", "us", "15m"))

# الرمز قد يحوي شرطة سفلية (BTC/USDT ← btc_usdt). التفكيك من اليسار
# كان يقطعه؛ ومن اليمين يصيب لأن السوق والفريم مفردتان بلا فواصل.
check("رمز بشرطة سفلية لا يُقطع",
      parse_event_id("evt_btc_usdt_crypto_1h") == ("BTC_USDT", "crypto", "1h"))

# ما لا يطابق البنية يعطي فراغاً — الفراغ الصادق أفضل من رمز مخترَع
check("نصّ غريب لا يخترع رمزاً", parse_event_id("hello world") == ("", "", ""))
check("بلا بادئة evt", parse_event_id("btcusdt_crypto_4h") == ("", "", ""))
check("سوق مجهول يُرفض", parse_event_id("evt_x_notamarket_4h") == ("", "", ""))
check("أجزاء ناقصة", parse_event_id("evt_btcusdt") == ("", "", ""))
check("فارغ", parse_event_id("") == ("", "", ""))
check("‏None لا يرفع", parse_event_id(None) == ("", "", ""))  # type: ignore[arg-type]

# ── ترتيب الثقة ──
check("الحقل الصريح يسبق الاشتقاق",
      identity_from({"symbol": "NVDA", "event_id": "evt_btcusdt_crypto_4h"},
                    {"market": "us", "timeframe": "15m"})
      == ("NVDA", "us", "15m"))
check("الاشتقاق يملأ الناقص وحده",
      identity_from({"symbol": "", "event_id": "evt_btcusdt_crypto_4h"})
      == ("BTCUSDT", "crypto", "4h"))
check("المصدر الأول يفوز",
      identity_from({"symbol": "AAA"}, {"symbol": "BBB"})[0] == "AAA")
check("مصدر فارغ يُتخطّى",
      identity_from({}, {"symbol": "BBB", "market": "us", "timeframe": "1h"})
      == ("BBB", "us", "1h"))
check("بلا مصادر", identity_from(None, {}) == ("", "", ""))


# ── الحاجز الأول: ختم الهويّة على الحزمة المستعادة ──
from scanner.ai_advisor.unified_pipeline import _restamp_identity  # noqa: E402


@dataclasses.dataclass(frozen=True)
class _Pkg:
    package_id: str = "udpkg_x"
    event_id: str = "evt_old_crypto_4h"
    metadata: dict = dataclasses.field(default_factory=dict)


stale = _Pkg(metadata={"symbol": "", "market": "", "timeframe": "",
                       "evidence": "قديم"})
fresh = _restamp_identity(
    stale,
    metadata={"symbol": "BTCUSDT", "market": "crypto", "timeframe": "4h",
              "trade_id": "7"},
    event_id="evt_btcusdt_crypto_4h",
)
check("الهويّة تُختم على المستعاد", fresh.metadata["symbol"] == "BTCUSDT")
check("والسوق كذلك", fresh.metadata["market"] == "crypto")
check("والفريم كذلك", fresh.metadata["timeframe"] == "4h")
check("ومعرّف الصفقة", fresh.metadata["trade_id"] == "7")
check("و event_id يُحدَّث", fresh.event_id == "evt_btcusdt_crypto_4h")

# الأدلّة تُستعاد كما هي — الذاكرة موجودة لهذا
check("الأدلّة المخزَّنة تبقى", fresh.metadata.get("evidence") == "قديم")

# الحزمة الأصلية لا تُمسّ (مجمَّدة، والاستبدال ينشئ نسخة)
check("الأصل لا يُعدَّل", stale.metadata["symbol"] == "")

# بيانات واردة فارغة لا تمحو ما في الحزمة
kept = _restamp_identity(
    _Pkg(metadata={"symbol": "ETHUSDT"}), metadata={"symbol": ""}, event_id="",
)
check("الوارد الفارغ لا يمحو", kept.metadata["symbol"] == "ETHUSDT")


# ── الحاجز الثاني: العرض ──
svc_src = (ROOT / "scanner" / "ai_advisor" / "explainability"
           / "review_timeline_service.py").read_text(encoding="utf-8")
svc_code = "\n".join(
    ln for ln in svc_src.splitlines() if not ln.strip().startswith("#")
)
check("الجدول يستعمل الهويّة الموحّدة", "identity_from(hist, meta)" in svc_code)
check("والترشيح كذلك", "identity_from(rec, meta)" in svc_code)
check("والبحث يشمل event_id", 'rec.get("event_id", "")' in svc_code)
check("لا رمز يُقرأ خاماً في صفّ الجدول",
      '"symbol": hist.get("symbol", "")' not in svc_code)

# التفصيل كان يفترض crypto/4h مثبَّتين — فتظهر مراجعة سهم أمريكي على
# 15m كأنها كريبتو على 4h، وهو خطأ صامت يفسد أي تجميع لاحق
check("لا سوق مثبَّت في التفصيل", '(mem or {}).get("market", "crypto")' not in svc_code)
check("لا فريم مثبَّت في التفصيل", '(mem or {}).get("timeframe", "4h")' not in svc_code)


# ── الحاجز الثالث: البيانات الوصفية للمراجعة التلقائية ──
eng_src = (ROOT / "scanner" / "ai_advisor" / "advisor_engine.py").read_text(encoding="utf-8")
eng_code = "\n".join(
    ln for ln in eng_src.splitlines() if not ln.strip().startswith("#")
)
check("المحرّك يسجّل البيانات الوصفية", "ReviewMetaStore" in eng_code)
check("بنوع تلقائي", 'review_type="automatic"' in eng_code)
check("ولا يكتب فوق اليدوي", "if not store.get(" in eng_code)
check("وفشلها لا يُسقط المراجعة",
      eng_code.count("except Exception:") >= 1 and "ReviewMetaStore" in eng_code)


# ── الحصيلة على السجلّ الحقيقي ──
#
# لا معنى لاختبار يمرّ على بيانات مصطنعة بينما الشاشة فارغة. فنقرأ
# الملفّ الفعلي: كل مراجعة يجب أن يكون لها رمز، إمّا مخزَّناً أو مشتقّاً.
hist_path = ROOT / "data" / "advisor_history.jsonl"
if hist_path.exists():
    import json

    rows = [json.loads(ln) for ln in hist_path.read_text(encoding="utf-8").splitlines()
            if ln.strip()]
    missing = [r for r in rows if not identity_from(r)[0]]
    check("كل مراجعة في السجلّ لها رمز", not missing,
          f"{len(missing)} بلا رمز من {len(rows)}")
else:
    check("كل مراجعة في السجلّ لها رمز", True, "لا سجلّ بعد")

failed = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not failed
      else f"✗ فشل {len(failed)} من {len(results)}")
sys.exit(1 if failed else 0)
