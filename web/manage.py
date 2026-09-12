#!/usr/bin/env python
"""إدارة مشروع Django.

    python web/manage.py migrate
    python web/manage.py scan --market crypto
    python web/manage.py runserver
"""
import os
import sys
from pathlib import Path

# جذر المشروع في المسار حتى تُستورد حزمة scanner كما هي، بلا نسخ ولا تعديل
ROOT = Path(__file__).resolve().parent.parent
for path in (str(ROOT), str(ROOT / "web")):
    if path not in sys.path:
        sys.path.insert(0, path)


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError("Django غير مثبت. شغّل: pip install -r requirements-web.txt") from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
