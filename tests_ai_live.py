# -*- coding: utf-8 -*-
"""اختبارات المحادثة الحيّة مع المستشار — بلا Django ولا شبكة.

المشكلة التي تحلّها الميزة: المراجعة 116 ثانية بالوسيط، والمستخدم يرى
شريط انتظار أعمى ثم صندوقاً أسود — حكماً بلا معرفة ما بُني عليه.

والخطر في التنفيذ صنفان:

  • **الخلط**: محادثتان متتاليتان تلتصق إجابتاهما فيبدو النصّ مشوّشاً.
  • **الإسقاط**: عطب في طبقة الرؤية يُفشل المراجعة نفسها — فتصير
    الميزة أضرّ من غيابها.

    python tests_ai_live.py
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner.ai_advisor import live_channel as L

results: list[tuple[bool, str, str]] = []


def check(name, cond, extra=""):
    results.append((bool(cond), name, str(extra)))


# ══════════════════ الدورة الكاملة

L.clear()
snap = L.snapshot()
check("بلا محادثة: لا نشاط", snap["active"] is False and snap["current"] is None)
check("ولا محفوظات", snap["recent"] == [])

cid = L.start(symbol="BTCUSDT", market="crypto", timeframe="4h",
              provider="ollama", model="qwen3:8b",
              system="أنت مراجع", user="المعطيات هنا")
check("البدء يعيد معرّفاً", bool(cid) and cid.startswith("conv_"))

snap = L.snapshot()
cur = snap["current"]
check("والمحادثة تصير نشطة", snap["active"] is True)
check("والموجّه متاح **قبل** وصول أي إجابة",
      cur["system"] == "أنت مراجع" and cur["user"] == "المعطيات هنا",
      "إظهاره بعد الجواب يفوّت نصف الغرض")
check("والحالة «يُرسل»", cur["state"] == "sending")
check("والرمز والفريم مسجَّلان",
      cur["symbol"] == "BTCUSDT" and cur["timeframe"] == "4h")
check("وأول مرحلة مسجَّلة", cur["stages"][0]["name"] == "أُرسل الموجّه")

L.append('{"agree')
check("أول جزء يبدّل الحالة إلى «يكتب»",
      L.snapshot()["current"]["state"] == "streaming")
L.append('ment": "partial"}')
cur = L.snapshot()["current"]
check("والأجزاء تتراكم بالترتيب",
      cur["answer"] == '{"agreement": "partial"}', cur["answer"])
check("ومرحلة «بدأت الإجابة» تُسجَّل مرة واحدة",
      sum(1 for s in cur["stages"] if s["name"] == "بدأت الإجابة") == 1)

L.stage("تحقّق من الصيغة")
check("والمراحل تُضاف بزمنها",
      L.snapshot()["current"]["stages"][-1]["name"] == "تحقّق من الصيغة")

L.finish()
snap = L.snapshot()
check("والإنهاء يُخلي الجارية", snap["active"] is False)
check("وينقلها إلى المحفوظة", len(snap["recent"]) == 1)
check("والحالة النهائية «اكتملت»", snap["recent"][0]["state"] == "done")
check("والمدة محسوبة", "elapsed" in snap["recent"][0])

# ══════════════════ لا خلط بين محادثتين

L.clear()
L.start(symbol="AAA", system="s1", user="u1")
L.append("جواب أول")
L.finish()
L.start(symbol="BBB", system="s2", user="u2")
cur = L.snapshot()["current"]
check("المحادثة الجديدة تبدأ بإجابة فارغة", cur["answer"] == "",
      "لصق إجابتين يجعل النصّ مشوّشاً بلا سبب ظاهر")
check("ومعرّفها مختلف",
      cur["id"] != L.snapshot()["recent"][0]["id"])
L.append("جواب ثانٍ")
check("ولا تختلط بالسابقة", L.snapshot()["current"]["answer"] == "جواب ثانٍ")
L.finish()
check("والمحفوظات بترتيب الأحدث أولاً",
      L.snapshot()["recent"][0]["symbol"] == "BBB")

# ══════════════════ الفشل يُروى لا يُبتلع

L.clear()
L.start(symbol="CCC")
L.finish(error="تعذّر الاتصال بالنموذج")
r = L.snapshot()["recent"][0]
check("الفشل يُسجَّل بحالته", r["state"] == "failed")
check("ونصّه محفوظ", "تعذّر الاتصال" in r["error"])
check("وتظهر مرحلة «فشلت»", r["stages"][-1]["name"] == "فشلت")

# ══════════════════ المزوّد غير المتدفّق

L.clear()
L.start(symbol="DDD")
L.finish(answer='{"x": 1}')
check("الإجابة الدفعية تُحفظ عند الإنهاء",
      L.snapshot()["recent"][0]["answer"] == '{"x": 1}',
      "مزوّد بلا بثّ يعطيها مرة واحدة في النهاية")

# ══════════════════ الحدود

L.clear()
L.append("بلا محادثة")            # يجب أن يُتجاهل بلا انهيار
L.stage("مرحلة يتيمة")
L.finish()
check("النداء بلا محادثة مفتوحة لا ينهار", L.snapshot()["active"] is False)

L.clear()
L.start(symbol="EEE", system="س" * (L.MAX_CHARS + 500))
cur = L.snapshot()["current"]
check("الموجّه الطويل يُقصّ للعرض",
      len(cur["system"]) < L.MAX_CHARS + 200 and "قُصّ" in cur["system"],
      f"{len(cur['system'])} محرف")
for _ in range(200):
    L.append("ح" * 500)
cur = L.snapshot()["current"]
check("والإجابة لا تنمو بلا حدّ في الذاكرة",
      len(cur["answer"]) <= L.MAX_CHARS + 10, len(cur["answer"]))
check("لكن العدّاد يحفظ الطول الحقيقي", cur["chars"] >= 100000, cur["chars"])
L.finish()

L.clear()
for i in range(L.MAX_KEPT + 8):
    L.start(symbol=f"S{i}")
    L.finish()
check("والمحفوظات لا تتجاوز سقفها",
      len(L._recent) == L.MAX_KEPT, len(L._recent))
check("والعرض يقتصر على خمس", len(L.snapshot()["recent"]) == 5)

# ══════════════════ التزامن

L.clear()
L.start(symbol="THREAD")
errors: list[str] = []


def writer():
    try:
        for _ in range(300):
            L.append("x")
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))


def reader():
    try:
        for _ in range(300):
            L.snapshot()
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))


threads = [threading.Thread(target=writer) for _ in range(3)]
threads += [threading.Thread(target=reader) for _ in range(3)]
for t in threads:
    t.start()
for t in threads:
    t.join()
check("الكتابة والقراءة معاً لا تنهاران", not errors, errors[:1])
check("ولا يضيع جزء", L.snapshot()["current"]["chars"] == 900,
      L.snapshot()["current"]["chars"])
check("واللقطة نسخة لا مرجع",
      L.snapshot()["current"] is not L.snapshot()["current"],
      "المرجع يعني أن العرض قد يتسلسل بنية تتغيّر تحته")
L.clear()

# ══════════════════ الربط بالمزوّد والعرض

prov = (ROOT / "scanner" / "ai_local" / "ollama_provider.py").read_text("utf-8")
check("المزوّد يفتح المحادثة **قبل** الإرسال",
      prov.index("live_channel.start") < prov.index("max_attempts = max"))
check("ويبثّ الأجزاء أثناء وصولها",
      "_chat_streaming" in prov and "live_channel.append" in prov)
check("والبثّ يقرأ سطراً سطراً لا الاستجابة كاملة",
      "for raw in resp" in prov,
      "‏read() ينتظر الاكتمال فيُلغي الغرض")
check("ويُنهي المحادثة في كل مسار خروج",
      prov.count("_live_finish(") >= 4,
      "مسار لا يُنهيها يترك اللوحة معلّقة إلى الأبد")
check("وفشل الرؤية لا يُسقط المراجعة",
      "def _live_finish" in prov and "except Exception" in
      prov[prov.index("def _live_finish"):],
      "ميزة مرافقة تُسقط الوظيفة أضرّ من غيابها")
check("والبثّ يعود إلى الطلب الدفعي عند التعذّر",
      "_http_post_json" in prov[prov.index("def _chat("):
                                prov.index("def _chat_streaming")])

views = (ROOT / "web" / "dashboard" / "ai_live_views.py").read_text("utf-8")
check("النقطة تقرأ من الذاكرة بلا حساب", "snapshot()" in views
      and "storage" not in views)
check("وترسل الجديد فقط عبر since", "since" in views)

js = (ROOT / "web" / "dashboard" / "static" / "dashboard"
      / "ai-live.js").read_text("utf-8")
check("الواجهة تصفّر عند تبدّل المعرّف", "cur.id !== currentId" in js,
      "بدونه تلتصق إجابتان")
check("وتفتح نفسها عند بدء محادثة", "if (!open) setOpen(true)" in js)
check("ولا تسحب القارئ لأسفل إن كان يقرأ", "userScrolled" in js)
check("وتُبطئ الاستعلام حين لا شيء يجري",
      "IDLE_MS" in js and "LIVE_MS" in js)

base = (ROOT / "web" / "dashboard" / "templates" / "dashboard"
        / "base.html").read_text("utf-8")
check("واللوحة في القالب الأساس — أي على كل الشاشات",
      'id="ai-live"' in base and "dashboard/ai-live.js" in base)
check("وتعرض ما أُرسل وما يصل معاً",
      "data-live-prompt" in base and "data-live-answer" in base,
      "الإجابة وحدها تبقى صندوقاً أسود")


bad = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not bad
      else f"✗ فشل {len(bad)} من {len(results)}")
sys.exit(1 if bad else 0)
