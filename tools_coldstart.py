# -*- coding: utf-8 -*-
"""تمرين إقلاعٍ بارد — يبني المكدّس على وحداتٍ فارغة ويستجوبه.

    python tools_coldstart.py            # البناء والفحص ثمّ الهدم
    python tools_coldstart.py --keep     # يُبقي المكدّس للفحص اليدوي
    python tools_coldstart.py --no-build # صورةٌ مبنيّة سلفاً

═══ لماذا وُجد ═══

كل عطبٍ ظهر على الخادم في هذه الجلسة كان من صنفٍ واحد: **شيءٌ لم
يُجرَّب قطّ من الصفر.**

    أقفال مزامنة متروكة      حالةٌ تراكمت شهراً على الجهاز
    ‏universe: auto معطّل     تخفيه ملفّاتُ القرص المتراكمة
    اسمٌ يُمرَّر واسمٌ يُقرأ    ‎.env‎ المحلّي مكتوبٌ بأسماء الكود
    المفتاح السرّي يتبدّل     ‎.env‎ المحلّي مكتوبٌ باليد ويبقى
    فحص صحّة المجدول         لا يوجد مجدولٌ منفصل على الجهاز
    بوّابة تحجب السوق        بيانات الجهاز لا تبرد أبداً

الستّة غير مرئيّة على جهازٍ يعمل منذ أشهر، وحتميّة على وحدةِ
تخزينٍ فارغة. ولم يكن العيب في البناء ولا في المعمار — بل في أنّ
**الإقلاع البارد لم يكن مساراً مختبَراً**، فكان كل نشرٍ أوّلَ
تجربةٍ له.

وظهورها واحداً بعد واحد ليس صدفة: كلٌّ منها يحجب ما بعده. فتُصلَح
الأولى فتظهر الثانية — عشر جولات بدل جولة.

═══ وما يفعله ═══

يرفع المكدّس على وحداتٍ **جديدة فارغة**، ثمّ يسأل ستّة أسئلة لكلّ
عطبٍ منها. ويعمل على جهازك قبل النشر، فيظهر ما كان يظهر على
الخادم — وقبله.

⚠ يستعمل اسم مشروعٍ مستقلّاً (``mscold``) ووحداتٍ خاصّة به، فلا
  يمسّ مكدّسك ولا بياناتك. ويهدم نفسه في النهاية.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
PROJECT = "mscold"           # اسمٌ لا يصطدم بـ market-scanner
COMPOSE = ["docker", "compose", "-p", PROJECT, "-f", str(ROOT / "docker-compose.yml")]

# ═══ بيئةٌ خاصّة بالتمرين ═══
#
# ‏compose يفضّل بيئة الصَّدَفة على ‎.env‎، فهذه تعلو ما في ملفّك.
#
# **المنفذ ٨٠٩٩ لا ٨٠٠٠.** مكدّسك — أو ``manage.py runserver`` —
# يحتجز ٨٠٠٠ غالباً، فيسقط التمرين بـ«port is already allocated»
# ويبدو الكود معطوباً وهو سليم.
#
# **وكلمة مرورٍ للتمرين.** ``POSTGRES_PASSWORD`` بلا قيمةٍ
# افتراضية في compose. وهي هنا لقاعدةٍ تُخلَق وتُمحى بعد دقائق،
# ولا تُنشر على منفذ — فلا سرّ فيها.
RUN_ENV = {
    "WEB_BIND": "127.0.0.1",
    "WEB_PORT": "8099",
    "POSTGRES_PASSWORD": "coldstart_rehearsal_only",
    "SEED_JOBS": "1",
}

results: list[tuple[bool, str, str]] = []


def check(name: str, ok: bool, extra: str = "") -> None:
    results.append((bool(ok), name, extra))
    print(("  ✓ " if ok else "  ✗ ") + name + (f"   [{extra}]" if extra and not ok else ""))


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    kw.setdefault("env", {**os.environ, **RUN_ENV})
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw)


def dexec(svc: str, *args: str, timeout: int = 180) -> subprocess.CompletedProcess:
    return run([*COMPOSE, "exec", "-T", svc, *args], timeout=timeout)


def teardown() -> None:
    # ‎-v‎ لازمة: بلاها تبقى الوحدات، فيصير التمرين التالي **دافئاً**
    # ويمرّ كاذباً. وهي آمنة هنا وحدها لأنّ المشروع مستقلّ.
    run([*COMPOSE, "down", "-v", "--remove-orphans"], timeout=180)


def main() -> int:
    ap = argparse.ArgumentParser(description="تمرين إقلاع بارد")
    ap.add_argument("--keep", action="store_true", help="أبقِ المكدّس بعده")
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--wait", type=int, default=180,
                    help="ثوانٍ لانتظار أوّل دورة مزامنة")
    args = ap.parse_args()

    if shutil.which("docker") is None:
        print("✗ لا docker في المسار.")
        return 1

    env_ok = (ROOT / ".env").exists()
    print("═══ تمرين إقلاع بارد ═══")
    print(f"  المشروع: {PROJECT} (مستقلّ — لا يمسّ market-scanner)")
    print(f"  المنفذ : 127.0.0.1:{RUN_ENV['WEB_PORT']} (لا 8000 — كي لا يصطدم بمكدّسك)")
    print(f"  ‎.env‎: {'موجود — ستُستعمل مفاتيحه' if env_ok else 'غائب — بلا مفاتيح'}")
    if not env_ok:
        print("  ⚠ بلا مفاتيح لن يُختبَر السوق الأمريكي ولا السعودي.")

    print("\n═══ ١) وحداتٌ نظيفة ═══")
    teardown()          # إن بقي شيءٌ من تمرينٍ سابق
    print("  هُدم ما سبق (إن وُجد)")

    print("\n═══ ٢) الإقلاع ═══")
    t0 = time.time()
    cmd = [*COMPOSE, "up", "-d"] + ([] if args.no_build else ["--build"])
    r = run(cmd, timeout=1800)
    if r.returncode != 0:
        print("✗ فشل الإقلاع:\n" + (r.stderr or r.stdout)[-2000:])
        if not args.keep:
            teardown()
        return 1
    print(f"  أقلع في {time.time()-t0:,.0f}ث")

    # ═══ ٣) الحاويات تبقى حيّة ═══
    #
    # حاويةٌ تُقلع ثمّ تموت بعد ثوانٍ تبدو ناجحة في مخرَج ``up``.
    print("\n═══ ٣) بعد ٣٠ث ═══")
    time.sleep(30)
    ps = run([*COMPOSE, "ps", "--format", "json"], timeout=60)
    states = {}
    for line in ps.stdout.splitlines():
        try:
            d = json.loads(line)
            states[d.get("Service", "?")] = (d.get("State", "?"), d.get("Health", ""))
        except ValueError:
            pass
    for svc in ("db", "web", "scheduler"):
        st, health = states.get(svc, ("مفقود", ""))
        check(f"٣ {svc} يعمل", st == "running", f"{st} {health}")

    print("\n═══ ٤) الأعطال الستّة ═══")

    # (١) المفتاح السرّي يثبت بين نداءين
    def secret() -> str:
        r = dexec("web", "python", "-c",
                  "import os,sys;sys.path.insert(0,'web');"
                  "os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings');"
                  "from config.settings import SECRET_KEY;print(SECRET_KEY)")
        return (r.stdout or "").strip().splitlines()[-1] if r.stdout.strip() else ""

    k1, k2 = secret(), secret()
    check("١ المفتاح السرّي ثابت", bool(k1) and k1 == k2,
          f"{k1[:8]}… ≠ {k2[:8]}…")
    r = dexec("web", "test", "-s", "/app/data/.django_secret_key")
    check("  ومحفوظ في وحدة البيانات", r.returncode == 0)

    # (٢) لا أقفال متروكة بعد الإقلاع
    r = dexec("scheduler", "sh", "-c",
              "ls /app/data/market_sync/locks/*.lock 2>/dev/null | wc -l")
    n_locks = (r.stdout or "0").strip().splitlines()[-1] if r.stdout.strip() else "0"
    check("٢ لا أقفال متروكة", n_locks.isdigit() and int(n_locks) < 50, n_locks)

    # (٣) المفاتيح تصل الكود بأسمائها المرادفة
    r = dexec("web", "python", "-c",
              "import scanner;from scanner.adapters.alpaca import credentials;"
              "k,s=credentials();print('KEYS', bool(k), bool(s))")
    line = next((l for l in (r.stdout or "").splitlines() if l.startswith("KEYS")), "")
    if env_ok:
        check("٣ مفاتيح Alpaca تصل المحوّل", "KEYS True True" in line, line or r.stderr[-120:])
    else:
        check("٣ مفاتيح Alpaca (لا ‎.env‎ — تُخطّى)", True)

    # (٤) الكون أكبر من قائمة البذور
    r = dexec("web", "python", "-c",
              "import logging;logging.disable(logging.ERROR);"
              "from scanner.market_sync.service import MarketDataSyncService as S;"
              "print('UNIV', len(S().resolve_symbols('crypto')))", timeout=300)
    line = next((l for l in (r.stdout or "").splitlines() if l.startswith("UNIV")), "")
    n = int(line.split()[1]) if line.split()[1:] and line.split()[1].isdigit() else 0
    # ‏١٠ بالضبط = قائمة الاحتياط وحدها = الاكتشاف لم يعمل
    check("٤ الاكتشاف يتجاوز قائمة البذور", n > 10, f"{n} رمزاً")

    # (٥) فحص صحّة المجدول ليس كاذباً
    time.sleep(5)
    r = run([*COMPOSE, "ps", "--format", "json"], timeout=60)
    sched_health = ""
    for line in r.stdout.splitlines():
        try:
            d = json.loads(line)
            if d.get("Service") == "scheduler":
                sched_health = d.get("Health", "")
        except ValueError:
            pass
    # ``starting`` مقبول: ‎start_period‎ خمس دقائق
    check("٥ المجدول ليس unhealthy",
          sched_health != "unhealthy", sched_health or "بلا فحص")

    # (٦) الشموع تصل، والبوّابة لا تحجب بلا سبب
    print(f"\n═══ ٥) انتظار أوّل مزامنة ({args.wait}ث) ═══")
    time.sleep(args.wait)
    r = dexec("scheduler", "python", "-c",
              "import logging;logging.disable(logging.ERROR);"
              "from scanner.market_sync.service import MarketDataSyncService as S;"
              "g=S().scan_freshness_gate('crypto','4h',auto_refresh=False);"
              "print('GATE', g['ok'], g['code'], len(g.get('usable',[])),"
              "len(g.get('excluded',[])))", timeout=600)
    line = next((l for l in (r.stdout or "").splitlines() if l.startswith("GATE")), "")
    parts = line.split()
    check("٦ الشموع وصلت", len(parts) > 3 and parts[3].isdigit() and int(parts[3]) > 0,
          line or (r.stderr or "")[-150:])
    check("  والبوّابة لا تحجب السوق كلّه",
          len(parts) > 1 and parts[1] == "True", line)

    print("\n═══ الخلاصة ═══")
    bad = [n for ok, n, _ in results if not ok]
    print(f"{len(results)-len(bad)}/{len(results)} "
          + ("✓ الإقلاع البارد سليم" if not bad
             else "✗ " + " · ".join(bad[:6])))
    if bad:
        print("\nسجلّ المجدول:")
        print(run([*COMPOSE, "logs", "--tail", "40", "scheduler"],
                  timeout=60).stdout[-1500:])

    if args.keep:
        print(f"\nالمكدّس باقٍ. للهدم:\n  docker compose -p {PROJECT} "
              f"-f docker-compose.yml down -v")
    else:
        print("\nأهدم المكدّس…")
        teardown()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
