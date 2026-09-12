import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for p in (str(ROOT), str(ROOT / "web")):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.asgi import get_asgi_application  # noqa: E402

application = get_asgi_application()
