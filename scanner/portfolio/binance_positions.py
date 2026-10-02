# -*- coding: utf-8 -*-
"""مراكز السوق الفوري — مُشتقّةً، لأنّ Binance لا يعطيها.

═══ المسألة ═══

العقود الدائمة فيها «مركز» صريح: كمّية ومتوسّط دخول وربحٌ غير
محقّق. والسوق الفوريّ **لا**: فيه رصيدٌ من أصل، وتاريخُ صفقاتٍ
منفصل. فمن اشترى بتكوين ثلاث مرّات يرى رصيداً واحداً ولا يرى
«متوسّط دخوله» في أيّ مكان.

فيُعاد بناؤه: تُقرأ صفقات الرمز بالترتيب، ويُمسَك متوسّطٌ مرجّح
يُخفَّض عند البيع ولا يتغيّر بالبيع نفسه.

═══ والفجوة التي يجب أن تُقال ═══

الرصيد **ليس** بالضرورة ناتج الصفقات. إيداعٌ من محفظة خارجية، أو
مكافأة، أو تحويلٌ من حسابٍ آخر — كلّها تزيد الرصيد بلا صفقةٍ
واحدة. فتكلفة ذلك الجزء **مجهولة**.

وحسابُ ربحٍ غير محقّق على تكلفةٍ مجهولة يُنتج رقماً واثقاً كاذباً.
فتُقاس الفجوة صراحةً: كمّية الصفقات مقابل الرصيد. وإن اختلفا
يُعلَن ``basis_partial`` ولا يُدَّعى رقمٌ دقيق.

═══ والبيع بمتوسّط الشراء لا بمتوسّطٍ جديد ═══

عند البيع تنقص الكمّية ويُخفَّض إجمالي التكلفة **بنفس النسبة** —
فيبقى متوسّط التكلفة كما هو. والخطأ الشائع أن يُعاد حساب المتوسّط
بسعر البيع، فيصير «متوسّط الدخول» متأثّراً بالخروج وهو ليس دخولاً.

═══ والعمولة تُحتسب ═══

عمولةٌ بعملة الاقتباس تزيد تكلفة الشراء. وعمولةٌ بالأصل نفسه
تُنقص الكمّية المستلَمة. وإهمالُها يجعل كل مركزٍ يبدو أربح ممّا
هو بنحو ٠٫١٪ لكل صفقة — وهو يتراكم.
"""
from __future__ import annotations

import logging

log = logging.getLogger("scanner.portfolio.binance_positions")

__all__ = ["cost_basis", "build", "QUOTES", "STABLE_ASSETS"]

#: عملات الاقتباس التي نبحث عن الرمز بها، بالترتيب
QUOTES = ("USDT", "USDC", "FDUSD", "BUSD", "BTC")

#: أصولٌ لا تُعدّ «مركزاً»: هي النقد نفسه
STABLE_ASSETS = frozenset({
    "USDT", "USDC", "FDUSD", "BUSD", "TUSD", "DAI", "USDP", "USD1",
})

#: فرقٌ أقلّ من هذا بين كمّية الصفقات والرصيد يُعدّ تقريب كسور
QTY_TOLERANCE = 0.005          # ٠٫٥٪

# ═══ سجلّ الصفقات يُجلَب مرّةً ═══
#
# ``myTrades`` نداءٌ موقَّع **لكل رمز**. وكانت ``build`` تجلبه
# لحساب متوسّط التكلفة، ثمّ تجلبه ``/api/wallet/closed/`` مرّةً
# أخرى لنفس الرموز — ضِعفُ الطلبات لنفس البيانات، وضِعفُ الزمن
# الذي تنتظره الصفحة.
#
# والمفتاح هنا بالرمز وحده: السجلّ لا يتغيّر إلّا بصفقةٍ جديدة،
# ومهلةُ دقائق تكفي.
_TRADES: dict[str, tuple[float, list]] = {}
TRADES_TTL = 180.0


def trades_for(symbol: str) -> list[dict]:
    """صفقات رمزٍ — من الذاكرة إن كانت طازجة."""
    import time

    from scanner.adapters import binance_account as ba

    key = symbol.upper()
    hit = _TRADES.get(key)
    if hit and (time.time() - hit[0]) < TRADES_TTL:
        return hit[1]
    rows = ba.my_trades(key)
    _TRADES[key] = (time.time(), rows)
    return rows


