# -*- coding: utf-8 -*-
"""محرّك المحفظة الورقية — تحجيمٌ بالمخاطرة، ورسومٌ حقيقية.

═══ ما يجعل المحاكاة صادقة ═══

ثلاثة أشياء تُسقط أغلب المحاكيات:

**الرسوم.** بينانس تأخذ ‎0.1٪‎ عند الدخول ومثلها عند الخروج —
‎0.2٪‎ ذهاباً وإياباً. وصفقةٌ ربحت ‎0.15٪‎ **خاسرة**. فالرسوم
تُحسب على قيمة المركز في الطرفين وتُخصم من الربح، وتُحفظ منفصلةً
كي تُرى.

**الانزلاق.** الأمر لا يُنفَّذ عند السعر المطلوب دائماً. والافتراض
هنا انزلاقٌ ضدّك في الطرفين — وافتراض التنفيذ المثالي يجعل
المحاكاة تربح ما لا يُربَح.

**الوقف يُفحص قبل الهدف.** الشمعة لا تخبرنا أيّهما لُمس أوّلاً،
فيُفترَض الأسوأ. والافتراض المتفائل يقلب خاسرةً إلى رابحة على
الورق وحده.

═══ والهدف ليس وعداً ═══

``target_total_pct`` حدٌّ **يوقف الفتح** عند بلوغه، لا ضمانٌ
ببلوغه. وقد تنتهي المحفظة تحت رأس مالها — وهذا ما تُبنى المحاكاة
لتُظهره قبل المال الحقيقي.
"""
from __future__ import annotations

import logging

log = logging.getLogger("dashboard.paper")

# ═══ الافتراضات — كلّها قابلة للتغيير من الشاشة ═══
DEFAULTS = {
    # ── إدارة المخاطر ──
    "risk_per_trade_pct": 1.0,      # من الرصيد لكل صفقة
    "max_open_positions": 5,
    "max_position_pct": 25.0,       # سقف قيمة المركز من الرصيد
    "max_daily_loss_pct": 3.0,      # يوقف الفتح بقيّة اليوم
    "target_total_pct": 3.0,        # يوقف الفتح عند بلوغه
    "min_rr": 1.5,
    # ── تكاليف بينانس ──
    "fee_pct": 0.1,                 # سبوت: 0.1٪ لكل طرف
    "slippage_pct": 0.05,           # افتراضٌ متحفّظ في الطرفين
    # ── مصدر الإشارات ──
    "source": "pes",                # pes | scanner | golden
    "markets": ["crypto"],
    "min_score": 75.0,              # عتبة PRE_BREAKOUT
    "allowed_states": ["PRE_BREAKOUT", "BREAKOUT_RETEST", "ENTRY_READY"],
    # ── الدخول الآمن ──
    "require_btc_bullish": False,   # لا يفتح في سوقٍ هابط
    "one_trade_per_symbol": True,
}


def settings_for(account) -> dict:
    """الافتراضات فوقها ما غيّره المستخدم."""
    out = dict(DEFAULTS)
    out.update(account.settings or {})
    return out


# ═══════════════════════ الحسابات ═══════════════════════

def position_size(balance: float, entry: float, stop: float,
                  cfg: dict) -> dict:
    """كمّية المركز من المخاطرة — لا من مبلغٍ ثابت.

    ═══ لماذا من المخاطرة ═══

    «ادخل بـ‎١٠٠٠‎ دولار» يجعل الخسارة تتغيّر بتغيّر بُعد الوقف:
    وقفٌ على بعد ‎1٪‎ يخسر ‎١٠‎ ووقفٌ على بعد ‎10٪‎ يخسر ‎١٠٠‎.
    والتحجيم بالمخاطرة يثبّت الخسارة ويغيّر الكمّية — وهو أصل
    إدارة المخاطر.

        الكمّية = (الرصيد × نسبة المخاطرة) ÷ (الدخول − الوقف)
    """
    risk_pct = float(cfg.get("risk_per_trade_pct", 1.0)) / 100.0
    risk_amount = balance * risk_pct
    per_unit = abs(float(entry) - float(stop))
    if per_unit <= 0 or entry <= 0:
        return {"ok": False, "reason": "الوقف يساوي الدخول"}

    qty = risk_amount / per_unit
    notional = qty * float(entry)

    # ═══ سقف حجم المركز ═══
    #
    # وقفٌ قريب جداً يعطي كمّيةً هائلة: مخاطرة ‎1٪‎ ووقفٌ على بعد
    # ‎0.1٪‎ تعني مركزاً بعشرة أضعاف الرصيد. والسقف يمنع ذلك.
    cap = balance * float(cfg.get("max_position_pct", 25.0)) / 100.0
    capped = False
    if notional > cap:
        capped = True
        notional = cap
        qty = notional / float(entry)
        risk_amount = qty * per_unit

    return {"ok": True, "quantity": qty, "notional": notional,
            "risk_amount": risk_amount, "capped": capped,
            "risk_pct_actual": round(risk_amount / balance * 100, 3)
            if balance else 0.0}


