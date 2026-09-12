# -*- coding: utf-8 -*-
"""اختبارات مخطط الإعدادات — بلا Django.

مدخلات المستخدم أخطر ما يدخل النظام: حقل فارغ أو نصّ في خانة رقم أو
عتبة عليا دون الدنيا. كلها تُختبر هنا قبل أن تصل قاعدة البيانات.

    python tests_settings.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scanner import liquidity as L
from scanner import settings_schema as S

results: list[tuple[bool, str, str]] = []


def check(name, cond, extra=""):
    results.append((bool(cond), name, str(extra)))


# ── سلامة المخطط نفسه ──
keys = [f.key for g in S.GROUPS for f in g.fields]
check("لا مفاتيح مكرّرة", len(keys) == len(set(keys)),
      [k for k in keys if keys.count(k) > 1])
check("كل حقل له افتراض", all(f.default is not None for f in S.FIELDS.values()))
check("كل حقل له شرح", all(f.help for f in S.FIELDS.values()),
      [k for k, f in S.FIELDS.items() if not f.help])
check("الافتراضي يجتاز التحقق بلا تنبيه",
      S.validate(dict(S.DEFAULTS))[1] == [], S.validate(dict(S.DEFAULTS))[1])
check("كل افتراضي داخل حدوده",
      all((f.minimum is None or f.default >= f.minimum) and
          (f.maximum is None or f.default <= f.maximum)
          for f in S.FIELDS.values() if f.kind in ("int", "float")))

# ── التحويل ──
check("نصّ رقمي يُقبل", S.coerce("workers", "16")[0] == 16)
check("عدد عشري في حقل صحيح يُقصّ", S.coerce("workers", "8.9")[0] == 8)
check("فاصلة الآلاف تُزال", S.coerce("min_quote_volume", "1,500,000")[0] == 1_500_000)
v, note = S.coerce("workers", "نص")
check("نصّ غير رقمي ← الافتراضي مع تنبيه", v == 12 and note, note)
v, note = S.coerce("workers", "999")
check("فوق الحدّ يُقصّ مع تنبيه", v == 32 and "الأقصى" in note, f"{v} · {note}")
v, note = S.coerce("workers", "0")
check("دون الحدّ يُرفع مع تنبيه", v == 1 and "الأدنى" in note, f"{v} · {note}")
check("فارغ ← الافتراضي بلا تنبيه", S.coerce("workers", "  ") == (12, None))
check("مفتاح مجهول يُرفض", S.coerce("لا-يوجد", 1)[1] is not None)

for raw, exp in (("on", True), ("true", True), ("1", True), ("نعم", True),
                 ("off", False), ("", False), (True, True), (False, False)):
    check(f"منطقي «{raw}» ← {exp}", S.coerce("enabled", raw)[0] is exp)

# ── القيود المتقاطعة ──
out, notes = S.validate({**S.DEFAULTS, "tier_high": 1000, "tier_mid": 5_000_000})
check("عتبة عليا دون الوسطى تُصحَّح",
      out["tier_high"] > out["tier_mid"] and any("العالية" in n for n in notes),
      f"{out['tier_high']:,.0f} · {notes}")

out, notes = S.validate({**S.DEFAULTS, "stop_atr": 3, "target_atr": 1})
check("هدف دون الوقف يُصحَّح",
      out["target_atr"] > out["stop_atr"] and any("الهدف" in n for n in notes),
      f"{out['target_atr']} · {notes}")

out, _ = S.validate({**S.DEFAULTS, "stop_atr": 2, "target_atr": 2})
check("هدف يساوي الوقف يُصحَّح أيضاً", out["target_atr"] > out["stop_atr"])

# ── الحقول الغائبة ──
out, _ = S.validate({"workers": 4})
check("الغائب يأخذ افتراضه لا يُسقط الحفظ",
      out["workers"] == 4 and out["candles"] == 1500, out.get("candles"))
check("منطقي غائب ← False (مربّع غير مؤشَّر لا يُرسَل)",
      S.validate({"workers": 4})["enabled"] is False
      if isinstance(S.validate({"workers": 4}), dict)
      else S.validate({"workers": 4})[0]["enabled"] is False)

# ── الدمج ──
check("المحفوظ يعلو الافتراضي",
      S.merged({"workers": 5})["workers"] == 5)
check("المفاتيح الغريبة تُتجاهَل",
      "زائد" not in S.merged({"زائد": 1}))
check("إعداد جديد يظهر بافتراضه بلا هجرة",
      S.merged({"workers": 5})["candles"] == 1500)
check("None آمن", S.merged(None) == S.DEFAULTS)

# ── ربط العتبات بوحدة السيولة ──
tiers = S.tiers_from({**S.DEFAULTS, "tier_high": 100, "tier_mid": 50, "tier_low": 10})
check("عتبة مخصّصة تغيّر التصنيف فعلاً",
      L.tier(120, tiers) == "high" and L.tier(60, tiers) == "mid"
      and L.tier(20, tiers) == "low" and L.tier(5, tiers) == "micro",
      [L.tier(v, tiers) for v in (120, 60, 20, 5)])
check("بلا عتبات مخصّصة تبقى الافتراضية",
      L.tier(60_000_000) == "high" and L.tier(300_000) == "micro")
check("غير معروف يبقى غير معروف مع عتبات مخصّصة",
      L.tier(None, tiers) == "unknown")

bad = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not bad else f"✗ فشل {len(bad)} من {len(results)}")
sys.exit(1 if bad else 0)