def cost_basis(trades: list[dict]) -> dict:
    """متوسّط التكلفة والمحقّق من سجلّ صفقات رمزٍ واحد.

    ``trades`` بترتيب الزمن — الأقدم أوّلاً.
    """
    qty = 0.0          # الكمّية المملوكة الآن
    cost = 0.0         # إجمالي ما دُفع فيها (بعملة الاقتباس)
    realized = 0.0     # ربح/خسارة ما بيع
    bought = 0.0       # إجمالي ما اشتُري — للفجوة
    sold = 0.0
    fees_quote = 0.0
    first_at = last_at = None

    for t in trades:
        px = float(t.get("price") or 0.0)
        q = float(t.get("qty") or 0.0)
        if px <= 0 or q <= 0:
            continue
        fee = float(t.get("commission") or 0.0)
        fee_asset = str(t.get("commission_asset") or "").upper()
        sym = str(t.get("symbol") or "")
        first_at = first_at or t.get("time")
        last_at = t.get("time")

        if t.get("is_buyer"):
            recv = q
            spent = px * q
            # ═══ العمولة: إمّا تُنقص المستلَم أو تزيد المدفوع ═══
            if fee and sym.startswith(fee_asset) and fee_asset:
                recv -= fee                      # عمولة بالأصل
            elif fee and sym.endswith(fee_asset) and fee_asset:
                spent += fee                     # عمولة بالاقتباس
                fees_quote += fee
            qty += recv
            cost += spent
            bought += recv
        else:
            if qty <= 0:
                # بيعٌ بلا شراءٍ مسجَّل: الرصيد جاء من إيداع.
                # لا يُحتسب ربحاً — تكلفته مجهولة.
                sold += q
                continue
            take = min(q, qty)
            avg = cost / qty if qty else 0.0
            proceeds = px * take
            if fee and sym.endswith(fee_asset) and fee_asset:
                proceeds -= fee
                fees_quote += fee
            realized += proceeds - avg * take
            # ═══ التكلفة تنقص بالنسبة لا بسعر البيع ═══
            cost -= avg * take
            qty -= take
            sold += q

    return {
        "qty_from_trades": round(qty, 10),
        "cost": round(cost, 8),
        "avg_cost": round(cost / qty, 10) if qty > 0 else None,
        "realized": round(realized, 8),
        "bought": round(bought, 10),
        "sold": round(sold, 10),
        "fees_quote": round(fees_quote, 8),
        "trades": len(trades),
        "first_at": first_at,
        "last_at": last_at,
    }


# ═══════════════════════════════════════════════════════════════
#  الصفقات المغلقة — ربحٌ وخسارة بعد العمولة
# ═══════════════════════════════════════════════════════════════
#
# ═══ لماذا مطابقةٌ بالوارد أوّلاً (FIFO) ═══
#
# «كم ربحت من هذه الصفقة» سؤالٌ بلا جواب في السوق الفوريّ ما لم
# يُقرَّر **أيّ شراءٍ** يقابل هذا البيع. واشتريتَ ثلاث مرّات ثمّ
# بعتَ مرّة: أيّها بعت؟
#
# و‏FIFO هو ما تستعمله مصلحة الضرائب في أغلب الولايات، وهو الذي
# تُبنى عليه كشوف Binance نفسها. واختيارُ غيره (آخرَ وارد، أو
# متوسّطاً) يعطي أرقاماً مختلفة لنفس التاريخ — فالتصريح به لازم.
#
# ═══ والعمولة بعملتها ═══
#
#     بعملة الاقتباس (USDT)   تُطرح من العائد مباشرةً
#     بالأصل نفسه (TRX)       تُنقص الكمّية المستلَمة
#     بـBNB                   **لا تُحوَّل**
#
# والثالثة هي الصادقة الصعبة: تحويلُ عمولة BNB إلى دولار يحتاج
# سعر BNB **لحظةَ الصفقة** لا الآن. وتقديرُه بسعر اليوم يُنتج
# رقماً يبدو دقيقاً وهو مخترَع.
#
# فتُجمَع بعملتها وتُعلَن، ويُوسَم الصافي بأنّه «قبل عمولات BNB».

