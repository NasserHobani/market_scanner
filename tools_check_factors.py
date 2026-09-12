# -*- coding: utf-8 -*-
"""عقد بين recommend.py و trades.py: كل عنوان بند له مفتاح عامل.

بند جديد في التوصية بلا مفتاح هنا يعني عاملاً يختفي من تحليل الأداء
بصمت — لا خطأ ولا تحذير، فقط شريحة ناقصة إلى الأبد. لذلك الفحص آلي.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / "scanner" / "analysis" / "recommend.py"
DST = ROOT / "web" / "dashboard" / "trades.py"


def vote_labels() -> set[str]:
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    out = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "vote" and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            out.add(node.args[0].value)
    return out


def mapped_labels() -> tuple[set[str], set[str]]:
    tree = ast.parse(DST.read_text(encoding="utf-8"))
    keys, labels = set(), set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        name = getattr(node.targets[0], "id", "")
        if name == "FACTOR_KEYS" and isinstance(node.value, ast.Dict):
            for k, v in zip(node.value.keys, node.value.values):
                keys.add(k.value)
                labels.add(v.value)
        if name == "FACTOR_LABELS" and isinstance(node.value, ast.Dict):
            for k in node.value.keys:
                labels.discard(None)
    return keys, labels


def main() -> int:
    votes = vote_labels()
    mapped, _ = mapped_labels()

    missing = sorted(votes - mapped)
    extra = sorted(mapped - votes)

    print(f"بنود التوصية: {len(votes)} · مربوطة: {len(mapped)}")
    if missing:
        print("\n✗ بنود بلا مفتاح عامل — ستختفي من تحليل «سبب الدخول»:")
        for m in missing:
            print(f"    · {m}")
    if extra:
        print("\n✗ مفاتيح لبنود لم تعد موجودة في recommend.py:")
        for e in extra:
            print(f"    · {e}")

    # كل مفتاح في FACTOR_KEYS له عنوان عرض في FACTOR_LABELS
    src = DST.read_text(encoding="utf-8")
    tree = ast.parse(src)
    kv, lv = {}, {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            name = getattr(node.targets[0], "id", "")
            d = {k.value: v.value for k, v in zip(node.value.keys, node.value.values)}
            if name == "FACTOR_KEYS":
                kv = d
            elif name == "FACTOR_LABELS":
                lv = d
    orphan = sorted(set(kv.values()) - set(lv))
    if orphan:
        print("\n✗ مفاتيح بلا عنوان عرض في FACTOR_LABELS:")
        for o in orphan:
            print(f"    · {o}")

    bad = missing or extra or orphan
    print("\n" + ("✗ العقد مكسور" if bad else "✓ كل بند مربوط بعامل وعنوان"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
