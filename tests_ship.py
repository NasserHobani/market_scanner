# -*- coding: utf-8 -*-
"""نقل البيانات إلى الخادم — وأربعة أعطال تُنتج «نجاحاً» كاذباً.

═══ الأوّل: أرشيفٌ جذرُه خاطئ ═══

أرشيفٌ يحمل ``data/crypto/…`` يُفَكّ في ‎/app/data‎ فينتج
‎/app/data/data/crypto‎. والسكربت ينجح، والعدّاد يقول ٤٢٣١ ملفّاً،
والنظام لا يرى شمعةً واحدة. فالجذر يجب أن يكون **محتوى** المجلّد.

═══ الثاني: ابتلاع المدخل ═══

``docker exec -i`` يوصل مدخل الطرفية بالحاوية ويبتلعه. ونداءٌ كهذا
داخل حلقةٍ تقرأ ``EXPECTED_ROWS`` يلتهم بقيّة الملفّ بعد أوّل سطر
— فيُفحَص جدولٌ واحد من ثلاثة عشر، ويُطبَع ✓، ويخرج بصفر.

═══ الثالث: الترتيب ═══

الاستعادة قبل إيقاف المجدول تترك جداول نصفَ مستعادة. والنسخة
الاحتياطية بعد ‎DROP SCHEMA‎ تنسخ العدم. وكلاهما يُنهي بلا خطأ.

═══ الرابع: تحزيم قاعدةٍ متأخّرة ═══

من رحّل إلى Postgres ثمّ عاد فعمل على SQLite، يحزم ``pg_dump``
عنده الماضي. فالمقارنة تسبق التحزيم، والاتّجاه مقصود: Postgres
أكثرُ سليم، وأقلُّ رفض.

ولا يشغّل هذا الملفّ Docker: يحاكيه ليقيس ما يفعله السكربت.
"""
from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import tools_ship as S  # noqa: E402

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


SH_RAW = (ROOT / "docker-restore.sh").read_text(encoding="utf-8")
PY_RAW = (ROOT / "tools_ship.py").read_text(encoding="utf-8")
TREE = ast.parse(PY_RAW)

# ═══ الفحص على الكود لا على شرحه ═══
#
# النصّ الخامّ يطابق التعليقات، وتعليقات هذين الملفّين تذكر
# ``docker exec -i`` و``--strip-components`` لتشرح لماذا تُجتنَب.
# ففحصٌ على الخامّ يجدها ويعلن العطب موجوداً — أو يعلنه مُصلَحاً
# بعد أن يُزال الكود ويبقى الشرح.
SH = "\n".join(l for l in SH_RAW.splitlines() if not l.lstrip().startswith("#"))


def _body(name: str) -> str:
    fn = next(n for n in ast.walk(TREE)
              if isinstance(n, ast.FunctionDef) and n.name == name)
    seg = ast.get_source_segment(PY_RAW, fn) or ""
    doc = ast.get_docstring(fn, clean=False)
    if doc:
        seg = seg.replace(doc, "", 1)
    return "\n".join(l for l in seg.splitlines()
                     if not l.strip().startswith("#"))


def at(needle: str) -> int:
    """موضع أوّل ظهور في الكود — لقياس الترتيب."""
    return SH.find(needle)


# ═══════════ ١) الاستبعاد ═══════════
#
# قفلٌ منسوخٌ من جهازك يجعل ‎market_sync‎ على الخادم يظنّ الرمز قيد
# المزامنة فيتخطّاه — بلا خطأ، وبلا شمعةٍ جديدة، إلى الأبد.
for path, want in [
    ("crypto/15m/BTCUSDT.npz", False),
    ("knowledge/records.jsonl", False),
    ("feature_snapshots/v3_snapshots.jsonl", False),
    ("market_sync/locks/crypto_BTCUSDT_15m.lock", True),
    ("dashboard.sqlite3", True),
    ("dashboard.sqlite3-wal", True),
    ("dashboard.sqlite3-shm", True),
    ("dashboard.sqlite3.bak-223950", True),
    (".django_secret_key", True),
    ("x/__pycache__/y.pyc", True),
]:
    got = bool(S._excluded(Path(path)))
    check(f"١ {'يُستبعَد' if want else 'يُحزَم'}: {path}", got == want)