def _fee_split(t: dict, symbol: str, base: str, quote: str) -> tuple:
    """العمولة موزّعةً: (بالاقتباس، بالأصل، أخرى_بعملتها)."""
    fee = float(t.get("commission") or 0.0)
    asset = str(t.get("commission_asset") or "").upper()
    if not fee or not asset:
        return (0.0, 0.0, None)
    if asset == quote:
        return (fee, 0.0, None)
    if asset == base:
        return (0.0, fee, None)
    return (0.0, 0.0, (asset, fee))


def split_symbol(symbol: str) -> tuple[str, str]:
    """الرمز إلى أصلٍ واقتباس — بأطول اقتباسٍ مطابق."""
    s = symbol.upper()
    for q in sorted(QUOTES, key=len, reverse=True):
        if s.endswith(q) and len(s) > len(q):
            return (s[: -len(q)], q)
    return (s, "USDT")


def roundtrips(trades: list[dict], symbol: str = "") -> dict:
    """صفقاتٌ مغلقة من سجلّ رمزٍ واحد — كلٌّ بربحها الصافي.

    ``trades`` بترتيب الزمن. ويعيد قائمةً: كل بيعٍ يُقابَل بما
    يسبقه من شراءٍ بالوارد أوّلاً، فيُنتج صفقةً مغلقة بسعر دخولٍ
    مرجّح وسعر خروجٍ وعمولةٍ وصافٍ.
    """
    sym = symbol or str((trades[0] if trades else {}).get("symbol") or "")
    base, quote = split_symbol(sym)

    lots: list[dict] = []          # {qty, unit_cost} بالوارد أوّلاً
    closed: list[dict] = []
    other_fees: dict[str, float] = {}
    orphan_sold = 0.0

    for t in trades:
        px = float(t.get("price") or 0.0)
        q = float(t.get("qty") or 0.0)
        if px <= 0 or q <= 0:
            continue
        f_quote, f_base, f_other = _fee_split(t, sym, base, quote)
        if f_other:
            other_fees[f_other[0]] = other_fees.get(f_other[0], 0.0) + f_other[1]

        if t.get("is_buyer"):
            recv = q - f_base                 # عمولة بالأصل تُنقص المستلَم
            spent = px * q + f_quote          # وبالاقتباس تزيد المدفوع
            if recv > 0:
                lots.append({"qty": recv, "unit_cost": spent / recv,
                             "time": t.get("time")})
            continue

        # ── بيع: يُقابَل بالوارد أوّلاً ──
        left = q
        cost = 0.0
        matched = 0.0
        opened_at = None
        while left > 1e-12 and lots:
            lot = lots[0]
            take = min(left, lot["qty"])
            cost += take * lot["unit_cost"]
            matched += take
            opened_at = opened_at or lot.get("time")
            lot["qty"] -= take
            left -= take
            if lot["qty"] <= 1e-12:
                lots.pop(0)

        if matched <= 0:
            # ═══ بيعٌ بلا شراءٍ مسجَّل ═══
            #
            # الرصيد جاء من إيداعٍ أو تحويل. ولا يُحتسب ربحاً:
            # تكلفته مجهولة، وعدّ العائد كلّه ربحاً كذبٌ صريح.
            orphan_sold += q
            continue

        # العائد يُنقَص بحصّة العمولة من الكمّية المطابَقة
        proceeds = matched * px - f_quote * (matched / q)
        net = proceeds - cost
        entry = cost / matched
        closed.append({
            "symbol": sym, "base": base, "quote": quote,
            "qty": round(matched, 10),
            "entry": round(entry, 10),
            "exit": round(px, 10),
            "cost": round(cost, 8),
            "proceeds": round(proceeds, 8),
            "net": round(net, 8),
            "pct": round((px - entry) / entry * 100.0, 3) if entry else None,
            "fee_quote": round(f_quote * (matched / q), 8),
            "won": net > 0,
            "opened_at": opened_at,
            "closed_at": t.get("time"),
            "partial": left > 1e-12,
        })

    wins = [r for r in closed if r["won"]]
    losses = [r for r in closed if not r["won"]]
    net_total = sum(r["net"] for r in closed)

    return {
        "symbol": sym, "quote": quote,
        "closed": closed[::-1],                 # الأحدث أوّلاً
        "n": len(closed),
        "wins": len(wins), "losses": len(losses),
        "net": round(net_total, 8),
        "gross_win": round(sum(r["net"] for r in wins), 8),
        "gross_loss": round(sum(r["net"] for r in losses), 8),
        "fees_quote": round(sum(r["fee_quote"] for r in closed), 8),
        "win_rate": round(len(wins) / len(closed) * 100.0, 1) if closed else None,
        "open_qty": round(sum(l["qty"] for l in lots), 10),
        # ═══ وما لا يُحسَب يُقال ═══
        "other_fees": {k: round(v, 8) for k, v in other_fees.items()},
        "orphan_sold": round(orphan_sold, 10),
        "method": "FIFO",
        "notes": _rt_notes(other_fees, orphan_sold, base, quote),
    }


