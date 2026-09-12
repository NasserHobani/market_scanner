# -*- coding: utf-8 -*-
"""قراءة وحفظ إعدادات المستخدم.

المخطط في ``scanner.settings_schema`` والتخزين هنا — الفصل مقصود حتى
يبقى التحقق قابلاً للاختبار بلا Django ولا قاعدة بيانات.

الذاكرة المؤقتة ضرورية لا تحسيناً: القيم تُقرأ لكل رمز في المسح، وهذا
مئات الاستعلامات في الدورة الواحدة لو قُرئت من القاعدة كل مرة.
"""
from __future__ import annotations

import logging
import threading
import time

from django.db.utils import DatabaseError, OperationalError, ProgrammingError

from scanner import settings_schema as schema

from .models import Setting

log = logging.getLogger(__name__)

CACHE_TTL = 5.0          # ثوانٍ — تعديل من الصفحة يظهر في المسح التالي فوراً
_cache: dict = {}
_cached_at = 0.0
_lock = threading.Lock()


def _read_db() -> dict:
    try:
        return {row.key: row.value for row in Setting.objects.all()}
    except (OperationalError, ProgrammingError):
        # الهجرة غير مطبَّقة — الافتراضيات تُبقي النظام يعمل
        log.debug("جدول الإعدادات غير موجود — تُستعمل الافتراضيات")
        return {}
    except DatabaseError:
        return {}


def values(force: bool = False) -> dict:
    """كل الإعدادات: المحفوظ فوق الافتراضي."""
    global _cache, _cached_at
    now = time.time()
    if not force and _cache and (now - _cached_at) < CACHE_TTL:
        return dict(_cache)
    with _lock:
        merged = schema.merged(_read_db())
        _cache = merged
        _cached_at = now
    return dict(merged)


def get(key: str, default=None):
    """قيمة إعداد واحد — الافتراضي من المخطط إن لم يُحدَّد بديل."""
    if key not in schema.FIELDS:
        return default
    return values().get(key, schema.DEFAULTS.get(key, default))


def save(raw: dict) -> tuple[dict, list[str]]:
    """يتحقّق ثم يحفظ. يعيد (القيم النهائية، تنبيهات)."""
    clean, notes = schema.validate(raw)
    try:
        for key, value in clean.items():
            Setting.objects.update_or_create(key=key, defaults={"value": value})
    except (OperationalError, ProgrammingError):
        return clean, notes + ["جدول الإعدادات غير موجود — شغّل migrate"]
    except DatabaseError as exc:
        return clean, notes + [f"تعذّر الحفظ: {str(exc)[:120]}"]
    invalidate()
    return clean, notes


def reset() -> dict:
    """استعادة الافتراضي بحذف المحفوظ — لا بكتابة القيم فوقه.

    الحذف أصحّ: إعدادٌ يتغيّر افتراضه لاحقاً سيتبع الجديد بدل أن يظلّ
    مثبّتاً على قيمة قديمة كُتبت يوم الاستعادة.
    """
    try:
        Setting.objects.all().delete()
    except (OperationalError, ProgrammingError, DatabaseError):
        pass
    invalidate()
    return values(force=True)


def invalidate() -> None:
    global _cache, _cached_at
    with _lock:
        _cache = {}
        _cached_at = 0.0


# ── مساعدات للمستهلكين ──

def liquidity_tiers() -> list:
    return schema.tiers_from(values())


def breakout_kwargs() -> dict:
    """وسائط ``scanner.breakout.detect`` من الإعدادات."""
    v = values()
    return {
        "min_rvol": float(v["min_rvol"]),
        "lookback": int(v["lookback"]),
        "stop_atr": float(v["stop_atr"]),
        "target_atr": float(v["target_atr"]),
        "min_body": float(v["min_body"]),
        "low_buffer": float(v["low_buffer"]),
    }


def breakout_enabled() -> bool:
    return bool(values().get("enabled", True))


def cost_model():
    """نموذج التنفيذ من الإعدادات — مصدر واحد لكل حساب كلفة.

    بناؤه هنا لا في كل مستدعٍ: الكلفة تدخل الحسم والعرض والاختبار
    الخلفي، ولو قرأ كلٌّ إعداداته بنفسه لانحرفت الأرقام بين الشاشات
    دون أن يُلاحَظ — وهو أسوأ أنواع الخطأ لأنه يبدو خلافاً في التفسير.
    """
    from scanner.execution import DEFAULT, CostModel

    v = values()
    try:
        return CostModel(
            maker_bps=float(v["maker_bps"]),
            taker_bps=float(v["taker_bps"]),
            slippage_scale=float(v["slippage_scale"]),
            spread_scale=float(v["slippage_scale"]),
        )
    except (KeyError, TypeError, ValueError):
        return DEFAULT
