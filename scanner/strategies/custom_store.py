# -*- coding: utf-8 -*-
"""حفظ الاستراتيجيات وتشغيلها على نتائج المسح.

═══ لماذا ملفّات لا جدول ═══

الاستراتيجيات بضع عشراتٍ على الأكثر، وتُقرأ كلّها دفعةً واحدة
ولا يُستعلَم عنها. فجدولٌ في القاعدة يعني هجرةً جديدة — وكلّ
هجرةٍ خطوةٌ إضافية في كل نشر، ومكانٌ آخر يمكن أن يفشل.

وملفّ JSON في ``data/`` يتبع ما يتبعه ``pes_scan`` و‏``topdown``:
يبقى في وحدة التخزين بعد النشر، ويُنقَل مع ``tools_ship``،
ويُقرأ بلا Django — فتعمل الأداة في سطر الأوامر كما في الويب.

═══ والمعرّف من الاسم ═══

ملفٌّ باسم الاستراتيجية بعد تنقيته. فحفظُ استراتيجيةٍ بالاسم
نفسه يستبدلها لا يضاعفها — وهو ما يتوقّعه من يضغط «حفظ» مرّتين.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

from . import custom

log = logging.getLogger("scanner.strategies.custom_store")

MAX_STRATEGIES = 50


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def store_dir() -> Path:
    return _root() / "data" / "strategies"


def slug(name: str) -> str:
    """اسمُ ملفٍّ آمن من اسمٍ عربيّ أو إنجليزيّ.

    والعربية تبقى: أسماء الملفّات تقبلها، وتحويلها إلى أرقام
    يجعل مجلّد ``data/strategies`` غير مقروءٍ لمن يفتحه.
    """
    s = re.sub(r"[^\w؀-ۿ -]", "", str(name or "")).strip()
    s = re.sub(r"[\s-]+", "-", s)
    return s[:60] or "بلا-اسم"


def path_for(name: str) -> Path:
    return store_dir() / f"{slug(name)}.json"


def list_all() -> list[dict]:
    """كل الاستراتيجيات، الأحدث تعديلاً أوّلاً.

    وملفٌّ معطوب يُتخطّى ويُسجَّل — ولا يُسقط القائمة كلّها.
    """
    d = store_dir()
    if not d.is_dir():
        return []
    out = []
    for p in d.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("استراتيجية معطوبة %s: %s", p.name, str(exc)[:90])
            continue
        if isinstance(data, dict) and data.get("name"):
            out.append(data)
    out.sort(key=lambda s: -float(s.get("updated_at") or 0))
    return out


def load(name: str) -> dict | None:
    try:
        return json.loads(path_for(name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save(strategy: dict) -> tuple[bool, str]:
    """يحفظ بعد التحقّق. ``(نجح، السبب)``.

    والتحقّق **قبل** الكتابة: استراتيجيةٌ معطوبة محفوظة تفشل
    صامتةً عند كل فرز — لا رمز يُطابق، ولا شيء يقول لماذا.
    """
    name = str(strategy.get("name") or "").strip()
    if not name:
        return False, "بلا اسم"
    conds = strategy.get("conditions")
    errs = custom.validate(conds)
    if errs:
        return False, " · ".join(errs[:3])

    d = store_dir()
    existing = {p.stem for p in d.glob("*.json")} if d.is_dir() else set()
    if slug(name) not in existing and len(existing) >= MAX_STRATEGIES:
        return False, f"بلغتَ الحدّ ({MAX_STRATEGIES}) — احذف واحدة أوّلاً"

    payload = {
        "name": name,
        "note": str(strategy.get("note") or "")[:400],
        "markets": [m for m in (strategy.get("markets") or []) if m],
        "conditions": conds,
        "color": str(strategy.get("color") or "")[:16],
        "active": bool(strategy.get("active", True)),
        "created_at": float(strategy.get("created_at")
                            or (load(name) or {}).get("created_at")
                            or time.time()),
        "updated_at": time.time(),
    }
    try:
        d.mkdir(parents=True, exist_ok=True)
        path_for(name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8")
    except OSError as exc:
        return False, f"تعذّر الحفظ: {exc}"
    return True, ""


def delete(name: str) -> bool:
    try:
        path_for(name).unlink()
        return True
    except OSError:
        return False


# ═══════════════════════════════════════════════════════════════
#  التشغيل على نتائج المسح
# ═══════════════════════════════════════════════════════════════

def run(strategy: dict, *, markets: list[str] | None = None,
        limit: int = 60) -> dict:
    """يفرز رموز الأسواق بهذه الاستراتيجية.

    يقرأ ملفّات مسح ‏PES المحفوظة — بلا شبكة ولا حساب. فالنتيجة
    فوريّة، وهي القيم نفسها التي تعرضها بقيّة الشاشات.
    """
    from . import pes_scan

    wanted = markets or strategy.get("markets") or []
    if not wanted:
        # بلا تحديد: كل سوقٍ له مسحٌ محفوظ
        d = _root() / "data" / "pes"
        wanted = sorted(p.stem for p in d.glob("*.json")) if d.is_dir() else []

    conds = strategy.get("conditions") or []
    cards: list[dict] = []
    scanned = 0
    missing: list[str] = []
    oldest: float | None = None

    for m in wanted:
        data = pes_scan.load(m)
        if not data:
            missing.append(m)
            continue
        ts = float(data.get("measured_at") or 0)
        oldest = ts if oldest is None else min(oldest, ts)
        for row in data.get("rows") or []:
            scanned += 1
            res = custom.evaluate(row, conds)
            if not res["match"]:
                continue
            st = row.get("supertrend") or {}
            cards.append({
                "symbol": row.get("symbol"), "market": m,
                "close": row.get("close"),
                "score": row.get("score"),
                "state": row.get("state"),
                "state_label": row.get("state_label"),
                "distance": row.get("distance"),
                "resistance": row.get("resistance"),
                "momentum": (row.get("momentum") or {}).get("score"),
                "supertrend_dir": st.get("direction"),
                "supertrend_bars": st.get("bars_since_flip"),
                "met": res["met"], "total": res["total"],
                "conditions": res["conditions"],
            })

    # الأعلى درجةً أوّلاً — والمطابِقون كلّهم استوفوا الشروط،
    # فالترتيب بينهم بالقوّة لا بالمطابقة.
    cards.sort(key=lambda c: -(c["score"] or 0))
    return {
        "name": strategy.get("name"),
        "color": strategy.get("color") or "",
        "note": strategy.get("note") or "",
        "markets": wanted,
        "missing": missing,
        "scanned": scanned,
        "matched": len(cards),
        "measured_at": oldest,
        "cards": cards[:limit],
        "truncated": max(0, len(cards) - limit),
    }


__all__ = ["list_all", "load", "save", "delete", "run", "slug",
           "store_dir", "path_for", "MAX_STRATEGIES"]