def _rt_notes(other_fees: dict, orphan: float, base: str,
              quote: str) -> list[str]:
    out = ["المطابقة بالوارد أوّلاً (FIFO) — وهي ما تعتمده كشوف "
           "Binance. وطريقةٌ أخرى تعطي أرقاماً مختلفة للتاريخ نفسه."]
    if other_fees:
        pretty = " · ".join(f"{v:.8g} {k}" for k, v in other_fees.items())
        out.append(
            f"عمولاتٌ دُفعت بعملةٍ أخرى ({pretty}) لم تُحوَّل إلى "
            f"{quote}: التحويل يحتاج سعرها **لحظة الصفقة**، وتقديرُه "
            "بسعر اليوم يُنتج رقماً يبدو دقيقاً وهو مخترَع. "
            "فالصافي أعلاه قبلها.")
    if orphan > 0:
        out.append(
            f"‏{orphan:.8g} {base} بيعت بلا شراءٍ مسجَّل على هذا الزوج "
            "— إيداعٌ أو تحويل. ولم تُحتسب ربحاً: تكلفتها مجهولة.")
    return out


def symbol_for(asset: str, known: set[str]) -> str | None:
    """أوّل رمزٍ متداوَل لهذا الأصل بعملات الاقتباس المعروفة."""
    a = asset.upper()
    for q in QUOTES:
        s = f"{a}{q}"
        if s in known:
            return s
    return None


def spot_prices(symbols: list[str]) -> dict[str, float]:
    """أسعار الآن من نقطةٍ عامّة — بلا مفتاح.

    ═══ ولماذا يجلبها الخادم أصلاً ═══

    الشاشة تعتمد ``LiveFeed`` وهو بثّ ويب‑سوكت من **المتصفّح**.
    والشبكة التي تحجب CDN تحجبه غالباً — فتبقى خانة السعر «…»
    إلى الأبد، ومعها القيمة والربح غير المحقّق.

    وسعرٌ عمره دقيقة خيرٌ من فراغ. فالخادم يجلبه في نداءٍ واحد
    (وزنه ٢ لكل الرموز)، والبثّ يحسّنه إن وصل — كما تفعل صفحة
    البتكوين تماماً، وتقول «من الخادم» لا «بثّ مباشر».
    """
    if not symbols:
        return {}
    try:
        from scanner.adapters import get_adapter

        raw = get_adapter("binance")._get("/api/v3/ticker/price", {})
    except Exception as exc:  # noqa: BLE001
        log.info("تعذّر جلب الأسعار: %s", str(exc)[:90])
        return {}

    want = {s.upper() for s in symbols}
    out: dict[str, float] = {}
    for row in raw if isinstance(raw, list) else []:
        s = str(row.get("symbol") or "").upper()
        if s in want:
            try:
                out[s] = float(row["price"])
            except (KeyError, TypeError, ValueError):
                continue
    return out


