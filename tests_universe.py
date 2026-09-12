# -*- coding: utf-8 -*-
"""مصدر قائمة الرموز — لا يُبتلع ولا يُخفى.

═══ العطب ═══

ملف السوق الأمريكي يقول ``universe: auto`` — كل سهم فوق عشرين مليون
دولار يومياً، قرابة سبعمئة. وسجلّ القاعدة يقول **عشرة رموز متمايزة في
كل تاريخ السوق**، وهي حرفياً قائمة ``symbols`` الاحتياطية.

فالاكتشاف لم ينجح قطّ، والمسح ارتدّ إلى القائمة في كل مرّة. والارتداد
كان يُكتب إلى ``stderr`` — والمسح من اللوحة يعمل في خيط، فلا يقرأه أحد.

وهذا أخطر من التوقّف: نظام يعمل بجزء من طاقته ويبدو سليماً. لا رسالة
خطأ تدفعك للفحص، ولا صفر نتائج ينبّهك — بل عشر نتائج تبدو معقولة.
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


def code_of(path: str) -> str:
    """المصدر بلا تعليقات — كي لا يُطابق شرحاً للعطب القديم."""
    src = (ROOT / path).read_text(encoding="utf-8")
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return "\n".join(
        ln for ln in src.splitlines()
        if not ln.strip().startswith(("#", "//", "{#"))
    )


# ── المسح يسجّل المصدر ──
scan = code_of("web/dashboard/management/commands/scan.py")
check("المسح يسجّل مصدر الرموز", "universe_source" in scan)
check("ويسجّل سببه", "universe_note" in scan)
check("ويصل الحقلان إلى الدورة",
      "universe_source=universe_source" in scan.replace(" ", ""))

for source in ("list", "auto", "fallback", "auto_thin"):
    check(f"يميّز الحالة «{source}»", f'"{source}"' in scan)

# اكتشاف ينجح ويعيد عدداً ضئيلاً ليس نجاحاً — يُرصد كتدهور
check("العدد الضئيل يُرصد تدهوراً", "auto_thin" in scan)
check("ويقارَن بالقائمة الاحتياطية",
      "len(cfg.symbols" in scan.replace(" ", "").replace("len(cfg.symbols",
                                                         "len(cfg.symbols"))

# ── النموذج والهجرة ──
models = code_of("web/dashboard/models.py")
check("الحقل في النموذج", "universe_source = models.CharField" in models)
check("وملاحظته", "universe_note = models.CharField" in models)
migs = list((ROOT / "web" / "dashboard" / "migrations").glob("*.py"))
check("وله هجرة",
      any("universe_source" in p.read_text(encoding="utf-8") for p in migs))

# ── الواجهة ترى ما جرى ──
views = code_of("web/dashboard/views.py")
check("الواجهة تُرسل المصدر", '"universe_source"' in views)
check("وتُعلن التدهور صراحةً", '"universe_degraded"' in views)
check("والتدهور يشمل الارتداد والعدد الضئيل",
      '"fallback"' in views and '"auto_thin"' in views)

app_js = code_of("web/dashboard/static/dashboard/app.js")
check("اللوحة ترسم البانر", "paintUniverse" in app_js)
check("وتستدعيه عند كل تحديث", "paintUniverse(d.run)" in app_js)
check("ولا تُظهره إلا عند التدهور", "universe_degraded" in app_js)
check("وتدلّ على أداة التشخيص", "tools_check_universe" in app_js)

tpl = code_of("web/dashboard/templates/dashboard/scanner.html")
check("والقالب فيه موضع البانر", 'id="universe-note"' in tpl)
check("ومخفيّ ابتداءً", "d-none" in tpl)

# ── أداة التشخيص ──
tool = ROOT / "tools_check_universe.py"
check("أداة التشخيص موجودة", tool.exists())
tool_src = tool.read_text(encoding="utf-8")
# الحلقات الأربع: مفاتيح، أصول، أحجام، عتبة — كلٌّ يُشخَّص وحده لأن
# علاجها مختلف، والرسالة الواحدة لا تفرّق بينها
for stage in ("المفاتيح", "الأصول", "الأحجام", "العتبة"):
    check(f"تفحص {stage}", stage in tool_src)
check("وتميّز list عن العطب", "معطّل بالإعداد لا بعطب" in tool_src)
check("وتقترح علاجاً لكل حلقة", tool_src.count("• ") >= 4)

# ── الإعداد نفسه ──
import yaml  # noqa: E402

us = yaml.safe_load((ROOT / "config" / "us.yaml").read_text(encoding="utf-8"))
check("السوق الأمريكي على الاكتشاف التلقائي", us.get("universe") == "auto")
check("وله قائمة احتياطية غير فارغة", len(us.get("symbols") or []) > 0)
# القائمة الاحتياطية شبكة أمان لا كون تداول. تساوي حجمها مع سقف المسح
# يجعل الارتداد غير مميَّز عن النجاح بالعدد وحده.
check("والاحتياطية أصغر بكثير من السقف",
      len(us.get("symbols") or []) < (us.get("top_n") or 0) / 5,
      f"{len(us.get('symbols') or [])} مقابل top_n={us.get('top_n')}")

# ── الأداة تعمل فعلاً على سوق قائمة (بلا شبكة) ──
import subprocess  # noqa: E402

# سوق مصطنع على ``list`` — لا نستعير ملفاً حقيقياً لأن قرار
# ``universe`` قرارٌ تشغيليّ يتغيّر (تحوّل السعودي إلى auto فكسر
# هذا الاختبار)، والمقصود هنا سلوك الأداة لا محتوى الإعداد.
import os  # noqa: E402
import tempfile  # noqa: E402

_cfgdir = Path(tempfile.mkdtemp())
(_cfgdir / "ثابت.yaml").write_text(
    "name: ثابت\nadapter: binance\ntimeframes: [\"1h\"]\ncandles: 50\n"
    "universe: list\nsymbols: [AAA, BBB]\nworkers: 2\n"
    "min_quote_volume: 0\ntop_n: 10\nweights: {}\nparams: {}\n",
    encoding="utf-8",
)
_env = {**os.environ, "SCANNER_CONFIG_DIR": str(_cfgdir),
        "PYTHONIOENCODING": "utf-8"}
proc = subprocess.run([sys.executable, str(tool), "ثابت"],
                      capture_output=True, text=True, timeout=90, env=_env)
check("الأداة تعمل على سوق list بلا شبكة", proc.returncode == 0,
      (proc.stdout + proc.stderr)[-200:])
check("وتقول إن الاكتشاف معطّل بالإعداد",
      "معطّل بالإعداد" in proc.stdout, proc.stdout[-200:])
check("ولا تلمس الشبكة أصلاً", "usdt_universe" not in proc.stdout)

shutil.rmtree(_cfgdir, ignore_errors=True)


# ── دليل الشركات هو الكون حين يوجد ──
#
# ═══ العطب ═══
#
# مُسح السوق السعودي على **عشرة أسهم** — قائمة الملف الاحتياطية —
# بينما ٣٢٦ شركة محفوظة في دليل القاعدة، والمستخدم يراها في جدولٍ
# أمامه في الصفحة نفسها.
#
# والسبب ترتيب المصادر: الاكتشاف الحيّ أوّلاً، وهو نداءُ شبكة يتعثّر
# بحدّ معدّل أو انقطاع، فيسقط مباشرةً إلى الملف. فقائمةٌ **جُلبت
# وحُفظت ورُئيت** كانت أدنى من نداءٍ عابر.
#
# الترتيب الصحيح: الدليل ← الاكتشاف الحيّ ← الكون المحفوظ ← الملف.
scan_code = code_of("web/dashboard/management/commands/scan.py")
check("الدليل مصدرٌ للكون", "_known_symbols" in scan_code)
check("  ويُسجَّل باسمه", '"directory"' in scan_code)
check("  ويسبق الاكتشاف الحيّ",
      scan_code.index("_known_symbols(cfg.name)")
      < scan_code.index("usdt_universe("))
check("  و --top يقصّه أيضاً",
      "symbols = symbols[:cap]" in scan_code)
# مرتَّب بقيمة التداول: القصّ يأخذ الأنشط لا الأبجدي
check("  والترتيب بقيمة التداول",
      '"-quote_value"' in scan_code)
# جدولٌ غير مهاجَر يجب ألّا يمنع مسحاً
check("  وغيابه لا يرمي", "return []" in scan_code)

# والقائمة الاحتياطية أُفرغت: سقوطٌ صامت إلى عشرة أسهم يتنكّر
# في ثوب نجاح، والفراغ يجعل الفشل يُعلن نفسه.
saudi = yaml.safe_load((ROOT / "config" / "saudi.yaml").read_text(encoding="utf-8"))
check("والسعودي بلا قائمة احتياطية تُخفي الفشل",
      not (saudi.get("symbols") or []),
      f"{len(saudi.get('symbols') or [])} رمزاً ما زالت")

# واللوحة تُعلن أنّ الكون من الدليل لا من اكتشافٍ حيّ
views_code = code_of("web/dashboard/views.py")
check("  واللوحة لا تُنذر على الدليل",
      '"directory"' not in views_code.split("universe_degraded")[1][:120])


failed = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not failed
      else f"✗ فشل {len(failed)} من {len(results)}")
sys.exit(1 if failed else 0)
