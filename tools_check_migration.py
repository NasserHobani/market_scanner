# -*- coding: utf-8 -*-
"""مطابقة حقول النموذج بحقول الهجرة بلا تشغيل Django.

makemigrations غير متاح في كل بيئة، وحقل يُضاف للنموذج بلا هجرة لا
يظهر خطؤه إلا عند أول استعلام في الإنتاج. الفحص هنا يسبق ذلك.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).parent
MODELS = ROOT / "web" / "dashboard" / "models.py"
MIGRATIONS = ROOT / "web" / "dashboard" / "migrations"

AUTO = {"id"}


def model_fields(name: str) -> dict[str, str]:
    tree = ast.parse(MODELS.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            out = {}
            for st in node.body:
                if (isinstance(st, ast.Assign) and isinstance(st.value, ast.Call)
                        and isinstance(st.value.func, ast.Attribute)
                        and getattr(st.value.func.value, "id", "") == "models"):
                    out[st.targets[0].id] = st.value.func.attr
            return out
    return {}


def migration_fields(model: str) -> dict[str, str]:
    """يجمع CreateModel وكل AddField لاحق."""
    out: dict[str, str] = {}
    for path in sorted(MIGRATIONS.glob("0*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = getattr(node.func, "attr", "")
            kw = {k.arg: k.value for k in node.keywords}
            if fn == "CreateModel":
                nm = kw.get("name")
                if not (nm and getattr(nm, "value", "").lower() == model.lower()):
                    continue
                for item in getattr(kw.get("fields"), "elts", []):
                    fname = item.elts[0].value
                    ftype = getattr(item.elts[1].func, "attr", "?")
                    out[fname] = ftype
            elif fn == "AddField":
                nm = kw.get("model_name")
                if not (nm and getattr(nm, "value", "").lower() == model.lower()):
                    continue
                out[kw["name"].value] = getattr(kw["field"].func, "attr", "?")
            elif fn == "RemoveField":
                nm = kw.get("model_name")
                if nm and getattr(nm, "value", "").lower() == model.lower():
                    out.pop(kw["name"].value, None)
    return out


def all_models() -> list[str]:
    """كل صنفٍ يرث ``models.Model`` في ``models.py``.

    الأصناف المجرّدة (‏``abstract = True``) تُستثنى: لا جدول لها
    فلا هجرة.
    """
    tree = ast.parse(MODELS.read_text(encoding="utf-8"))
    out = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        bases = {getattr(b, "attr", getattr(b, "id", "")) for b in node.bases}
        if "Model" not in bases:
            continue
        abstract = False
        for st in ast.walk(node):
            if (isinstance(st, ast.Assign)
                    and getattr(st.targets[0], "id", "") == "abstract"
                    and getattr(st.value, "value", False) is True):
                abstract = True
        if not abstract:
            out.append(node.name)
    return out


def main() -> int:
    bad = []
    # ═══ النماذج تُكتشَف لا تُعدَّد ═══
    #
    # كانت القائمة مكتوبة بخطّ اليد: ‏ScanRun و ScanResult و
    # SignalAlert و Watch و Trade. فأُضيف ``Company`` ولم يُضَف
    # هنا — فبقيت هجرته بلا فحص، وكذلك كلّ نموذجٍ يأتي بعده.
    #
    # وفاحصٌ يفحص خمسةً من سبعة يعطي طمأنينةً كاذبة: يمرّ أخضر
    # واللائحة ناقصة.
    for model in all_models():
        mf = model_fields(model)
        gf = migration_fields(model)
        if not mf:
            continue
        missing = sorted(set(mf) - set(gf) - AUTO)
        extra = sorted(set(gf) - set(mf) - AUTO)
        mismatch = sorted(f"{k}: نموذج {mf[k]} ≠ هجرة {gf[k]}"
                          for k in set(mf) & set(gf) if mf[k] != gf[k])
        mark = "✗" if (missing or extra or mismatch) else "✓"
        print(f"{mark} {model}: {len(mf)} حقل")
        for m in missing:
            bad.append(f"{model}.{m} في النموذج بلا هجرة")
        for e in extra:
            bad.append(f"{model}.{e} في الهجرة بلا نموذج")
        bad += [f"{model}.{m}" for m in mismatch]

    print()
    if bad:
        print("\n".join("  ✗ " + b for b in bad))
        return 1
    print("✓ النماذج والهجرات متطابقة")
    return 0


if __name__ == "__main__":
    sys.exit(main())