def build(*, dust_usd: float = 5.0, max_symbols: int = 40,
          known_symbols: set[str] | None = None) -> dict:
    """مراكز الحساب كاملةً — أو سببُ التعذّر.

    ``max_symbols`` حدُّ وزن: ``myTrades`` نداءٌ لكل رمز، وحسابٌ
    فيه ستّون أصلاً يعني ستّين طلباً في الدورة الواحدة.
    """
    from scanner.adapters import binance_account as ba

    if not ba.configured():
        return {"ok": False, "why": "مفاتيح Binance غير مضبوطة",
                "positions": [], "cash": []}

    try:
        raw = ba.balances(dust=0.0)
    except ba.BinanceAuthError as exc:
        return {"ok": False, "why": str(exc)[:240],
                "positions": [], "cash": []}

    if known_symbols is None:
        try:
            from scanner.adapters import get_adapter

            known_symbols = set(get_adapter("binance").usdt_universe(0))
        except Exception:  # noqa: BLE001
            known_symbols = set()

    cash = [b for b in raw if b["asset"].upper() in STABLE_ASSETS]
    assets = [b for b in raw if b["asset"].upper() not in STABLE_ASSETS]

    positions: list[dict] = []
    skipped: list[str] = []

    for b in assets[:max_symbols]:
        asset = b["asset"].upper()
        sym = symbol_for(asset, known_symbols) or f"{asset}USDT"
        try:
            trades = trades_for(sym)
        except ba.BinanceAuthError as exc:
            skipped.append(f"{asset}: {str(exc)[:60]}")
            continue

        cb = cost_basis(trades)
        held = b["total"]

        # ═══ الفجوة ═══
        #
        # كمّية الصفقات ≠ الرصيد ⇒ جزءٌ من الرصيد لم يُشترَ هنا.
        from_trades = cb["qty_from_trades"]
        gap = held - from_trades
        partial = (abs(gap) > max(QTY_TOLERANCE * max(held, 1e-12), 1e-12))

        positions.append({
            "asset": asset, "symbol": sym,
            "qty": held, "free": b["free"], "locked": b["locked"],
            "avg_cost": cb["avg_cost"],
            "cost": cb["cost"],
            "realized": cb["realized"],
            "fees_quote": cb["fees_quote"],
            "trades": cb["trades"],
            "first_at": cb["first_at"], "last_at": cb["last_at"],
            # ═══ ويُقال صراحةً ═══
            #
            # رقمٌ واثقٌ مبنيٌّ على تكلفةٍ مجهولة أسوأ من لا رقم.
            "basis_partial": bool(partial),
            "basis_gap_qty": round(gap, 10),
            "basis_note": (
                "" if not partial else
                f"‏{abs(gap):.8g} {asset} من الرصيد لم تأتِ من صفقةٍ على "
                f"{sym} — إيداعٌ أو تحويل أو شراءٌ بزوجٍ آخر. "
                "فمتوسّط التكلفة والربح غير المحقّق يخصّان الجزء "
                "المشترى وحده."),
            "quote": sym[len(asset):] or "USDT",
        })

    # ═══ السعر والربح غير المحقّق يُحسبان هنا ═══
    #
    # لا في المتصفّح وحده: بثُّ الويب‑سوكت قد لا يصل، وحينها تبقى
    # الصفحة بلا أيّ رقم. والبثّ — إن وصل — يحدّثهما لحظياً فوق
    # هذه القيمة.
    px = spot_prices([p["symbol"] for p in positions])
    for p in positions:
        price = px.get(p["symbol"].upper())
        p["last_price"] = price
        p["value"] = round(price * p["qty"], 8) if price else None
        avg = p["avg_cost"]
        if price and avg:
            p["pnl"] = round((price - avg) * p["qty"], 8)
            p["pnl_pct"] = round((price - avg) / avg * 100.0, 2)
            p["winning"] = p["pnl"] > 0
        else:
            # ═══ والمجهول ‎None‎ لا صفر ═══
            #
            # الصفر يُجمَع ويُلوَّن ويُقرأ «لا ربح ولا خسارة»،
            # وهو هنا «لا أعرف»: تكلفةٌ مجهولة أو سعرٌ لم يصل.
            p["pnl"] = p["pnl_pct"] = p["winning"] = None

    positions.sort(key=lambda p: -(p["value"] or p["cost"] or 0.0))
    return {
        "ok": True,
        "positions": positions,
        "priced": len(px),
        "cash": cash,
        "skipped": skipped,
        "truncated": len(assets) > max_symbols,
        "assets_total": len(assets),
    }
