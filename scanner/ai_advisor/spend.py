# -*- coding: utf-8 -*-
"""سجلّ الإنفاق وسقفُه — لأنّ «عند الطلب فقط» وعدٌ لا يحرس نفسه.

═══ المسألة ═══

«لا تُنادَ إلّا بزرّ» نيّةٌ صحيحة، ويكسرها سطرٌ واحد: حلقةٌ تنادي
المحلّل لكل رمز، أو زرٌّ يُضغط مرّتين، أو صفحةٌ تُعاد كل عشرين
ثانية وفيها نداءٌ نُسي خلف شرط.

ولا شيء يقول إنّ ذلك وقع — حتى تصل الفاتورة.

فالحارس هنا **ماليّ لا نيّويّ**: كل نداءٍ يُسجَّل بتكلفته، ويُرفَض
ما يتجاوز السقف اليوميّ أو الشهريّ. فالعطب — إن وقع — يتوقّف عند
حدٍّ تعرفه سلفاً بدل أن يُكتشَف في كشف الحساب.

═══ والتكلفة تقدير لا فاتورة ═══

السعر يُضرَب في عدد الوحدات الذي يعيده المزوّد. وهو تقديرٌ قريب،
لكنّه ليس الفاتورة: الأسعار تتغيّر، وقد تُضاف رسوم. فالرقم
معروضٌ بوصفه **تقديراً بالسعر المضبوط**، والسعر نفسه قابلٌ
للتعديل من الإعدادات.

═══ ولماذا ملفّ لا قاعدة ═══

السجلّ يُكتب عند كل نداء ويُقرأ عند كل نداء — وهو سطرٌ واحد في
الدقيقة في أسوأ الحالات. وجدولٌ في القاعدة يعني هجرةً وقفلاً
وكاتباً إضافياً مقابل لا شيء.

و‏JSONL يُلحَق به ولا يُعاد كتابته، فانقطاعٌ في منتصف السطر يُفسد
سطراً واحداً تتخطّاه القراءة.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone as tz
from pathlib import Path

log = logging.getLogger("scanner.ai_advisor.spend")

__all__ = ["record", "summary", "check_budget", "estimate_cost",
           "LEDGER", "DEFAULT_PRICES", "BudgetExceeded"]

_LOCK = threading.Lock()


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


LEDGER = "data/ai_spend.jsonl"

# ═══ الأسعار بالدولار لكل مليون وحدة ═══
#
# مصدرها صفحة المزوّد وقت الكتابة (أكتوبر ٢٠٢٦)، وهي **تتغيّر**.
# فتُقرأ من البيئة إن ضُبطت، ويُعرَض تاريخ المرجع مع كل تقدير.
DEFAULT_PRICES = {
    "openai/gpt-oss-120b": {"in": 0.15, "out": 0.60},
    "openai/gpt-oss-20b": {"in": 0.05, "out": 0.20},
}
PRICES_AS_OF = "2026-10"


class BudgetExceeded(RuntimeError):
    """تجاوزُ السقف — ويحمل الرسالة التي تُعرَض للمستخدم."""


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except (TypeError, ValueError):
        return default


def limits() -> dict:
    """السقوف — من البيئة، وبقيمٍ محافظة إن لم تُضبط.

    والافتراض **منخفض** عمداً: سقفٌ كبير منسيّ لا يحرس شيئاً،
    وسقفٌ صغير يُرفع بوعيٍ حين يُحتاج.
    """
    return {
        "daily_usd": _f("AI_DAILY_USD", 1.0),
        "monthly_usd": _f("AI_MONTHLY_USD", 10.0),
        # نداءٌ واحد لا يتجاوز هذا مهما كان الطلب
        "per_call_usd": _f("AI_PER_CALL_USD", 0.25),
    }


def prices(model: str) -> dict:
    p = DEFAULT_PRICES.get(model, {"in": 0.15, "out": 0.60})
    return {"in": _f("AI_PRICE_IN", p["in"]),
            "out": _f("AI_PRICE_OUT", p["out"])}


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    p = prices(model)
    return round(tokens_in / 1e6 * p["in"] + tokens_out / 1e6 * p["out"], 6)


def _path() -> Path:
    p = _root() / LEDGER
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _rows() -> list[dict]:
    path = _path()
    if not path.exists():
        return []
    out = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                # سطرٌ مبتور من انقطاع — يُتخطّى ولا يُسقط السجلّ
                continue
    except OSError as exc:  # noqa: BLE001
        log.warning("تعذّرت قراءة سجلّ الإنفاق: %s", str(exc)[:90])
    return out


def summary() -> dict:
    """ما أُنفق اليوم وهذا الشهر، مع السقوف."""
    now = datetime.now(tz.utc)
    today = now.date().isoformat()
    month = now.strftime("%Y-%m")
    rows = _rows()

    day = sum(r.get("cost", 0.0) for r in rows
              if str(r.get("at", ""))[:10] == today)
    mon = sum(r.get("cost", 0.0) for r in rows
              if str(r.get("at", ""))[:7] == month)
    lim = limits()
    return {
        "today_usd": round(day, 4),
        "month_usd": round(mon, 4),
        "calls_today": sum(1 for r in rows
                           if str(r.get("at", ""))[:10] == today),
        "calls_total": len(rows),
        "limits": lim,
        "day_left": round(max(0.0, lim["daily_usd"] - day), 4),
        "month_left": round(max(0.0, lim["monthly_usd"] - mon), 4),
        "prices_as_of": PRICES_AS_OF,
        "last": rows[-1] if rows else None,
    }


def check_budget(model: str, est_in: int, est_out: int) -> None:
    """يرمي ``BudgetExceeded`` إن كان النداء سيتجاوز سقفاً.

    ═══ والفحص **قبل** الإرسال ═══

    الفحصُ بعده يسجّل التجاوز ولا يمنعه — وهو دفتر محاسبةٍ لا
    حارس. والتقدير هنا قبليّ، ويُصحَّح بالعدد الحقيقيّ بعد الردّ.
    """
    lim = limits()
    est = estimate_cost(model, est_in, est_out)
    if est > lim["per_call_usd"]:
        raise BudgetExceeded(
            f"النداء الواحد مقدَّر بـ${est:.4f} وسقفه "
            f"${lim['per_call_usd']:.2f}. قلّل حجم ما تُرسله أو ارفع "
            "‎AI_PER_CALL_USD‎.")

    s = summary()
    if s["today_usd"] + est > lim["daily_usd"]:
        raise BudgetExceeded(
            f"السقف اليوميّ ${lim['daily_usd']:.2f} — أُنفق "
            f"${s['today_usd']:.4f} اليوم، وهذا النداء مقدَّر بـ"
            f"${est:.4f}. ارفع ‎AI_DAILY_USD‎ أو انتظر الغد.")
    if s["month_usd"] + est > lim["monthly_usd"]:
        raise BudgetExceeded(
            f"السقف الشهريّ ${lim['monthly_usd']:.2f} — أُنفق "
            f"${s['month_usd']:.4f} هذا الشهر. ارفع ‎AI_MONTHLY_USD‎.")


def record(*, provider: str, model: str, tokens_in: int, tokens_out: int,
           purpose: str = "", latency_ms: float | None = None,
           ok: bool = True, error: str = "") -> dict:
    """يُلحق سطراً بالسجلّ ويعيده.

    ولا يرمي: فشلُ الكتابة يجب ألّا يُضيّع نتيجةً وصلت فعلاً —
    والمستخدم دفع ثمنها.
    """
    row = {
        "at": datetime.now(tz.utc).isoformat(timespec="seconds"),
        "provider": provider, "model": model,
        "tokens_in": int(tokens_in), "tokens_out": int(tokens_out),
        "cost": estimate_cost(model, tokens_in, tokens_out),
        "purpose": str(purpose)[:60],
        "latency_ms": None if latency_ms is None else round(latency_ms),
        "ok": bool(ok),
    }
    if error:
        row["error"] = str(error)[:160]
    try:
        with _LOCK:
            with _path().open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as exc:  # noqa: BLE001
        log.warning("تعذّر تسجيل الإنفاق: %s", str(exc)[:90])
    return row
