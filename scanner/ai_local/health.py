# -*- coding: utf-8 -*-
"""Ollama health checks — configuration ≠ runtime availability."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable

from .config import LocalAIConfig, load_local_config
from .model_registry import resolve_model


def _default_get(url: str, timeout: float = 5.0) -> dict[str, Any]:
    """يمرّ عبر ``ai_local.http`` الذي يتجاوز البروكسي للعناوين المحلية.

    كان ``urlopen`` المباشر يمرّر ``127.0.0.1`` عبر البروكسي المضبوط في
    البيئة أو سجلّ ويندوز، فيفشل بينما المتصفّح و curl — اللذان
    يستثنيان المضيف المحلي تلقائياً — يعملان على العنوان نفسه.
    """
    from .http import get_json

    return get_json(url, timeout=timeout)


def check_ollama_health(cfg: LocalAIConfig | None = None,
                        *, http_get: Callable[[str], dict[str, Any]] | None = None
                        ) -> dict[str, Any]:
    cfg = cfg or load_local_config()
    get = http_get or _default_get
    base = (cfg.ollama_base_url or "http://127.0.0.1:11434").rstrip("/")
    model = resolve_model(cfg.local_default_model)

    out: dict[str, Any] = {
        "enabled": cfg.local_enabled and cfg.ollama_enabled,
        "ollama_reachable": False,
        "model_available": False,
        "base_url": base,
        "default_model": model,
        "models": [],
        "error": "",
    }
    if not out["enabled"]:
        out["error"] = "Local AI disabled in settings"
        return out

    try:
        tags = get(f"{base}/api/tags")
        out["ollama_reachable"] = True
        names = [m.get("name", "") for m in (tags.get("models") or []) if m.get("name")]
        out["models"] = [{"model": n, "available": True} for n in names]

        # المطابقة على ثلاث درجات، من الأدقّ إلى الأوسع. السبب أن
        # Ollama يسمّي النموذج بوسمه الكامل (‏qwen3:8b) بينما المستخدم
        # قد يكتب الاسم وحده (‏qwen3) أو وسماً آخر (‏qwen3:latest).
        # ورفضُ ذلك كان يقول «غير موجود» عن نموذج مثبَّت فعلاً.
        base_name = model.split(":")[0]
        exact = [n for n in names if n == model]
        same_tag = [n for n in names if n.split(":")[0] == base_name]
        out["model_available"] = bool(exact or same_tag)
        out["matched_model"] = (exact or same_tag or [""])[0]
        out["exact_match"] = bool(exact)

        if not out["model_available"]:
            out["error"] = (
                f"النموذج «{model}» غير مثبَّت. "
                + (f"المتاح: {'، '.join(names[:6])}" if names
                   else "لا نماذج مثبَّتة — شغّل: ollama pull " + model))
        elif not exact:
            # يعمل، لكن الاسم المضبوط ليس ما سيُستعمل — يُقال لا يُخفى
            out["error"] = (f"«{model}» غير موجود بالضبط؛ "
                            f"سيُستعمل «{out['matched_model']}»")
    except Exception as exc:  # noqa: BLE001
        from .http import diagnose

        d = diagnose(f"{base}/api/tags")
        out["error"] = d.get("reason") or str(exc)[:200]
        out["hint"] = d.get("hint", "")
        out["proxy_env"] = d.get("proxy_env", {})
        out["proxy_bypassed"] = d.get("proxy_bypassed", False)

    return out


def test_ollama_connection(cfg: LocalAIConfig | None = None,
                           *, http_get: Callable[[str], dict[str, Any]] | None = None
                           ) -> dict[str, Any]:
    h = check_ollama_health(cfg, http_get=http_get)
    # «متّصل» تعني الوصول إلى Ollama. ووجود النموذج شرط للمراجعة لا
    # للاتصال، وخلطهما كان يقول «غير متّصل» عن خادم يستجيب تماماً —
    # فيبحث المستخدم في الشبكة والمشكلة في اسم نموذج.
    return {
        "connected": bool(h.get("ollama_reachable")),
        "ready": bool(h.get("ollama_reachable") and h.get("model_available")),
        "ollama_reachable": h.get("ollama_reachable"),
        "model_available": h.get("model_available"),
        "model": h.get("default_model"),
        "matched_model": h.get("matched_model", ""),
        "exact_match": h.get("exact_match", False),
        "base_url": h.get("base_url"),
        "error": h.get("error", ""),
        "hint": h.get("hint", ""),
        "proxy_env": h.get("proxy_env", {}),
        "proxy_bypassed": h.get("proxy_bypassed", False),
        "models": h.get("models", []),
    }
