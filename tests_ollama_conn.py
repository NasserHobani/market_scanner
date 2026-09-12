# -*- coding: utf-8 -*-
"""اختبارات اتصال Ollama — بلا Django ولا شبكة.

العطب الذي تحرسه: «الاختبار يفشل وOllama يعمل خارج النظام». وله
سببان يعطيان الرسالة نفسها:

  ١. ``urllib`` يمرّر 127.0.0.1 عبر البروكسي المضبوط في البيئة أو
     سجلّ ويندوز. المتصفّح و curl يستثنيان المحلي تلقائياً فيعملان.
  ٢. اسم النموذج كان يُستبدل بصمت بـ ``qwen3:8b``، فمن ثبّت غيره
     يُسأل عن نموذج لا يملكه.

    python tests_ollama_conn.py
"""
from __future__ import annotations

import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner.ai_local import health as H
from scanner.ai_local import http as LH
from scanner.ai_local.config import LocalAIConfig
from scanner.ai_local.model_registry import is_known, resolve_model

results: list[tuple[bool, str, str]] = []


def check(name, cond, extra=""):
    results.append((bool(cond), name, str(extra)))


# ══════════════════ تجاوز البروكسي

check("‏127.0.0.1 يُعدّ محلياً", LH.is_local("http://127.0.0.1:11434"))
check("و localhost كذلك", LH.is_local("http://localhost:11434"))
check("والشبكة الخاصة كذلك", LH.is_local("http://192.168.1.50:11434"))
check("و ::1 كذلك", LH.is_local("http://[::1]:11434"))
check("والنطاق العام ليس محلياً",
      not LH.is_local("https://api.anthropic.com"),
      "تجاوز البروكسي للعام يكسر بيئةً تحتاجه فعلاً")
check("وعنوان معطوب لا يُسقط الفحص", LH.is_local("::::") is False)
check("وعنوان فارغ كذلك", LH.is_local("") is False)

# ‏build_opener يُسقط ProxyHandler الفارغ من قائمة المعالجات بدل
# الاحتفاظ به — لأنه بلا دوال ``*_open``. والأثر هو المطلوب تماماً:
# المعالج الافتراضي (الذي يقرأ البيئة والسجلّ) لا يُضاف أصلاً، فلا
# بروكسي في المسار. الفحص على السلوك لا على البنية.
check("الفاتح المباشر بلا أي معالج بروكسي",
      not any(isinstance(h, urllib.request.ProxyHandler)
              for h in LH._direct_opener.handlers),
      [type(h).__name__ for h in LH._direct_opener.handlers])
check("بينما الفاتح الافتراضي يحمله",
      any(isinstance(h, urllib.request.ProxyHandler)
          for h in urllib.request.build_opener().handlers),
      "المقارنة تُثبت أن الفرق مقصود لا صدفة")

# ══════════════════ اسم النموذج لا يُستبدل بصمت

check("الاسم المعروف يُحترم", resolve_model("qwen3:8b") == "qwen3:8b")
check("والاسم غير المعروف **يُحترم أيضاً**",
      resolve_model("qwen2.5:7b") == "qwen2.5:7b",
      "الاستبدال الصامت كان يسأل عن نموذج غير مثبّت")
check("و llama3.1 لا يصير qwen", resolve_model("llama3.1:8b") == "llama3.1:8b")
check("و qwen3:latest يبقى كما هو",
      resolve_model("qwen3:latest") == "qwen3:latest")
check("والفارغ وحده يأخذ افتراضاً", resolve_model("") == "qwen3:8b")
check("والمسافات تُنظَّف", resolve_model("  qwen3:4b  ") == "qwen3:4b")
check("والسجلّ صار دليلاً لا حارساً",
      is_known("qwen3:8b") and not is_known("llama3.1:8b"),
      "يقترح في القائمة ولا يمنع ما سواه")


# ══════════════════ فحص الصحّة

def cfg(model="qwen3:8b", on=True):
    return LocalAIConfig(local_enabled=on, ollama_enabled=on,
                         ollama_base_url="http://127.0.0.1:11434",
                         local_default_model=model)


def tags(*names):
    return lambda url: {"models": [{"name": n} for n in names]}


h = H.check_ollama_health(cfg(), http_get=tags("qwen3:8b", "llama3.1:8b"))
check("الوصول يُسجَّل", h["ollama_reachable"] is True)
check("والمطابقة التامّة تُكتشف",
      h["model_available"] and h["exact_match"] and not h["error"])
