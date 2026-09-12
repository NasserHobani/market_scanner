# -*- coding: utf-8 -*-
"""تحزيم بياناتك كلّها للخادم — قاعدةً وملفّات، ببرهانٍ على التمام.

    python tools_ship.py --check      # تحقّقٌ بلا كتابة
    python tools_ship.py              # بناء الحزمة

═══ ما تحلّه هذه الأداة ═══

نقلُ قاعدةٍ يفشل صامتاً بأربع طرق، كلّها وقعت في مشاريع قبل هذا:

**سجلّ ‏WAL.** ‏SQLite يكتب في ملفٍّ جانبيّ ويدمجه لاحقاً. فمن نسخ
``dashboard.sqlite3`` وحده فقد ما لم يُدمج بعد — والملفّ يُفتح،
والجداول موجودة، والصفوف الأخيرة غائبة بلا رسالة.

**قاعدةٌ محلّية متأخّرة.** إن رحّلت إلى Postgres ثمّ عدت فعملت على
SQLite، فـ``pg_dump`` يحزم القديم. فهنا تُقارَن الجهتان صفّاً
بصفّ، ويُرفَض التحزيم إن نقصت Postgres.

**أرشيفٌ ناقص.** ١٫١ غيغابايت عبر الشبكة تُقطع. فتُحسب بصمة
‏sha256 هنا ويتحقّق منها سكربت الخادم قبل أن يفكّ شيئاً.

**ملفّاتٌ تُفسد الوجهة.** أقفال المزامنة ومفتاح Django السرّي
وملفّ SQLite نفسه تُستبعَد: الأوّل يوقف المزامنة على الخادم،
والثاني يُبطل جلساته، والثالث يُغري بالرجوع إلى قاعدةٍ مهجورة.

═══ وما لا تفعله ═══

لا تتّصل بخادمك ولا تنقل شيئاً. تبني حزمةً في ``ship/`` وتطبع
أمرَي ‎scp‎ اللذين تنسخهما أنت. النقل بيدك، والاستعادة بسكربتٍ
تراه قبل تشغيله.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "ship"

# ═══ ما لا يُحزَم ═══
#
# الأوّلان ليسا تنظيفاً بل تصحيحاً: قفلٌ منسوخٌ من جهازك يجعل
# ‎market_sync‎ على الخادم يظنّ رمزاً قيد المزامنة فيتخطّاه أبداً،
# وملفّ SQLite منسوخاً يجعل تشخيص أيّ خللٍ لاحق يبدأ من القاعدة
# الخطأ.
EXCLUDE_NAMES = {
    ".django_secret_key",   # للخادم مفتاحه، وتبديله يُبطل الجلسات
    "dashboard.sqlite3",
    "dashboard.sqlite3-wal",
    "dashboard.sqlite3-shm",
}
EXCLUDE_SUFFIX = (".lock",)
EXCLUDE_DIRS = {"__pycache__"}


def _excluded(rel: Path) -> str:
    """سبب الاستبعاد، أو سلسلةٌ فارغة إن كان يُحزَم."""
    if any(p in EXCLUDE_DIRS for p in rel.parts):
        return "__pycache__"
    name = rel.name
    if name in EXCLUDE_NAMES:
        return name
    if name.startswith("dashboard.sqlite3."):   # النسخ الاحتياطية .bak-*
        return "نسخة SQLite احتياطية"
    if name.endswith(EXCLUDE_SUFFIX):
        return "قفل"
    return ""


# ═══════════════════ القاعدة ═══════════════════

TABLE_PREFIX = "dashboard_"


def sqlite_counts(db: Path) -> dict[str, int]:
    """أعداد صفوف SQLite — **مع** ما في سجلّ WAL.

    الفتح للقراءة في المجلّد نفسه يقرأ ‎-wal‎ تلقائياً. ونسخُ
    الملفّ إلى مكانٍ آخر أوّلاً هو ما يفقده.
    """
    if not db.exists():
        return {}
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        names = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name LIKE ?", (TABLE_PREFIX + "%",))]
        return {n: con.execute(f"SELECT COUNT(*) FROM [{n}]").fetchone()[0]
                for n in names}
    finally:
        con.close()


def psql(container: str, user: str, db: str, sql: str) -> str:
    """استعلامٌ بلا مشغّل Python — ‎psql‎ داخل الحاوية يكفي."""
    r = subprocess.run(
        ["docker", "exec", "-i", container,
         "psql", "-U", user, "-d", db, "-At", "-c", sql],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip())
    return r.stdout.strip()


def pg_counts(container: str, user: str, db: str) -> dict[str, int]:
    out = psql(container, user, db,
               "SELECT tablename FROM pg_tables WHERE schemaname='public' "
               f"AND tablename LIKE '{TABLE_PREFIX}%' ORDER BY tablename")
    names = [n for n in out.splitlines() if n]
    if not names:
        return {}
    # استعلامٌ واحد لكل الجداول بدل استعلامٍ لكلٍّ منها
    union = " UNION ALL ".join(
        f"SELECT '{n}' t, COUNT(*) c FROM \"{n}\"" for n in names)
    res = {}
    for line in psql(container, user, db, union).splitlines():
        if "|" in line:
            t, c = line.rsplit("|", 1)
            res[t] = int(c)
    return res


def compare(sq: dict[str, int], pg: dict[str, int]) -> tuple[bool, list[str]]:
    """هل ‏Postgres المحلّية تحمل كل ما في SQLite؟

    ═══ الاتّجاه مقصود ═══

    ‏Postgres **أكثر** ليس خطأً: بعد الترحيل يكتب النظام فيها وحدها
    ويتجمّد ملفّ SQLite. لكن ‏Postgres **أقلّ** يعني ترحيلاً لم
    يتمّ أو كتابةً استمرّت على SQLite بعده — وتحزيمُها حينئذٍ شحنُ
    الماضي.
    """
    lines, ok = [], True
    for t in sorted(set(sq) | set(pg)):
        a, b = sq.get(t, 0), pg.get(t, 0)
        if b < a:
            ok = False
            lines.append(f"  ✗ {t:32s} SQLite {a:>7,}  ←  Postgres {b:>7,}")
        elif b > a:
            lines.append(f"  + {t:32s} SQLite {a:>7,}  →  Postgres {b:>7,}")
        else:
            lines.append(f"  ✓ {t:32s} {a:>7,}")
    return ok, lines


# ═══════════════════ الأرشيف ═══════════════════

def sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for blk in iter(lambda: f.read(chunk), b""):
            h.update(blk)
    return h.hexdigest()


def build_tar(src: Path, dest: Path) -> dict:
    """أرشيفٌ جذرُه **محتوى** المجلّد لا اسمه.

    فيُفَكّ مباشرةً داخل ‎/app/data‎ بلا ‎--strip-components‎ —
    والخطأ الشائع أن ينتج ‎/app/data/data/…‎ فيبدو النقل ناجحاً
    والنظام لا يرى شمعةً واحدة.
    """
    files = skipped = 0
    raw = 0
    t0 = time.time()
    with tarfile.open(dest, "w:gz", compresslevel=6) as tar:
        for p in sorted(src.rglob("*")):
            rel = p.relative_to(src)
            if _excluded(rel):
                if p.is_file():
                    skipped += 1
                continue
            if p.is_dir():
                continue
            try:
                tar.add(p, arcname=str(rel).replace(os.sep, "/"))
            except (OSError, PermissionError) as e:      # noqa: PERF203
                print(f"   ⚠ تعذّر: {rel} — {e}")
                skipped += 1
                continue
            files += 1
            raw += p.stat().st_size
            if files % 500 == 0:
                print(f"   … {files:,} ملفّاً · {raw/1e6:,.0f} م.ب "
                      f"· {time.time()-t0:,.0f}ث", flush=True)
    return {"files": files, "skipped": skipped, "raw_bytes": raw,
            "gz_bytes": dest.stat().st_size,
            "seconds": round(time.time() - t0, 1)}


def git_head() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                           capture_output=True, text=True)
        return r.stdout.strip()[:12] if r.returncode == 0 else ""
    except OSError:
        return ""


# ═══════════════════ المسار ═══════════════════

def main() -> int:
    ap = argparse.ArgumentParser(description="تحزيم البيانات للخادم")
    ap.add_argument("--container", default="scanner-localdb",
                    help="حاوية Postgres المحلّية")
    ap.add_argument("--user", default=os.getenv("POSTGRES_USER", "scanner"))
    ap.add_argument("--db", default=os.getenv("POSTGRES_DB", "scanner"))
    ap.add_argument("--check", action="store_true",
                    help="قارِن وحسب — بلا كتابة")
    ap.add_argument("--skip-files", action="store_true",
                    help="القاعدة وحدها، بلا أرشيف data/")
    args = ap.parse_args()

    if shutil.which("docker") is None:
        print("✗ لا ‎docker‎ في المسار. شغّل Docker Desktop.")
        return 1

    # ١) مقارنة الجهتين ─────────────────────────────────────────
    print("═══ ١) القاعدة ═══")
    sq = sqlite_counts(ROOT / "data" / "dashboard.sqlite3")
    try:
        pg = pg_counts(args.container, args.user, args.db)
    except RuntimeError as e:
        print(f"✗ تعذّر سؤال Postgres المحلّية ({args.container}):\n  {e}\n")
        print("  شغّلها:  docker compose -f docker-compose.localdb.yml up -d")
        print("  ثمّ رحّل: انظر docs/POSTGRES.md")
        return 1

    if not pg:
        print("✗ لا جداول في Postgres المحلّية — الترحيل لم يبدأ.")
        print("  اتبع docs/POSTGRES.md خطواتٍ ١ إلى ٤ أوّلاً.")
        return 1

    ok, lines = compare(sq, pg)
    print("\n".join(lines))
    print(f"  المجموع: SQLite {sum(sq.values()):,} · "
          f"Postgres {sum(pg.values()):,}")
    if not ok:
        print("\n✗ ‏Postgres المحلّية ناقصة. أعد الترحيل قبل التحزيم:")
        print("    python web\\manage.py migrate_to_postgres --check")
        print("    python web\\manage.py migrate_to_postgres")
        return 1
    print("✓ ‏Postgres المحلّية تحمل كل ما في SQLite.")

    if args.check:
        print("\n(‎--check‎ — لم يُكتب شيء)")
        return 0

    OUT.mkdir(exist_ok=True)
    manifest: dict = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git": git_head(),
        "db": {"container": args.container, "name": args.db,
               "user": args.user, "rows": pg,
               "total_rows": sum(pg.values())},
        "artifacts": {},
    }

    # ٢) نسخة القاعدة ───────────────────────────────────────────
    #
    # ‎-Fc‎ لا ‎-Fp‎: الصيغة المضغوطة تحمل التسلسلات وترتيب
    # الاستعادة، ويقبلها ‎pg_restore‎ بـ‎--clean‎. والنصّ الخامّ
    # يُدرَج بالترتيب المكتوب فيُصطدم بالمفاتيح الأجنبية.
    print("\n═══ ٢) نسخة القاعدة ═══")
    dump = OUT / "scanner.dump"
    with dump.open("wb") as fh:
        r = subprocess.run(
            ["docker", "exec", args.container, "pg_dump",
             "-U", args.user, "-d", args.db, "-Fc", "--no-owner"],
            stdout=fh, stderr=subprocess.PIPE)
    if r.returncode != 0:
        print("✗ فشل pg_dump:\n" + r.stderr.decode("utf-8", "replace"))
        dump.unlink(missing_ok=True)
        return 1
    manifest["artifacts"]["scanner.dump"] = {
        "bytes": dump.stat().st_size, "sha256": sha256(dump)}
    print(f"✓ {dump.name} — {dump.stat().st_size/1e6:,.1f} م.ب")

    # ٣) الملفّات ────────────────────────────────────────────────
    if not args.skip_files:
        for name, src in (("appdata.tar.gz", ROOT / "data"),
                          ("reports.tar.gz", ROOT / "reports")):
            if not src.is_dir():
                continue
            print(f"\n═══ ٣) {src.name}/ → {name} ═══")
            info = build_tar(src, OUT / name)
            info["sha256"] = sha256(OUT / name)
            manifest["artifacts"][name] = info
            print(f"✓ {info['files']:,} ملفّاً · "
                  f"{info['raw_bytes']/1e9:,.2f} غ.ب → "
                  f"{info['gz_bytes']/1e6:,.0f} م.ب "
                  f"· استُبعد {info['skipped']}")

    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # ═══ وملفّان عاديّان بجانب المانيفست ═══
    #
    # سكربت الخادم لا يقرأ JSON: لا ‎jq‎ ولا Python مضمونان على
    # خادمٍ لا يحمل إلّا Docker. و``sha256sum -c`` موجودٌ في كل
    # توزيعة. فالبرهان يبقى قابلاً للتحقّق بأدوات الصندوق.
    (OUT / "SHA256SUMS").write_text(
        "".join(f"{a['sha256']}  {n}\n"
                for n, a in sorted(manifest["artifacts"].items())),
        encoding="utf-8", newline="\n")
    (OUT / "EXPECTED_ROWS").write_text(
        "".join(f"{t}\t{c}\n" for t, c in sorted(pg.items())),
        encoding="utf-8", newline="\n")

    script = ROOT / "docker-restore.sh"
    if script.exists():
        shutil.copy2(script, OUT / script.name)

    # ٤) ما تنسخه أنت ───────────────────────────────────────────
    total = sum(a.get("bytes", a.get("gz_bytes", 0))
                for a in manifest["artifacts"].values())
    print(f"\n═══ الحزمة جاهزة — {total/1e6:,.0f} م.ب في ship\\ ═══\n")
    print("  scp -r ship user@server:~/scanner-ship")
    print("  ssh user@server 'bash ~/scanner-ship/docker-restore.sh "
          "~/scanner-ship'")
    print("\nوالتفصيل في docs/SHIP.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
