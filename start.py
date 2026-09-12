"""قائمة تشغيل تفاعلية.

سبب وجودها بدل ملف دفعي عربي: cmd يقرأ ملفات .bat بايتاً بايتاً ويتتبّع
موضعه فيها. تغيير صفحة الترميز في منتصف الملف (chcp 65001) يزيح المواضع،
فيستأنف cmd من منتصف كلمة وينفّذ شظايا مثل «anage.py» و«ython».
بايثون يقرأ الملف كنص UTF-8 كاملاً، فلا تقع المشكلة أصلاً.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable

OPTIONS = [
    ("مسح سريع للعملات + تقرير HTML",
     [PY, "main.py", "--market", "crypto", "--html"]),
    ("متابعة حية (يمسح عند إغلاق كل شمعة)",
     [PY, "main.py", "--market", "crypto", "--live", "--html"]),
    ("تشخيص: لماذا استُبعد كل رمز",
     [PY, "main.py", "--market", "crypto", "--diagnose", "--quiet"]),
    ("التحقق التاريخي",
     [PY, "backtest.py", "--market", "crypto", "--top", "30", "--split"]),
    ("السوق الأمريكي", [PY, "main.py", "--market", "us", "--html"]),
    ("السوق السعودي", [PY, "main.py", "--market", "saudi", "--html"]),
    ("لوحة الويب (Django)", "web"),
    ("تثبيت المتطلبات", "install"),
]


def run(cmd: list[str]) -> int:
    print("\n> " + " ".join(str(c) for c in cmd) + "\n")
    try:
        return subprocess.call(cmd, cwd=ROOT)
    except FileNotFoundError:
        print("تعذّر تشغيل بايثون. تحقّق من التثبيت.")
        return 1
    except KeyboardInterrupt:
        return 130


def install() -> int:
    code = run([PY, "-m", "pip", "install", "pandas", "numpy", "pyyaml"])
    ans = input("\nتريد لوحة الويب أيضاً؟ (y/n): ").strip().lower()
    if ans in ("y", "yes", "ن", "نعم"):
        code = run([PY, "-m", "pip", "install", "-r", "requirements-web.txt"])
    return code


def web() -> int:
    manage = ROOT / "web" / "manage.py"
    if run([PY, str(manage), "migrate"]) != 0:
        print("\nفشل التجهيز — جرّب خيار التثبيت أولاً.")
        return 1
    run([PY, str(manage), "scan", "--market", "crypto"])
    print("\nافتح: http://127.0.0.1:8000/    (Ctrl+C للإيقاف)\n")
    return run([PY, str(manage), "runserver"])


def main() -> int:
    missing = [m for m in ("pandas", "numpy", "yaml") if not _has(m)]
    print("=" * 42)
    print("  ماسح الأسواق")
    print("=" * 42)
    if missing:
        print(f"  تنبيه: حزم ناقصة ({', '.join(missing)}) — اختر التثبيت")
    print()
    for i, (label, _) in enumerate(OPTIONS, 1):
        print(f"  {i}  {label}")
    print("  0  خروج\n")

    try:
        choice = input("اختر رقماً: ").strip()
    except (EOFError, KeyboardInterrupt):
        return 0
    if choice in ("0", ""):
        return 0
    if not choice.isdigit() or not (1 <= int(choice) <= len(OPTIONS)):
        print("اختيار غير صحيح.")
        return 1

    action = OPTIONS[int(choice) - 1][1]
    if action == "install":
        return install()
    if action == "web":
        return web()
    return run(action)


def _has(module: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(module) is not None


if __name__ == "__main__":
    try:
        code = main()
    except KeyboardInterrupt:
        code = 130
    if sys.platform == "win32":
        input("\nاضغط Enter للإغلاق…")
    raise SystemExit(code)