# ═══════════ ٢) جذر الأرشيف ═══════════
with tempfile.TemporaryDirectory() as _d:
    d = Path(_d)
    src = d / "data"
    (src / "crypto" / "15m").mkdir(parents=True)
    (src / "crypto" / "15m" / "A.npz").write_bytes(b"x" * 64)
    (src / "knowledge").mkdir()
    (src / "knowledge" / "records.jsonl").write_text("{}\n")
    (src / "dashboard.sqlite3").write_bytes(b"db")
    (src / "locks").mkdir()
    (src / "locks" / "a.lock").write_text("1")

    info = S.build_tar(src, d / "t.tgz")
    names = sorted(tarfile.open(d / "t.tgz").getnames())

    check("٢ الجذر محتوى المجلّد لا اسمه",
          names == ["crypto/15m/A.npz", "knowledge/records.jsonl"], str(names))
    check("  ولا مسار يبدأ بـ data/",
          not any(n.startswith("data/") for n in names))
    check("  ولا مسار مطلق أو صاعد",
          not any(n.startswith(("/", "..")) for n in names))
    check("  والفواصل ‎/‎ لا ‎\\‎ (ويندوز → لينكس)",
          not any("\\" in n for n in names))
    check("  والمستبعَد محسوب لا مُهمَل",
          info["files"] == 2 and info["skipped"] == 2, str(info))
    check("  والبصمة تُحسب فعلاً", len(S.sha256(d / "t.tgz")) == 64)


# ═══════════ ٣) اتّجاه المقارنة ═══════════
check("٣ متساويان يمرّان", S.compare({"t": 10}, {"t": 10})[0])
# بعد الترحيل يكتب النظام في Postgres وحدها ويتجمّد ملفّ SQLite
check("  وPostgres أكثر يمرّ", S.compare({"t": 10}, {"t": 12})[0])
check("  وPostgres أقلّ يُرفَض", not S.compare({"t": 10}, {"t": 9})[0])
check("  وجدولٌ مفقود يُرفَض", not S.compare({"t": 10}, {})[0])
check("  والفرق يُطبَع لا يُبتلَع",
      any("✗" in l for l in S.compare({"t": 10}, {"t": 9})[1]))

# وقراءة SQLite ترى سجلّ WAL: الفتح في مكانه، للقراءة، بـ uri
sq = _body("sqlite_counts")
check("  وSQLite تُفتح للقراءة في مكانها",
      "mode=ro" in sq and "uri=True" in sq)

main = _body("main")
check("  والتحزيم يتوقّف عند الرفض", "return 1" in main)
check("  وpg_dump بصيغة ‎-Fc‎", '"-Fc"' in main)
check("  وتُكتَب SHA256SUMS", "SHA256SUMS" in main)
check("  وتُكتَب EXPECTED_ROWS", "EXPECTED_ROWS" in main)
# ‎\n‎ صريح: ويندوز يكتب ‎\r\n‎ افتراضاً، و‎sha256sum -c‎ على لينكس
# يجعل ‎\r‎ جزءاً من اسم الملفّ فلا يجده
check("  بنهايات أسطر لينكس", main.count('newline="\\n"') >= 2)


# ═══════════ ٤) ابتلاع المدخل ═══════════
check("٤ psql بلا ‎-i‎",
      "docker exec -i" not in SH.split("psql_()")[1].split("}")[0]
      if "psql_()" in SH else False)
check("  والحلقة تقرأ من الوصف 3", "<&3" in SH and "3< EXPECTED_ROWS" in SH)
check("  و‎-i‎ لـ pg_restore وحده",
      SH.count("docker exec -i") == 1 and "pg_restore" in SH[at("docker exec -i"):at("docker exec -i") + 80])


# ═══════════ ٥) الترتيب ═══════════
i_sha = at("sha256sum -c")
i_stop = at("docker stop")
i_back = at("pre-restore-")
i_drop = at("DROP SCHEMA")
i_rest = at("pg_restore")
i_start = at("docker start \"$c\"") if at("docker start \"$c\"") >= 0 else at("docker start")
# ═══ موضع الحلقة لا موضع أوّل ذكر ═══
#
# ``EXPECTED_ROWS`` يُذكر أوّلاً في تحقّق المتطلّبات (خطوة ١) —
# وهو **قبل** الاستعادة بالضرورة. فقياس الترتيب بأوّل ظهورٍ
# للاسم يقارن الشيء بغير نفسه. المقصود حلقةُ التحقّق، وعلامتها
# إعادةُ توجيهها.
i_verify = at("3< EXPECTED_ROWS")

