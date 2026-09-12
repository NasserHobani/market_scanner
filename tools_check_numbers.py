# -*- coding: utf-8 -*-
"""لا رقم سعري يُطبع خاماً في قالب.

السبب من واقعة حقيقية: جدول الصفقات كان يعرض «0.0759999999999»
مبتوراً في خلية ضيّقة بدل «0.076». ورقم بأربع عشرة خانة لا يوهم
بدقة زائدة فحسب — بل يُقرأ خطأً حين يُبتر.

المشروع فيه تنسيق موحّد (scanner/formatting.py) تستعمله كل شاشة
تُبنى في JavaScript؛ هذا الفحص يفرضه على ما يُبنى في الخادم أيضاً.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

TPL = Path(__file__).parent / "web" / "dashboard" / "templates" / "dashboard"

# حقول تحمل سعراً أو مضاعفاً — يجب أن تمرّ بمرشّح عرض
PRICE_FIELDS = (
    "entry", "stop", "target1", "target", "close", "entry_price",
    "exit_price", "trigger_price", "last_price", "price",
)
R_FIELDS = ("r_multiple", "expectancy", "total_r", "avg_r", "avg_win_r",
            "avg_loss_r", "best_r", "worst_r")

OK_FILTERS = ("price", "rmult", "num", "ratio", "pct", "money",
              "date", "time", "default_if_none:\"—\"|price")

VAR = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


def offenders(text: str, fields, kind: str) -> list[str]:
    out = []
    for m in VAR.finditer(text):
        body = m.group(1)
        parts = [p.strip() for p in body.split("|")]
        name = parts[0].split(".")[-1].strip()
        if name not in fields:
            continue
        filters = {p.split(":")[0].strip() for p in parts[1:]}
        if filters & set(OK_FILTERS):
            continue
        out.append(f"{{{{ {body} }}}}  ({kind})")
    return out


def main() -> int:
    bad: list[str] = []
    for f in sorted(TPL.glob("*.html")):
        text = f.read_text(encoding="utf-8")
        # التلميحات تُظهر القيمة الخام عمداً — تُستثنى
        text = re.sub(r'title="\{\{[^"]*\}\}"', "", text)
        found = (offenders(text, PRICE_FIELDS, "سعر")
                 + offenders(text, R_FIELDS, "مضاعف R"))
        print(("✗ " if found else "✓ ") + f.name)
        bad += [f"{f.name}: {x}" for x in found]

    print()
    if bad:
        print("أرقام تُطبع خاماً بلا مرشّح عرض:")
        for b in bad:
            print("  ✗ " + b)
        print("\nاستعمل |price للأسعار و|rmult لمضاعف R "
              "(‏{% load fmt %} في أعلى القالب).")
        return 1
    print("✓ كل الأرقام السعرية تمرّ بمرشّح عرض")
    return 0


if __name__ == "__main__":
    sys.exit(main())
