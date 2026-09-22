# -*- coding: utf-8 -*-
"""هل LightGBM يعمل على هذه الآلة؟ — جوابٌ قاطع في سطرٍ واحد.

    docker exec <web> python tools_doctor_lgb.py

═══ لماذا تلزم أداة ═══

«لا يعمل» له معنيان تخلطهما الشاشة:

    ١. المكتبة غائبة    → ارتدّ الحساب إلى انحدارٍ لوجستيّ
    ٢. المكتبة تعمل     → النموذج **خسر** أمام خطّ الأساس فرُفض

والثاني ليس عطباً: هو النظام يفعل ما بُني له. وتشخيصُه كعطبٍ يقود
إلى «إصلاح» ما ليس مكسوراً — أي إلى تعطيل البوّابة التي تمنع
ضجيجاً مصقولاً من أن يصير توصية.

وهذه الأداة تفصل بينهما بلا تخمين، وعلى **الآلة التي تسأل عنها**:
فحصٌ على جهازك يقيس بايثونَ آخر ومكتباتٍ أخرى.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))


def main() -> int:
    print(__doc__.strip().splitlines()[0])
    print()
    print(f"بايثون {sys.version.split()[0]} · {sys.executable}")

    # ── ١) الاستيراد ──
    #
    # ‏libgomp غيابُه هو السبب الأشهر: المكتبة مثبَّتة بـpip
    # والاستيراد يفشل عند تحميل ‎.so‎ — فتبدو غير مثبّتة.
    try:
        import lightgbm as lgb

        print(f"✓ lightgbm {lgb.__version__}")
        ok_import = True
    except Exception as exc:  # noqa: BLE001
        print(f"✗ تعذّر الاستيراد — {type(exc).__name__}: {str(exc)[:160]}")
        if "libgomp" in str(exc):
            print("  السبب: حزمة OpenMP ناقصة.")
            print("  الصورة تثبّتها في Dockerfile (libgomp1) — فإن ظهر")
            print("  هذا فالصورة قديمة: أعد البناء بلا ذاكرة مؤقّتة.")
        else:
            print("  التثبيت: pip install -r requirements-ai.txt")
        ok_import = False

    # ── ٢) ما تراه الشاشة ──
    try:
        from scanner.btc import direction

        print(f"  والعلَم الذي تقرؤه الشاشة: HAS_LGB = {direction.HAS_LGB}")
        if direction.HAS_LGB != ok_import:
            print("  ⚠ العلَم لا يطابق الاستيراد — وحدةٌ حُمِّلت قبل الإصلاح")
    except Exception as exc:  # noqa: BLE001
        print(f"✗ تعذّر تحميل scanner.btc.direction: {str(exc)[:120]}")
        return 1

    if not ok_import:
        print()
        print("⇒ المكتبة لا تعمل. الحساب يرتدّ إلى انحدارٍ لوجستيّ —")
        print("  وهو يعمل، لكنّ الشاشة كانت تسمّيه باسمه فقط.")
        return 1

    # ── ٣) تدريبٌ صغير: يعمل فعلاً لا يُستورَد فقط ──
    #
    # الاستيراد ينجح أحياناً ويسقط ``fit`` على خيوطٍ أو ذاكرة.
    import numpy as np

    try:
        x = np.random.default_rng(0).normal(size=(300, 4))
        y = (x[:, 0] + x[:, 1] > 0).astype(int)
        m = lgb.LGBMClassifier(n_estimators=20, num_leaves=7, verbose=-1)
        m.fit(x, y)
        acc = float((m.predict(x) == y).mean())
        print(f"✓ تدريبٌ تجريبيّ نجح — دقّة {acc * 100:.0f}% على بياناتٍ "
              "مصطنعة (تحقّقٌ من التشغيل لا من الجودة)")
    except Exception as exc:  # noqa: BLE001
        print(f"✗ الاستيراد نجح والتدريب فشل — {type(exc).__name__}: "
              f"{str(exc)[:160]}")
        return 1

    # ── ٤) والتقرير الحقيقيّ ──
    print()
    print("═══ التقييم على بيانات البتكوين ═══")
    try:
        from scanner import storage
        from scanner.btc import report as btc_report

        any_row = False
        for tf in ("4h", "1d"):
            df = storage.load("crypto", "BTCUSDT", tf)
            if df is None or len(df) < 600:
                n = 0 if df is None else len(df)
                print(f"  {tf}: شموع غير كافية ({n}) — "
                      "لا علاقة للمكتبة بهذا")
                continue
            any_row = True
            rep = btc_report.direction_report(df)
            if not rep.get("valid"):
                print(f"  {tf}: {rep.get('reason', 'غير مقيَّم')}")
                continue
            print(f"  {tf}: {rep['model']} · دقّة {rep['accuracy']:.1f}% "
                  f"({rep['ci_low']:.1f}–{rep['ci_high']:.1f}) · "
                  f"عيّنة {rep['n_test']}")
            for k, v in rep["baselines"].items():
                mark = "◀ الأعلى" if k == rep["best_baseline"] else ""
                print(f"       خطّ أساس {k}: {v:.1f}% {mark}")
            print(f"       الفارق {rep['edge_points']:+.2f} نقطة · "
                  f"{'يُستعمل' if rep['usable'] else 'لا يُستعمل'}")

        if any_row:
            print()
            print("⇒ المكتبة تعمل. وإن كان الحكم «لا يُستعمل» فذلك لأنّ")
            print("  النموذج خسر أمام خطّ الأساس — وهي بوّابة الجودة")
            print("  تفعل ما بُنيت له، لا عطب.")
    except Exception as exc:  # noqa: BLE001
        print(f"  تعذّر التقييم: {type(exc).__name__}: {str(exc)[:140]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
