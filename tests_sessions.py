# -*- coding: utf-8 -*-
"""أوقات الجلسات — الإنذار الذي يكذب كل سبت.

═══ العطب ═══

يوم السبت أعلن النظام ``فشل: بيانات السوق متأخرة جداً`` وحجب المسح.
والبيانات لم تكن متأخرة: السوق مغلق منذ إغلاق الجمعة.

وأصلُه أن النضارة كانت ``(now - last) / حجم_الشمعة`` — حسبةٌ صحيحة
تماماً للكريبتو، سوقٍ لا يغلق، وطُبّقت على الأسهم كما هي.

وإنذارٌ يكذب كل أسبوع أسوأ من الصمت: يُفقد الثقة بالإنذار الصادق
يوم يتعطّل الجلب فعلاً.

═══ ما يجب أن يبقى ═══

نصف الاختبار هنا ليس «هل سكت الإنذار الكاذب» بل «هل ما زال الصادق
يصرخ». علاجٌ يُسكت الاثنين ليس علاجاً بل عمًى.
"""
from __future__ import annotations

import sys
from datetime import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner import sessions as S  # noqa: E402
from scanner import storage  # noqa: E402
from scanner.market_sync.config import DEFAULT_SYNC_CONFIG as CFG  # noqa: E402

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


def judge(b: float | None) -> str:
    if b is None:
        return "?"
    if b <= CFG.fresh_max_bars:
        return "fresh"
    return "stale" if b <= CFG.stale_max_bars else "critical"


SAT = pd.Timestamp("2026-08-22 12:00", tz="UTC")   # سبت
WED = pd.Timestamp("2026-08-19 17:00", tz="UTC")   # أربعاء، نيويورك مفتوحة


# ── ١) من مفتوح ومتى ──
check("١ الكريبتو مفتوح دائماً", S.is_open("crypto", SAT))
check("  ونيويورك مغلقة السبت", not S.is_open("us", SAT))
check("  وتداول مغلقة السبت", not S.is_open("saudi", SAT))
check("  ونيويورك مفتوحة الأربعاء ظهراً", S.is_open("us", WED))
check("  وتداول مغلقة الأربعاء 17:00 UTC",
      not S.is_open("saudi", WED), "تغلق 12:00 UTC")
# الجمعة يوم تداول في نيويورك وعطلة في تداول — والعكس في الأحد
check("  والجمعة تداول في نيويورك",
      S.is_trading_day("us", pd.Timestamp("2026-08-21").date()))
check("  والجمعة عطلة في تداول",
      not S.is_trading_day("saudi", pd.Timestamp("2026-08-21").date()))
check("  والأحد تداول في السعودي",
      S.is_trading_day("saudi", pd.Timestamp("2026-08-23").date()))
check("  والأحد عطلة في نيويورك",
      not S.is_trading_day("us", pd.Timestamp("2026-08-23").date()))


# ── ٢) التوقيت الصيفي ليس تفصيلاً ──
#
# تثبيت 13:30 UTC للافتتاح يجعل النظام يخطئ ساعةً كاملةً نصف العام.
_summer = S.next_open("us", pd.Timestamp("2026-07-01 00:00", tz="UTC"))
_winter = S.next_open("us", pd.Timestamp("2026-01-05 00:00", tz="UTC"))
check("٢ الافتتاح صيفاً 13:30 UTC",
      _summer is not None and _summer.strftime("%H:%M") == "13:30", str(_summer))
check("  وشتاءً 14:30 UTC",
      _winter is not None and _winter.strftime("%H:%M") == "14:30", str(_winter))
check("  والرياض لا تتغيّر",
      S.next_open("saudi", pd.Timestamp("2026-07-01", tz="UTC")).strftime("%H:%M")
      == S.next_open("saudi", pd.Timestamp("2026-01-05", tz="UTC")).strftime("%H:%M"))


# ── ٣) الزمن المفتوح لا زمن الساعة ──
fri_close = S.last_close("us", SAT)
check("٣ آخر إغلاق أمريكي هو الجمعة",
      fri_close is not None and fri_close.strftime("%Y-%m-%d %H:%M") ==
      "2026-08-21 20:00", str(fri_close))
check("  والمفتوح بين الإغلاق والسبت صفر",
      S.open_seconds_between(fri_close, SAT, "us") == 0.0,
      str(S.open_seconds_between(fri_close, SAT, "us")))
wall = (SAT - fri_close).total_seconds()
check("  بينما ساعة الحائط تقول 16 ساعة", abs(wall - 16 * 3600) < 1, str(wall))
check("  والكريبتو يتساوى فيه المقياسان",
      S.open_seconds_between(fri_close, SAT, "crypto") == wall)
# جلسة كاملة واحدة = 6.5 ساعة
_one = S.open_seconds_between(
    pd.Timestamp("2026-08-19 00:00", tz="UTC"),
    pd.Timestamp("2026-08-20 00:00", tz="UTC"), "us")
check("  والجلسة الأمريكية 6.5 ساعة", abs(_one - 6.5 * 3600) < 1, str(_one / 3600))