check("وقائمة المثبَّت تُعاد", len(h["models"]) == 2)

h = H.check_ollama_health(cfg("qwen3"), http_get=tags("qwen3:8b"))
check("واسم بلا وسم يطابق المثبَّت",
      h["model_available"] and h["matched_model"] == "qwen3:8b",
      "‏Ollama يسمّي بالوسم الكامل والمستخدم يكتب الاسم")
check("لكن يُقال إنه ليس تطابقاً تامّاً",
      not h["exact_match"] and "سيُستعمل" in h["error"],
      "العمل بنموذج غير المطلوب يجب أن يُعلَن لا يُخفى")

h = H.check_ollama_health(cfg("qwen3:8b"), http_get=tags("llama3.1:8b"))
check("والنموذج الغائب يُقال بوضوح", not h["model_available"])
check("مع ذكر المتاح فعلاً", "llama3.1:8b" in h["error"],
      "«غير موجود» وحدها لا تدلّ على ما يجب فعله")

h = H.check_ollama_health(cfg(), http_get=tags())
check("وبلا نماذج يُقترح الأمر", "ollama pull" in h["error"])

h = H.check_ollama_health(cfg(on=False), http_get=tags("qwen3:8b"))
check("والمعطَّل يُقال معطَّلاً لا مقطوعاً",
      not h["enabled"] and "disabled" in h["error"].lower())


def boom(url):
    raise urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))


h = H.check_ollama_health(cfg(), http_get=boom)
check("وتعذّر الوصول يُنتج تشخيصاً",
      not h["ollama_reachable"] and h.get("hint"),
      "رسالة مبتورة تجعل البحث ساعةً بدل ثانية")
check("والتلميح يذكر ollama serve", "ollama serve" in h.get("hint", ""))

# ══════════════════ «متّصل» ≠ «جاهز»

t = H.test_ollama_connection(cfg("qwen3:8b"), http_get=tags("llama3.1:8b"))
check("الخادم المستجيب بنموذج ناقص = متّصل",
      t["connected"] is True,
      "خلطهما كان يقول «غير متّصل» عن خادم يعمل تماماً")
check("لكنه ليس جاهزاً", t["ready"] is False)
check("والسبب مذكور", "llama3.1" in t["error"])

t = H.test_ollama_connection(cfg(), http_get=tags("qwen3:8b"))
check("والوصول مع النموذج = جاهز", t["connected"] and t["ready"])

# ══════════════════ التشخيص المفصّل

d = LH.diagnose("http://127.0.0.1:1/api/tags", timeout=1.0)
check("منفذ مغلق يُشخَّص", not d["ok"] and d["reason"])
check("ويُقترح الحلّ", "ollama" in d["hint"].lower() or d["hint"])
check("والتشخيص يعرف أنه محلي", d["local"] is True)
check("ويذكر البروكسي إن وُجد", "proxy_env" in d)

# ══════════════════ الربط

prov = (ROOT / "scanner" / "ai_local" / "ollama_provider.py").read_text("utf-8")
for name, frag in (("الجلب", "from .http import get_json"),
                   ("الإرسال", "from .http import post_json"),
                   ("البثّ", "from .http import open_stream")):
    check(f"المزوّد يستعمل الطبقة في {name}", frag in prov,
          "‏urlopen مباشرةً يعيد عطب البروكسي")
check("ولا urlopen مباشر باقٍ في المزوّد",
      "urllib.request.urlopen" not in prov,
      "مسار واحد متبقٍّ يُعيد العطب من حيث لا يُتوقَّع")

hl = (ROOT / "scanner" / "ai_local" / "health.py").read_text("utf-8")
check("وفحص الصحّة كذلك", "from .http import get_json" in hl)

tool = (ROOT / "tools_check_ollama.py").read_text("utf-8")
check("وثمّة أداة تشخيص مستقلّة", "def main" in tool)
check("تفصل الاتصال عن النموذج عن التوليد",
      all(k in tool for k in ("── الاتصال ──", "── النماذج المثبَّتة ──",
                              "── نداء تجريبي ──")),
      "الفصل هو ما يحوّل «لا يعمل» إلى سبب محدَّد")


bad = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not bad
      else f"✗ فشل {len(bad)} من {len(results)}")
sys.exit(1 if bad else 0)
