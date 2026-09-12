"""نقطة دخول تعمل بأي طريقة تشغيل.

سبب وجود هذا الملف: تشغيل `python scanner/run.py` بمساره يفشل، لأن بايثون
لا يتعرّف على `scanner` كحزمة فتنكسر الاستيرادات النسبية. أما تشغيل هذا
الملف — من جذر المشروع أو بمساره الكامل أو بالنقر عليه — فيضيف بايثون
مجلده تلقائياً إلى مسار البحث، فتصبح الحزمة مرئية.

    python main.py --market crypto --html
    python -m scanner.run --market crypto --html      (مكافئ)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scanner.run import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
