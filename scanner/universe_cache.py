# -*- coding: utf-8 -*-
"""ذاكرة كون الرموز على القرص — ولماذا كانت الذاكرة في الرام كذبة.

═══ العطب ═══

قال القِمع::

    [١] الاكتشاف
      ✗ تعثّر الاكتشاف: Alpaca 429: too many requests
          النزول إلى الملف: 10 رمزاً

و‏429 يعني «أكثرتَ الطلب» — أي أنّ المفتاح سليم والشبكة سليمة
والحساب سليم، والنظام هو الذي أرهق المزوّد بنفسه.

وكان في المحوّل ``_universe_cache`` بمهلة ساعة — لكنّه **متغيّر
صنف في الذاكرة**. وكل أمر سطر أوامر عمليّةٌ جديدة، فالذاكرة تبدأ
باردة دائماً. فكل نداء يعيد الحساب كاملاً: اثنا عشر ألفاً وخمسمئة
أصل، لكلٍّ شموع عشرين يوماً.

فذاكرةٌ لا تتجاوز عمر العمليّة ليست ذاكرة — هي تعليقٌ يقول
«محفوظ» ولا يحفظ. وأداة التشخيص التي نجحت قبل دقائق هي التي أحرقت
الحصّة، فأفشلت المسح الذي تلاها. أي أنّ **الفحص كان يسبّب العطب
الذي يفحصه**.

═══ والسلّم الخاطئ ═══

وحين يفشل الاكتشاف كان النزول إلى عشرة رموز مكتوبة في ملف
الإعداد — بينما على القرص كونٌ كامل اكتُشف قبل ساعة. ورمي أربعمئة
رمز معروف لأجل انقطاعٍ عابر خسارةٌ بلا مقابل.

فالسلّم الصحيح ثلاث درجات لا درجتان::

    اكتشافٌ حيّ  →  آخر كون محفوظ (ولو قديماً)  →  قائمة الملف

والقائمة الاحتياطية آخر ما يُلجَأ إليه لا ثانيه.
"""
from __future__ import annotations

import json
import os
import random
import threading
import time
from pathlib import Path
from typing import Any

# مهلة الطزاجة: كون الأسهم القابلة للتداول لا يتغيّر خلال اليوم.
# اثنتا عشرة ساعة تعني حساباً واحداً ثقيلاً في اليوم لا واحداً في
# كل أمر.
DEFAULT_TTL = 12 * 3600.0

_LOCK = threading.Lock()


def _root() -> Path:
    from . import storage

    return Path(storage.DATA_DIR) / "universe"


def path_for(name: str) -> Path:
    safe = "".join(c for c in str(name) if c.isalnum() or c in "-_") or "unknown"
    return _root() / f"{safe}.json"


def save(name: str, symbols: list[str],
         volumes: dict[str, float] | None = None) -> bool:
    """يحفظ الكون. يعيد False بدل أن يرمي — الحفظ لا يُفشل الاكتشاف."""
    if not symbols:
        return False
    payload = {
        "saved_at": time.time(),
        "symbols": list(symbols),
        # الأحجام قد تغيب (باقة لا تعطي الأسعار) — والكون يبقى نافعاً
        "volumes": {k: float(v) for k, v in (volumes or {}).items()},
    }
    p = path_for(name)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False

    # الكتابة الذرّية بالنمط نفسه الذي عولج به ``status.json``:
    # اسمٌ مؤقّت فريد لكل خيط، ومحاولات مع تراجع — ويندوز يرفض
    # ``os.replace`` بـ WinError 5 إن كان الهدف مفتوحاً.
    tmp = p.with_name(f"{p.stem}.{os.getpid()}.{threading.get_ident()}.tmp")
    delay = 0.05
    for attempt in range(5):
        try:
            tmp.write_text(json.dumps(payload, ensure_ascii=False),
                           encoding="utf-8")
            os.replace(tmp, p)
            return True
        except PermissionError:
            if attempt >= 4:
                break
            time.sleep(delay * (0.6 + 0.8 * random.random()))
            delay *= 2
        except OSError:
            break
    try:
        tmp.unlink(missing_ok=True)
    except OSError:
        pass
    return False


def load(name: str, *, max_age: float | None = None) -> dict[str, Any] | None:
    """يقرأ الكون المحفوظ.

    ``max_age=None`` يعني «مهما قدُم» — وهو المطلوب عند فشل الاكتشاف:
    كونٌ عمره يومان خيرٌ من عشرة رموز مكتوبة يدوياً.
    """
    p = path_for(name)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("symbols"):
        return None
    age = max(0.0, time.time() - float(data.get("saved_at") or 0))
    if max_age is not None and age > max_age:
        return None
    data["age_seconds"] = age
    return data


def fresh_symbols(name: str, ttl: float | None = None
                  ) -> tuple[list[str], dict[str, float]] | None:
    """الكون إن كان ما يزال طازجاً — وإلّا ``None``.

    ``ttl=None`` يعني ``DEFAULT_TTL`` وقتَ النداء لا وقتَ التعريف.

    كُتبت أوّلاً ``ttl: float = DEFAULT_TTL`` — وهي قيمة تُربَط مرّةً
    عند تعريف الدالّة. فتعديل ``DEFAULT_TTL`` بعد الاستيراد لا يغيّر
    شيئاً، والمفتاح يبدو موجوداً وهو معطّل. أمسكه الاختبار حين ضبط
    المهلة صفراً فبقيت الذاكرة طازجة.
    """
    limit = DEFAULT_TTL if ttl is None else ttl
    with _LOCK:
        d = load(name, max_age=limit)
    if not d:
        return None
    return list(d["symbols"]), dict(d.get("volumes") or {})


def describe(name: str) -> str:
    d = load(name)
    if not d:
        return "لا كون محفوظ"
    age = d["age_seconds"]
    unit = (f"{age / 3600:.1f} ساعة" if age >= 3600 else f"{age / 60:.0f} دقيقة")
    return f"{len(d['symbols'])} رمزاً · عمره {unit}"


__all__ = ["save", "load", "fresh_symbols", "describe", "path_for",
           "DEFAULT_TTL"]
