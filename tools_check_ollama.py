# -*- coding: utf-8 -*-
"""تشخيص اتصال Ollama — يقول ما الخطأ بالضبط.

    python tools_check_ollama.py

═══ العطب الذي أوجده ═══

«اختبار الاتصال يفشل، وOllama يعمل تماماً خارج النظام».

سببان وجدناهما، وكلاهما يعطي الرسالة نفسها:

  ١. **البروكسي.** ``urllib`` يقرأ إعدادات البروكسي من البيئة ومن
     سجلّ ويندوز ويمرّر بها **كل** طلب — بما فيه ``127.0.0.1``.
     والمتصفّح و ``curl`` يستثنيان المضيف المحلي تلقائياً، فيعملان.

  ٢. **استبدال اسم النموذج بصمت.** كان السجلّ يستبدل أي اسم خارجه
     بـ ``qwen3:8b``، فمن ثبّت نموذجاً آخر كان النظام يسأل عن نموذج
     لا يملكه ويقول «غير متّصل».

هذه الأداة تفصل الأسباب: هل الخدمة تستجيب؟ وأي نماذج مثبّتة؟ وهل
المضبوط بينها؟
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))


def main() -> int:
    from scanner.ai_local import http as local_http

    print("═" * 62)
    print("تشخيص Ollama")
    print("═" * 62)

    # ── الإعدادات ──
    url = "http://127.0.0.1:11434"
    model = "qwen3:8b"
    enabled = None
    try:
        from scanner.ai_local.config import load_local_config

        cfg = load_local_config()
        url = cfg.ollama_base_url or url
        model = cfg.local_default_model or model
        enabled = cfg.local_enabled and cfg.ollama_enabled
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠ تعذّرت قراءة الإعدادات ({str(exc)[:60]}) — تُستعمل الافتراضات")

    print(f"\n  العنوان        : {url}")
    print(f"  النموذج المضبوط: {model}")
    if enabled is not None:
        mark = "✓" if enabled else "✗"
        print(f"  مفعَّل في الإعدادات: {mark}")
        if not enabled:
            print("     ⇒ فعّل «الذكاء المحلي» و«Ollama» من صفحة الإعدادات.")

    # ── البروكسي ──
    import urllib.request

    proxies = {k: v for k, v in urllib.request.getproxies().items() if k != "no"}
    print(f"\n  بروكسي في البيئة: {proxies or 'لا شيء'}")
    if proxies:
        print("     ⇒ العناوين المحلية تتجاوزه في هذا النظام الآن.")
        print("       (كان هذا سبب الفشل قبل الإصلاح)")

    # ── الوصول ──
    print("\n── الاتصال ──")
    d = local_http.diagnose(f"{url}/api/tags", timeout=6.0)
    if d["ok"]:
        print(f"  ✓ Ollama يستجيب ({d['latency_ms']:.0f} م.ث)")
    else:
        print(f"  ✗ لا يستجيب — {d['reason']}")
        if d.get("hint"):
            print(f"    {d['hint']}")
        print("\n  جرّب من الطرفية:  curl http://127.0.0.1:11434/api/tags")
        return 1

    # ── النماذج ──
    print("\n── النماذج المثبَّتة ──")
    try:
        tags = local_http.get_json(f"{url}/api/tags", timeout=6.0)
        names = [m.get("name", "") for m in (tags.get("models") or [])
                 if m.get("name")]
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ تعذّرت قراءة القائمة: {str(exc)[:120]}")
        return 1

    if not names:
        print("  ✗ لا نماذج مثبّتة.")
        print(f"     شغّل:  ollama pull {model}")
        return 1
    for n in names:
        mark = "◀ المضبوط" if n == model else ""
        print(f"  · {n}  {mark}")

    base = model.split(":")[0]
    exact = model in names
    same = [n for n in names if n.split(":")[0] == base]
    print()
    if exact:
        print(f"  ✓ «{model}» مثبَّت بالضبط")
    elif same:
        print(f"  ~ «{model}» غير موجود بهذا الوسم؛ سيُستعمل «{same[0]}»")
    else:
        print(f"  ✗ «{model}» غير مثبَّت ولا ما يشبهه")
        print(f"     إمّا:  ollama pull {model}")
        print(f"     أو غيّر «النموذج المحلي» في الإعدادات إلى: {names[0]}")
        return 1

    # ── نداء حقيقي ──
    print("\n── نداء تجريبي ──")
    use = model if exact else same[0]
    try:
        out = local_http.post_json(
            f"{url}/api/chat",
            {"model": use, "stream": False,
             "messages": [{"role": "user", "content": "قل: جاهز"}],
             "options": {"num_predict": 16}, "keep_alive": "30m"},
            timeout=120.0)
        text = ((out.get("message") or {}).get("content") or "").strip()
        print(f"  ✓ ردّ في {out.get('_latency_ms', 0) / 1000:.1f} ثانية")
        print(f"    «{text[:80]}»")
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ تعذّر النداء: {str(exc)[:160]}")
        print("    الخدمة تستجيب لكن التوليد فشل — قد يكون النموذج")
        print("    يُحمَّل الآن (أول نداء بطيء)، أو الذاكرة لا تكفيه.")
        return 1

    print("\n" + "═" * 62)
    print("✓ كل شيء سليم — الاتصال والنموذج والتوليد.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
