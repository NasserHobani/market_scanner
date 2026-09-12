# -*- coding: utf-8 -*-
"""نداء HTTP للخدمات المحلية — بلا بروكسي، وبتشخيص يقول ما حدث.

═══ العطب الذي عولج ═══

«اختبار الاتصال بـ Ollama يفشل، وهو يعمل تماماً خارج النظام».

السبب أن ``urllib.request.urlopen`` يقرأ إعدادات البروكسي من البيئة
ومن سجلّ ويندوز، ويمرّر **كل** طلب عبرها — بما فيه ``127.0.0.1``.
والمتصفّح و ``curl`` يستثنيان المضيف المحلي تلقائياً، فيعملان بينما
يفشل بايثون على العنوان نفسه.

وهذا يفسّر أيضاً حجب cdnjs الذي رأيناه: الشبكة خلف بروكسي.

فالحلّ أن يُبنى فاتح (opener) بـ ``ProxyHandler({})`` — قاموس فارغ
يعني «لا بروكسي إطلاقاً» لا «استعمل الافتراضي». وهو مطبَّق على
العناوين المحلية والخاصة وحدها؛ ما سواها يبقى على السلوك الافتراضي
فلا نكسر بيئةً تحتاج البروكسي فعلاً.
"""
from __future__ import annotations

import ipaddress
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

# فاتح واحد يُعاد استعماله: بناؤه في كل نداء يعيد قراءة الإعدادات بلا داعٍ
_direct_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def is_local(url: str) -> bool:
    """هل العنوان محلي أو على شبكة خاصة؟

    الأسماء التي لا تُحلّ (خادم متوقّف مثلاً) تُعدّ محلية إن كانت
    ``localhost`` أو ما شابه — فالغرض تفادي البروكسي لا تصنيف الشبكة.
    """
    try:
        host = urllib.parse.urlparse(url).hostname or ""
    except ValueError:
        return False
    if not host:
        return False
    if host in ("localhost", "localhost.localdomain") or host.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_loopback or ip.is_private or ip.is_link_local
    except ValueError:
        pass
    try:
        return ipaddress.ip_address(socket.gethostbyname(host)).is_private
    except (OSError, ValueError):
        return False


def _open(req, timeout: float):
    if is_local(req.full_url):
        return _direct_opener.open(req, timeout=timeout)
    return urllib.request.urlopen(req, timeout=timeout)


def get_json(url: str, *, timeout: float = 5.0) -> dict[str, Any]:
    req = urllib.request.Request(url, method="GET",
                                 headers={"Accept": "application/json"})
    with _open(req, timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def post_json(url: str, payload: dict, *, timeout: float = 60.0) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json"})
    start = time.monotonic()
    with _open(req, timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    data["_latency_ms"] = round((time.monotonic() - start) * 1000, 1)
    return data


def open_stream(url: str, payload: dict, *, timeout: float = 300.0):
    """اتصال متدفّق — يعيد الاستجابة لتُقرأ سطراً سطراً."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json"})
    return _open(req, timeout)


def diagnose(url: str, *, timeout: float = 5.0) -> dict[str, Any]:
    """تشخيص مفصّل بدل رسالة خطأ واحدة مبتورة.

    الفرق بين «المنفذ مغلق» و«الاسم لا يُحلّ» و«مهلة» و«بروكسي يعترض»
    هو الفرق بين إصلاح في ثانية وبحث في ساعة — وكلها كانت تظهر
    كـ«تعذّر الاتصال».
    """
    out: dict[str, Any] = {
        "url": url, "ok": False, "reason": "", "hint": "",
        "local": is_local(url), "proxy_bypassed": False,
        "latency_ms": None,
    }
    proxies = urllib.request.getproxies()
    out["proxy_env"] = {k: v for k, v in proxies.items() if k != "no"}
    out["proxy_bypassed"] = out["local"] and bool(out["proxy_env"])

    start = time.monotonic()
    try:
        get_json(url, timeout=timeout)
        out["ok"] = True
        out["latency_ms"] = round((time.monotonic() - start) * 1000, 1)
        return out
    except urllib.error.HTTPError as exc:
        out["reason"] = f"استجاب برمز {exc.code}"
        out["hint"] = "الخدمة تعمل لكن المسار خاطئ" if exc.code == 404 else ""
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        out["reason"] = str(reason)[:160]
        text = str(reason).lower()
        if "refused" in text or "10061" in text:
            out["hint"] = ("المنفذ مغلق — تأكّد أن Ollama يعمل "
                           "(‏ollama serve) وأن المنفذ 11434 هو الصحيح.")
        elif "timed out" in text or "timeout" in text:
            out["hint"] = ("مهلة — قد يكون جدار الحماية يحجب المنفذ، "
                           "أو النموذج يُحمَّل الآن.")
        elif "name or service" in text or "getaddrinfo" in text:
            out["hint"] = "اسم المضيف لا يُحلّ — استعمل 127.0.0.1."
        elif out["proxy_env"]:
            out["hint"] = ("بروكسي مضبوط في البيئة. العناوين المحلية "
                           "تتجاوزه هنا، فإن بقي الفشل فالسبب غيره.")
    except (json.JSONDecodeError, ValueError) as exc:
        out["reason"] = f"استجابة غير صالحة: {str(exc)[:120]}"
        out["hint"] = "العنوان يشير إلى خدمة أخرى لا إلى Ollama."
    except Exception as exc:  # noqa: BLE001
        out["reason"] = str(exc)[:160]
    return out
