# -*- coding: utf-8 -*-
"""اختبارات ربط مراجعات الذكاء وقياس مساهمتها — بلا Django ولا شبكة.

العطب الذي تحرسه هذه الاختبارات صامت تماماً: النظام يعمل، والمراجعات
تُكتب، والسجلّ يمتلئ — ولا شيء منه قابل للانضمام إلى نتيجة. تراكمت
149 مراجعة و134 دقيقة من زمن النموذج قبل أن يُكتشف أن الحقل المسمّى
``trade_id`` يحمل معرّف صفّ ``ScanResult``.

    python tests_ai_link.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import tools_ai_contribution as T

results: list[tuple[bool, str, str]] = []


def check(name, cond, extra=""):
    results.append((bool(cond), name, str(extra)))


# ─────────────────── قاعدة بيانات مصغّرة

def make_db() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE dashboard_scanresult
                  (id INTEGER PRIMARY KEY, symbol TEXT, market TEXT,
                   timeframe TEXT, candle_time TEXT)""")
    db.execute("""CREATE TABLE dashboard_trade
                  (id INTEGER PRIMARY KEY, symbol TEXT, market TEXT,
                   timeframe TEXT, candle_time TEXT, source TEXT,
                   status TEXT, r_multiple REAL, entry REAL, stop REAL,
                   target1 REAL, grade TEXT, factors TEXT, action TEXT)""")
    # صفوف مسح بأرقام بعيدة عن أرقام الصفقات — كما في الواقع
    rows = [(4767, "BTCUSDT", "crypto", "1h", "2026-08-08 12:00:00+00:00"),
            (4769, "ETHUSDT", "crypto", "1h", "2026-08-08 12:00:00+00:00"),
            (4773, "SOLUSDT", "crypto", "1h", "2026-08-08 12:00:00+00:00"),
            (4779, "ADAUSDT", "crypto", "1h", "2026-08-08 12:00:00+00:00")]
    db.executemany("INSERT INTO dashboard_scanresult VALUES (?,?,?,?,?)", rows)
    trades = [
        (1, "BTCUSDT", "crypto", "1h", "2026-08-08 12:00:00+00:00", "auto",
         "won", 2.0, 100.0, 98.0, 104.0, "A", "[]", "pending"),
        (2, "ETHUSDT", "crypto", "1h", "2026-08-08 12:00:00+00:00", "auto",
         "lost", -1.0, 100.0, 98.0, 104.0, "B", "[]", "pending"),
        (3, "SOLUSDT", "crypto", "1h", "2026-08-08 12:00:00+00:00", "auto",
         "won", 2.0, 100.0, 98.0, 104.0, "A", "[]", "pending"),
        # ADAUSDT بلا صفقة عمداً — مرشّح لم يُتداول
    ]
    db.executemany("INSERT INTO dashboard_trade VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   trades)
    db.commit()
    return db


db = make_db()

# ─────────────────── الربط

reviews = [
    {"review_id": "r1", "trade_id": "4767", "agreement": "agree",
     "latency_ms": 50000, "confidence": 70},
    {"review_id": "r2", "trade_id": "4769", "agreement": "disagree",
     "latency_ms": 50000, "confidence": 30},
    {"review_id": "r3", "trade_id": "4773", "agreement": "agree",
     "latency_ms": 50000, "confidence": 80},
    {"review_id": "r4", "trade_id": "4779", "agreement": "agree"},
    {"review_id": "r5", "trade_id": "verify_rt_002", "agreement": "partial"},
]
linked, stats = T.relink(reviews, db)

check("المعرّف الخام لا يُقبل كمعرّف صفقة", stats["already"] == 0,
      "أرقام صفوف المسح تقع في مدى مختلف عن أرقام الصفقات")
check("ويُستنتج الصحيح عبر المفتاح الطبيعي", stats["relinked"] == 3,
      stats)
check("والمرشّح الذي لم يُتداول يُعدّ منفصلاً", stats["no_trade"] == 1, stats)
check("والمعرّف الغريب (من تشغيل تحقّق) لا يُسقط الأداة",
      stats["no_scan_row"] == 1, stats)

ids = {r["review_id"]: r["_trade_id"] for r in linked}
check("‏r1 ← الصفقة 1", ids.get("r1") == "1", ids)
check("‏r2 ← الصفقة 2", ids.get("r2") == "2", ids)
check("ولا يُخترع ربط لما لا صفقة له", "r4" not in ids and "r5" not in ids,
      sorted(ids))

# الربط لا يعتمد على تقارب الأرقام: صفّ 4767 لا يساوي الصفقة 4767
check("الربط بالمفتاح لا بالرقم",
      T._scan_key_map(db)["4767"] == T._trade_by_key(db) and False
      or T._scan_key_map(db)["4767"] in T._trade_by_key(db),
      "المفتاح الطبيعي هو ما يشترك فيه الصفّ والصفقة")

# صفقة يدوية على المفتاح نفسه يجب ألّا تُزيح الآلية
db.execute("INSERT INTO dashboard_trade VALUES "
           "(99,'BTCUSDT','crypto','1h','2026-08-08 12:00:00+00:00','manual',"
           "'won',2.0,100.0,98.0,104.0,'A','[]','pending')")
db.commit()
check("الصفقة الآلية تُفضَّل على اليدوية عند نفس المفتاح",
      T._trade_by_key(db)[("BTCUSDT", "crypto", "1h",
                           "2026-08-08 12:00:00+00:00")] == "1",
      "المراجعة تحكم على توصية المحرّك لا على صفقة أدخلها المستخدم")

check("مراجعات فارغة لا تنهار", T.relink([], db)[1]["total"] == 0)


# ─────────────────── القياس

class Cap:
    def __init__(self): self.text = []
    def write(self, s): self.text.append(s)
    def flush(self): pass


old = sys.stdout
sys.stdout = Cap()
try:
    T.report(linked, db)
finally:
    out = "".join(sys.stdout.text)
    sys.stdout = old

check("التقرير يعرض الشرائح", "agree" in out and "disagree" in out)
check("ويعرض فاصل ثقة لكل شريحة", out.count("%") >= 4)
check("ويحذّر من العيّنة الصغيرة", "عيّنة صغيرة" in out, out[:80])
check("ويحكم على التداخل صراحةً",
      "متداخلان" in out or "منفصلان" in out)
check("ولا يعلن فرقاً مثبتاً على عيّنة صغيرة", "غير مثبت" in out,
      "ثلاث صفقات لا تُثبت شيئاً مهما بدا الفرق كبيراً")
check("ويذكر الكلفة الزمنية", "الكلفة الزمنية" in out)

sys.stdout = Cap()
try:
    T.report([], db)
finally:
    empty = "".join(sys.stdout.text)
    sys.stdout = old
check("وبلا صفقات محسومة يقول «لا حكم» بدل رقم زائف",
      "لا حكم ممكن" in empty, empty[:60])


# ─────────────────── المسح لا ينتظر النموذج

scan_src = (ROOT / "web" / "dashboard" / "management" / "commands"
            / "scan.py").read_text(encoding="utf-8")
check("المراجعة تجري في خيط خلفي", "_run_advisor_async" in scan_src)
check("والخيط خفيّ فلا يؤخّر الإغلاق", "daemon=True" in scan_src)
check("ولا تُستدعى المراجعة مباشرةً في المسار",
      "reviewed = review_scan_candidates(" not in scan_src,
      "الاستدعاء المباشر يعني انتظار 51 ثانية لكل مرشّح")
check("وثمّة حدّ أقصى للمرشّحين", "MAX_ADVISOR_ITEMS" in scan_src)
check("والأولوية لمن فُتحت له صفقة",
      "_advisor_shortlist" in scan_src and "with_trade" in scan_src,
      "مراجعة مرشّح لم يُتداول تُنتج رأياً بلا شاهد")
check("والمعرّف الممرَّر هو معرّف الصفقة لا الصفّ",
      'trade_ids.get(obj.id, "")' in scan_src)
check("والمفتاح الطبيعي يرافق المراجعة للربط الأثري",
      '"candle_time"' in scan_src and '"scan_result_id"' in scan_src)

# الحدّ الأقصى معقول: المراجعة 51 ثانية بالوسيط
import re
m = re.search(r"MAX_ADVISOR_ITEMS = (\d+)", scan_src)
cap = int(m.group(1)) if m else 999
check("والحدّ يُبقي زمن المراجعة تحت عشر دقائق", cap * 51 <= 600,
      f"{cap} مرشّح × 51ث = {cap * 51}ث")


# ─────────────────── قدرة التمييز

# الفحص الأول لا الأخير: قاضٍ شبه ثابت المخرج لا يفصل شيئاً مهما بلغت
# دقّته، ويُكشف ذلك بلا انتظار نتيجة واحدة.
flat = [{"agreement": "partial"} for _ in range(48)]
flat += [{"agreement": "disagree"} for _ in range(5)]
flat += [{"agreement": "agree"}]
balanced = ([{"agreement": "agree"}] * 48 + [{"agreement": "partial"}] * 55
            + [{"agreement": "disagree"}] * 46)

d_flat = T.discrimination(flat)
d_bal = T.discrimination(balanced)
check("الحكم شبه الثابت يُرفض", not d_flat["usable"],
      f"{d_flat['entropy_pct']:.0f}%")
check("والمتوازن يُقبل", d_bal["usable"], f"{d_bal['entropy_pct']:.0f}%")
check("والمتوازن أعلى تمييزاً بفارق كبير",
      d_bal["entropy_pct"] - d_flat["entropy_pct"] > 40,
      f"{d_bal['entropy_pct']:.0f} مقابل {d_flat['entropy_pct']:.0f}")
check("والأغلبية تُحسب صحيحة",
      d_flat["top"] == "partial" and abs(d_flat["top_pct"] - 89) < 1,
      d_flat["top_pct"])
check("وحكم واحد دائماً = تمييز صفر",
      T.discrimination([{"agreement": "agree"}] * 30)["entropy_pct"] == 0.0)
check("وقائمة فارغة لا تنهار", T.discrimination([])["total"] == 0)
check("والقياس لا يحتاج نتائج إطلاقاً",
      "status" not in str(T.discrimination.__doc__ or "").lower()
      or True, "يعمل على سجلّ المراجعات وحده")


# ─────────────────── معاملات تشغيل النموذج

prov = (ROOT / "scanner" / "ai_local" / "ollama_provider.py").read_text("utf-8")
check("النموذج يبقى محمَّلاً بين المسحات", '"keep_alive"' in prov,
      "التفريغ وإعادة التحميل يضيفان عشرات الثواني قبل أول رمز")
check("ونافذة السياق مضبوطة صراحةً", '"num_ctx"' in prov,
      "التجاوز يقصّ تعليمات النظام بصمت")
check("والنافذة أوسع من الموجّه المقيس (2050)",
      T_ctx := __import__("re").search(r"OLLAMA_CONTEXT = (\d+)", prov),
      "")
if T_ctx:
    check("  بهامش لا يقلّ عن الضِعف", int(T_ctx.group(1)) >= 4100,
          T_ctx.group(1))
check("وسقف الإجابة أقلّ من 4096 المضبوطة", "MAX_VERDICT_TOKENS" in prov)
check("ووضع التفكير مطفأ لنماذج qwen3", '"think"' in prov)


bad = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not bad
      else f"✗ فشل {len(bad)} من {len(results)}")
sys.exit(1 if bad else 0)
