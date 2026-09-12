# -*- coding: utf-8 -*-
"""تشريح الصفقات المحسومة — أسباب النجاح وأسباب الفشل.

    python tools_postmortem.py                 # قياس فقط
    python tools_postmortem.py --ai            # قياس ثمّ تفسير بالنموذج
    python tools_postmortem.py --market crypto --tf 4h --since 2026-06-01

الأرقام تُطبع أولاً دائماً. التفسير يأتي بعدها ولا يحلّ محلّها: إن
تعارضا فالأرقام هي الحقيقة.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner.postmortem import analyze, build_prompt, render_report  # noqa: E402

DB = ROOT / "data" / "dashboard.sqlite3"


def _open_readonly() -> sqlite3.Connection | None:
    """اتصال للقراءة يحتمل قاعدة يعمل عليها الخادم.

    ثلاث محاولات بترتيب الأفضلية:

    ١. ``mode=ro`` — الأنظف: لا ينافس الكاتب على قفل ولا يعدّل شيئاً.
    ٢. اتصال عادي — ‏WAL يسمح بقارئ مع كاتب، فهذا يكفي غالباً.
    ٣. نسخة مؤقّتة — إن أخفق الاثنان (قفل ويندوز، أو ``-wal`` غير
       مقروء). أبطأ لكنّه لا يفشل، وقراءة تقرير لا يجوز أن تتعطّل
       لأن الخادم يعمل.
    """
    import shutil
    import tempfile

    for attempt in (1, 2):
        try:
            con = sqlite3.connect(
                f"file:{DB}?mode=ro" if attempt == 1 else str(DB),
                uri=(attempt == 1), timeout=10)
            con.row_factory = sqlite3.Row
            con.execute("SELECT 1 FROM dashboard_trade LIMIT 1").fetchone()
            return con
        except sqlite3.Error:
            continue

    try:
        tmp = Path(tempfile.gettempdir()) / "postmortem_snapshot.sqlite3"

        # ═══ تنظيف الملفّات الجانبية أوّلاً ═══
        #
        # نسخة سابقة تترك ``-wal`` و``-shm`` خلفها. ونسخُ قاعدة جديدة
        # فوقها يترك السجلّ القديم بجانبها، فيرى SQLite زوجاً غير
        # متّسق ويرفض الفتح بـ«disk I/O error» — وهو خطأ مضلّل تماماً:
        # يوحي بعطب في القرص وسببه ملفّ متبقٍّ.
        for suffix in ("", "-wal", "-shm"):
            stale = tmp.with_name(tmp.name + suffix)
            if stale.exists():
                stale.unlink(missing_ok=True)

        shutil.copy2(DB, tmp)

        # ‏``-wal`` يُنسَخ، و``-shm`` **لا**.
        #
        # الأخير ملفّ ذاكرة مشتركة يربط العمليات الحيّة، ونسخُه على
        # بعض أنظمة الملفّات يرفع «Input/output error». و SQLite يعيد
        # بناءه من السجلّ وحده، فنسخُه لا يفيد ويكسر.
        #
        # وبلا هذا التمييز كانت الأداة تفشل كلّما عمل الخادم — أي في
        # أغلب الأوقات منذ تفعيل WAL.
        wal = DB.with_name(DB.name + "-wal")
        if wal.exists():
            try:
                shutil.copy2(wal, tmp.with_name(tmp.name + "-wal"))
            except OSError:
                # سجلّ غير قابل للنسخ: النسخة بلا آخر المعاملات، وهي
                # كافية لتقرير تحليلي. والصمت هنا أهون من تعطّل الأداة.
                pass
        con = sqlite3.connect(str(tmp))
        con.row_factory = sqlite3.Row
        con.execute("SELECT 1 FROM dashboard_trade LIMIT 1").fetchone()
        return con
    except Exception:  # noqa: BLE001
        return None


def load_trades(market: str = "", timeframe: str = "",
                since: str = "", source: str = "") -> list[dict]:
    # الرسائل إلى stderr لا stdout.
    #
    # ‏``--json`` يُستهلَك برمجياً، وسطرٌ عربي قبل الفتحة يُسقط
    # ``json.loads`` بخطأ لا علاقة له بالسبب الحقيقي — وهو ما وقع.
    if not DB.exists():
        print(f"قاعدة البيانات غير موجودة: {DB}", file=sys.stderr)
        return []
    con = _open_readonly()
    if con is None:
        print("تعذّر فتح قاعدة البيانات للقراءة.", file=sys.stderr)
        return []
    sql = "SELECT * FROM dashboard_trade WHERE status IN ('won','lost')"
    args: list = []
    if market:
        sql += " AND market = ?"; args.append(market)
    if timeframe:
        sql += " AND timeframe = ?"; args.append(timeframe)
    if source:
        sql += " AND source = ?"; args.append(source)
    if since:
        sql += " AND signal_at >= ?"; args.append(since)
    rows = [dict(r) for r in con.execute(sql, args)]
    con.close()
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="تشريح الصفقات المحسومة")
    ap.add_argument("--market", default="")
    ap.add_argument("--tf", default="", dest="timeframe")
    ap.add_argument("--source", default="")
    ap.add_argument("--since", default="", help="YYYY-MM-DD")
    ap.add_argument("--ai", action="store_true", help="أضف تفسير النموذج")
    ap.add_argument("--json", action="store_true", help="أخرج JSON خاماً")
    a = ap.parse_args()

    trades = load_trades(a.market, a.timeframe, a.since, a.source)
    rep = analyze(trades)

    if a.json:
        print(json.dumps(rep.to_dict(), ensure_ascii=False, indent=2))
        return 0

    print("=" * 62)
    print("تشريح الصفقات المحسومة")
    print("=" * 62)
    print(render_report(rep))
    print("=" * 62)

    # التفسير يُسمح به حين يثبت عامل، أو حين تحمل المجموعة إشارة —
    # وفي الثانية يقتصر دور النموذج على اقتراح تجارب تحسم المرشَّحين.
    if not rep.has_findings and not rep.global_signal:
        print("\nلا عامل يفصل، ولا المجموعة ككلّ تتجاوز الضجيج.")
        print("هذه نتيجة صالحة: ما يُقاس اليوم لا يحمل الحافّة،")
        print("والخطوة التالية جمع خصائص جديدة لا تفسير القديمة.")
        return 0

    if not a.ai:
        print("\nأضف --ai لتفسير هذه الفروق بالنموذج.")
        return 0

    print("\n" + "─" * 62)
    print("تفسير النموذج (آليات مقترحة — ليست إثباتاً)")
    print("─" * 62)
    prompt = build_prompt(rep)
    try:
        from scanner.ai_advisor.prompt_builder import AdvisorPrompt
        from scanner.ai_advisor.provider_registry import get_registry
        from scanner.ai_local.config import load_local_config

        local = load_local_config()
        provider_id = "ollama" if local.local_enabled else "claude"
        provider = get_registry().get(provider_id)
        raw = provider.analyze(AdvisorPrompt(
            version="postmortem_v1",
            system_prompt=prompt["system_prompt"],
            user_prompt=prompt["user_prompt"],
            package_id=f"postmortem_{rep.n_total}",
            event_id="postmortem::cli",
        ), package=None)
        text = raw if isinstance(raw, str) else json.dumps(
            raw, ensure_ascii=False, indent=2)
        print(text[:4000])
    except Exception as exc:  # noqa: BLE001
        print(f"تعذّر نداء النموذج: {str(exc)[:200]}")
        print("\nالموجّه جاهز — يمكن لصقه في أي نموذج:")
        print("─" * 62)
        print(prompt["user_prompt"][:2500])
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