def fees_on(notional: float, cfg: dict) -> float:
    return notional * float(cfg.get("fee_pct", 0.1)) / 100.0


def _slip(price: float, cfg: dict, *, buying: bool) -> float:
    """الانزلاق ضدّك دائماً — الشراء أغلى والبيع أرخص."""
    s = float(cfg.get("slippage_pct", 0.05)) / 100.0
    return price * (1 + s) if buying else price * (1 - s)


# ═══════════════════════ الحرّاس ═══════════════════════

def can_open(account, cfg: dict, *, symbol: str = "") -> dict:
    """هل يُسمح بفتح صفقة الآن؟ — وإن لا، فلماذا."""
    from django.utils import timezone

    from .models import PaperTrade

    open_qs = PaperTrade.objects.filter(account=account, status="open")
    n_open = open_qs.count()
    if n_open >= int(cfg.get("max_open_positions", 5)):
        return {"ok": False, "reason": f"المراكز المفتوحة {n_open} بلغت الحدّ"}

    if cfg.get("one_trade_per_symbol", True) and symbol:
        if open_qs.filter(symbol=symbol).exists():
            return {"ok": False, "reason": f"{symbol} مفتوحة بالفعل"}

    # ═══ الهدف يوقف الفتح ═══
    #
    # بلغتَ ما أردت — والاستمرار بعده مقامرةٌ بما رَبِحت.
    equity = account.balance
    gain_pct = (equity - account.initial_balance) / account.initial_balance * 100
    target = float(cfg.get("target_total_pct", 3.0))
    if target and gain_pct >= target:
        return {"ok": False,
                "reason": f"بلغت الهدف {gain_pct:+.2f}٪ — توقّف الفتح"}

    # ═══ حدّ الخسارة اليومية ═══
    #
    # يومٌ سيّئ يُغلق. والاستمرار فيه مطاردةٌ للخسارة، وهي أسرع
    # طريقٍ لمضاعفتها.
    day_cap = float(cfg.get("max_daily_loss_pct", 3.0))
    if day_cap:
        today = timezone.now().date()
        closed_today = PaperTrade.objects.filter(
            account=account, status__in=("won", "lost"),
            closed_at__date=today)
        day_pnl = sum(float(t.pnl or 0) for t in closed_today)
        if day_pnl < 0 and abs(day_pnl) >= account.initial_balance * day_cap / 100:
            return {"ok": False,
                    "reason": f"خسارة اليوم {day_pnl:.2f} بلغت الحدّ"}

    return {"ok": True, "reason": ""}


# ═══════════════════════ الفتح والإغلاق ═══════════════════════

def open_trade(account, signal: dict) -> dict:
    """يفتح صفقة من إشارة — أو يقول لماذا لم يفتح."""
    from django.utils import timezone

    from . import blocklist
    from .models import PaperTrade

    cfg = settings_for(account)
    sym = str(signal.get("symbol") or "")
    market = str(signal.get("market") or "crypto")

    if blocklist.is_blocked(market, sym):
        return {"ok": False, "reason": f"{sym} محظور"}

    gate = can_open(account, cfg, symbol=sym)
    if not gate["ok"]:
        return gate

    try:
        entry = float(signal["entry"])
        stop = float(signal["stop"])
    except (KeyError, TypeError, ValueError):
        return {"ok": False, "reason": "لا مستويات دخول ووقف"}
    target = signal.get("target")
    target = float(target) if target not in (None, "") else None

    if stop >= entry:
        return {"ok": False, "reason": "الوقف فوق الدخول — ليست شراءً"}
    if target:
        rr = (target - entry) / (entry - stop)
        if rr < float(cfg.get("min_rr", 1.5)):
            return {"ok": False,
                    "reason": f"عائد/مخاطرة {rr:.2f} دون الحدّ"}

    fill = _slip(entry, cfg, buying=True)
    size = position_size(account.balance, fill, stop, cfg)
    if not size["ok"]:
        return size

    fee = fees_on(size["notional"], cfg)
    # النقد يُخصم منه المركز والرسوم — محفظةٌ لا تنقص ليست محفظة
    cost = size["notional"] + fee
    if cost > account.balance:
        return {"ok": False, "reason": "النقد لا يكفي"}

    t = PaperTrade.objects.create(
        account=account, symbol=sym, market=market,
        timeframe=str(signal.get("timeframe") or ""),
        side="buy", source=str(signal.get("source") or cfg.get("source", "")),
        entry=fill, stop=stop, target=target,
        quantity=size["quantity"], notional=size["notional"],
        risk_amount=size["risk_amount"], fee_in=fee,
        status="open", opened_at=timezone.now(),
        last_price=fill,
        note=("حُدّ حجمه بالسقف" if size.get("capped") else ""),
    )
    account.balance -= cost
    account.save(update_fields=["balance", "updated_at"])
    return {"ok": True, "trade_id": t.id, "quantity": size["quantity"],
            "notional": round(size["notional"], 2), "fee": round(fee, 4),
            "risk": round(size["risk_amount"], 2)}


