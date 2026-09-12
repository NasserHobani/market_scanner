# -*- coding: utf-8 -*-
"""بحث الرموز عبر المصادر — مستقلّ عن Django.

المشكلة التي يحلّها تحديد النطاق: البحث عن عملة كان يسأل Yahoo أيضاً
وينتظره، وهو أبطأ المصدرين وأكثرهما عرضة لحدّ الطلبات. الرمز الذي
يبحث عنه المستخدم يكون في مصدر واحد غالباً، فسؤال الآخر انتظار خالص.

وحين يُطلب «كل الأسواق» تُسأل المصادر **بالتوازي**، فيصير الزمن زمن
أبطأ مصدر لا مجموعهما.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

# النطاق ← المصادر التي تُسأل
#
# الأمريكي يُسأل من alpaca ثم yahoo: الأول يبحث في قائمة أصول محلية
# مخزَّنة (بلا انتظار شبكة بعد أول نداء) ويطابق ما يستطيع الماسح جلبه
# فعلاً، والثاني احتياط حين تغيب مفاتيح Alpaca — فالبحث يجب أن يعمل
# قبل ضبط المفاتيح لا بعدها.
SOURCES: dict[str, tuple[str, ...]] = {
    "crypto": ("binance",),
    "us": ("alpaca", "yahoo"),
    "saudi": ("yahoo",),
}
ALL = "all"

SCOPES = [
    {"key": ALL, "label": "كل الأسواق"},
    {"key": "crypto", "label": "العملات"},
    {"key": "us", "label": "الأمريكي"},
    {"key": "saudi", "label": "السعودي"},
]
SCOPE_KEYS = {s["key"] for s in SCOPES}

DEFAULT_TIMEOUT = 12.0
MAX_RESULTS = 20


def normalize_scope(value: str | None, fallback: str = ALL) -> str:
    """يقبل النطاق المعروف فقط — أي قيمة أخرى تعود للافتراضي بصمت."""
    value = (value or "").strip()
    if value in SCOPE_KEYS:
        return value
    return fallback if fallback in SCOPE_KEYS else ALL


def sources_for(scope: str) -> tuple[str, ...]:
    if scope == ALL:
        # dict.fromkeys يحفظ الترتيب ويزيل التكرار (yahoo مشترك بين سوقين)
        merged: list[str] = []
        for names in SOURCES.values():
            merged.extend(names)
        return tuple(dict.fromkeys(merged))
    return SOURCES.get(scope, ())


def run(query: str, scope: str, resolve_adapter, *,
        timeout: float = DEFAULT_TIMEOUT,
        limit: int = MAX_RESULTS) -> dict:
    """ينفّذ البحث ويعيد النتائج والأخطاء والزمن.

    ``resolve_adapter`` دالة تأخذ اسم المصدر وتعيد المحوّل — تُمرَّر من
    الخارج حتى تبقى هذه الوحدة قابلة للاختبار بلا شبكة.
    """
    query = (query or "").strip()
    if not query:
        return {"results": [], "failures": [], "elapsed": 0.0, "sources": ()}

    names = sources_for(scope)
    started = time.time()

    def ask(name: str) -> list[dict]:
        adapter = resolve_adapter(name)
        if not hasattr(adapter, "search"):
            return []
        return list(adapter.search(query) or [])

    found: list[dict] = []
    failures: list[str] = []

    if len(names) <= 1:
        for name in names:
            try:
                found.extend(ask(name))
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{name}: {str(exc)[:120]}")
    else:
        with ThreadPoolExecutor(max_workers=len(names)) as pool:
            futures = [(pool.submit(ask, n), n) for n in names]
            for future, name in futures:
                try:
                    found.extend(future.result(timeout=timeout))
                except FutureTimeout:
                    failures.append(f"{name}: تجاوز {timeout:.0f}ث")
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"{name}: {str(exc)[:120]}")

    # Yahoo يعيد الأمريكي والسعودي معاً في استجابة واحدة، فالترشيح
    # لا بدّ أن يقع بعد الجلب لا قبله
    if scope != ALL:
        found = [r for r in found if r.get("market") == scope]

    seen: set[str] = set()
    unique: list[dict] = []
    for row in found:
        sym = row.get("symbol")
        if not sym or sym in seen:
            continue
        seen.add(sym)
        unique.append(row)

    return {
        "results": unique[:limit],
        "failures": failures,
        "elapsed": round(time.time() - started, 2),
        "sources": names,
    }
