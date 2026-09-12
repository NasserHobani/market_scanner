# -*- coding: utf-8 -*-
"""مخزن الأحكام — سجلٌّ صغيرٌ لما قاله المستشار وما رُفض.

═══ لماذا مخزنٌ جديد ═══

السجلّ القديم ثلاثة ملفّات متقاطعة (``advisor_history`` و
``advisor_memory`` و``advisor_review_meta``) وستّة وثلاثون حقلاً،
منها أربعة فارغة في **١٠٠٪** من ١٦٤ مراجعة. وكتابةُ حكمٍ من خمسة
حقول في ذلك القالب تعني ملء واحدٍ وثلاثين حقلاً بالفراغ — وهو
بالضبط ما أنتج «مراجعاتٍ» بلا محتوى.

فهنا سطرٌ واحد لكل حكم، فيه ما قيل وما رُفض ولماذا.

═══ والمرفوض يُحفظ ═══

المستشار القديم كان يُسقط المخرَج المرفوض صامتاً، فيبدو السجلّ
نظيفاً وهو ناقص. ومعدّل الرفض هو أصدق مقياسٍ لصلاحية النموذج
للمهمّة — إخفاؤه يخفي العطب لا يصلحه.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

# سقفٌ للسجلّ: ``events.jsonl`` بلغ ٣٠٥ ميغابايت بلا حدّ، فصار
# قراءةُ سطرٍ منه تُكلّف ثوانٍ. الحدّ هنا يُفرض عند الكتابة.
MAX_RECORDS = 5000

_LOCK = threading.Lock()


def _default_path() -> Path:
    root = Path(__file__).resolve().parents[2]
    return Path(os.environ.get("VERDICT_STORE")
                or root / "data" / "verdicts.jsonl")


def append(record: dict[str, Any], *, path: Path | None = None) -> None:
    """يضيف حكماً — ولا يرمي أبداً.

    فشل الكتابة يجب ألّا يُسقط مسحاً: السجلّ توثيقٌ لا شرط عمل.
    """
    p = Path(path) if path else _default_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, default=str)
        with _LOCK:
            with p.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
            _trim(p)
    except Exception:  # noqa: BLE001
        pass


def _trim(p: Path) -> None:
    """يقصّ السجلّ إلى ``MAX_RECORDS`` — بكتابةٍ ذرّية.

    القصّ في مكانه يترك الملفّ ناقصاً إن قُطع البرنامج أثناءه؛
    والاستبدال الذرّي يبقي القديم سليماً حتى تكتمل النسخة.
    """
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    if len(lines) <= MAX_RECORDS:
        return
    keep = lines[-MAX_RECORDS:]
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("\n".join(keep) + "\n")
        os.replace(tmp, p)
    except Exception:  # noqa: BLE001
        try:
            os.unlink(tmp)
        except OSError:
            pass


def load_all(*, path: Path | None = None,
             limit: int = 0) -> list[dict[str, Any]]:
    """يقرأ الأحكام — والأحدث أوّلاً.

    السطر التالف يُتخطّى ولا يُسقط الباقي: ملفٌّ قُطعت كتابته
    مرّة لا يجوز أن يعمي السجلّ كلّه.
    """
    p = Path(path) if path else _default_path()
    try:
        raw = p.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    out: list[dict[str, Any]] = []
    for ln in reversed(raw):
        ln = ln.strip()
        if not ln:
            continue
        try:
            rec = json.loads(ln)
        except (ValueError, TypeError):
            continue
        if isinstance(rec, dict):
            out.append(rec)
        if limit and len(out) >= limit:
            break
    return out


def get(verdict_id: str, *, path: Path | None = None) -> dict[str, Any] | None:
    for rec in load_all(path=path):
        if rec.get("id") == verdict_id:
            return rec
    return None


def stats(*, path: Path | None = None) -> dict[str, Any]:
    """ما يستحقّ أن يُعرض فوق الجدول: القبول والقرارات.

    ومعدّل الرفض أوّل ما يُقاس — إن ارتفع فالنموذج غير صالح
    للمهمّة، وهو خبرٌ يجب أن يُرى لا أن يُبتلع.
    """
    recs = load_all(path=path)
    counts: dict[str, int] = {}
    accepted = 0
    for r in recs:
        if r.get("accepted"):
            accepted += 1
            d = str((r.get("fields") or {}).get("القرار") or "—")
        else:
            d = "مرفوض"
        counts[d] = counts.get(d, 0) + 1
    return {
        "total": len(recs),
        "accepted": accepted,
        "rejected": len(recs) - accepted,
        "decisions": counts,
    }


__all__ = ["append", "load_all", "get", "stats", "MAX_RECORDS"]
