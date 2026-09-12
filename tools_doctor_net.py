# -*- coding: utf-8 -*-
"""لماذا لا تصل الشموع إلى الخادم؟ — فحصُ المصادر الأربعة.

    python tools_doctor_net.py

═══ متى تُستعمل ═══

حين يقول النظام ``بيانات السوق متأخرة جداً`` وقد حاول التحديث
وفشل. الرسالة تقول **أنّ** الشموع قديمة ولا تقول **لماذا**، وبين
السببين فرقٌ في العلاج:

    مفتاحٌ ناقص   ← يُضاف في بورتينر ويُعاد التشغيل
    منفذٌ مغلق    ← جدار الخادم
    حظرٌ جغرافي   ← لا يُصلحه مفتاح ولا جدار

والثالث هو الفخّ: بينانس تردّ ‎451‎ على عناوين كثير من مراكز
البيانات بينما تعمل من بيتك تماماً. فينجح كل شيء على جهازك
ويفشل كلّ شيء على الخادم، ولا رسالة تقول السبب.

═══ ماذا يفعل ═══

يطلب **شمعةً واحدة** من كل مصدرٍ يستعمله النظام فعلاً، ويطبع ما
ردّ به: رمز الحالة، والزمن، وأوّل سطرٍ من الجسد إن كان خطأً.

ولا يطبع مفتاحاً ولا جزءاً منه — يقول «موجود» أو «غائب» فقط.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request

TIMEOUT = 15

# استيراد ``scanner`` يحمّل ‎.env‎ ويترجم الأسماء المرادفة. وبلا
# ذلك يقول هذا الفاحص «غائب» عن مفتاحٍ يقرؤه النظام بمرادفه —
# وهو بالضبط الالتباس الذي وُجد ليزيله.
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
try:
    import scanner  # noqa: F401
except Exception as _exc:  # noqa: BLE001
    print(f"⚠ تعذّر تحميل حزمة scanner ({_exc}) — تُقرأ البيئة كما هي")

# (اسم، سوق، رابط شمعةٍ واحدة، ترويسات، متغيّرات لازمة)
PROBES = [
    ("بينانس (شموع الكريبتو)", "crypto",
     "https://data-api.binance.vision/api/v3/klines"
     "?symbol=BTCUSDT&interval=4h&limit=1", {}, []),
    ("بينانس — المرآة الثانية", "crypto",
     "https://api.binance.com/api/v3/klines"
     "?symbol=BTCUSDT&interval=4h&limit=1", {}, []),
    ("ياهو (شموع السوق السعودي)", "saudi",
     "https://query1.finance.yahoo.com/v8/finance/chart/2222.SR"
     "?range=5d&interval=1d", {"User-Agent": "Mozilla/5.0"}, []),
    ("ألباكا (شموع السوق الأمريكي)", "us",
     "https://data.alpaca.markets/v2/stocks/AAPL/bars"
     "?timeframe=1Day&limit=1", {}, ["ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY"]),
    ("سهمك (اكتشاف السوق السعودي)", "saudi",
     "https://api.sahmk.sa/api/v1/market/companies",
     {}, ["SAHMK_API_KEY"]),
]


def probe(url: str, headers: dict) -> tuple[str, str]:
    """(الحكم، التفصيل) — ولا يرمي أبداً."""
    req = urllib.request.Request(url, headers=headers)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read(400)
            ms = (time.time() - t0) * 1000
            return "ok", f"HTTP {r.status} · {ms:,.0f}ms · {len(body)}ب"
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read(200).decode("utf-8", "replace").replace("\n", " ")
        except Exception:  # noqa: BLE001
            pass
        # ═══ ٤٥١ ليست خطأ إعداد ═══
        #
        # «غير متاح لأسباب قانونية» = حظرٌ على عنوان الخادم. ولا
        # مفتاح ولا جدارٌ يغيّره — يحتاج وكيلاً أو مزوّداً آخر.
        note = {401: "مفتاح خاطئ أو ناقص", 403: "مرفوض — مفتاح أو حظر",
                429: "تجاوز الحدّ — أبطئ", 451: "حظر جغرافي على عنوان الخادم",
                418: "حظر مؤقّت من بينانس"}.get(e.code, "")
        return "http", f"HTTP {e.code}" + (f" — {note}" if note else "") + \
                       (f" · {body[:120]}" if body else "")
    except urllib.error.URLError as e:
        r = str(e.reason)
        note = ("لا DNS — الحاوية بلا مُحلِّل أسماء"
                if "Name or service not known" in r or "getaddrinfo" in r
                # ‏«Tunnel connection failed» توقيعُ وكيلٍ يرفض، لا
                # جدارٍ يصمت: ‎HTTPS_PROXY‎ مضبوط ويمنع الوجهة.
                else "وكيلٌ يرفض (HTTPS_PROXY مضبوط ويحجب الوجهة)"
                if "Tunnel connection failed" in r
                else "المنفذ مغلق أو لا مسار للخارج"
                if "refused" in r or "unreachable" in r else "")
        return "net", r[:100] + (f" — {note}" if note else "")
    except (socket.timeout, TimeoutError):
        return "net", f"لا ردّ خلال {TIMEOUT}ث — جدارٌ يبتلع الطلب غالباً"
    except Exception as e:  # noqa: BLE001
        return "err", f"{type(e).__name__}: {str(e)[:100]}"


def main() -> int:
    print("═══ المفاتيح ═══")
    # ═══ كل تسمياته ═══
    #
    # سؤالٌ عن اسمٍ واحد يقول «موجود» والكود لا يقرؤه — وهو عطبٌ
    # وقع: ‏compose يمرّر ``ALPACA_API_KEY`` والمحوّل كان يقرأ
    # ``ALPACA_API_KEY_ID`` وحده. فيُسأل عن المجموعة كلّها.
    GROUPS = {
        "مفتاح Alpaca": ("ALPACA_API_KEY_ID", "APCA_API_KEY_ID",
                         "ALPACA_API_KEY"),
        "سرّ Alpaca": ("ALPACA_API_SECRET_KEY", "APCA_API_SECRET_KEY",
                       "ALPACA_SECRET_KEY"),
        "مفتاح سهمك": ("SAHMK_API_KEY",),
        "توكن تيليجرام": ("TELEGRAM_TOKEN", "TELEGRAM_BOT_TOKEN"),
    }
    # الوجود لا القيمة: طبعُ جزءٍ من مفتاح في سجلٍّ يُقرأ لاحقاً
    # تسريبٌ صغير، وهو كافٍ لتمييزه حين يُسرَّب الباقي.
    for label, names in GROUPS.items():
        found = next((n for n in names if os.getenv(n, "").strip()), "")
        if found:
            print(f"  ✓ {label:16s} موجود باسم {found} "
                  f"({len(os.getenv(found, ''))} حرفاً)")
        else:
            print(f"  ✗ {label:16s} غائب — جُرّب: {' · '.join(names)}")

    print("\n═══ المصادر ═══")
    verdicts = {}
    for name, market, url, headers, needs in PROBES:
        missing = [k for k in needs if not os.getenv(k)]
        if missing:
            print(f"  ⊘ {name}\n      يحتاج {' و'.join(missing)} — لم يُجرَّب")
            verdicts.setdefault(market, []).append(("key", name))
            continue
        h = dict(headers)
        if "ALPACA_API_KEY_ID" in needs:
            h["APCA-API-KEY-ID"] = os.getenv("ALPACA_API_KEY_ID", "")
            h["APCA-API-SECRET-KEY"] = os.getenv("ALPACA_API_SECRET_KEY", "")
        if "SAHMK_API_KEY" in needs:
            h["Authorization"] = "Bearer " + os.getenv("SAHMK_API_KEY", "")
        kind, detail = probe(url, h)
        mark = {"ok": "✓", "http": "✗", "net": "✗", "err": "✗"}[kind]
        print(f"  {mark} {name}\n      {detail}")
        verdicts.setdefault(market, []).append((kind, name))

    # ═══ الحكم لكل سوق ═══
    #
    # مصدرٌ واحد يعمل يكفي السوق: بينانس لها مرآتان، والسعودي
    # يجلب من ياهو ويكتشف من سهمك — فتعطّل الاكتشاف يقلّل الرموز
    # ولا يمنع الشموع.
    print("\n═══ الخلاصة ═══")
    names = {"crypto": "الكريبتو", "us": "الأمريكي", "saudi": "السعودي"}
    bad = 0
    for m, rows in verdicts.items():
        good = [n for k, n in rows if k == "ok"]
        if good:
            print(f"  ✓ {names[m]:10s} يصل — {good[0]}")
        else:
            bad += 1
            why = rows[0][0]
            fix = {"key": "أضف المفتاح في بورتينر ← Environment variables",
                   "http": "انظر رمز الحالة أعلاه — ٤٥١ يعني حظراً جغرافياً",
                   "net": "لا مخرج من الحاوية: DNS أو جدار الخادم",
                   "err": "خطأ غير متوقّع — انسخ السطر أعلاه"}[why]
            print(f"  ✗ {names[m]:10s} لا يصل — {fix}")

    if not bad:
        print("\nكل المصادر تصل. فالتأخّر ليس من الشبكة:")
        print("  راجع /jobs/ — مهمّة market_sync قد تكون متعطّلة أو مُشبَعة.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
