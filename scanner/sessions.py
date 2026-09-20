# -*- coding: utf-8 -*-
"""أوقات جلسات الأسواق — ولماذا «متأخرة جداً» كانت كذبة.

═══ العطب ═══

يوم السبت أعلن النظام ``فشل: بيانات السوق متأخرة جداً`` وحجب المسح.
والبيانات لم تكن متأخرة: السوق **مغلق**. آخر شمعة أمريكية كانت من
إغلاق الخميس، وبين الإغلاق والسبت أربعون ساعة لا تُتداول فيها ورقة
واحدة.

وأصل الخطأ أن النضارة كانت تُقاس بساعة الحائط::

    behind = (now - last_candle) / حجم_الشمعة

وهذه حسبة صحيحة تماماً **للكريبتو** — سوق لا يغلق. وطُبّقت على
الأسهم كما هي. فكل عطلة نهاية أسبوع تُنتج إنذاراً، وكل ليلة تُنتج
إنذاراً أصغر، والنظام يتعلّم صاحبُه أن يتجاهل إنذاراته.

وهذا أسوأ من الصمت: إنذارٌ يكذب كل سبت يُفقد الثقة بالإنذار الصادق
يوم يتعطّل الجلب فعلاً.

═══ المقياس الصحيح ═══

التأخّر يُقاس **بزمن السوق المفتوح** لا بزمن الساعة. فإن أُغلق
السوق يوم الخميس ولم يُفتح بعد، فالزمن المفتوح المنقضي = صفر،
والبيانات حديثة مهما طال الأسبوع.

وتُطرح فوق ذلك **مهلة البثّ**: الاشتراك المجاني يتأخّر خمس عشرة
دقيقة، فأحدث ما يمكن الحصول عليه أصلاً عمره ربع ساعة. عدّها تأخّراً
يعني معاقبة النظام على حدٍّ في الاشتراك لا على خلل فيه.

═══ حدود هذا الملف ═══

لا يعرف الإجازات الرسمية. أُضيفت ``holidays`` في ملف السوق لمن أراد
دقّةً أعلى، وأثر الإجازة المجهولة محصور: جلسةٌ واحدة تُحسَب مفتوحة
وهي مغلقة — أي انزياحٌ بمقدار يوم، لا بمقدار أسبوع كما كان.

ولا يعرف الجلسات الممتدّة (pre/after market): المقصود جلسة التداول
النظامية التي تُبنى منها الشموع.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

import pandas as pd

# يوم الأسبوع بترقيم Python: الاثنين 0 … الأحد 6
MON, TUE, WED, THU, FRI, SAT, SUN = range(7)


@dataclass(frozen=True)
class Session:
    """جلسة سوق واحدة: أيّامها ووقتها بالتوقيت المحلّي للسوق."""

    tz: str
    days: frozenset[int]
    open_at: time
    close_at: time
    feed_delay_seconds: int = 0
    holidays: frozenset[date] = field(default_factory=frozenset)

    @property
    def always_open(self) -> bool:
        return False


@dataclass(frozen=True)
class AlwaysOpen:
    """سوق لا يغلق — الكريبتو. زمن السوق = زمن الساعة."""

    tz: str = "UTC"
    feed_delay_seconds: int = 0

    @property
    def always_open(self) -> bool:
        return True


# ═══ الجلسات ═══
#
# الأوقات بالتوقيت المحلّي للسوق لا بـ UTC عمداً: نيويورك تُغيّر
# فارقها مع UTC مرّتين في السنة، وتثبيت 13:30 UTC يجعل النظام يخطئ
# ساعةً كاملةً نصفَ العام. والتحويل يتكفّل به pandas.
#
# مهلة البثّ خمس عشرة دقيقة للسوقين: هي مهلة الاشتراكات المجانية
# المعتادة (Alpaca IEX وسهمك المجاني). من رقّى اشتراكه فليصفّرها في
# ملف السوق.
_SESSIONS: dict[str, Session | AlwaysOpen] = {
    "crypto": AlwaysOpen(),
    "us": Session(
        tz="America/New_York",
        days=frozenset({MON, TUE, WED, THU, FRI}),
        open_at=time(9, 30),
        close_at=time(16, 0),
        feed_delay_seconds=15 * 60,
    ),
    "saudi": Session(
        tz="Asia/Riyadh",
        days=frozenset({SUN, MON, TUE, WED, THU}),
        open_at=time(10, 0),
        close_at=time(15, 0),
        feed_delay_seconds=15 * 60,
    ),

    # ═══ الذهب: رموز بينانس المغطّاة ═══
    #
    # ‏PAXG و‏XAUT يُتداولان على بينانس ٢٤/٧ كأيّ زوج — لا جلسة
    # ولا عطلة. وهي **ليست** جلسة سوق الذهب الفوريّ (٢٤/٥): هذان
    # رمزان رقميّان يتبعان سعره، ودفترهما مفتوحٌ يوم السبت.
    "gold": AlwaysOpen(),

    # ═══ النفط: جلسةٌ ممتدّة لا سوقٌ مفتوح ═══
    #
    # والمجهول يُعامَل «مفتوحاً دائماً» — وهو هنا خطأ مكلف: عطلة
    # نهاية الأسبوع تُحسب تأخّراً، فيُعلَن النفط «متأخّراً تأخّراً
    # حرجاً» كل اثنين وتحجبه البوّابة. وهو العطب نفسه الذي وقع
    # على السوق السعودي كل سبت، وعولج بقياس التأخّر بزمن السوق
    # المفتوح لا بساعة الحائط.
    #
    # ونايمكس تفتح الأحد ٦ مساءً وتغلق الجمعة ٥ عصراً بتوقيت
    # نيويورك، وفيها توقّفٌ يوميّ ساعة. والتبسيط هنا مقصود: يومٌ
    # من ٦ مساءً إلى ٥ عصراً لا يُمثَّل بنافذةٍ واحدة في هذا
    # النموذج، فأخذنا القلب النشط (٩ صباحاً – ٥ عصراً) — وهو ما
    # يُقاس عليه التأخّر. وأثرُ التبسيط أنّ ساعات الليل الهادئة
    # لا تُعدّ تأخّراً، وهو الاتّجاه الآمن.
    "oil": Session(
        tz="America/New_York",
        days=frozenset({MON, TUE, WED, THU, FRI}),
        open_at=time(9, 0),
        close_at=time(17, 0),
        feed_delay_seconds=15 * 60,
    ),
}

# سوق مجهول: يُعامل كمفتوح دائماً. الافتراض الآمن هو الأقسى —
# ألاّ نمنح رخصة نضارة لسوق لا نعرف أوقاته.
_DEFAULT: AlwaysOpen = AlwaysOpen()


def get_session(market: str) -> Session | AlwaysOpen:
    return _SESSIONS.get((market or "").strip().lower(), _DEFAULT)


def configure(market: str, *, feed_delay_seconds: int | None = None,
              holidays: list[str] | None = None) -> Session | AlwaysOpen:
    """تعديل جلسة سوق من الإعدادات — للإجازات ومهلة البثّ."""
    key = (market or "").strip().lower()
    cur = _SESSIONS.get(key)
    if cur is None:
        return _DEFAULT
    if isinstance(cur, AlwaysOpen):
        if feed_delay_seconds is not None:
            cur = AlwaysOpen(tz=cur.tz, feed_delay_seconds=int(feed_delay_seconds))
            _SESSIONS[key] = cur
        return cur

    days = set()
    for h in holidays or []:
        try:
            days.add(pd.Timestamp(h).date())
        except (ValueError, TypeError):
            continue
    new = Session(
        tz=cur.tz,
        days=cur.days,
        open_at=cur.open_at,
        close_at=cur.close_at,
        feed_delay_seconds=(cur.feed_delay_seconds if feed_delay_seconds is None
                            else int(feed_delay_seconds)),
        holidays=frozenset(days) if holidays is not None else cur.holidays,
    )
    _SESSIONS[key] = new
    return new


def _local(ts, tz: str) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    t = t.tz_localize("UTC") if t.tzinfo is None else t
    try:
        return t.tz_convert(tz)
    except Exception:  # noqa: BLE001
        # قاعدة المناطق الزمنية غائبة (يقع على ويندوز بلا حزمة
        # tzdata). العودة إلى UTC تُبقي المنطق عاملاً بخطأ ساعة
        # موسمية — وهو أهون من انهيار كل تقييم نضارة.
        return t


def is_trading_day(market: str, day: date) -> bool:
    s = get_session(market)
    if s.always_open:
        return True
    return day.weekday() in s.days and day not in s.holidays


def is_open(market: str, at=None) -> bool:
    """هل السوق مفتوح في هذه اللحظة؟"""
    s = get_session(market)
    if s.always_open:
        return True
    t = _local(at if at is not None else pd.Timestamp.now("UTC"), s.tz)
    if not is_trading_day(market, t.date()):
        return False
    return s.open_at <= t.time() < s.close_at


def open_seconds_between(start, end, market: str) -> float:
    """الثواني التي كان السوق فيها **مفتوحاً** بين لحظتين.

    هذه هي الدالّة التي كان غيابها يجعل كل عطلة إنذاراً. للكريبتو
    تعيد الفارق كما هو، فلا يتغيّر شيء في السوق الذي لا يغلق.
    """
    s = get_session(market)
    a = pd.Timestamp(start)
    b = pd.Timestamp(end)
    a = a.tz_localize("UTC") if a.tzinfo is None else a
    b = b.tz_localize("UTC") if b.tzinfo is None else b
    if b <= a:
        return 0.0
    if s.always_open:
        return float((b - a).total_seconds())

    la, lb = _local(a, s.tz), _local(b, s.tz)

    # حدّ للمرور اليوميّ: ملفٌّ مهجور منذ سنوات لا يستحقّ آلاف
    # الدورات، والجواب عندها «متأخّر جداً» أيّاً كان الرقم.
    span_days = (lb.date() - la.date()).days
    if span_days > 400:
        return float((b - a).total_seconds())

    total = 0.0
    day = la.date()
    last_day = lb.date()
    while day <= last_day:
        if is_trading_day(market, day):
            try:
                o = pd.Timestamp(datetime.combine(day, s.open_at),
                                 tz=s.tz)
                c = pd.Timestamp(datetime.combine(day, s.close_at),
                                 tz=s.tz)
            except Exception:  # noqa: BLE001
                day += timedelta(days=1)
                continue
            lo = max(o, la)
            hi = min(c, lb)
            if hi > lo:
                total += (hi - lo).total_seconds()
        day += timedelta(days=1)
    return float(total)


def last_close(market: str, at=None) -> pd.Timestamp | None:
    """آخر لحظة إغلاق سابقة — مرجع النضارة حين يكون السوق مغلقاً."""
    s = get_session(market)
    if s.always_open:
        return None
    t = _local(at if at is not None else pd.Timestamp.now("UTC"), s.tz)
    day = t.date()
    for _ in range(30):
        if is_trading_day(market, day):
            c = pd.Timestamp(datetime.combine(day, s.close_at), tz=s.tz)
            if c <= t:
                return c.tz_convert("UTC")
        day -= timedelta(days=1)
    return None


def next_open(market: str, at=None) -> pd.Timestamp | None:
    """أوّل لحظة فتح قادمة — كي تقول الواجهة متى تعود الحياة."""
    s = get_session(market)
    if s.always_open:
        return None
    t = _local(at if at is not None else pd.Timestamp.now("UTC"), s.tz)
    day = t.date()
    for _ in range(30):
        if is_trading_day(market, day):
            o = pd.Timestamp(datetime.combine(day, s.open_at), tz=s.tz)
            if o > t:
                return o.tz_convert("UTC")
        day += timedelta(days=1)
    return None


def feed_delay_seconds(market: str) -> int:
    return int(getattr(get_session(market), "feed_delay_seconds", 0) or 0)


def session_seconds(market: str) -> float | None:
    """طول الجلسة الواحدة بالثواني — ``None`` لسوق لا يغلق."""
    s = get_session(market)
    if s.always_open:
        return None
    o = s.open_at.hour * 3600 + s.open_at.minute * 60 + s.open_at.second
    c = s.close_at.hour * 3600 + s.close_at.minute * 60 + s.close_at.second
    return float(max(0, c - o))


def bars_elapsed(last, now, timeframe_sec: float, market: str) -> float:
    """كم شمعة انقضت — بمقياس السوق لا بمقياس الساعة.

    ═══ الفخّ الثاني ═══

    لا يكفي قياس المنقضي بزمن السوق المفتوح ثمّ قسمته على حجم
    الشمعة. الشمعة **اليومية** في سوق الأسهم لا تساوي أربعاً
    وعشرين ساعة بل **جلسةً واحدة** — ستّ ساعات ونصفاً في نيويورك،
    وخمساً في تداول.

    فلو قُسم الزمن المفتوح على 86400 لظهر جلبٌ متعطّل عشرة أيام
    وكأنّه متأخّر ``2.7`` شمعة فقط — أي «متأخّر» لا «حرج»، فيمرّ.
    التقصير في الإنذار هنا أخطر من الإفراط فيه.

    فالقاعدة: ما دون الجلسة يُقاس بحجمه، وما فوقها يُقاس بعدد
    الجلسات التي يحويها.
    """
    if timeframe_sec <= 0:
        return 0.0
    elapsed = open_seconds_between(last, now, market)
    sess = session_seconds(market)
    if sess is None or sess <= 0:
        return elapsed / timeframe_sec        # سوق لا يغلق

    if timeframe_sec < sess:
        return elapsed / timeframe_sec        # داخل الجلسة

    # يوميّ فأعلى: الشمعة تساوي عدداً صحيحاً من الجلسات.
    days_per_bar = max(1.0, timeframe_sec / 86400.0)
    trading_days_per_week = max(1, len(getattr(get_session(market), "days", ())))
    sessions_per_bar = (1.0 if days_per_bar <= 1.0
                        else days_per_bar * trading_days_per_week / 7.0)
    return elapsed / (sess * sessions_per_bar)


__all__ = [
    "Session", "AlwaysOpen", "get_session", "configure", "is_open",
    "is_trading_day", "open_seconds_between", "last_close", "next_open",
    "feed_delay_seconds",
]