check("٥ البصمة قبل أيّ إيقاف", 0 <= i_sha < i_stop, f"{i_sha} < {i_stop}")
check("  والإيقاف قبل الاستعادة", 0 <= i_stop < i_rest)
check("  والنسخة الاحتياطية قبل التفريغ", 0 <= i_back < i_drop)
check("  والتفريغ قبل الاستعادة", 0 <= i_drop < i_rest)
check("  والتحقّق بعد الاستعادة", i_verify > i_rest)
check("  والتشغيل بعد كل شيء", at("═══ ٨") > i_rest)


# ═══════════ ٦) الوحدة تُكتشَف لا تُخمَّن ═══════════
#
# بادئة المشروع تتغيّر باسم المجلّد وبإعدادات بورتينر. والتخمين
# الخاطئ يُنشئ وحدةً **جديدة فارغة** ويبدو ناجحاً تماماً.
check("٦ اسم الوحدة من docker inspect",
      "Mounts" in SH and "Destination" in SH)
check("  ولا بادئة مشروع مكتوبة في الكود",
      "market-scanner_appdata" not in SH)
check("  والحاويات بلافتات compose",
      "com.docker.compose.service" in SH
      and "com.docker.compose.project" in SH)
check("  واسم المكدّس قابل للتغيير", 'STACK:-' in SH)
check("  وبلا ‎--strip-components‎", "--strip-components" not in SH)
check("  والصورة المساعدة موجودة أصلاً",
      "Config.Image" in SH and "docker pull" not in SH)
check("  ولا يُحذف ‎/app/data‎",
      "rm -rf /dest" not in SH and "rm -rf /d" not in SH)


# ═══════════ ٧) الفشل يُعلَن ═══════════
check("٧ set -euo pipefail", "set -euo pipefail" in SH)
check("  وعدمُ التطابق يخرج بـ 1", "exit 1" in SH[i_verify:])
check("  ومسار التراجع يُطبَع", SH[i_verify:].count("pre-restore") >= 1
      or "للتراجع" in SH_RAW)


# ═══════════ ٨) بروفة كاملة بـ docker مُحاكى ═══════════
#
# الفحوص أعلاه ثابتة: تقرأ ولا تشغّل. وهذه تشغّل السكربت كلّه على
# ‎docker‎ مزيّف، فتقيس ما لا يُقرأ من النصّ: الترتيب الفعليّ،
# ورمز الخروج، وكم جدولاً فُحص حقّاً.
#
# ═══ وما لا تكشفه ═══
#
# جُرِّبت بإعادة ‎-i‎ إلى ‎psql_‎ فمرّت — لأنّ الحلقة تقرأ من الوصف
# ٣ فلا يمسّها ابتلاع المدخل أصلاً. فالحزام الأوّل هو الوصف ٣،
# و‎-i‎ يمسكه الفحص الثابت (٤) وحده. وقولُ غير ذلك يشتري طمأنينة
# بلا ثمن.
#
# وتُتخطّى إن غاب bash (ويندوز بلا Git Bash).
BASH = shutil.which("bash")
if not BASH:
    check("٨ البروفة (تحتاج bash — تُخطَّى)", True, "skip")
