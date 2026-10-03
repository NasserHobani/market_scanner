# -*- coding: utf-8 -*-
"""أرشيف الإجابات — كلّ نداءٍ دُفع ثمنُه يُحفَظ.

═══ لماذا منفصلٌ عن سجلّ الإنفاق ═══

``spend.py`` يسجّل المال: وحداتٌ وتكلفة. وهو سجلٌّ محاسبيّ يُقرأ
كاملاً في كل فحص، فإثقالُه بنصوص الإجابات يجعل كل حساب ميزانية
يقرأ ميغابايتات.

وهذا يسجّل **المحتوى**: السؤال والجواب. يُقرأ عند الطلب وحده،
ويُرشَّح بالرمز.

═══ ولماذا يُحفَظ أصلاً ═══

النداء يكلّف. وإجابةٌ تُعرَض ثمّ تُفقَد بإغلاق التبويب تعني أنّك
دفعت مرّتين للسؤال نفسه — وهو بالضبط ما يناقض «عند الطلب فقط».

وفائدةٌ ثانية: المقارنة. قراءةُ الرمز قبل أسبوع بجانب قراءته
اليوم تُظهر هل تغيّر التحليل أم تغيّرت صياغته.

═══ وما لا يُحفَظ ═══

لا مفاتيح ولا ترويسات. والمحفوظ ما أُرسل في **متن** السؤال وما
عاد في الجواب — وكلاهما من صنع هذه المنصّة.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone as tz
from pathlib import Path

log = logging.getLogger("scanner.ai_advisor.archive")

__all__ = ["save", "list_for", "get", "recent", "stats", "ARCHIVE"]

ARCHIVE = "data/ai_answers.jsonl"

#: سقفٌ للملفّ — ما زاد يُقصّ من أوّله
MAX_ROWS = 2000

_LOCK = threading.Lock()


def _path() -> Path:
    p = Path(__file__).resolve().parents[2] / ARCHIVE
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _rows() -> list[dict]:
    path = _path()
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                # سطرٌ مبتور من انقطاع — يُتخطّى ولا يُسقط الأرشيف
                continue
    except OSError as exc:  # noqa: BLE001
        log.warning("تعذّرت قراءة الأرشيف: %s", str(exc)[:90])
    return out


def save(*, subject: str, purpose: str, model: str, answer: str,
         question: str = "", cost: float = 0.0, tokens_in: int = 0,
         tokens_out: int = 0, latency_ms: float | None = None) -> dict:
    """يحفظ إجابةً ويعيد سطرها.

    ولا يرمي: فشل الحفظ يجب ألّا يُضيّع إجابةً وصلت ودُفع ثمنها —
    تُعرَض على الشاشة ولو لم تُؤرشَف.
    """
    row = {
        "id": f"{int(time.time() * 1000):x}",
        "at": datetime.now(tz.utc).isoformat(timespec="seconds"),
        "subject": str(subject or "")[:40].upper(),
        "purpose": str(purpose or "")[:24],
        "model": str(model or "")[:64],
        "answer": str(answer or ""),
        # السؤال يُقصّ: المقصود تذكّرُ ما سُئل لا إعادة إنتاجه
        "question": str(question or "")[:4000],
        "cost": round(float(cost or 0.0), 6),
        "tokens_in": int(tokens_in), "tokens_out": int(tokens_out),
        "latency_ms": None if latency_ms is None else round(latency_ms),
    }
    try:
        with _LOCK:
            path = _path()
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            _trim(path)
    except OSError as exc:  # noqa: BLE001
        log.warning("تعذّر حفظ الإجابة: %s", str(exc)[:90])
    return row


def _trim(path: Path) -> None:
    """يقصّ الأقدم حين يتجاوز الملفّ الحدّ.

    ═══ والقصّ بالعدّ لا بالحجم ═══

    إجابةٌ طويلة واحدة لا تبرّر حذف مئةٍ قصيرة. والعدّ يُبقي
    التاريخ متّسقاً.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    if len(lines) <= MAX_ROWS:
        return
    keep = lines[-MAX_ROWS:]
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text("\n".join(keep) + "\n", encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def list_for(subject: str, *, limit: int = 20) -> list[dict]:
    """إجابات رمزٍ واحد — الأحدث أوّلاً، بلا نصّ السؤال."""
    want = str(subject or "").upper()
    out = [r for r in _rows() if str(r.get("subject", "")).upper() == want]
    out.reverse()
    return [{k: v for k, v in r.items() if k != "question"}
            for r in out[:limit]]


def recent(limit: int = 30) -> list[dict]:
    rows = _rows()[-limit:]
    rows.reverse()
    return [{k: v for k, v in r.items() if k not in ("question", "answer")}
            for r in rows]


def get(answer_id: str) -> dict | None:
    for r in reversed(_rows()):
        if r.get("id") == answer_id:
            return r
    return None


def stats() -> dict:
    rows = _rows()
    subjects: dict[str, int] = {}
    for r in rows:
        s = str(r.get("subject") or "—")
        subjects[s] = subjects.get(s, 0) + 1
    return {
        "count": len(rows),
        "cost": round(sum(float(r.get("cost") or 0) for r in rows), 6),
        "subjects": sorted(subjects.items(), key=lambda x: -x[1])[:10],
        "first": rows[0]["at"] if rows else None,
        "last": rows[-1]["at"] if rows else None,
    }
