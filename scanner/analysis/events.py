# -*- coding: utf-8 -*-
"""تقويم الأحداث — مواعيدُ معروفة، ونصفٌ محسوب، بلا تنبّؤ.

═══ ما هذا ═══

ثلاثة أشياء تتحرّك بها سوق البيتكوين لأسبابٍ خارج الشارت:

    قرار الفِد        سيولةٌ عالمية
    التضخّم           توقّعات الفائدة
    النصف             عرضٌ جديد يُخفَّض

وكلّها **مواعيد معلومة** لا تنبّؤات. فالوحدة هنا تقول متى، ولا
تقول ماذا سيحدث للسعر — ولا تدّعي أنّ حدثاً يعني صعوداً أو
هبوطاً.

═══ ولماذا يُعرَض أصلاً ═══

خطّةٌ بأفق ثلاثة أيّام تمرّ على قرار فائدة ليست خطّةً بأفق ثلاثة
أيّام. والمعلومة هنا **إدارةُ مخاطر**: حجمٌ أصغر أو انتظار،
بقرار القارئ لا بقرار النظام.

═══ والنصف يُحسَب لا يُكتَب ═══

ارتفاعُ الكتلة معلومٌ لحظةً بلحظة، والنصف عند كل ٢١٠٬٠٠٠ كتلة.
فالتاريخ مشتقٌّ منه لا منسوخٌ من مقال — ويبقى صحيحاً بلا تحديث.
والتقدير **تقريبيّ**: متوسّط الكتلة عشر دقائق، والفعليّ يتذبذب.

═══ وما رُفض عمداً ═══

نماذج سعرٍ مبنيّة على النصف (S2F وأمثالها) لا تُبنى هنا. راجعتُ
ما نُشر: تفشل في الاختبار خارج العيّنة، ولا تتفوّق على تنبّؤٍ
ساذج بـ«سعر اليوم» على آفاق شهرٍ إلى ستّة. وعرضُ هدفٍ سعريّ منها
يوهم بمعرفةٍ لا يملكها أحد — وهو المعيار نفسه الذي أُخفيت به
احتمالات LightGBM في هذه المنصّة.

فالنصف هنا **موعدٌ** لا هدف.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone as tz
from pathlib import Path

log = logging.getLogger("scanner.analysis.events")

__all__ = ["upcoming", "halving", "calendar_health"]

HALVING_INTERVAL = 210_000
#: متوسّط زمن الكتلة بالدقائق — تصميميّ، والفعليّ يتذبذب حوله
BLOCK_MINUTES = 10.0

KIND_LABELS = {
    "fomc": "الفِد",
    "cpi": "التضخّم",
    "halving": "النصف",
    "other": "حدث",
}

_CACHE: dict[str, tuple[float, object]] = {}
_TTL = 900.0


def _config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "events.yaml"


def _load() -> dict:
    """محتوى ``config/events.yaml`` — أو فراغٌ إن تعذّر.

    وملفٌّ معطوب لا يُسقط الصفحة: التقويم إضافةٌ وصفية.
    """
    try:
        import yaml

        raw = _config_path().read_text(encoding="utf-8")
        out = yaml.safe_load(raw)
        return out if isinstance(out, dict) else {}
    except Exception as exc:  # noqa: BLE001
        log.info("تعذّرت قراءة تقويم الأحداث: %s", str(exc)[:80])
        return {}


def _block_height() -> int | None:
    """ارتفاع الكتلة الحالي — من نقطةٍ عامّة بلا مفتاح."""
    hit = _CACHE.get("height")
    now = time.time()
    if hit and now - hit[0] < _TTL:
        return hit[1]
    try:
        req = urllib.request.Request(
            "https://blockchain.info/q/getblockcount",
            headers={"User-Agent": "market-scanner/0.1"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            h = int(resp.read().decode("utf-8").strip())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        log.info("تعذّر جلب ارتفاع الكتلة: %s", str(exc)[:60])
        return None
    _CACHE["height"] = (now, h)
    return h


def halving() -> dict:
    """النصف القادم — كتلةً وتاريخاً تقريبياً.

    ``ok=False`` مع سبب إن تعذّر جلب الارتفاع: تقديرٌ بلا ارتفاعٍ
    حقيقيّ سيكون رقماً مخترعاً.
    """
    h = _block_height()
    if h is None:
        return {"ok": False, "why": "تعذّر جلب ارتفاع الكتلة"}
    target = ((h // HALVING_INTERVAL) + 1) * HALVING_INTERVAL
    left = target - h
    when = datetime.now(tz.utc) + timedelta(minutes=left * BLOCK_MINUTES)
    return {
        "ok": True,
        "height": h,
        "target": target,
        "blocks_left": left,
        "date": when.date().isoformat(),
        "days_left": max(0, (when.date() - date.today()).days),
        # التقدير يُعلَن تقديراً — لا يُعرَض كموعدٍ مؤكّد
        "approx": True,
        "note": f"تقدير على متوسّط {BLOCK_MINUTES:g} دقائق للكتلة — "
                "والفعليّ يتذبذّب بأسابيع",
    }


def _parse(d) -> date | None:
    if isinstance(d, date):
        return d
    try:
        return datetime.strptime(str(d).strip(), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def upcoming(days: int = 45, *, today: date | None = None,
             with_halving: bool = True) -> list[dict]:
    """الأحداث القادمة خلال النافذة — الأقرب أوّلاً، والنصف معها.

    و``with_halving=False`` يقطع نداء الشبكة: الفواحص يجب أن
    تعمل بلا إنترنت، وفحصٌ يعتمد على شبكةٍ يسقط لأسبابٍ لا علاقة
    لها بما يفحصه.
    """
    now = today or date.today()
    end = now + timedelta(days=days)
    out: list[dict] = []

    for ev in (_load().get("events") or []):
        if not isinstance(ev, dict):
            continue
        when = _parse(ev.get("date"))
        if when is None or not (now <= when <= end):
            continue
        kind = str(ev.get("kind") or "other")
        out.append({
            "date": when.isoformat(),
            "days": (when - now).days,
            "kind": kind,
            "kind_label": KIND_LABELS.get(kind, KIND_LABELS["other"]),
            "title": str(ev.get("title") or KIND_LABELS.get(kind, "حدث")),
            "impact": str(ev.get("impact") or "medium"),
            "approx": False,
        })

    hv = halving() if with_halving else {"ok": False}
    if hv.get("ok") and hv["days_left"] <= days:
        out.append({
            "date": hv["date"], "days": hv["days_left"],
            "kind": "halving", "kind_label": KIND_LABELS["halving"],
            "title": f"النصف — الكتلة {hv['target']:,}",
            "impact": "high", "approx": True, "note": hv["note"],
        })

    return sorted(out, key=lambda x: x["days"])


def calendar_health(*, today: date | None = None) -> dict:
    """هل التقويم حيٌّ أم نفد؟

    ═══ الصمت هو العطب ═══

    تقويمٌ انتهت مواعيده يعرض قائمةً فارغة — وهي تُقرأ «لا أحداث
    قادمة»، وهو ادّعاءٌ كاذب. فالفرق بين «لا حدث» و«لا أعرف»
    يُقال هنا صراحةً.
    """
    now = today or date.today()
    data = _load()
    dates = [_parse(e.get("date")) for e in (data.get("events") or [])
             if isinstance(e, dict)]
    dates = [d for d in dates if d]
    if not dates:
        return {"ok": False, "why": "تقويم الأحداث فارغ — "
                                    "لم يُملأ ‎config/events.yaml‎"}
    last = max(dates)
    if last < now:
        return {"ok": False, "last": last.isoformat(),
                "why": f"آخر موعد في التقويم {last.isoformat()} وقد مضى — "
                       "التقويم قديم، انسخ مواعيد السنة من الفِد و BLS"}
    ahead = (last - now).days
    if ahead < 30:
        return {"ok": True, "warn": True, "last": last.isoformat(),
                "why": f"التقويم ينفد بعد {ahead} يوماً"}
    return {"ok": True, "last": last.isoformat(), "days_ahead": ahead}
