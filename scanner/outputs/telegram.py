"""تنبيهات تيليجرام.

قواعد التصميم:
  • رسالة واحدة مجمّعة لأفضل N، لا رسالة لكل رمز — وإلا تُكتم الإشعارات
  • السبب قبل السعر: تعرف لماذا رُشّح قبل أن ترى الأرقام
  • لا رسالة بلا رابط شارت — بدونه ستهجر الأداة خلال أسبوعين
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

from ..formatting import price as fmt_price

API = "https://api.telegram.org/bot{token}/sendMessage"


def _esc(text: str) -> str:
    for ch in ("_", "*", "[", "]", "`"):
        text = text.replace(ch, "\\" + ch)
    return text


def format_message(df: pd.DataFrame, market: str, timeframe: str,
                   top: int = 5, threshold: float = 25.0) -> str | None:
    if df.empty:
        return None

    ready = df[df["ready"]] if "ready" in df.columns else df[df["score"] >= threshold]
    if ready.empty:
        return f"🔍 {market} · {timeframe}\nلا فرص مكتملة الشروط اليوم."

    lines = [f"🔍 *{_esc(market)}* · {timeframe} · {len(ready)} فرصة", ""]
    for _, r in ready.head(top).iterrows():
        icon = "🟢" if r["score"] >= threshold * 2 else "🔵"
        lines.append(f"{icon} *{_esc(str(r['symbol']))}* · {r['score']:.0f} نقطة")
        if r.get("reasons") and r["reasons"] != "—":
            lines.append(f"الالتقاء {int(r.get('confluence', 0))} · {_esc(str(r['reasons']))}")
        htf = int(r.get("htf", 0))
        lines.append(f"الفريم الأعلى: {'صاعد' if htf == 1 else 'هابط' if htf == -1 else 'مختلط'}")
        lines.append(f"السعر {fmt_price(r['close'])}")
        if r.get("chart"):
            lines.append(f"[افتح الشارت]({r['chart']})")
        lines.append("")

    if len(ready) > top:
        lines.append(f"_و{len(ready) - top} فرصة أخرى في التقرير_")
    return "\n".join(lines)


def send(text: str, token: str | None = None, chat_id: str | None = None,
         timeout: int = 15) -> bool:
    token = token or os.getenv("TELEGRAM_TOKEN")
    chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("تيليجرام غير مُعد: يلزم TELEGRAM_TOKEN و TELEGRAM_CHAT_ID")
        return False

    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": "true",
    }).encode()

    try:
        req = urllib.request.Request(API.format(token=token), data=data)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode()).get("ok", False)
    except urllib.error.HTTPError as exc:
        print(f"تيليجرام رفض الطلب: {exc.code} — تحقق من التوكن ومعرّف المحادثة")
    except Exception as exc:  # noqa: BLE001
        print(f"تعذّر إرسال التنبيه: {exc}")
    return False
