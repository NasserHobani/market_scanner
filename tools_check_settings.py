# -*- coding: utf-8 -*-
"""كل إعداد في الصفحة له أثر حقيقي في الكود.

صفحة إعدادات تعرض حقلاً لا يقرأه أحد أسوأ من غيابه: المستخدم يعدّله
ويظنّ أن شيئاً تغيّر. هذا الفحص يمنع ذلك آلياً.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner import settings_schema as S

# مفاتيح تُقرأ عبر مساعدات في appsettings بدل ذكر اسمها في المستهلك
VIA_HELPER = {
    "tier_high": "liquidity_tiers()", "tier_mid": "liquidity_tiers()",
    "tier_low": "liquidity_tiers()",
    "min_rvol": "breakout_kwargs()", "lookback": "breakout_kwargs()",
    "stop_atr": "breakout_kwargs()", "target_atr": "breakout_kwargs()",
    "min_body": "breakout_kwargs()", "low_buffer": "breakout_kwargs()",
    "enabled": "breakout_enabled()",
    "maker_bps": "cost_model()", "taker_bps": "cost_model()",
    "slippage_scale": "cost_model()",
}

SKIP = {"settings_schema.py", "appsettings.py", "tools_check_settings.py",
        "tests_settings.py"}


def sources():
    for base in ("web/dashboard", "scanner"):
        for f in (ROOT / base).rglob("*.py"):
            if f.name not in SKIP and "migrations" not in f.parts:
                yield f


def main() -> int:
    files = list(sources())
    texts = {f: f.read_text(encoding="utf-8") for f in files}
    helper_text = (ROOT / "web" / "dashboard" / "appsettings.py").read_text("utf-8")
    schema_text = (ROOT / "scanner" / "settings_schema.py").read_text("utf-8")

    orphan, ok = [], []
    for key in S.FIELDS:
        where = [f.name for f, t in texts.items()
                 if re.search(rf'["\']{re.escape(key)}["\']', t)]
        if not where and key in VIA_HELPER:
            # السلسلة كاملة: المخطط يذكر المفتاح ← appsettings يعرّف
            # المساعد ← ملفٌ ما يستدعيه. كسر أي حلقة يُبلَّغ عنه.
            helper = VIA_HELPER[key].rstrip("()")
            in_schema = re.search(rf'["\']{re.escape(key)}["\']', schema_text)
            in_helper = f"def {helper}" in helper_text
            consumers = [f.name for f, t in texts.items() if helper in t]
            if in_schema and in_helper and consumers:
                where = [f"{VIA_HELPER[key]} ← {', '.join(sorted(set(consumers)))}"]
            elif not in_schema:
                where = []
                print(f"  ✗ {key}: المخطط لا يمرّره عبر {VIA_HELPER[key]}")
            elif not in_helper:
                where = []
                print(f"  ✗ {key}: {VIA_HELPER[key]} غير معرّف في appsettings")
        if where:
            ok.append((key, sorted(set(where))))
        else:
            orphan.append(key)

    for key, where in ok:
        print(f"  ✓ {key:<20} {', '.join(where)[:70]}")
    if orphan:
        print("\n✗ إعدادات معروضة بلا أي مستهلك:")
        for key in orphan:
            print(f"    · {key} — «{S.FIELDS[key].label}»")

    # والعكس: القالب يعرض كل الحقول
    tpl = (ROOT / "web" / "dashboard" / "templates" / "dashboard"
           / "settings.html").read_text("utf-8")
    if "{% for f in g.fields %}" not in tpl:
        print("\n✗ القالب لا يمرّ على حقول المخطط — قد تُخفى حقول")
        orphan.append("__template__")

    print("\n" + ("✗ العقد مكسور" if orphan
                  else f"✓ {len(ok)} إعداداً كلها مستهلَكة"))
    return 1 if orphan else 0


if __name__ == "__main__":
    sys.exit(main())
