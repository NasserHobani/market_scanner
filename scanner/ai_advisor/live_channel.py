# -*- coding: utf-8 -*-
"""قناة المحادثة الحيّة مع المستشار — ما يُرسَل وما يصل، لحظةً بلحظة.

═══ لماذا ═══

المراجعة تستغرق **116 ثانية بالوسيط** (وأقصاها 177). وطوال هذه المدة
لا يرى المستخدم شيئاً: لا الموجّه الذي أُرسل، ولا الإجابة وهي تُبنى،
ولا أين وصلت. فيبدو النظام معلّقاً وهو يعمل — وحين يصل الجواب يكون
صندوقاً أسود لا يُعرف على أي معطيات بُني.

وهذا يناقض غرض المشروع: نظامٌ كل شيء فيه قابل للقياس يجب أن يكون
نداؤه للنموذج مرئياً أيضاً. رأيٌ لا تُرى مدخلاته لا يمكن الحكم عليه.

═══ التصميم ═══

سجلّ في الذاكرة يكتب فيه المزوّد أثناء العمل، ويقرأ منه العرض. لا
قاعدة بيانات: المحادثة الجارية حالة لحظية لا تستحقّ كتابة على القرص
كل بضع كلمات — والمكتمل يُحفظ أصلاً في ``advisor_history``.

والقفل ضروري لا احتياطي: المزوّد يعمل في خيط خلفي والعرض يقرأ من خيط
الطلب، والقراءة أثناء الكتابة تعطي نصّاً مقطوعاً في منتصف محرف عربي.
"""
from __future__ import annotations

import threading
import time
from collections import deque

# آخر محادثات محفوظة للعرض بعد انتهائها. عشرون كافية لمراجعة جلسة،
# وأكثر منها يراكم نصوصاً بحجم ميغابايتات في ذاكرة العملية.
MAX_KEPT = 20

# سقف النصّ المخزَّن لكل محادثة. الموجّه يبلغ 8285 رمزاً عند المستشار،
# والقصّ هنا للعرض فقط — الأصل يُرسَل كاملاً.
MAX_CHARS = 60_000

_lock = threading.Lock()
_current: dict | None = None
_recent: deque = deque(maxlen=MAX_KEPT)
_seq = 0


def _clip(text: str) -> str:
    if text is None:
        return ""
    text = str(text)
    if len(text) <= MAX_CHARS:
        return text
    return text[:MAX_CHARS] + f"\n… (قُصّ {len(text) - MAX_CHARS} محرفاً)"


def start(*, symbol: str = "", market: str = "", timeframe: str = "",
          provider: str = "", model: str = "", system: str = "",
          user: str = "") -> str:
    """يفتح محادثة جديدة ويعيد معرّفها."""
    global _current, _seq
    with _lock:
        _seq += 1
        cid = f"conv_{_seq}_{int(time.time())}"
        _current = {
            "id": cid, "symbol": symbol, "market": market,
            "timeframe": timeframe, "provider": provider, "model": model,
            "system": _clip(system), "user": _clip(user),
            "answer": "", "state": "sending", "error": "",
            "started": time.time(), "updated": time.time(),
            "chars": 0, "stages": [{"at": 0.0, "name": "أُرسل الموجّه"}],
        }
        return cid


def stage(name: str) -> None:
    """يسجّل مرحلة — للمستخدم أن يرى أين وصل بدل شريط انتظار أعمى."""
    with _lock:
        if _current is None:
            return
        _current["stages"].append(
            {"at": round(time.time() - _current["started"], 1), "name": name})
        _current["updated"] = time.time()


def append(chunk: str) -> None:
    """يُلحق جزءاً من الإجابة أثناء وصولها."""
    with _lock:
        if _current is None or not chunk:
            return
        if _current["state"] == "sending":
            _current["state"] = "streaming"
            _current["stages"].append(
                {"at": round(time.time() - _current["started"], 1),
                 "name": "بدأت الإجابة"})
        if len(_current["answer"]) < MAX_CHARS:
            _current["answer"] += str(chunk)
        _current["chars"] += len(str(chunk))
        _current["updated"] = time.time()


def finish(*, error: str = "", answer: str = "") -> None:
    """يغلق المحادثة الجارية وينقلها إلى المحفوظة."""
    global _current
    with _lock:
        if _current is None:
            return
        # المزوّد غير المتدفّق يعطي الإجابة دفعة واحدة عند النهاية
        if answer and not _current["answer"]:
            _current["answer"] = _clip(answer)
            _current["chars"] = len(str(answer))
        _current["state"] = "failed" if error else "done"
        _current["error"] = str(error)[:400]
        _current["elapsed"] = round(time.time() - _current["started"], 1)
        _current["stages"].append(
            {"at": _current["elapsed"],
             "name": "فشلت" if error else "اكتملت"})
        _recent.appendleft(dict(_current))
        _current = None


def snapshot() -> dict:
    """الحالة للعرض. نسخة لا مرجع — العرض يتسلسل خارج القفل."""
    with _lock:
        cur = dict(_current) if _current else None
        if cur:
            cur["elapsed"] = round(time.time() - cur["started"], 1)
            cur.pop("started", None)
        return {
            "active": cur is not None,
            "current": cur,
            "recent": [
                {k: v for k, v in r.items() if k != "started"}
                for r in list(_recent)[:5]
            ],
        }


def clear() -> None:
    """للاختبارات ولإعادة الضبط بعد فشل صامت."""
    global _current
    with _lock:
        _current = None
        _recent.clear()
