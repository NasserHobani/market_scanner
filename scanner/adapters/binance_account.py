# -*- coding: utf-8 -*-
"""حساب Binance — قراءةٌ موقَّعة، ولا أمرَ واحد.

═══ ما لا يوجد في هذا الملفّ ═══

لا ``POST /api/v3/order``، ولا إلغاء، ولا سحب. وليس ذلك سهواً:
المنصّة استشارية بنصّ المادّة ١٣ §٣٣ — «المحلّل لا ينفّذ صفقات
ولا يغيّر وقفاً ولا هدفاً». وغيابُ الشيفرة أقوى من راية تمنعها،
لأنّ الراية تُقلَب سطراً واحداً.

═══ والمفتاح يجب أن يكون للقراءة فقط ═══

مفتاحٌ يسمح بالتداول يفتح حسابك لأيّ ثغرةٍ في هذا الخادم — وهو
خادمٌ بلا HTTPS على شبكةٍ محلّية. و``restrictions()`` يسأل Binance
عن صلاحيات المفتاح فعلاً ويحذّر إن زادت عن القراءة.

ولا يكتفي بالوعد: ``canTrade`` في ``/api/v3/account`` يصف الحساب
لا المفتاح. والصلاحيات الحقيقية في ‎/sapi/v1/account/apiRestrictions‎.

═══ والتوقيع ═══

‏HMAC-SHA256 على سلسلة الاستعلام كما هي **قبل** إرسالها. وأيّ
إعادة ترتيبٍ بعد التوقيع تُبطله — فالسلسلة تُبنى مرّةً وتُستعمل
هي نفسها.

═══ وفارق الساعة ═══

‏Binance يرفض طلباً ``timestamp`` فيه يسبق ساعته بأكثر من
``recvWindow``. وحاوية Docker قد تنجرف ساعتُها. فالفارق يُقاس من
‎/api/v3/time‎ ويُصحَّح — بدل «Timestamp for this request was
1000ms ahead» التي لا تدلّ على ساعةٍ منحرفة.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("scanner.adapters.binance_account")

HOST = "https://api.binance.com"
UA = {"User-Agent": "market-scanner/0.1"}
RECV_WINDOW = 10_000

#: أسماء المتغيّرات المقبولة — ``env.ALIASES`` يوحّدها لاحقاً
KEY_VARS = ("BINANCE_API_KEY", "BINANCE_KEY")
SECRET_VARS = ("BINANCE_API_SECRET", "BINANCE_SECRET")

#: فارق ساعة الخادم عن ساعتنا — يُقاس مرّةً ويُعاد قياسه عند الفشل
_drift_ms: int = 0
_drift_at: float = 0.0
_DRIFT_TTL = 1800.0


class BinanceAuthError(RuntimeError):
    """مفتاحٌ ناقص أو مرفوض — برسالةٍ تقول ما يُفعل."""


def credentials() -> tuple[str, str]:
    key = secret = ""
    for name in KEY_VARS:
        key = os.environ.get(name, "").strip()
        if key:
            break
    for name in SECRET_VARS:
        secret = os.environ.get(name, "").strip()
        if secret:
            break
    return key, secret


def configured() -> bool:
    k, s = credentials()
    return bool(k and s)


def _require() -> tuple[str, str]:
    k, s = credentials()
    if not (k and s):
        raise BinanceAuthError(
            "مفاتيح Binance غير مضبوطة. أنشئ مفتاحاً **للقراءة فقط** من "
            "Binance ← API Management، واترك «Enable Spot Trading» و"
            "«Enable Withdrawals» مُطفأين، ثمّ أضف في بورتينر ← "
            "Environment variables: BINANCE_API_KEY و BINANCE_API_SECRET.")
    return k, s


# ═══════════════════════════════════════════════════════════════
#  النقل
# ═══════════════════════════════════════════════════════════════

def _server_time_drift() -> int:
    """فارق ساعة Binance عن ساعتنا بالميلي ثانية."""
    global _drift_ms, _drift_at

    if time.time() - _drift_at < _DRIFT_TTL:
        return _drift_ms
    try:
        req = urllib.request.Request(f"{HOST}/api/v3/time", headers=UA)
        with urllib.request.urlopen(req, timeout=10) as resp:
            server = int(json.loads(resp.read())["serverTime"])
        _drift_ms = server - int(time.time() * 1000)
        _drift_at = time.time()
        if abs(_drift_ms) > 2000:
            log.warning("ساعة هذه الآلة تنحرف %d مللي ثانية عن Binance — "
                        "يُصحَّح تلقائياً", _drift_ms)
    except Exception as exc:  # noqa: BLE001
        log.info("تعذّر قياس فارق الساعة: %s", str(exc)[:80])
    return _drift_ms


def _get(path: str, params: dict | None = None, *, signed: bool = True,
         timeout: int = 15):
    """طلبٌ ``GET`` — ويرمي ``BinanceAuthError`` برسالةٍ مفهومة."""
    key, secret = _require()
    p = dict(params or {})
    if signed:
        p["timestamp"] = int(time.time() * 1000) + _server_time_drift()
        p["recvWindow"] = RECV_WINDOW
    # ═══ السلسلة تُبنى مرّةً ═══
    #
    # التوقيع على ``qs`` ثمّ إرسال قاموسٍ يُرمَّز ثانيةً قد يعطي
    # ترتيباً مختلفاً، فيسقط التوقيع بـ«Signature for this request
    # is not valid» — وهو خطأٌ يقود إلى الشكّ في المفتاح لا في
    # الترميز.
    qs = urllib.parse.urlencode(p, doseq=True)
    if signed:
        sig = hmac.new(secret.encode(), qs.encode(), hashlib.sha256)
        qs = f"{qs}&signature={sig.hexdigest()}"

    req = urllib.request.Request(f"{HOST}{path}?{qs}",
                                 headers={**UA, "X-MBX-APIKEY": key})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8")[:200]
        except Exception:  # noqa: BLE001
            pass
        if exc.code in (401, 403):
            raise BinanceAuthError(
                f"رفض Binance المفتاح ({exc.code}). تحقّق أنّه صحيح، وأنّ "
                f"عنوان هذا الخادم مسموحٌ في قائمة IP إن قيّدتها. "
                f"[{body}]") from exc
        if exc.code == 418 or exc.code == 429:
            raise BinanceAuthError(
                "تجاوزتَ حدّ الطلبات عند Binance — انتظر دقائق. "
                "وإن تكرّر فقلّل عدد الرموز المتابَعة.") from exc
        # ═══ توقيتٌ خاطئ يُقال باسمه ═══
        if "-1021" in body or "Timestamp" in body:
            global _drift_at
            _drift_at = 0.0          # أعد القياس في الطلب التالي
            raise BinanceAuthError(
                "ساعة الخادم منحرفة عن Binance. أُعيد قياس الفارق — "
                "أعد المحاولة. وإن تكرّر فاضبط وقت الآلة (NTP).") from exc
        raise BinanceAuthError(f"‏Binance ردّ {exc.code}: {body}") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise BinanceAuthError(
            f"تعذّر الوصول إلى Binance: {str(exc)[:120]}") from exc


# ═══════════════════════════════════════════════════════════════
#  القراءات
# ═══════════════════════════════════════════════════════════════

def restrictions() -> dict:
    """صلاحيات المفتاح — ومن هنا يأتي التحذير.

    ``canTrade`` في ``/api/v3/account`` يصف **الحساب** لا المفتاح:
    حسابٌ يستطيع التداول يعيدها ``true`` ولو كان المفتاح للقراءة
    فقط. فالصلاحيات الحقيقية هنا.
    """
    try:
        raw = _get("/sapi/v1/account/apiRestrictions")
    except BinanceAuthError as exc:
        # بعض المفاتيح لا تملك صلاحية قراءة هذا المسار نفسه —
        # وهو ليس عطباً، فيُقال «مجهول» لا «آمن».
        return {"ok": False, "why": str(exc)[:160], "safe": None}

    read_only = not (raw.get("enableSpotAndMarginTrading")
                     or raw.get("enableWithdrawals")
                     or raw.get("enableFutures")
                     or raw.get("enableMargin")
                     or raw.get("enableInternalTransfer"))
    warn = []
    if raw.get("enableWithdrawals"):
        warn.append("**السحب مفعَّل** — أخطر صلاحية على الإطلاق")
    if raw.get("enableSpotAndMarginTrading"):
        warn.append("التداول الفوري مفعَّل")
    if raw.get("enableFutures"):
        warn.append("العقود الدائمة مفعَّلة")
    if raw.get("enableInternalTransfer"):
        warn.append("التحويل الداخلي مفعَّل")

    return {
        "ok": True,
        "safe": read_only,
        "reading": bool(raw.get("enableReading")),
        "withdrawals": bool(raw.get("enableWithdrawals")),
        "spot_trading": bool(raw.get("enableSpotAndMarginTrading")),
        "futures": bool(raw.get("enableFutures")),
        "ip_restricted": bool(raw.get("ipRestrict")),
        "warnings": warn,
        "why": ("المفتاح للقراءة فقط — وهو الصحيح." if read_only else
                "هذا المفتاح يستطيع أكثر من القراءة: " + " · ".join(warn) +
                ". أنشئ مفتاحاً جديداً بالقراءة وحدها واحذف هذا."),
    }


def account() -> dict:
    """الأرصدة وحالة الحساب."""
    return _get("/api/v3/account")


def balances(*, dust: float = 0.0) -> list[dict]:
    """الأرصدة غير الصفرية — الحرّ والمحجوز.

    ``dust`` يُسقط ما يقلّ مجموعه عنه: حساباتٌ قديمة فيها كسورٌ
    من عشرات العملات تُنتج صفوفاً لا تعني شيئاً.
    """
    out = []
    for b in (account().get("balances") or []):
        try:
            free = float(b.get("free") or 0.0)
            locked = float(b.get("locked") or 0.0)
        except (TypeError, ValueError):
            continue
        total = free + locked
        if total <= dust:
            continue
        out.append({"asset": b.get("asset", ""), "free": free,
                    "locked": locked, "total": total})
    return sorted(out, key=lambda x: -x["total"])


def my_trades(symbol: str, *, limit: int = 1000,
              from_id: int | None = None) -> list[dict]:
    """صفقات رمزٍ واحد — الأقدم أوّلاً.

    ═══ ولا يمكن طلبها لكل الرموز ═══

    ‏Binance يشترط ``symbol`` هنا. فلا سبيل إلى «كل صفقاتي» بنداءٍ
    واحد: تُعدَّد الرموز المرشّحة وتُسأل واحداً واحداً. وهذا ما
    يجعل الحدّ على عدد الرموز المتابَعة مسألة وزنٍ لا ذوق.
    """
    p: dict = {"symbol": symbol.upper(), "limit": min(int(limit), 1000)}
    if from_id is not None:
        p["fromId"] = int(from_id)
    raw = _get("/api/v3/myTrades", p)
    out = []
    for t in raw if isinstance(raw, list) else []:
        try:
            out.append({
                "id": int(t["id"]),
                "symbol": t.get("symbol", symbol.upper()),
                "time": int(t["time"]),
                "price": float(t["price"]),
                "qty": float(t["qty"]),
                "quote_qty": float(t.get("quoteQty") or 0.0),
                "commission": float(t.get("commission") or 0.0),
                "commission_asset": t.get("commissionAsset", ""),
                "is_buyer": bool(t.get("isBuyer")),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(out, key=lambda x: x["time"])


def open_orders(symbol: str | None = None) -> list[dict]:
    """الأوامر المعلّقة — كلّها أو لرمزٍ واحد.

    بلا رمز: وزنُ الطلب ٤٠ بدل ٦. وهو مقبولٌ في دورةٍ كل دقيقة،
    وأرخص بكثير من سؤال أربعين رمزاً واحداً واحداً.
    """
    raw = _get("/api/v3/openOrders",
               {"symbol": symbol.upper()} if symbol else None)
    out = []
    for o in raw if isinstance(raw, list) else []:
        try:
            out.append({
                "order_id": int(o["orderId"]),
                "symbol": o.get("symbol", ""),
                "side": o.get("side", ""),
                "type": o.get("type", ""),
                "price": float(o.get("price") or 0.0),
                "stop_price": float(o.get("stopPrice") or 0.0),
                "orig_qty": float(o.get("origQty") or 0.0),
                "executed_qty": float(o.get("executedQty") or 0.0),
                "time": int(o.get("time") or 0),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return out


__all__ = [
    "BinanceAuthError", "configured", "credentials", "restrictions",
    "account", "balances", "my_trades", "open_orders",
]
