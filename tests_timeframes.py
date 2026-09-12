# -*- coding: utf-8 -*-
"""الفريمات: ما يُعرَض في الواجهة وما يُمسح فعلاً.

═══ العطب المُبلَّغ عنه ═══

«في السوق الأمريكي الفريم ٤ ساعات لا يعمل».

وكان يعمل تماماً كما بُرمج — وهذا هو العطب. ثلاث طبقاتٍ اجتمعت:

    ١) ``config/us.yaml`` يذكر ``timeframes: ["1d"]``
    ٢) والمسح يقرأ ``cfg.timeframes[0]`` وحده — فالقائمة كانت
       تعِد بما لا تفي به: من كتب فريمين مُسح له واحد
    ٣) والواجهة تعرض الفريمات الخمسة لكل سوق، ثمّ يستبدل الخادم
       المطلوبَ بأحدث ما مُسح **بلا كلمة**

فمن اختار ٤ ساعات رأى بياناتٍ يومية. والنتيجة المقيسة: صفر جولة
مسحٍ لـ ‏us/4h منذ إنشاء النظام — بينما شموعه تُزامَن كل عشر
دقائق وتُخزَّن كاملة (٣٢٣ رمزاً).

═══ والاستبدال الصامت أسوأ من الفراغ ═══

الفراغ يدفع للسؤال. والاستبدال الصامت يُقرأ **جواباً**: أرقامٌ
معروضة تحت عنوان فريمٍ آخر، بلا خطأ ولا تحذير.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner.live import UI_TIMEFRAMES          # noqa: E402

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


VIEWS = (ROOT / "web" / "dashboard" / "views.py").read_text(encoding="utf-8")
CRON = (ROOT / "web" / "dashboard" / "cron.py").read_text(encoding="utf-8")
APP = (ROOT / "web" / "dashboard" / "static" / "dashboard"
       / "app.js").read_text(encoding="utf-8")


def _fn(src: str, name: str) -> str:
    """جسدُ دالّة بلا تعليقاتها — الفحص على الكود لا على شرحه."""
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == name)
    seg = ast.get_source_segment(src, fn) or ""
    doc = ast.get_docstring(fn, clean=False)
    if doc:
        seg = seg.replace(doc, "", 1)
    return "\n".join(l for l in seg.splitlines()
                     if not l.strip().startswith("#"))


# ═══ ١) القائمة تُقرأ كلّها لا أوّلها ═══
#
# ``timeframes`` قائمة. وقراءة ``[0]`` وحده تجعلها وعداً كاذباً:
# يكتب المستخدم فريمين ويُمسح له واحد، بلا خطأ.
h_scan = _fn(CRON, "_h_scan")
check("١ المسح يقرأ القائمة كلّها", "cfg.timeframes" in h_scan)
check("  ولا يكتفي بأوّلها", "timeframes[0]" not in h_scan)
check("  ويمرّ عليها", "for one in frames" in h_scan)
# وحمولة المهمّة تعلو الملفّ: تسمح بفصل الفريم الثقيل في مهمّة
check("  والحمولة تعلو الإعداد",
      'payload.get("timeframe")' in h_scan and "if tf:" in h_scan)
# فشل فريمٍ لا يُسقط البقيّة
check("  وفشل فريم لا يُسقط غيره",
      "failed.append" in h_scan and "if not done:" in h_scan)
# والازدحام يوقف الحلقة: القفل واحد
check("  والازدحام يوقف الحلقة", "raise JobBusy" in h_scan)


# ═══ ٢) لا استبدال صامت ═══
api = _fn(VIEWS, "api_results")
check("٢ التنويه يُحسب", "_timeframe_notice(" in api)
check("  ويُعاد مع النتائج", '"notice": notice' in api)
check("  والمطلوب يُعاد أيضاً", '"requested_timeframe"' in api)
check("  والفراغ يُعلَّل", "لا جولة مسحٍ" in VIEWS)

notice = _fn(VIEWS, "_timeframe_notice")
# يفرّق بين «غير مُهيّأ» و«مُهيّأ ولم يُمسح» — والفرق يغيّر الفعل
check("  ويفرّق غير المهيّأ عن غير الممسوح",
      "requested not in configured" in notice)
check("  ولا تنويه إن تطابقا",
      "if not requested or requested == served" in notice)
check("  ويقول ما يفعله المستخدم",
      "config/" in notice and "yaml" in notice)


# ═══ ٣) الفريم المطلوب يُتحقَّق منه ═══
#
# يدخل نصّ التنويه، والتنويه يُعرض. فنصٌّ من شريط العنوان كان
# يصل الـDOM.
check("٣ المطلوب محصورٌ بالمسموح", "requested_tf not in UI_TIMEFRAMES" in api)
check("  ويُلغى إن خالف", "requested_tf = None" in api)
# وحزامٌ ثانٍ في الواجهة
check("  والواجهة تهرب النصّ", "function esc(" in APP)
check("  وتستعمله في التنويه", "esc(n.why)" in APP)


# ═══ ٤) الواجهة تعرض التنويه ═══
check("٤ تلتقطه من الاستجابة", "state.notice = d.notice" in APP)
check("  وترسمه", "function paintTimeframeNotice" in APP)
check("  ويُقدَّم على أسباب الفراغ الأخرى",
      APP.index("if (state.notice && state.notice.why)")
      < APP.index("state.liquidity !== \"all\""))
tpl = (ROOT / "web" / "dashboard" / "templates" / "dashboard"
       / "scanner.html").read_text(encoding="utf-8")
check("  وله موضع في القالب", 'id="tf-notice"' in tpl)


# ═══ ٥) كل فريمٍ مُهيّأ مدعومٌ في الواجهة والمحوّل ═══
#
# فريمٌ في الإعداد لا تعرضه الواجهة يُمسح ولا يُرى. والعكس —
# وهو ما وقع — يُعرض ولا يُمسح.
for market in ("us", "crypto", "saudi"):
    cfg = yaml.safe_load((ROOT / "config" / f"{market}.yaml").read_text(
        encoding="utf-8"))
    tfs = cfg.get("timeframes") or []
    check(f"٥ {market}: له فريم مسح", bool(tfs), str(tfs))
    bad = [t for t in tfs if t not in UI_TIMEFRAMES]
    check(f"  و{market} كلّها معروضة في الواجهة", not bad, str(bad))

us = yaml.safe_load((ROOT / "config" / "us.yaml").read_text(encoding="utf-8"))
check("  والأمريكي يشمل 4h الآن", "4h" in (us.get("timeframes") or []),
      str(us.get("timeframes")))


# ═══ ٦) المحوّل يدعم ما يُطلب منه ═══
alp = (ROOT / "scanner" / "adapters" / "alpaca.py").read_text(encoding="utf-8")
check("٦ ‏Alpaca يدعم 4h", '"4h": "4Hour"' in alp)
# ويرفض غير المدعوم بسببٍ مسمّى لا بصمت
check("  ويرفض غيره بسببه", "فريم غير مدعوم في Alpaca" in alp)


bad = 0
for ok, name, extra in results:
    if not ok:
        bad += 1
    print(("✓ " if ok else "✗ ") + name
          + ("" if ok or not extra else "  ← " + extra))
print()
print(f"✗ فشل {bad} من {len(results)}" if bad else f"✓ {len(results)} اختباراً")
sys.exit(1 if bad else 0)