else:
    with tempfile.TemporaryDirectory() as _w:
        w = Path(_w)
        b = w / "bundle"
        b.mkdir()
        (b / "scanner.dump").write_bytes(b"FAKEDUMP\n")
        with tarfile.open(b / "appdata.tar.gz", "w:gz") as t:
            p = w / "A.npz"
            p.write_bytes(b"npz")
            t.add(p, arcname="crypto/15m/A.npz")
        rows = {"dashboard_trade": 721, "dashboard_watch": 3006,
                "dashboard_scanresult": 16308}
        (b / "EXPECTED_ROWS").write_text(
            "".join(f"{k}\t{v}\n" for k, v in rows.items()), newline="\n")
        sums = "".join(f"{S.sha256(b / n)}  {n}\n"
                       for n in ("appdata.tar.gz", "scanner.dump"))
        (b / "SHA256SUMS").write_text(sums, newline="\n")

        mock = w / "bin"
        mock.mkdir()
        (mock / "docker").write_text(r'''#!/usr/bin/env bash
case "$1" in
  ps) svc=""; proj=""
      for a in "$@"; do case "$a" in
        *compose.service=*) svc="${a##*=}";;
        *compose.project=*) proj="${a##*=}";; esac; done
      case "$*" in *--format*) echo "  m-db-1 (market-scanner)"; exit 0;; esac
      [ "$proj" = "market-scanner" ] || exit 0
      case "$svc" in db) echo dbc;; web) echo webc;; scheduler) echo schc;; esac ;;
  inspect)
      case "$*" in
        *Destination*app/data*) echo "proj_appdata" ;;
        *Destination*app/reports*) echo "proj_reports" ;;
        *Config.Image*) echo "postgres:16-alpine" ;;
        *Config.Env*) printf 'POSTGRES_USER=scanner\nPOSTGRES_DB=scanner\n' ;;
      esac ;;
  exec) q="${@: -1}"
      # ‎-i‎ يبتلع المدخل — والمحاكي يبتلعه مثله، وإلّا لم تكشف
      # البروفة العطب الذي وُضعت له
      case "$*" in *" -i "*) cat >/dev/null ;; esac
      case "$*" in
        *pg_isready*) exit 0 ;;
        *pg_dump*) echo OLD ;;
        *pg_restore*) cat >/dev/null ;;
        *) case "$q" in
             *dashboard_trade*) echo 721 ;;
             *dashboard_watch*) echo 3006 ;;
             *dashboard_scanresult*) echo 16308 ;;
             *) echo "" ;; esac ;;
      esac ;;
  run) case "$*" in *find*) echo 4231 ;; esac ;;
  start|stop) exit 0 ;;
esac
''', newline="\n")
        (mock / "docker").chmod(0o755)

        env = dict(os.environ, PATH=f"{mock}{os.pathsep}{os.environ['PATH']}")

        def run(bundle: Path, **kw) -> subprocess.CompletedProcess:
            # ‎DEVNULL‎ لا الوراثة: السكربت يُشغَّل على الخادم عبر
            # ssh بلا طرفية، و‎docker exec -i‎ الذي يبتلع مدخلاً
            # مفتوحاً يعلّق هنا بدل أن يفشل — فيصير الفحص تعليقاً.
            return subprocess.run(
                [BASH, str(ROOT / "docker-restore.sh"), str(bundle)],
                capture_output=True, text=True, env={**env, **kw},
                stdin=subprocess.DEVNULL,
                encoding="utf-8", errors="replace", timeout=120)

        r = run(b)
        out = r.stdout + r.stderr
        check("٨ البروفة تنجح", r.returncode == 0, out[-400:])
        # ═══ الفحص الذي يكشف ابتلاع المدخل ═══
        #
        # ‏١٣ جدولاً و‎-i‎ موجود = سطرٌ واحد يُفحَص وخروجٌ بصفر.
        # فالعدد هو الدليل، لا رمز الخروج.
        check("  وكل الجداول الثلاثة فُحصت",
              sum(f"✓ {k}" in out.replace("  ", " ") or k in out
                  for k in rows) == 3, out[-300:])
        check("  ونسخة التراجع أُخذت", "pre-restore-" in out)
        check("  والأرشيف فُكّ في الوحدة", "proj_appdata" in out)

        # عددٌ لا يطابق ⇒ خروجٌ بـ 1 ولا ادّعاء نجاح
        (b / "EXPECTED_ROWS").write_text(
            "dashboard_trade\t999\n", newline="\n")
        (b / "SHA256SUMS").write_text(sums, newline="\n")
        r2 = run(b)
        check("  وعددٌ مخالف يفشل", r2.returncode == 1)
        check("  ولا يقول «تمّ»", "✓ تمّ" not in r2.stdout)

        # بصمةٌ لا تطابق ⇒ توقّفٌ **قبل** لمس القاعدة
        (b / "scanner.dump").write_bytes(b"CORRUPTED\n")
        r3 = run(b)
        check("  وبصمةٌ مكسورة توقف مبكّراً", r3.returncode == 1)
        check("  قبل إيقاف أيّ حاوية",
              "إيقاف web" not in r3.stdout, r3.stdout[-200:])

        # مكدّسٌ غير موجود ⇒ رسالةٌ تعرض الأسماء المتاحة
        (b / "scanner.dump").write_bytes(b"FAKEDUMP\n")
        (b / "SHA256SUMS").write_text(
            "".join(f"{S.sha256(b / n)}  {n}\n"
                    for n in ("appdata.tar.gz", "scanner.dump")), newline="\n")
        r4 = run(b, STACK="nope")
        check("  ومكدّسٌ مجهول يشرح لا يصمت",
              r4.returncode == 1 and "m-db-1" in (r4.stdout + r4.stderr))


# ═══════════ التقرير ═══════════
print(__doc__.strip().splitlines()[0])
print()
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f"   [{extra}]" if extra and not ok else ""))
bad = [n for ok, n, _ in results if not ok]
print()
print(f"{len(results) - len(bad)}/{len(results)} "
      + ("✓" if not bad else "✗ فشل: " + " · ".join(bad[:5])))
sys.exit(1 if bad else 0)