def close_trade(account, trade, price: float, reason: str) -> dict:
    """يغلق صفقة ويعيد النقد بعد الرسوم."""
    from django.utils import timezone

    cfg = settings_for(account)
    exit_fill = _slip(float(price), cfg, buying=False)
    proceeds = trade.quantity * exit_fill
    fee_out = fees_on(proceeds, cfg)

    # ═══ الربح بعد الرسوم وحده ═══
    #
    # صفقةٌ ربحت ‎0.15٪‎ ورسومها ‎0.2٪‎ خاسرة. وعرضُ الربح قبل
    # الرسوم يُظهرها رابحة — وهو أكثر ما يُضلّل في المحاكيات.
    gross = proceeds - trade.notional
    net = gross - trade.fee_in - fee_out

    trade.exit_price = exit_fill
    trade.exit_reason = reason
    trade.fee_out = fee_out
    trade.pnl = net
    trade.r_multiple = (net / trade.risk_amount) if trade.risk_amount else None
    trade.status = "won" if net > 0 else "lost"
    trade.closed_at = timezone.now()
    trade.last_price = float(price)
    trade.save()

    account.balance += proceeds - fee_out
    account.save(update_fields=["balance", "updated_at"])
    return {"ok": True, "pnl": round(net, 4), "status": trade.status,
            "r": trade.r_multiple}


def mark_and_settle(account, prices: dict) -> dict:
    """يُقيّم المفتوحة بالأسعار الحالية ويغلق من بلغ وقفه أو هدفه.

    ═══ الوقف قبل الهدف ═══

    السعر الوارد نقطةٌ واحدة، والشمعة قد تكون لمست الاثنين. فبلا
    علمٍ بالترتيب يُفترَض الأسوأ — وهو ما يفعله المحاكي في
    ``scanner/exits/simulator.py`` أيضاً.
    """
    from .models import PaperTrade

    closed, marked = [], 0
    for t in PaperTrade.objects.filter(account=account, status="open"):
        px = prices.get(t.symbol)
        if px is None:
            continue
        px = float(px)
        t.last_price = px
        marked += 1
        if px <= t.stop:
            closed.append({"symbol": t.symbol,
                           **close_trade(account, t, t.stop, "وقف")})
        elif t.target and px >= t.target:
            closed.append({"symbol": t.symbol,
                           **close_trade(account, t, t.target, "هدف")})
        else:
            t.save(update_fields=["last_price"])
    return {"marked": marked, "closed": closed}


# ═══════════════════════ الملخّص ═══════════════════════

def summary(account) -> dict:
    """حالة المحفظة — والقيمة السوقية لا النقد وحده."""
    from .models import PaperTrade

    cfg = settings_for(account)
    qs = PaperTrade.objects.filter(account=account)
    open_t = list(qs.filter(status="open"))
    won = qs.filter(status="won")
    lost = qs.filter(status="lost")

    # قيمة المراكز المفتوحة بسعرها الحالي
    open_value = sum(float(t.quantity) * float(t.last_price or t.entry)
                     for t in open_t)
    equity = account.balance + open_value
    n_won, n_lost = won.count(), lost.count()
    settled = n_won + n_lost

    realized = sum(float(t.pnl or 0) for t in qs.filter(
        status__in=("won", "lost")))
    fees = sum(float(t.fee_in or 0) + float(t.fee_out or 0) for t in qs)
    gains = sum(float(t.pnl) for t in won)
    losses = -sum(float(t.pnl) for t in lost)

    return {
        "name": account.name,
        "initial_balance": account.initial_balance,
        "cash": round(account.balance, 2),
        "open_value": round(open_value, 2),
        "equity": round(equity, 2),
        "pnl": round(equity - account.initial_balance, 2),
        "pnl_pct": round((equity - account.initial_balance)
                         / account.initial_balance * 100, 2),
        "realized": round(realized, 2),
        # ═══ الرسوم تُعرض وحدها ═══
        #
        # مجموعها على مئة صفقة يبتلع أرباحاً كثيرة، ولا يُرى إن
        # ذاب في صافي الربح.
        "fees_total": round(fees, 2),
        "target_pct": float(cfg.get("target_total_pct", 3.0)),
        "target_reached": (equity - account.initial_balance)
        / account.initial_balance * 100 >= float(
            cfg.get("target_total_pct", 3.0)),
        "open_count": len(open_t),
        "won": n_won, "lost": n_lost, "settled": settled,
        "win_rate": round(100 * n_won / settled, 1) if settled else None,
        "profit_factor": round(gains / losses, 2) if losses else None,
        "avg_r": (round(sum(float(t.r_multiple or 0) for t in
                            qs.filter(status__in=("won", "lost")))
                        / settled, 2) if settled else None),
        "can_open": can_open(account, cfg),
    }


def get_or_create_account():
    """المحفظة النشِطة — تُنشأ عند أوّل فتح للصفحة."""
    from .models import PaperAccount

    acc = PaperAccount.objects.filter(active=True).order_by("id").first()
    if acc is None:
        acc = PaperAccount.objects.create()
    return acc


__all__ = ["DEFAULTS", "settings_for", "position_size", "fees_on",
           "can_open", "open_trade", "close_trade", "mark_and_settle",
           "summary", "get_or_create_account"]
