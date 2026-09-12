# -*- coding: utf-8 -*-
"""‏CompactAnalystContext — ما يراه المحلّل، لا ما تعرفه المنصّة.

═══ الفكرة ═══

الحزمة الموحّدة (‏UDP) تبقى مرجع المنصّة الكامل: التتبّع والتدقيق
والأدلّة والحفظ. وهذا صحيح ولا يُمَسّ.

لكنّ إرسالها كما هي إلى النموذج خلط بين غرضين: التوثيق شيء، والإحاطة
شيء آخر. المدقّق يريد كل شيء؛ المحلّل يريد ما يغيّر رأيه.

فهذا الكائن هو **الإحاطة**: حقائق مختارة، بلا فراغات، بلا تكرار، وبلا
تفاصيل داخلية لا تُغيّر حكماً.

═══ لماذا نصّ عربي لا JSON ═══

كتلة ``JSON`` بمسافات كانت 62٪ من الموجّه، وثلثها أقواس وعلامات اقتباس
ومفاتيح مكرّرة — رموز تُدفَع مرّتين: في القراءة، وفي التوليد الأبطأ
الذي يليها.

والنموذج يقرأ سطراً عربياً واضحاً أفضل مما يقرأ شجرة JSON متداخلة،
لأن السطر يحمل المعنى بلا أن يستنتج البنية.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = ["CompactAnalystContext", "EvidenceItem", "ANALYST_CONTEXT_VERSION"]

ANALYST_CONTEXT_VERSION = "1.0.0"

# صياغات الغياب. تُكتب صراحةً ولا تُحذف: «غير متاح» حقيقة عالية القيمة
# للمحلّل، بينما الحقل المحذوف يجعله يفترض أن الأمر لم يُفحص.
UNAVAILABLE = "غير متاح"


@dataclass(frozen=True)
class EvidenceItem:
    """حقيقة مفردة بمعرّفها — المعرّف هو ما يُتحقّق منه لاحقاً."""

    evidence_id: str
    fact: str
    priority: int = 50          # الأدنى يُحذف أولاً

    def render(self) -> str:
        return f"[{self.evidence_id}] {self.fact}"


@dataclass
class CompactAnalystContext:
    symbol: str = ""
    market: str = ""
    timeframe: str = ""

    # نوع الطلب: مراجعة قرار قائم، أم تحليل سوق مبتدأ؟
    #
    # التمييز ضروري: حين تكون خطة المنصّة ``action=analysis`` بلا اتجاه
    # ولا ثقة، فليس هناك قرار **يُراجَع**. ومطالبة النموذج بالموافقة أو
    # المخالفة حينها تدفعه إلى اختراع قرار لم يصدر.
    analysis_type: str = "trade_review"    # أو "market_analysis"

    platform: dict[str, Any] = field(default_factory=dict)
    market_state: dict[str, Any] = field(default_factory=dict)
    historical: dict[str, Any] = field(default_factory=dict)
    research: dict[str, Any] = field(default_factory=dict)
    prediction: dict[str, Any] = field(default_factory=dict)
    features: dict[str, Any] = field(default_factory=dict)
    risk: dict[str, Any] = field(default_factory=dict)
    data_quality: dict[str, Any] = field(default_factory=dict)
    contradictions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    evidence: list[EvidenceItem] = field(default_factory=list)

    # مفتاح السياق ← معرّف الدليل. يُلحَق بالسطر نفسه.
    #
    # ═══ لماذا داخل السطر ═══
    #
    # الحقيقة إمّا أن تُذكر في المتن وتُعاد في قائمة الأدلّة — فيقرأها
    # النموذج مرّتين ويدفع رموزها مرّتين — وإمّا أن تُذكر مرّة ويضيع
    # معرّفها فلا يستطيع الاستشهاد بها.
    #
    # والمخرج أن يُلصَق المعرّف بالحقيقة: «الاتجاه: صاعد [ev_011]».
    # كلفته أربعة رموز، ويُبقي الاستشهاد ممكناً والتحقّق الخادمي قائماً.
    inline_ids: dict[str, str] = field(default_factory=dict)

    profile: str = "STANDARD"
    fingerprint: str = ""
    version: str = ANALYST_CONTEXT_VERSION
    dropped_sections: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    # ───────────────────────────────────────────── العرض

    def render(self) -> str:
        """السياق كنصّ عربي مضغوط — هذا ما يصل النموذج."""
        out: list[str] = []
        head = f"## الرمز: {self.symbol} · السوق: {self.market} · الفريم: {self.timeframe}"
        out.append(head)

        if self.analysis_type == "market_analysis":
            out.append(
                "## نوع الطلب\n"
                "تحليل سوق مبتدأ — المنصّة **لم تُصدر** توصية شراء أو بيع. "
                "لا توافق قراراً ولا تخالفه؛ حلّل الوضع الراهن."
            )

        # جودة البيانات أولاً حين تكون منخفضة: ما بعدها يُقرأ على ضوئها
        dq = self._render_data_quality()
        if dq and self.data_quality.get("degraded"):
            out.append(dq)

        for title, body in (
            ("قرار المنصّة", self._render_platform()),
            ("حالة السوق", self._render_market()),
            ("النموذج الإحصائي", self._render_prediction()),
            ("السوابق التاريخية", self._render_historical()),
            ("البحث", self._render_research()),
            ("ذكاء الخصائص", self._render_features()),
            ("المخاطر", self._render_risk()),
        ):
            if body:
                out.append(f"## {title}\n{body}")

        if dq and not self.data_quality.get("degraded"):
            out.append(dq)

        if self.contradictions:
            out.append("## تناقضات\n" + "\n".join(f"- {c}" for c in self.contradictions))

        if self.evidence:
            out.append("## الأدلّة\n"
                       + "\n".join(e.render() for e in self.evidence))

        if self.dropped_sections:
            out.append("## ملاحظة\nأقسام لم تُرسَل لضيق السياق: "
                       + "، ".join(self.dropped_sections)
                       + " — عاملها «غير متاحة» ولا تفترض محتواها.")

        if self.notes:
            out.extend(self.notes)

        return "\n\n".join(out)

    # ───────────────────────────────────────────── أقسام العرض

    @staticmethod
    def _fmt(value: Any) -> str:
        """عرض عربي — بلا ``repr`` بايثوني في وجه القارئ."""
        if isinstance(value, (list, tuple)):
            return "، ".join(str(v) for v in value)
        if isinstance(value, dict):
            return "، ".join(f"{k}={v}" for k, v in value.items())
        if isinstance(value, float):
            return f"{value:.4g}"
        return str(value)

    def _kv(self, pairs: list[tuple[str, Any]],
            keys: list[str] | None = None) -> str:
        bits = []
        for i, (label, value) in enumerate(pairs):
            if value is None or value == "" or value == []:
                continue
            tag = ""
            if keys and i < len(keys):
                eid = self.inline_ids.get(keys[i], "")
                tag = f" [{eid}]" if eid else ""
            bits.append(f"{label}: {self._fmt(value)}{tag}")
        return " · ".join(bits)

    def _render_platform(self) -> str:
        p = self.platform
        if not p:
            return ""
        if self.analysis_type == "market_analysis":
            return "لا توصية تداول قائمة — الطلب تحليل وضع راهن."
        return self._kv([
            ("القرار", p.get("action")), ("الاتجاه", p.get("direction")),
            ("الدرجة", p.get("score")), ("الثقة", p.get("confidence")),
            ("التصنيف", p.get("grade")), ("العائد/المخاطرة", p.get("rr")),
            ("الدخول", p.get("entry")), ("الوقف", p.get("stop")),
        ], ["platform.action", "platform.direction", "platform.score",
            "platform.confidence", "platform.grade", "platform.rr",
            "platform.entry", "platform.stop"])

    def _render_market(self) -> str:
        m = self.market_state
        return self._kv([
            ("الاتجاه", m.get("trend")), ("قوّته", m.get("trend_strength")),
            ("النظام", m.get("regime")), ("الهيكل", m.get("structure")),
            ("الزخم", m.get("momentum")), ("الحجم", m.get("volume")),
            ("التقلّب", m.get("volatility")),
            ("أنماط", m.get("patterns")), ("معالم", m.get("facts")),
        ], ["market_state.trend", "market_state.trend_strength",
            "market_state.regime", "market_state.structure",
            "market_state.momentum", "market_state.volume",
            "market_state.volatility", "market_state.patterns",
            "market_state.facts"])

    def _render_prediction(self) -> str:
        p = self.prediction
        if not p or not p.get("available"):
            reason = (p or {}).get("reason") or "لا نموذج اجتاز بوابة الجودة"
            return (f"{UNAVAILABLE} — {reason}. "
                    "لا تذكر احتمالاً رقمياً ولا تشتقّه.")
        return self._kv([
            ("النموذج", p.get("model")),
            ("احتمال النجاح", p.get("probability_win")),
            ("المعايرة", p.get("calibration")),
            ("خارج العيّنة", p.get("oos")),
            ("خطّ الأساس", p.get("baseline")),
        ]) + "\n(قيّمه كدليل؛ لا تعدّل الرقم.)"

    def _render_historical(self) -> str:
        h = self.historical
        if not h:
            return ""
        if not h.get("matches"):
            return f"{UNAVAILABLE} — لا حالات مشابهة موثوقة."
        return self._kv([
            ("حالات مشابهة", h.get("matches")),
            ("درجة التشابه", h.get("similarity_score")),
            ("نسبة النجاح", h.get("win_rate")),
            ("التوقّع (R)", h.get("expectancy")),
            ("كفاية العيّنة", h.get("sample_note")),
        ], ["historical.matches", "historical.similarity_score",
            "historical.win_rate", "historical.expectancy", ""])

    def _render_research(self) -> str:
        r = self.research
        if not r or not r.get("available"):
            return f"{UNAVAILABLE} — {(r or {}).get('reason') or 'لا نتائج مُصادَق عليها'}."
        findings = r.get("findings") or []
        body = self._kv([("الثقة", r.get("confidence"))])
        if findings:
            body += "\n" + "\n".join(f"- {f}" for f in findings)
        return body

    def _render_features(self) -> str:
        f = self.features
        if not f or not f.get("available"):
            return ""
        return self._kv([
            ("أهمّ الخصائص", "، ".join(f.get("top") or [])),
            ("الثبات", f.get("stability")), ("الانجراف", f.get("drift")),
            ("تنبيهات", "، ".join(f.get("warnings") or [])),
        ])

    def _render_risk(self) -> str:
        keys = self.risk.get("key_risks") or []
        return "\n".join(f"- {r}" for r in keys) if keys else ""

    def _render_data_quality(self) -> str:
        d = self.data_quality
        if not d:
            return ""
        body = self._kv([
            ("التغطية", d.get("coverage")), ("الجودة", d.get("quality")),
            ("الخصائص", d.get("feature_count")),
            ("غائب", "، ".join(d.get("missing") or [])),
        ], ["data_quality.coverage", "data_quality.quality",
            "data_quality.feature_count", ""])
        if not body:
            return ""
        head = "## جودة البيانات"
        if d.get("degraded"):
            head = "## ⚠ تحذير جودة البيانات"
            body += ("\n**جودة البيانات منخفضة جدًا، لذلك لا يمكن بناء "
                     "توصية موثوقة.** إن لم تكفِ الأدلّة فاختر "
                     "`insufficient` بدل الترجيح بين الموافقة والمخالفة.")
        return f"{head}\n{body}"

    # ───────────────────────────────────────────── مساعدات

    def evidence_map(self) -> dict[str, str]:
        """معرّف الدليل ← الحقيقة. للتحقّق من الاستشهاد خادميّاً."""
        return {e.evidence_id: e.fact for e in self.evidence}

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol, "market": self.market,
            "timeframe": self.timeframe, "analysis_type": self.analysis_type,
            "platform": self.platform, "market_state": self.market_state,
            "historical": self.historical, "research": self.research,
            "prediction": self.prediction, "features": self.features,
            "risk": self.risk, "data_quality": self.data_quality,
            "contradictions": list(self.contradictions),
            "evidence": [{"id": e.evidence_id, "fact": e.fact}
                         for e in self.evidence],
            "profile": self.profile, "fingerprint": self.fingerprint,
            "version": self.version,
            "dropped_sections": list(self.dropped_sections),
            "metrics": dict(self.metrics),
        }
