# -*- coding: utf-8 -*-
"""Ollama local LLM provider — implements AI Advisor LLMProvider contract."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

from scanner.ai_advisor.decision_package import DecisionPackage
from scanner.ai_advisor.prompt_builder import AdvisorPrompt
from scanner.ai_advisor.provider_config import AIAdvisorConfig, load_config
from scanner.ai_advisor.providers.base import LLMProvider, ProviderMetadata
from scanner.ai_advisor.response_parser import ResponseParser, ResponseParseError

from .config import LocalAIConfig, load_local_config
from .model_registry import resolve_model

# ── معاملات التشغيل، مشتقّة من قياس على 54 مراجعة محلية ──
#
#   الموجّه 2050 رمزاً · الإجابة 706 · الزمن 116 ثانية · 5.8 رمز/ثانية
#
# السرعة تدلّ على استدلال على المعالج لا على بطاقة رسومية، فكل رمز
# إضافي يُدفع ثمنه مضاعفاً. ولهذا تُضبط الثلاثة أدناه صراحةً بدل
# الاعتماد على افتراضات الخادم.

# حكمٌ مبنيّ بصيغة JSON لا يحتاج أكثر من هذا. الرقم سقف لا هدف:
# ‏4096 المضبوطة في الإعدادات تسمح للنموذج بأن يُسهب بلا رادع.
MAX_VERDICT_TOKENS = 900

# نافذة السياق: تتّسع للموجّه الحالي ثلاث مرات، فالنمو لا يقصّ
# التعليمات بصمت.
OLLAMA_CONTEXT = 8192

# إبقاء النموذج في الذاكرة بين المسحات — أطول من دورة المسح الافتراضية
KEEP_ALIVE = "30m"

PROVIDER_VERSION = "1.0.0"


class OllamaError(Exception):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass
class OllamaProvider(LLMProvider):
    """Local inference via Ollama — never raises uncaught into trading pipeline."""

    _config: AIAdvisorConfig = field(default_factory=load_config)
    _local: LocalAIConfig = field(default_factory=load_local_config)
    _http_post: Callable[..., dict[str, Any]] | None = field(default=None, repr=False)
    last_usage: dict[str, Any] = field(default_factory=dict, repr=False)
    last_error: str = ""

    def __post_init__(self) -> None:
        self._meta = ProviderMetadata(
            provider_id="ollama",
            display_name="Ollama (Local)",
            vendor="ollama",
            model_family="qwen",
            supports_json=True,
            supports_streaming=False,
            description="Local Qwen via Ollama — AIA-06",
        )
        self._parser = ResponseParser()

    @property
    def provider_id(self) -> str:
        return "ollama"

    @property
    def metadata(self) -> ProviderMetadata:
        return self._meta

    def model_name(self) -> str:
        return resolve_model(self._local.local_default_model)

    def base_url(self) -> str:
        return (self._local.ollama_base_url or "http://127.0.0.1:11434").rstrip("/")

    def analyze(self, prompt: AdvisorPrompt, *,
                package: DecisionPackage) -> dict[str, Any]:
        if not self._local.local_enabled or not self._local.ollama_enabled:
            raise OllamaError("Local AI is disabled in settings")

        model = self.model_name()
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": prompt.system_prompt},
                {"role": "user", "content": prompt.user_prompt},
            ],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": self._config.temperature,
                # سقف الإجابة لا حجمها المرغوب. الحكم الواحد بضع مئات
                # من الرموز، والسقف العالي لا يكلّف شيئاً ما لم يُسهب
                # النموذج — والقياس يقول إنه يُسهب: 706 رمزاً بالوسيط.
                "num_predict": min(int(self._config.max_tokens or 1024),
                                   MAX_VERDICT_TOKENS),
                # نافذة السياق صريحة: الموجّه 2050 رمزاً بالوسيط، وبعض
                # الإعدادات الافتراضية 2048. التجاوز يقصّ **بداية**
                # الموجّه — أي تعليمات النظام — فيجيب النموذج بلا أن
                # يكون قد رآها، ويبدو الخلل ضعفاً في النموذج لا قصّاً.
                "num_ctx": OLLAMA_CONTEXT,
            },
            # إبقاء النموذج محمَّلاً بين المسحات. الافتراضي خمس دقائق،
            # ودورة المسح أطول منها غالباً، فيُفرَّغ النموذج ويُعاد
            # تحميله في كل مرة — وتحميل نموذج بثمانية مليارات معامل
            # يضيف عشرات الثواني قبل أول رمز. وهذا يفسّر جزءاً كبيراً
            # من الـ116 ثانية المقيسة.
            "keep_alive": KEEP_ALIVE,
        }
        if model.startswith("qwen3"):
            payload["think"] = False

        # تُفتح المحادثة قبل الإرسال لا بعده: الموجّه هو نصف ما يريد
        # المستخدم رؤيته، وإظهاره بعد وصول الجواب يفوّت الغرض.
        try:
            from scanner.ai_advisor import live_channel

            live_channel.start(
                symbol=getattr(package, "symbol", "") or "",
                market=getattr(package, "market", "") or "",
                timeframe=getattr(package, "timeframe", "") or "",
                provider="ollama", model=model,
                system=prompt.system_prompt, user=prompt.user_prompt)
        except Exception:  # noqa: BLE001
            pass

        max_attempts = max(1, self._config.retry_count + 1)
        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                raw = self._chat(payload)
                text = self._extract_text(raw)
                parsed = self._parse_json(text)
                usage = self._extract_usage(raw)
                self.last_usage = usage
                self.last_error = ""
                _live_finish(answer=text)
                return parsed
            except (json.JSONDecodeError, ResponseParseError) as exc:
                last_exc = exc
                if attempt >= max_attempts:
                    self.last_error = f"invalid_json: {exc}"
                    _live_finish(error=f"استجابة غير صالحة: {exc}")
                    raise OllamaError(f"Invalid JSON from Ollama: {exc}") from exc
                _live_stage(f"إجابة غير صالحة — إعادة {attempt + 1}")
            except OllamaError as exc:
                last_exc = exc
                if not exc.retryable or attempt >= max_attempts:
                    self.last_error = str(exc)
                    _live_finish(error=str(exc))
                    raise
                _live_stage(f"تعذّر — إعادة {attempt + 1}")
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                self.last_error = str(exc)[:200]
                _live_finish(error=str(exc)[:200])
                raise OllamaError(str(exc), retryable=False) from exc

        _live_finish(error=str(last_exc or "unknown error"))
        raise OllamaError(str(last_exc or "unknown error"))

    def health(self) -> dict[str, Any]:
        from .health import check_ollama_health
        h = check_ollama_health(self._local, http_get=self._http_get)
        return {
            "healthy": h.get("ollama_reachable", False) and h.get("enabled", False),
            "provider_id": "ollama",
            "model_name": self.model_name(),
            "ollama_reachable": h.get("ollama_reachable", False),
            "model_available": h.get("model_available", False),
            "enabled": self._local.local_enabled and self._local.ollama_enabled,
            "base_url": self.base_url(),
            "last_error": self.last_error,
            "provider_version": PROVIDER_VERSION,
            "mode": "local",
        }

    def test_connection(self) -> dict[str, Any]:
        from .health import test_ollama_connection
        return test_ollama_connection(self._local, http_get=self._http_get)

    def list_models(self) -> list[str]:
        try:
            data = self._http_get(f"{self.base_url()}/api/tags")
            models = data.get("models") or []
            return [m.get("name", "") for m in models if m.get("name")]
        except Exception:  # noqa: BLE001
            return []

    def _chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._http_post:
            return self._http_post(f"{self.base_url()}/api/chat", payload)
        # البثّ المتدفّق حين تكون هناك محادثة حيّة مفتوحة: المستخدم يرى
        # الإجابة تُبنى بدل انتظار 116 ثانية أمام شاشة صامتة. وإن تعذّر
        # لأي سبب نعود إلى الطلب الدفعي — الرؤية تحسين لا شرط عمل.
        try:
            from scanner.ai_advisor import live_channel

            if live_channel.snapshot().get("active"):
                return self._chat_streaming(payload)
        except Exception:  # noqa: BLE001
            pass
        return self._http_post_json(f"{self.base_url()}/api/chat", payload)

    def _chat_streaming(self, payload: dict[str, Any]) -> dict[str, Any]:
        """يقرأ إجابة Ollama سطراً سطراً ويبثّها إلى القناة الحيّة.

        Ollama يُرجع مع ``stream: true`` سطر JSON لكل جزء. والقراءة
        بـ ``readline`` لا ``read()`` هي بيت القصيد: الثانية تنتظر
        اكتمال الاستجابة كلها فتُلغي الغرض.

        الحمولة المعادة بنفس شكل الطلب الدفعي، فبقية السلسلة (التحليل
        والتحقق والتسجيل) لا تعرف أن شيئاً تغيّر.
        """
        from scanner.ai_advisor import live_channel

        from .http import open_stream

        start = time.monotonic()
        parts: list[str] = []
        final: dict[str, Any] = {}
        # عبر ``http.open_stream`` لا ``urlopen`` مباشرةً: الأخير يمرّر
        # 127.0.0.1 عبر البروكسي المضبوط فيفشل بينما الخدمة تعمل
        with open_stream(f"{self.base_url()}/api/chat",
                         {**payload, "stream": True},
                         timeout=self._config.timeout) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                piece = ((row.get("message") or {}).get("content")
                         or row.get("response") or "")
                if piece:
                    parts.append(piece)
                    live_channel.append(piece)
                if row.get("done"):
                    final = row
        text = "".join(parts)
        out = dict(final)
        out.setdefault("message", {})
        out["message"] = {**(final.get("message") or {}), "content": text}
        out["_latency_ms"] = round((time.monotonic() - start) * 1000, 1)
        return out

    def _http_get(self, url: str) -> dict[str, Any]:
        from .http import get_json

        return get_json(url, timeout=self._config.timeout)

    def _http_post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        from .http import post_json

        start = time.monotonic()
        try:
            # نفس السبب: تجاوز البروكسي للعناوين المحلية
            return post_json(url, payload, timeout=self._config.timeout)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:200]
            retryable = exc.code in (429, 502, 503, 504)
            raise OllamaError(f"HTTP {exc.code}: {detail}", retryable=retryable) from exc
        except urllib.error.URLError as exc:
            raise OllamaError(f"Ollama unreachable: {exc.reason}", retryable=False) from exc

    @staticmethod
    def _extract_text(raw: dict[str, Any]) -> str:
        msg = raw.get("message") or {}
        if isinstance(msg, dict) and msg.get("content"):
            text = str(msg["content"])
        elif raw.get("response"):
            text = str(raw["response"])
        else:
            text = ""
        # Strip Qwen3 thinking blocks if present
        think_close = "</" + "think" + ">"
        if think_close in text:
            text = text.split(think_close, 1)[-1]
        return text.strip()

    def _parse_json(self, text: str) -> dict[str, Any]:
        if self._config.strict_json:
            return self._parser.parse(text)
        try:
            return self._parser.parse(text)
        except ResponseParseError:
            return json.loads(text.strip())

    @staticmethod
    def _extract_usage(raw: dict[str, Any]) -> dict[str, Any]:
        prompt = int(raw.get("prompt_eval_count") or 0)
        completion = int(raw.get("eval_count") or 0)
        return {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
            "latency_ms": raw.get("_latency_ms"),
        }


def _live_stage(name: str) -> None:
    """تسجيل مرحلة في القناة الحيّة — يبتلع أي فشل.

    الرؤية ميزة مرافقة: لو أسقطت المراجعة لكانت أضرّ من غيابها.
    """
    try:
        from scanner.ai_advisor import live_channel

        live_channel.stage(name)
    except Exception:  # noqa: BLE001
        pass


def _live_finish(*, answer: str = "", error: str = "") -> None:
    try:
        from scanner.ai_advisor import live_channel

        live_channel.finish(answer=answer, error=error)
    except Exception:  # noqa: BLE001
        pass
