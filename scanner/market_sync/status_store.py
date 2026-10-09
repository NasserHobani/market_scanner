# -*- coding: utf-8 -*-
"""Persisted sync status store."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from .config import DEFAULT_SYNC_CONFIG, MarketSyncConfig
from .freshness import utc_now_iso

_LOCK = threading.Lock()


def _path(config: MarketSyncConfig) -> Path:
    return Path(config.status_path)


# ═══ الكتابة الذرّية على ويندوز ═══
#
# ‏``tmp.replace(path)`` يفشل على ويندوز بـ«[WinError 5] Access is
# denied» حين يكون الملفّ الهدف مفتوحاً لدى عملية أخرى — قارئ، أو
# مضاد فيروسات يفحصه في تلك اللحظة.
#
# وليس نظرياً: 5 من 453 زوجاً أمريكياً في سجلّك تحمل هذا الخطأ، وكل
# مزامناتها متوقّفة منذ 2026-08-14 — وهو نفس تاريخ آخر شمعة أمريكية.
#
# وتفاقمه أن حالة المزامنة تُقرأ من كل صفحة كل ثلاثين ثانية، فنافذة
# التصادم مفتوحة باستمرار.
#
# والعلاج ثلاثي:
#   • اسم مؤقّت فريد لكل كاتب — وإلّا داس كاتبان ملفاً واحداً.
#   • إعادة محاولة بانتظار متزايد: الحجب على ويندوز عابر بطبعه.
#   • وفشلٌ نهائي **لا يُسقط المنادي**: تسجيل الحالة خدمةٌ للعرض، وليس
#     أولى من المزامنة نفسها. وإسقاطها للدورة هو ما أوقف السوق.
_WRITE_ATTEMPTS = 5
_WRITE_BASE_DELAY = 0.05


def _atomic_write(path: Path, data: dict[str, Any]) -> bool:
    """يكتب JSON ذرّياً. يعيد ``False`` عند الفشل ولا يرفع."""
    import logging
    import os
    import random
    import time as _time

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, default=str, indent=2)
    tmp = path.with_name(f"{path.stem}.{os.getpid()}.{threading.get_ident()}.tmp")

    delay = _WRITE_BASE_DELAY
    for attempt in range(1, _WRITE_ATTEMPTS + 1):
        try:
            tmp.write_text(payload, encoding="utf-8")
            os.replace(tmp, path)
            return True
        except PermissionError:
            # ويندوز: الهدف مفتوح لدى غيرنا. الانتظار المشوَّش يفرّق
            # الكاتبين بدل أن يعيدهما إلى التصادم نفسه.
            if attempt >= _WRITE_ATTEMPTS:
                break
            _time.sleep(delay * (0.6 + 0.8 * random.random()))
            delay *= 2
        except OSError as exc:
            logging.getLogger(__name__).warning(
                "تعذّرت كتابة حالة المزامنة: %s", str(exc)[:120])
            break

    try:
        tmp.unlink(missing_ok=True)
    except OSError:
        pass
    logging.getLogger(__name__).warning(
        "تعذّرت كتابة حالة المزامنة بعد %s محاولات — المزامنة تكمل، "
        "والحالة المعروضة تتأخّر.", _WRITE_ATTEMPTS)
    return False


def load_status(config: MarketSyncConfig = DEFAULT_SYNC_CONFIG) -> dict[str, Any]:
    path = _path(config)
    if not path.exists():
        return {"pairs": {}, "worker": {}, "updated_at": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"pairs": {}, "worker": {}, "updated_at": None}


def save_status(data: dict[str, Any], config: MarketSyncConfig = DEFAULT_SYNC_CONFIG) -> None:
    path = _path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = dict(data)
    data["updated_at"] = utc_now_iso()
    with _LOCK:
        _atomic_write(path, data)


def pair_key(market: str, symbol: str, timeframe: str) -> str:
    return f"{market}|{symbol}|{timeframe}"


# ═══════════════════════════════════════════════════════════════
#  الكتابة المجمَّعة — وهذا كان عنق الزجاجة
# ═══════════════════════════════════════════════════════════════
#
# ═══ ما كان ═══
#
# ``update_pair`` يقرأ ملفّ الحالة **كاملاً**، يعدّل مفتاحاً
# واحداً، ويعيد كتابته **كاملاً**. وتحت ``_LOCK`` — فالخيوط العشرة
# تصطفّ عليه واحداً واحداً.
#
# والملفّ يحمل **كل** الأزواج: ١٥٨٨ زوجاً في سجلّك. فدورةٌ على
# خمسة آلاف زوج تعني خمسة آلاف قراءةٍ وكتابةٍ لملفٍّ بحجم
# ميغابايتات — أي عملٌ تربيعيّ، وغيغابايتات من الإدخال والإخراج
# في الدورة الواحدة.
#
# ═══ وتصحيحٌ لما كُتب هنا أوّلاً ═══
#
# كُتب هنا «الشبكة لم تكن العنق بل القرص». والقياس على الخادم
# قال غير ذلك:
#
#     كتابة حالة زوج     135ms  →   291ث في الدورة
#     طلبٌ شبكيّ واحد     997ms  →  2146ث في الدورة
#
# فالشبكة **سبعة أضعاف** القرص. والقرص عنقٌ ثانٍ حقيقيّ يستحقّ
# هذا التجميع — لا الأوّل. ومن قرأ الجملة الأولى وحدها رفع
# الخيوط وقلّل الرموز، وكلاهما علاجٌ لعَرَض.
#
# والقفل يُسلسل الخيوط العشرة في هذا الجزء، فلا تنفع فيه أصلاً.
#
# ═══ وما صار ═══
#
# أثناء دورة المزامنة تُجمَّع التحديثات في الذاكرة وتُكتب **مرّة
# واحدة** في نهايتها. فخمسة آلاف كتابة تصير واحدة.
#
# والنداء المفرد (من زرٍّ أو إنعاشٍ صغير) يبقى كما كان: الكتابة
# الفورية صحيحةٌ حين تكون واحدة.

_BUFFER: dict[str, dict[str, Any]] = {}
_BUFFERING = False


def batch_begin() -> None:
    """يبدأ تجميع التحديثات بدل كتابة كلٍّ على حدة."""
    global _BUFFERING
    with _LOCK:
        _BUFFERING = True
        _BUFFER.clear()


def batch_flush(*, config: MarketSyncConfig = DEFAULT_SYNC_CONFIG) -> int:
    """يكتب المجمَّع دفعةً واحدة ويعيد عدده.

    ولا يرمي: فشل الكتابة يجب ألّا يُضيّع مزامنةً تمّت — الحالة
    خدمةٌ للعرض، والشموع على القرص أصلاً.
    """
    global _BUFFERING
    with _LOCK:
        _BUFFERING = False
        pending = dict(_BUFFER)
        _BUFFER.clear()
        if not pending:
            return 0
        data = load_status(config)
        pairs = data.setdefault("pairs", {})
        for key, payload in pending.items():
            prev = dict(pairs.get(key) or {})
            prev.update(payload)
            pairs[key] = prev
        data["updated_at"] = utc_now_iso()
        _atomic_write(_path(config), data)
        return len(pending)


def update_pair(
    market: str,
    symbol: str,
    timeframe: str,
    payload: dict[str, Any],
    *,
    config: MarketSyncConfig = DEFAULT_SYNC_CONFIG,
) -> None:
    key = pair_key(market, symbol, timeframe)
    with _LOCK:
        if _BUFFERING:
            # عمليّةُ قاموسٍ لا قرص — وهي ما يجعل الخيوط تعمل فعلاً
            prev = dict(_BUFFER.get(key) or {})
            prev.update(payload)
            _BUFFER[key] = prev
            return
        data = load_status(config)
        pairs = data.setdefault("pairs", {})
        prev = dict(pairs.get(key) or {})
        prev.update(payload)
        pairs[key] = prev
        data["updated_at"] = utc_now_iso()
        path = _path(config)
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, data)


def update_worker(payload: dict[str, Any], *, config: MarketSyncConfig = DEFAULT_SYNC_CONFIG) -> None:
    with _LOCK:
        data = load_status(config)
        worker = data.setdefault("worker", {})
        worker.update(payload)
        data["updated_at"] = utc_now_iso()
        path = _path(config)
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, data)
