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


def symbol_for(asset: str, known: set[str]) -> str | None:
    """أوّل رمزٍ متداوَل لهذا الأصل بعملات الاقتباس المعروفة."""
    a = asset.upper()
    for q in QUOTES:
        s = f"{a}{q}"
        if s in known:
            return s
    return None


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
            trades = ba.my_trades(sym)
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

    positions.sort(key=lambda p: -(p["cost"] or 0.0))
    return {
        "ok": True,
        "positions": positions,
        "cash": cash,
        "skipped": skipped,
        "truncated": len(assets) > max_symbols,
        "assets_total": len(assets),
    }
