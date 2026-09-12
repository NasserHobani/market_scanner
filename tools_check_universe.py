# -*- coding: utf-8 -*-
"""تشخيص اكتشاف الرموز — أين يتعثّر بالضبط.

═══ لماذا هذه الأداة ═══

السوق الأمريكي مضبوط على ``universe: auto`` أي «كل سهم فوق عشرين مليون
دولار يومياً» — قرابة سبعمئة سهم. وسجلّ القاعدة يقول: **عشرة رموز
متمايزة في كل تاريخ السوق**، وهي حرفياً قائمة ``symbols`` الاحتياطية في
``config/us.yaml``.

أي أن الاكتشاف لم ينجح قطّ، والمسح ارتدّ إلى القائمة في كل مرّة صامتاً.

والاكتشاف سلسلة من أربع حلقات، وأيّ واحدة تكسرها تعطي النتيجة نفسها:

    ١. المفاتيح موجودة وصالحة
    ٢. ``/v2/assets`` يعيد الأصول القابلة للتداول
    ٣. الشموع اليومية تصل لحساب الحجم
    ٤. عدد كافٍ يتجاوز عتبة ``min_quote_volume``

وحلقة مكسورة في الرابعة (عتبة عالية) تختلف علاجاً عن مكسورة في الأولى
(مفتاح خاطئ) — والرسالة الواحدة «تعذّر اكتشاف الرموز» لا تفرّق بينهما.

    الاستعمال:  python tools_check_universe.py [us|crypto|saudi]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

OK, BAD, WARN = "✓", "✗", "!"


def _line(mark: str, text: str, detail: str = "") -> None:
    print(f"  {mark} {text}" + (f" — {detail}" if detail else ""))


def main() -> int:
    market = (sys.argv[1] if len(sys.argv) > 1 else "us").strip().lower()
    print("=" * 58)
    print(f"تشخيص اكتشاف الرموز — سوق {market}")
    print("=" * 58)

    from scanner.config import load_market

    # مجلّد الإعدادات قابل للإزاحة: الاختبار يحتاج سوقاً على ``list``
    # ليتحقّق من رسالة «معطّل بالإعداد»، وكان يستعير ملفاً حقيقياً
    # لذلك — فانكسر يوم تحوّل السوق السعودي إلى ``auto``. الاختبار
    # لا ينبغي أن يرهن نفسه بقرار إعداديّ يتغيّر.
    cfg_root = Path(os.environ.get("SCANNER_CONFIG_DIR") or (ROOT / "config"))
    cfg_path = cfg_root / f"{market}.yaml"
    if not cfg_path.exists():
        _line(BAD, f"ملف السوق غير موجود: {cfg_path.name}")
        return 1
    cfg = load_market(cfg_path)

    print("\n[١] الإعداد")
    _line(OK, f"المحوّل: {cfg.adapter}")
    _line(OK, f"الكون: {cfg.universe}")
    _line(OK, f"العتبة: {cfg.min_quote_volume:,.0f}$")
    _line(OK, f"السقف top_n: {cfg.top_n or 'بلا'}")
    _line(OK, f"قائمة الملف الاحتياطية: {len(cfg.symbols or [])} رمزاً")

    if cfg.universe == "list":
        _line(WARN, "الكون مضبوط على list — الاكتشاف معطّل بالإعداد لا بعطب")
        print("\n  لتفعيله: غيّر universe إلى auto في " + cfg_path.name)
        return 0

    from scanner.adapters import get_adapter

    # الاكتشاف قد يكون من محوّل غير محوّل الشموع. فحص الخطأ في
    # المحوّل الخطأ يُنتج تشخيصاً يبدو سليماً وهو يفحص شيئاً آخر.
    fetch_name = cfg.adapter
    disc_name = getattr(cfg, "universe_adapter", "") or cfg.adapter
    if disc_name != fetch_name:
        _line(OK, f"محوّل الشموع: {fetch_name}")
        _line(OK, f"محوّل الاكتشاف: {disc_name}  ← المفحوص هنا")

    adapter = get_adapter(disc_name)
    if not hasattr(adapter, "usdt_universe"):
        _line(BAD, f"المحوّل {disc_name} لا يدعم الاكتشاف")
        return 1

    # ── طبقات الاشتراك عند سهمك ──
    #
    # ‏/companies/‎ مجاني و‎/quotes/‎ و‎/historical/‎ يحتاجان Starter.
    # وفشل الأخيرَين لا يعني فشل الاكتشاف — يعني فقدان الترتيب أو
    # الشموع. خلطها هو ما جعل حساباً مجانياً يظنّ أن كل شيء معطّل.
    if disc_name == "sahmk" and hasattr(adapter, "test_connection"):
        print("\n[١.٥] طبقات اشتراك سهمك")
        try:
            t = adapter.test_connection()
        except Exception as exc:  # noqa: BLE001
            t = {"ok": False, "error": str(exc)}
        if not t.get("ok"):
            _line(BAD, "‏/companies/‎ فشل — وهو مجاني",
                  str(t.get("error"))[:160])
            # «المفتاح غير مضبوط» جوابٌ ناقص: هل الملف غائب؟ أم
            # موجود بلا المفتاح؟ أم يحويه ولم يُحمَّل؟ الفروق الثلاثة
            # علاجها مختلف، وجمعها في رسالة واحدة أرسل المستخدم
            # يبحث عن مفتاحٍ هو في مكانه أصلاً.
            from scanner.env import describe_key, env_status

            st = env_status()
            where = ("موجود · %d مفتاحاً" % len(st["keys"])
                     if st["exists"] else "غير موجود")
            print("\n  حالة المفتاح:")
            print(f"    SAHMK_API_KEY: {describe_key('SAHMK_API_KEY')}")
            print(f"    ملف .env: {st['path']} ({where})")
            print("\n  أغلب الأسباب:")
            print("    • SAHMK_API_KEY خاطئ أو منتهٍ")
            print("    • حجب شبكي على api.sahmk.sa")
            print("    • الحساب موقوف — افحصه في لوحة سهمك")
            return 1
        _line(OK, f"‏/companies/‎ (مجاني): {t.get('companies', 0)} شركة")
        if t.get("quotes"):
            _line(OK, "‏/quotes/‎ (Starter+): متاح — الترتيب بالحجم يعمل")
        else:
            _line(WARN, "‏/quotes/‎ (Starter+): غير متاح",
                  str(t.get("quotes_error"))[:90])
            print("      ← لا يمنع الاكتشاف. السوق يُدرَج كاملاً بلا ترتيب.")
        if t.get("historical"):
            _line(OK, "‏/historical/‎ (Starter+): متاح")
        else:
            _line(WARN, "‏/historical/‎ (Starter+): غير متاح",
                  str(t.get("historical_error"))[:90])
            if fetch_name == "sahmk":
                print("      ← وهذا يمنع الشموع. اجعل adapter: yahoo "
                      "و universe_adapter: sahmk")
            else:
                print(f"      ← لا يضرّ: الشموع تأتي من {fetch_name}")

    # ── ٢) المفاتيح ──
    print("\n[٢] المفاتيح")
    key = getattr(adapter, "key", None)
    secret = getattr(adapter, "secret", None)
    if hasattr(adapter, "key"):
        if not key or not secret:
            _line(BAD, "المفاتيح غير مضبوطة",
                  "أضفها في صفحة الإعدادات أو ملف .env")
            return 1
        _line(OK, f"المفتاح موجود ({str(key)[:2]}…{str(key)[-2:]})")
        if hasattr(adapter, "trading_host"):
            try:
                _line(OK, f"مضيف التداول المستنتَج: {adapter.trading_host()}")
            except Exception as exc:  # noqa: BLE001
                _line(WARN, "تعذّر استنتاج المضيف", str(exc)[:80])
    else:
        _line(OK, "المحوّل لا يحتاج مفاتيح")

    # ── ٣) الأصول ──
    print("\n[٣] الأصول القابلة للتداول")
    assets = []
    if hasattr(adapter, "assets"):
        try:
            assets = adapter.assets()
            if not assets:
                _line(BAD, "الرد فارغ",
                      "المفتاح صالح لكن لا أصول — تحقّق من نوع الحساب")
                return 1
            _line(OK, f"{len(assets)} أصلاً")
            print("      " + "، ".join(a["symbol"] for a in assets[:8]) + " …")
        except Exception as exc:  # noqa: BLE001
            _line(BAD, "فشل جلب الأصول", str(exc)[:200])
            print("\n  هذه هي الحلقة المكسورة. أغلب الأسباب:")
            print("    • مفتاح حساب ورقي على مضيف حقيقي أو العكس (401)")
            print("    • المفتاح أُلغي أو أُعيد توليده")
            print("    • حجب شبكي على api.alpaca.markets")
            return 1
    else:
        _line(OK, "المحوّل يكتشف الرموز بلا نداء أصول منفصل")

    # ── ٤) الأحجام والعتبة ──
    print("\n[٤] الأحجام والعتبة")
    print("      (قد يستغرق دقيقة — يجلب شموع عشرين يوماً لكل الأصول)")
    try:
        symbols = adapter.usdt_universe(cfg.min_quote_volume,
                                        top_n=cfg.top_n)
    except Exception as exc:  # noqa: BLE001
        _line(BAD, "فشل حساب الأحجام", str(exc)[:200])
        print("\n  الأصول تصل لكن الشموع لا. الأسباب الغالبة:")
        print("    • حدّ الطلبات (429) — قلّل workers أو أعد المحاولة")
        print("    • التغذية غير مصرَّح بها لهذا الاشتراك")
        return 1

    volumes = getattr(adapter, "last_volumes", {}) or {}
    _line(OK if len(symbols) > 20 else BAD,
          f"اجتاز العتبة: {len(symbols)} رمزاً")

    if volumes:
        top = sorted(volumes.items(), key=lambda p: p[1], reverse=True)[:5]
        print("      الأعلى حجماً:")
        for sym, qv in top:
            print(f"        {sym:8} {qv:>18,.0f}$")

    fallback = len(cfg.symbols or [])
    print("\n" + "=" * 58)
    if len(symbols) <= fallback:
        print(f"{BAD} الاكتشاف يعطي {len(symbols)} رمزاً فقط — "
              f"أي بحجم القائمة الاحتياطية ({fallback}) أو أقلّ.")
        if volumes:
            above = sum(1 for v in volumes.values() if v >= cfg.min_quote_volume)
            print(f"\n  حُسب الحجم لـ {len(volumes)} رمزاً، "
                  f"منها {above} فوق العتبة.")
            if above > len(symbols):
                print(f"  والمسح يأخذ {cfg.top_n} فقط (‏top_n) — "
                      "ارفعه إن أردت أكثر.")
            elif above < 50:
                print(f"  العتبة {cfg.min_quote_volume:,.0f}$ عالية على ما وصل "
                      "من بيانات. خفّضها أو تحقّق من اكتمال الشموع.")
        return 1

    print(f"{OK} الاكتشاف سليم: {len(symbols)} رمزاً "
          f"(القائمة الاحتياطية {fallback}).")
    print("  إن كانت اللوحة ما زالت تعرض القليل، فالسبب في المسح لا في "
          "الاكتشاف — راجع بانر «مصدر الرموز» في صفحة الماسح.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
