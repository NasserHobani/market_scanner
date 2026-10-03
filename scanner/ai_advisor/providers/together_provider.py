# -*- coding: utf-8 -*-
"""‏Together AI — ‏gpt-oss-120b، عند الطلب وحده.

═══ لماذا هذا المزوّد ═══

‏Claude مزوّدٌ ممتاز وغالٍ، والمحلّي (Ollama) مجّانيٌّ ومحدود.
و‏gpt-oss-120b عند Together بينهما: نموذجٌ مفتوح الأوزان بمئة
وعشرين مليار معامل، بسعرٍ أقلّ بمراتب من النماذج المغلقة.

═══ وشرطُ «عند الطلب فقط» يُحرَس بثلاثة ═══

    ١. لا يُسجَّل مزوّداً افتراضياً — يُطلب بمعرّفه صراحةً
    ٢. سقفٌ ماليّ يُفحَص **قبل** الإرسال (``spend.check_budget``)
    ٣. فحصٌ بنيويّ يمنع استيراده من ``cron.py`` وأيّ معالج مهمّة

والثالث هو المهمّ: «لن أناديه في حلقة» نيّةٌ يكسرها سطرٌ واحد
بعد أشهر. والفحص يسقط حينها.

═══ والواجهة متوافقة مع OpenAI ═══

‏Together يقدّم ‎/v1/chat/completions‎ بالصيغة نفسها. فلا حاجة
لمكتبةٍ جديدة: ``urllib`` يكفي، ولا تدخل الصورة حزمةٌ أخرى.

═══ والوحدات تُقرأ من الردّ لا تُخمَّن ═══

‏``usage`` في الردّ يحمل العدد الحقيقيّ. وتقديرُه بعدّ الحروف يخطئ
بثلاثين بالمئة على العربية — ويُقرأ كأنّه دقيق.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from .. import spend
from ..decision_package import DecisionPackage
from ..prompt_builder import AdvisorPrompt
from .base import LLMProvider, ProviderMetadata

PROVIDER_ID = "together"
PROVIDER_VERSION = "1.0.0"

#: المضيفان — الأوّل هو المعلن، والثاني يبقى عاملاً
HOSTS = ("https://api.together.xyz", "https://api.together.ai")
DEFAULT_MODEL = "openai/gpt-oss-120b"

KEY_VARS = ("TOGETHER_API_KEY", "TOGETHERAI_API_KEY")

#: سقفٌ للمخرَجات — حارسٌ ثانٍ للتكلفة بعد السقف الماليّ
DEFAULT_MAX_TOKENS = 1200


class TogetherError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


def api_key() -> str:
    for name in KEY_VARS:
        v = os.environ.get(name, "").strip()
        if v:
            return v
    return ""


def configured() -> bool:
    return bool(api_key())


def model_id() -> str:
    return os.environ.get("TOGETHER_MODEL", "").strip() or DEFAULT_MODEL


def _rough_tokens(text: str) -> int:
    """تقديرٌ **قبليّ** للوحدات — للسقف وحده لا للفوترة.

    نحو أربعة حروفٍ للوحدة في الإنجليزية، وأقلّ في العربية. وهو
    تقديرٌ خشن مقصود: وظيفته منع نداءٍ ضخمٍ قبل إرساله، والعدد
    الحقيقيّ يأتي من ``usage`` بعد الردّ.
    """
    return max(1, int(len(text) / 3))


class TogetherProvider(LLMProvider):
    """مزوّدٌ يُنادى بزرّ — لا من جدولةٍ ولا من رسم صفحة."""

    def __init__(self) -> None:
        self._healthy = False
        self._last_error = ""
        self._last_latency: float | None = None
        self._calls = 0

    @property
    def provider_id(self) -> str:
        return PROVIDER_ID

    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider_id=PROVIDER_ID,
            display_name="Together · gpt-oss-120b",
            vendor="Together AI",
            model_family="gpt-oss",
            supports_json=True,
            description=("نموذجٌ مفتوح الأوزان عبر Together. يُنادى عند "
                         "الطلب وحده، وبسقفٍ ماليّ يُفحَص قبل الإرسال."),
        )

    def model_name(self) -> str:
        return model_id()

    # ── النداء ──────────────────────────────────────────────

    def complete(self, system: str, user: str, *, purpose: str = "",
                 max_tokens: int = DEFAULT_MAX_TOKENS,
                 temperature: float = 0.2,
                 json_mode: bool = True) -> dict[str, Any]:
        """نداءٌ واحد — ويعيد النصّ مع تكلفته المسجَّلة.

        هذه هي الواجهة المباشرة. و``analyze`` تبني عليها لتوافق
        بقيّة المزوّدين.
        """
        key = api_key()
        if not key:
            raise TogetherError(
                "مفتاح Together غير مضبوط. أنشئه من api.together.ai ← "
                "Settings ← API Keys، وأضفه في بورتينر ← Environment "
                "variables: TOGETHER_API_KEY.")

        model = model_id()
        # ═══ السقف قبل الإرسال ═══
        est_in = _rough_tokens(system) + _rough_tokens(user)
        spend.check_budget(model, est_in, max_tokens)

        body = {
            "model": model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "max_tokens": int(max_tokens),
            "temperature": float(temperature),
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "market-scanner/0.1",
        }

        start = time.monotonic()
        last = ""
        for host in HOSTS:
            req = urllib.request.Request(
                f"{host}/v1/chat/completions", data=payload,
                headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                detail = ""
                try:
                    detail = exc.read().decode("utf-8")[:240]
                except Exception:  # noqa: BLE001
                    pass
                if exc.code in (401, 403):
                    raise TogetherError(
                        f"رفض Together المفتاح ({exc.code}). تحقّق أنّه "
                        f"صحيح وأنّ للحساب رصيداً. [{detail}]") from exc
                if exc.code == 429:
                    raise TogetherError(
                        "تجاوزتَ حدّ الطلبات عند Together — انتظر قليلاً.",
                        retryable=True) from exc
                last = f"{exc.code}: {detail}"
            except (urllib.error.URLError, OSError, ValueError) as exc:
                last = f"{type(exc).__name__}: {str(exc)[:120]}"
        else:
            self._healthy = False
            self._last_error = last
            raise TogetherError(f"تعذّر الوصول إلى Together — {last}",
                                retryable=True)

        latency = (time.monotonic() - start) * 1000.0
        text = ""
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            pass

        # ═══ الوحدات من الردّ ═══
        usage = data.get("usage") or {}
        t_in = int(usage.get("prompt_tokens") or est_in)
        t_out = int(usage.get("completion_tokens") or _rough_tokens(text))

        row = spend.record(provider=PROVIDER_ID, model=model,
                           tokens_in=t_in, tokens_out=t_out,
                           purpose=purpose, latency_ms=latency,
                           ok=bool(text))
        self._healthy = bool(text)
        self._last_latency = latency
        self._calls += 1
        if not text:
            self._last_error = "ردٌّ بلا محتوى"
            raise TogetherError("ردّ Together بلا محتوى")

        return {"text": text, "usage": row, "latency_ms": round(latency),
                "model": model}

    # ── توافق واجهة المزوّدين ────────────────────────────────

    def analyze(self, prompt: AdvisorPrompt, *,
                package: DecisionPackage) -> dict[str, Any]:
        out = self.complete(
            getattr(prompt, "system", "") or "",
            getattr(prompt, "user", "") or str(prompt),
            purpose=f"advisor:{getattr(package, 'event_id', '')}"[:60])
        text = out["text"]
        try:
            return json.loads(text)
        except ValueError:
            # ═══ النصّ لا يُرمى ═══
            #
            # ردٌّ غير صالحٍ JSON كلّفك مالاً فعلاً. وإخفاؤه يعني
            # أنّك دفعت ولم ترَ شيئاً.
            return {"_raw": text, "_parse_error": True,
                    "_usage": out["usage"]}

    def health(self) -> dict[str, Any]:
        s = spend.summary()
        return {
            "healthy": self._healthy,
            "configured": configured(),
            "model": self.model_name(),
            "latency_ms": self._last_latency,
            "calls": self._calls,
            "last_error": self._last_error,
            "spend": s,
            "provider_version": PROVIDER_VERSION,
        }


def create_together_provider() -> TogetherProvider:
    return TogetherProvider()
