"""فحص الأسماء غير المعرّفة عبر المشروع.

سبب وجوده: py_compile يتحقق من النحو فقط. الاستيراد الموضعي داخل دالة
لا يُرى من دالة أخرى، فيمرّ الملف سليماً ثم ينهار وقت التشغيل بـ NameError.
هذا ما حدث في views.py: get_adapter مستورد داخل دالتين واستُخدم في ثالثة.

    python tools_check_names.py
"""
from __future__ import annotations

import ast
import builtins
import sys
from pathlib import Path

BUILTINS = set(dir(builtins)) | {"__name__", "__file__", "__doc__", "__spec__"}


def _bind_args(args: ast.arguments, into: set[str]) -> None:
    for group in (args.args, args.posonlyargs, args.kwonlyargs):
        for a in group:
            into.add(a.arg)
    if args.vararg:
        into.add(args.vararg.arg)
    if args.kwarg:
        into.add(args.kwarg.arg)


def undefined_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    defined = set(BUILTINS)

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                defined.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defined.add(node.name)
            _bind_args(node.args, defined)
        elif isinstance(node, ast.Lambda):
            _bind_args(node.args, defined)      # كان مفقوداً — مصدر إنذارات زائفة
        elif isinstance(node, ast.ClassDef):
            defined.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            defined.add(node.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            defined.add(node.name)
        elif isinstance(node, ast.comprehension):
            for n in ast.walk(node.target):
                if isinstance(n, ast.Name):
                    defined.add(n.id)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars:
                    for n in ast.walk(item.optional_vars):
                        if isinstance(n, ast.Name):
                            defined.add(n.id)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            defined.update(node.names)

    used = {n.id for n in ast.walk(tree)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    return sorted(used - defined)


def main() -> int:
    root = Path(__file__).resolve().parent
    problems = 0
    for f in sorted(root.rglob("*.py")):
        if "__pycache__" in str(f) or ".venv" in str(f) or f.name == Path(__file__).name:
            continue
        missing = undefined_names(f)
        if missing:
            problems += 1
            print(f"  ✗ {f.relative_to(root)}: {', '.join(missing)}")
    if problems:
        print(f"\n{problems} ملفاً به أسماء غير معرّفة")
        return 1
    print("✓ لا أسماء غير معرّفة")
    return 0


if __name__ == "__main__":
    sys.exit(main())
