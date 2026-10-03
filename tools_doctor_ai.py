# -*- coding: utf-8 -*-
"""لماذا لا يردّ النداء المدفوع؟ — بالاختبار لا بالتخمين.

    docker exec <web> python tools_doctor_ai.py
    docker exec <web> python tools_doctor_ai.py --live

بلا ‎--live‎ لا يُرسَل شيء ولا يُنفَق قرش: تُفحَص الإعدادات
والمفتاح والسقوف والسجلّ. ومع ‎--live‎ يُرسَل نداءٌ صغيرٌ واحد
بتكلفةٍ تقارب فلساً — وهو الذي يقطع الشكّ.

═══ ولماذا أداة ═══

«اضغط فلا يحدث شيء» له أسباب كثيرة: مفتاحٌ غائب، أو سقفٌ بلغ،
أو إطفاءٌ من الإعدادات، أو مهمّةٌ كُتبت في ذاكرة عاملٍ ولم يرها
الآخر. والشاشة تعرض الأثر لا السبب.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def main() -> int:
    import django

    print(__doc__.strip().splitlines()[0])
    print()
    try:
        django.setup()
    except Exception as exc:  # noqa: BLE001
        print(f"✗ تعذّر إقلاع Django: {str(exc)[:160]}")
        return 1

    from scanner.ai_advisor import spend
    from scanner.ai_advisor.providers import together_provider as tp

    bad = 0

    # ── ١) المفتاح ──
    if tp.configured():
        k = tp.api_key()
        print(f"✓ المفتاح مضبوط ({len(k)} حرفاً، يبدأ بـ{k[:4]}…)")
    else:
        bad += 1
        print("✗ المفتاح غير مضبوط")
        print("  أضف TOGETHER_API_KEY في بورتينر ← Environment variables،")
        print("  ثمّ **Update the stack** — إعادة تشغيل الحاوية لا تكفي.")

    # ── ٢) التفعيل والنموذج ──
    on = spend.enabled()
    print(f"{'✓' if on else '✗'} التفعيل: {'مُفعَّل' if on else 'مُطفأ'}"
          f"{'' if on else ' — الإعدادات ← الذكاء المدفوع'}")
    if not on:
        bad += 1
    print(f"  النموذج: {tp.model_id()}")

    # ── ٣) السقوف والإنفاق ──
    try:
        s = spend.summary()
        lim = s["limits"]
        print(f"✓ السقوف: نداء ${lim['per_call_usd']:.3f} · "
              f"يوم ${lim['daily_usd']:.2f} · شهر ${lim['monthly_usd']:.2f}")
        print(f"  أُنفق: اليوم ${s['today_usd']:.4f} · "
              f"الشهر ${s['month_usd']:.4f} · {s['calls_total']} نداءً")
        if s["day_left"] <= 0:
            bad += 1
            print("  ✗ السقف اليوميّ بلغ — لا نداء حتى الغد أو رفعه.")
        if s["month_left"] <= 0:
            bad += 1
            print("  ✗ السقف الشهريّ بلغ.")
    except Exception as exc:  # noqa: BLE001
        bad += 1
        print(f"✗ تعذّرت قراءة الإنفاق: {str(exc)[:160]}")

    # ── ٤) مجلّد المهامّ ──
    #
    # ثلاثة عمّالٍ يتشاركونه. وتعذّر الكتابة يعني أنّ النداء يعمل
    # ولا تُعرَف نتيجته أبداً.
    try:
        from dashboard import together_views as tv

        d = tv._dir()
        probe = d / ".probe"
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        n = len(list(d.glob("*.json")))
        print(f"✓ مجلّد المهامّ قابل للكتابة ({d}) — {n} مهمّة محفوظة")
    except Exception as exc:  # noqa: BLE001
        bad += 1
        print(f"✗ تعذّرت الكتابة في مجلّد المهامّ: {str(exc)[:160]}")
        print("  وهذا يعني أنّ النداء يعمل ولا تُعرَف نتيجته.")

    # ── ٥) نداءٌ حقيقيّ ──
    if "--live" not in sys.argv:
        print()
        print("⇒ لم يُرسَل شيء. أضف ‎--live‎ لنداءٍ صغيرٍ حقيقيّ "
              "(تكلفته تقارب فلساً).")
        return 1 if bad else 0

    if not tp.configured() or not on:
        print()
        print("⇒ لا يُرسَل نداءٌ والإعداد ناقص.")
        return 1

    print()
    print("── نداءٌ تجريبيّ…")
    try:
        out = tp.TogetherProvider().complete(
            "أجب بـJSON فقط.",
            'أعد {"ok": true} ولا شيء غيره.',
            purpose="doctor", max_tokens=50)
        u = out["usage"]
        print(f"✓ وصل الردّ في {out['latency_ms']} م.ث")
        print(f"  النصّ: {out['text'][:120]}")
        print(f"  الوحدات: {u['tokens_in']} داخل · {u['tokens_out']} خارج")
        print(f"  التكلفة: ${u['cost']:.6f}")
        print()
        print("⇒ المزوّد يعمل. فإن بقي الزرّ بلا نتيجة فالعطب في")
        print("  نقل الحالة بين العمّال — راجع مجلّد المهامّ أعلاه.")
    except Exception as exc:  # noqa: BLE001
        bad += 1
        print(f"✗ {type(exc).__name__}: {str(exc)[:300]}")

    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