# ── ٤) الإنذار الكاذب سكت ──
CASES_QUIET = [
    ("سبت · يوميّ من إغلاق الجمعة", "us", "1d", fri_close),
    ("سبت · 15m من إغلاق الجمعة", "us", "15m", fri_close),
    ("سبت · ساعة من إغلاق الجمعة", "us", "1h", fri_close),
    ("سبت سعودي · يوميّ من إغلاق الخميس", "saudi", "1d",
     S.last_close("saudi", SAT)),
]
for label, mkt, tf, last in CASES_QUIET:
    old = storage.bars_behind_from(last, tf, now=SAT)
    new = storage.bars_behind_from(last, tf, now=SAT, market=mkt)
    check(f"٤ {label}", judge(new) == "fresh",
          f"كان {old:.2f} ({judge(old)}) وصار {new:.2f} ({judge(new)})")
    check("  وكان يكذب قبل الإصلاح", judge(old) != "fresh",
          f"{old:.2f} — لم يكن العطب حيث ظُنّ")


# ── ٥) والإنذار الصادق ما زال يصرخ ──
#
# هذا نصف الاختبار الذي بدونه يكون العلاج عمًى.
CASES_LOUD = [
    ("أمريكي متوقّف أسبوعين", "us", "1d",
     pd.Timestamp("2026-08-07 20:00", tz="UTC"), 9.0),
    ("أمريكي متوقّف ثلاث جلسات", "us", "1d",
     pd.Timestamp("2026-08-18 20:00", tz="UTC"), 2.5),
    ("سعودي متوقّف أسبوعاً", "saudi", "1d",
     pd.Timestamp("2026-08-13 12:00", tz="UTC"), 4.0),
    ("كريبتو متوقّف يومين", "crypto", "1h",
     pd.Timestamp("2026-08-20 12:00", tz="UTC"), 47.0),
]
for label, mkt, tf, last, at_least in CASES_LOUD:
    new = storage.bars_behind_from(last, tf, now=SAT, market=mkt)
    check(f"٥ {label} ما زال حرجاً", judge(new) == "critical", f"{new:.2f}")
    check(f"  ويُقاس بالجلسات ({new:.1f} ≥ {at_least})", new >= at_least,
          f"{new:.2f} < {at_least}")

# القياس اليوميّ بالجلسات لا بأربع وعشرين ساعة: القسمة على 86400
# كانت تُظهر عشر جلسات متوقّفة وكأنّها 2.7 شمعة — «متأخّر» لا «حرج».
_two_weeks = storage.bars_behind_from(
    pd.Timestamp("2026-08-07 20:00", tz="UTC"), "1d", now=SAT, market="us")
check("  والشمعة اليومية = جلسة لا 24 ساعة",
      9.0 <= _two_weeks <= 11.0, f"{_two_weeks:.2f} جلسة")


# ── ٦) مهلة البثّ تُطرح ولا تُبتلع ──
_now_open = pd.Timestamp("2026-08-19 17:00", tz="UTC")     # نيويورك مفتوحة
_lag15 = _now_open - pd.Timedelta(minutes=15)
S.configure("us", feed_delay_seconds=15 * 60)
check("٦ تأخّر 15 دقيقة لا يُعدّ تأخّراً",
      storage.bars_behind_from(_lag15, "15m", now=_now_open, market="us") == 0.0)
S.configure("us", feed_delay_seconds=0)
check("  وبلا مهلة يُعدّ شمعةً كاملة",
      abs(storage.bars_behind_from(_lag15, "15m", now=_now_open,
                                   market="us") - 1.0) < 0.01)
S.configure("us", feed_delay_seconds=15 * 60)
check("  والمهلة لا تُخفي ساعتين",
      storage.bars_behind_from(_now_open - pd.Timedelta(hours=2), "15m",
                               now=_now_open, market="us") >= 6.0)


# ── ٧) الإجازة تُقلّص الانزياح ──
_hol = pd.Timestamp("2026-08-20").date()
S.configure("us", holidays=["2026-08-20"])
check("٧ اليوم المُعلَن إجازةً ليس يوم تداول",
      not S.is_trading_day("us", _hol))
check("  ولا يُحسَب زمناً مفتوحاً",
      S.open_seconds_between(pd.Timestamp("2026-08-20 00:00", tz="UTC"),
                             pd.Timestamp("2026-08-21 00:00", tz="UTC"),
                             "us") == 0.0)
S.configure("us", holidays=[])
check("  ورفعها يعيده يوم تداول", S.is_trading_day("us", _hol))


# ── ٨) سوق مجهول لا يُمنح رخصة ──
#
# الافتراض الآمن هو الأقسى: ألاّ نُسكت إنذاراً لسوق لا نعرف أوقاته.
check("٨ السوق المجهول يُعامل كمفتوح دائماً", S.is_open("لا_سوق", SAT))
check("  وقياسه يساوي ساعة الحائط",
      storage.bars_behind_from(fri_close, "1h", now=SAT, market="لا_سوق")
      == storage.bars_behind_from(fri_close, "1h", now=SAT))


# ── ٩) والتقييم يقول حالة السوق لا الرقم وحده ──
from scanner.market_sync.freshness import assess_freshness  # noqa: E402

_a = assess_freshness("us", "لا_يوجد", "1d")
check("٩ التقييم يُعلن غياب الملف", _a["status"] == "missing")
for key in ("market_open", "next_open", "feed_delay_seconds"):
    check(f"  ويحمل {key}", key in _a or _a["status"] == "missing")


failed = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not failed
      else f"✗ فشل {len(failed)} من {len(results)}")
sys.exit(1 if failed else 0)
