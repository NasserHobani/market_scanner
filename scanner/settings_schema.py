# -*- coding: utf-8 -*-
"""تعريف تصريحي لإعدادات الماسح — مستقلّ عن Django.

لماذا مخطط بدل حقول مكتوبة يدوياً في القالب:

كل إعداد له اسم وحدّ ووصف ونوع. لو تفرّقت هذه على ثلاثة أماكن — نموذج
وقالب وعرض — لانحرفت مع أول تعديل، فيظهر حقل بلا تحقق أو تحقق بلا حقل.
هنا مصدر واحد يُبنى منه العرض والتحقق معاً، ويُختبر بلا Django ولا
متصفّح.

والقيم كلها لها افتراض معقول، فالإعدادات تحسين لا شرط تشغيل.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from scanner.ai_advisor.models_catalog import (
    claude_model_choices,
    default_claude_model,
    ollama_model_choices,
    provider_choices,
    resolve_ollama_model,
)
from scanner.ai_local.config import EXECUTION_MODES
from scanner.ai_advisor.prompt_builder import PromptBuilder

_AI_PROMPT_CHOICES = tuple((v, v) for v in PromptBuilder().list_versions())


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    kind: str                     # int / float / bool / choice / text
    default: Any
    help: str = ""
    minimum: float | None = None
    maximum: float | None = None
    unit: str = ""
    choices: tuple[tuple[str, str], ...] = ()
    step: float | None = None


@dataclass(frozen=True)
class Group:
    key: str
    title: str
    note: str = ""
    fields: tuple[Field, ...] = field(default_factory=tuple)


GROUPS: tuple[Group, ...] = (
    Group(
        key="liquidity",
        title="السيولة",
        note="حجم التداول اليومي بالدولار. إشارة على زوج حجمه مئات الآلاف "
             "ليست كإشارة على زوج بمئات الملايين — أمر واحد كبير يحرّك "
             "الأول، والانزلاق عند التنفيذ قد يبتلع الربح المتوقّع كله. "
             "الفئات هنا تحذير مرافق للإشارة لا حكم عليها.",
        fields=(
            Field("min_quote_volume", "أدنى حجم لدخول المسح", "float",
                  5_000_000,
                  "الرموز دون هذا الحجم لا تُجلب أصلاً.\n\n"
                  "رُفع من 200 ألف بعد قياس صريح: عند 200 ألف يدخل 495 "
                  "رمزاً من 496 — أي بلا ترشيح فعلي — وزمن التحليل ~55 "
                  "ثانية. وعند 5 ملايين يبقى 71 رمزاً و~8 ثوانٍ.\n\n"
                  "ولا يُقال إنه يزيد الربح: قِيس التوقّع الصافي عند كل "
                  "أرضية (200 ألف · مليون · 5 ملايين · 20 مليوناً) فبقي "
                  "سالباً عند الجميع بين ‎−0.29R‎ و‎−0.38R‎. القيد ليس "
                  "السيولة بل ضيق الوقف نسبةً إلى التكلفة، وهو موجود في "
                  "كل الفئات. فهذا إعداد **سرعة** لا إعداد ربح.",
                  minimum=0, maximum=1_000_000_000, unit="$"),
            Field("tier_high", "حدّ السيولة العالية", "float", 50_000_000,
                  "فوقه تُعدّ السيولة عالية.", minimum=0,
                  maximum=1_000_000_000, unit="$"),
            Field("tier_mid", "حدّ السيولة المتوسطة", "float", 5_000_000,
                  "فوقه متوسطة، دونه منخفضة.", minimum=0,
                  maximum=1_000_000_000, unit="$"),
            Field("tier_low", "حدّ السيولة المنخفضة", "float", 1_000_000,
                  "دونه تُعدّ السيولة دقيقة ويظهر تحذير.", minimum=0,
                  maximum=1_000_000_000, unit="$"),
        ),
    ),
    Group(
        key="scan",
        title="المسح",
        note="الجلب تراكمي: لا يُعاد تنزيل التاريخ إلا لرمز جديد أو بعد "
             "انقطاع طويل.",
        fields=(
            Field("workers", "طلبات متوازية", "int", 12,
                  "للشبكة فقط — التحليل يجري في خيط واحد لأن تشغيله داخل "
                  "الخيوط قيس أبطأ (pandas مقيّد بـ GIL).",
                  minimum=1, maximum=32),
            Field("top_n", "أقصى عدد رموز", "int", 150,
                  "الرموز مرتّبة بحجم التداول، فالحدّ يُبقي الأكثر سيولة. "
                  "0 يعني بلا حدّ — وهو ما كان مضبوطاً، فيصير المسح "
                  "مفتوحاً بلا سقف مهما نمت المنصّة. السقف هنا حارس "
                  "ثانٍ بعد أرضية السيولة: الأرضية تُصفّي بالجودة "
                  "والسقف يضمن ألّا يطول المسح إن هبطت الأحجام عموماً.",
                  minimum=0, maximum=5000),
            Field("require_htf", "فلتر الفريم الأعلى", "bool", True,
                  "يمنع الشراء حين يكون الاتجاه الأكبر هابطاً، ويضيف وزناً "
                  "حين يكون صاعداً. القياس على 230 صفقة أعطاه أسوأ توقّع "
                  "بين العوامل الثمانية (‏−0.20R على 157 صفقة) — أي أنه "
                  "يضرّ لا ينفع على هذه البيانات. جرّب إطفاءه وقارن."),
            Field("candles", "شموع التاريخ", "int", 1500,
                  "للرمز الجديد فقط. فلتر الفريم الأعلى يحتاج تاريخاً "
                  "كافياً؛ دون 800 شمعة يتعطّل ويُحجب معظم الإشارات.",
                  minimum=300, maximum=5000),
            Field("max_pair_corr", "أقصى ارتباط بين صفقتين متزامنتين",
                  "float", 0.55,
                  "المرشّح الذي يرتبط بمقبولٍ فوق هذا الحدّ يُسقط: هو "
                  "يكرّره لا يضيف إليه.\n\n"
                  "القياس على 352 رمزاً: الارتباط الوسيط بالبتكوين "
                  "‎+0.46‎، و42٪ فوق 0.50. وعند 0.46 يكون عشرون مركزاً "
                  "مفتوحاً مكافئاً لـ **2.05 رهاناً مستقلاً** بمخاطرة "
                  "‎×3.12‎ — أي أن من يظنّ أنه يخاطر بـ ‎1R‎ عشرين مرة "
                  "يخاطر بما يقارب ‎6R‎ على حركة واحدة.\n\n"
                  "0 يعطّل الترشيح. والرمز الذي لا يُعرف ارتباطه يُقبل "
                  "— الرفض عقوبة على نقص بيانات لا على تشابه.",
                  minimum=0, maximum=1, step=0.05),
            Field("max_new_trades", "أقصى صفقات من مسح واحد", "int", 3,
                  "فُتحت سبع صفقات في لحظة واحدة على 15m فخسرت خمس معاً. "
                  "سبعة رموز في سوق واحد ولحظة واحدة ليست سبع عيّنات بل "
                  "عيّنة واحدة — تتحرّك معاً وتُحسم معاً، فتبدو الإحصاءات "
                  "حاسمة وهي ضجيج، وتضرب الخسارة رأس المال دفعة واحدة. "
                  "يُطبَّق على التوصيات والاختراقات كلٍّ على حدة، والمختار "
                  "هو الأعلى تصنيفاً. 0 يعني بلا حدّ.",
                  minimum=0, maximum=50),
            Field("ml_vote_enabled", "تفعيل تصويت النموذج", "bool", False,
                  "يُضاف كوزن مستقل فقط بعد نجاح تقييم OOS في ملف النموذج."),
            Field("sync_timeframes", "فريمات المزامنة لكل سوق", "text", "",
                  "ما يُجلَب من المنصّة — لا ما يُمسح. "
                  "المزامنة تجلب أربعة فريمات لكل سوق افتراضياً: "
                  "‎15m, 1h, 4h, 1d‎. وهي عدد الرموز × أربعة — ٥٣٠ رمز "
                  "كريبتو تصير ٢٬١٢٠ طلباً في الدورة الواحدة، على جدولٍ "
                  "مُشبَعٍ أصلاً.\n\n"
                  "الصيغة: سوق=فريمات، والفريمات بفواصل، والأسواق "
                  "بمسافةٍ أو سطرٍ أو نقطة — الثلاثة سواء:\n"
                  "    crypto=4h,1d saudi=1d gold=4h,1d\n\n"
                  "والسوق غير المذكور يبقى على الأربعة. وما يُمسح "
                  "يُزامَن دائماً ولو لم يُذكر هنا — إسقاطه يعني سوقاً "
                  "يُمسح بلا شموع: صفر نتائج بلا خطأ."),
            # ═══ والمسح إعدادٌ آخر ═══
            #
            # كان فريم المسح في ``config/<سوق>.yaml`` وحده. فمن أضاف
            # ‎1h‎ إلى فريمات المزامنة ثمّ ضغط «١ ساعة» في شاشة المسح
            # أعادته الشاشة إلى ‎4h‎: لا جولة مسحٍ على ‎1h‎ قطّ،
            # فالشاشة تستبدل بأحدث ما مُسح فعلاً.
            #
            # والعلاج ليس تعطيل الاستبدال — بل أن يصير الفريم قابلاً
            # للتفعيل من الشاشة نفسها.
            Field("scan_timeframes", "فريمات المسح لكل سوق", "text", "",
                  "ما يُمسح ويُعرض في شاشة المسح. الصيغة نفسها:\n"
                  "    crypto=4h,1h us=1d gold=4h,1d\n\n"
                  "والسوق غير المذكور يبقى على ما في "
                  "‎config/<سوق>.yaml‎. وكل فريمٍ يُضاف هنا يُزامَن "
                  "تلقائياً.\n\n"
                  "والثمن صريح: المسح يعيد تحليل كل رموز السوق على كل "
                  "فريمٍ مذكور. ففريمان يعنيان ضعف زمن الدورة — و‎15m‎ "
                  "على ٥٣٠ رمزاً دورةٌ لا تنتهي قبل أن تبدأ التالية."),
        ),
    ),
    Group(
        key="breakout",
        title="تنبيه الاختراق",
        note="رصد الشمعة الأولى من حركة عنيفة — تنبيه لا توصية. أول خمس "
             "صفقات حيّة خسرت كلها، فتبيّن أن السبب الوقف لا الإشارة: "
             "كان يُقاس بمتوسط أربع عشرة شمعة ويُطبَّق على سوق ضاعف "
             "الانفجار تقلّبه عشر مرات، فيقع داخل الضجيج. وبعد تصحيحه "
             "صار التوقّع صفراً على 2893 اختراقاً في ثلاثة فريمات — "
             "لا نزف ولا أفضلية. فهو تنبيه حركة، لا يُتداول وحده.",
        fields=(
            Field("enabled", "تشغيل التنبيه", "bool", True,
                  "إطفاؤه يوقف الرصد والتسجيل معاً."),
            Field("min_rvol", "أدنى حجم نسبي", "float", 8.0,
                  "مضاعف الحجم مقارنة بمتوسط 20 شمعة. خفضه يزيد "
                  "الإنذارات الكاذبة بسرعة.", minimum=1.5, maximum=20,
                  step=0.5),
            Field("lookback", "قمة كم شمعة تُخترق", "int", 20,
                  "المدى الذي يجب تجاوزه ليُعدّ اختراقاً.",
                  minimum=5, maximum=200),
            Field("stop_atr", "الوقف بوحدات ATR", "float", 1.5,
                  "حدّ أدنى لا أكثر: الوقف الفعلي هو الأوسع بين هذا وبين "
                  "قاع شمعة الاختراق ناقص 10٪ من مداها. رفع هذا الرقم "
                  "يوسّع الوقف في الحالات الهادئة فقط؛ أما بعد الانفجار "
                  "فقاع الشمعة هو الحاكم لأنه يقيس التقلّب الجديد.",
                  minimum=0.5, maximum=6, step=0.25),
            Field("low_buffer", "هامش تحت قاع الشمعة", "float", 0.10,
                  "كسر من مدى شمعة الاختراق. الوقف عند القاع بالضبط "
                  "يُلمس كثيراً فيصير هدفاً لا حماية؛ وتوسيعه أكثر من "
                  "اللازم يجعل المخاطرة أكبر من أن تُبرَّر.",
                  minimum=0, maximum=1, step=0.05),
            Field("target_atr", "الهدف بوحدات ATR", "float", 3.0,
                  "يجب أن يتجاوز الوقف وإلا كانت المخاطرة أكبر من العائد.",
                  minimum=0.5, maximum=12, step=0.25),
            Field("min_body", "أدنى نسبة جسم الشمعة", "float", 0.35,
                  "جسم صغير بفتيل طويل يعني ارتداد السعر عن قمته داخل "
                  "الشمعة — اصطياد سيولة لا اختراق.",
                  minimum=0, maximum=1, step=0.05),
        ),
    ),
    Group(
        key="execution",
        title="نموذج التنفيذ",
        note="الكلفة نسبة ثابتة من السعر، والمخاطرة هي عرض الوقف — "
             "فحصّة الكلفة من المخاطرة تنفجر كلما ضاق الوقف. القياس على "
             "96 صفقة: الوقف دون 0.5% يعطي ‎+0.36R‎ إجمالياً و‎−3.75R‎ "
             "بعد التكلفة، والوقف فوق 4% يبقى ‎+0.29R‎ صافياً. الرسوم "
             "معلومة ومنشورة؛ الفارق والانزلاق تقديرات معلنة تُعاير "
             "بمقارنة سعر التنفيذ الفعلي بسعر الإشارة.",
        fields=(
            Field("maker_bps", "عمولة الأمر المحدَّد", "float", 10.0,
                  "بنقاط الأساس (‏10 = 0.1%). بينانس سبوت VIP0 = 0.1%، "
                  "ومع خصم BNB ≈ 7.5.", minimum=0, maximum=100, unit="ن.أ"),
            Field("taker_bps", "عمولة أمر السوق", "float", 10.0,
                  "الدخول «الآن» وضرب الوقف كلاهما أمر سوق.",
                  minimum=0, maximum=100, unit="ن.أ"),
            Field("slippage_scale", "مضاعف الانزلاق", "float", 1.0,
                  "1 = التقدير الأساسي (‏1 نقطة للسيولة العالية إلى 20 "
                  "للدقيقة). ارفعه لاختبار متانة النتيجة، أو اخفضه إن "
                  "قِست انزلاقك الفعلي وكان أقل.",
                  minimum=0, maximum=10, step=0.25),
            Field("max_cost_ratio", "أقصى كلفة كنسبة من المخاطرة", "float",
                  0.25,
                  "الخطة التي تتجاوز كلفتها هذه النسبة من وقفها تُرفض "
                  "قبل تسجيلها — خسارتها حسابية لا تحتاج انتظار السوق. "
                  "0 يعطّل البوّابة. الاستبعاد على العيّنة الحالية يحذف "
                  "نصف الخطط ويرفع التوقّع الصافي إلى ‎+0.45R‎.",
                  minimum=0, maximum=1, step=0.05),
        ),
    ),
    Group(
        key="alerts",
        title="التنبيهات",
        fields=(
            Field("telegram_watches", "تنبيه بلوغ سعر الدخول", "bool", True,
                  "يُرسل عند وصول السعر لنقطة دخول قرّرتها إشارة سابقة."),
            Field("telegram_breakouts", "تنبيه الحركة الحجمية", "bool", True,
                  "رسالة واحدة مجمّعة لكل مسح لا رسالة لكل رمز."),
            Field("settlement_seconds", "دورة حسم الصفقات", "int", 180,
                  "المدة بين محاولات حسم الصفقات الحيّة بالثواني. الحسم "
                  "مستقلّ عن المسح، فصفقة على فريم لا يمسحه المسح "
                  "التلقائي تُحسم أيضاً.", minimum=30, maximum=3600,
                  unit="ث"),
            Field("monitor_seconds", "دورة المراقبة", "int", 300,
                  "المدة بين فحوص الأسعار بالثواني. تقصيرها يزيد الطلبات "
                  "بلا تحسين الحسم — الحسم من الشموع لا من السعر اللحظي.",
                  minimum=60, maximum=3600, unit="ث"),
        ),
    ),
    Group(
        key="ai_advisor",
        title="مستشار الذكاء الاصطناعي",
        note="إعدادات مستشار الذكاء الاصطناعي في وضع الظل. المستشار يراجع "
             "القرارات فقط — لا يعدّل الاستراتيجية ولا ينفّذ صفقات. مفتاح "
             "API يُحمَّل من المتغير ANTHROPIC_API_KEY ولا يظهر هنا.",
        fields=(
            Field("ai_claude_enabled", "تفعيل Claude", "bool", True,
                  "تفعيل مزوّد Anthropic Claude للمراجعة الحية."),
            Field("ai_default_provider", "المزوّد الافتراضي", "choice", "claude",
                  "المزوّد المستخدم عند طلب مراجعة المستشار.",
                  choices=provider_choices()),
            Field("ai_claude_model", "نموذج Claude", "choice",
                  default_claude_model(),
                  "النموذج المستخدم — يُحمَّل من ملف التكوين وليس من الكود.",
                  choices=claude_model_choices()),
            Field("ai_temperature", "درجة الحرارة", "float", 0.2,
                  "0 = حتمي، 1 = إبداعي. للمراجعة يُفضَّل قيمة منخفضة.",
                  minimum=0, maximum=1, step=0.05),
            Field("ai_max_tokens", "أقصى رموز", "int", 4096,
                  "الحد الأقصى لطول الاستجابة.",
                  minimum=256, maximum=16384),
            Field("ai_timeout", "مهلة الانتظار", "float", 60.0,
                  "ثوانٍ قبل اعتبار الطلب منتهياً.",
                  minimum=5, maximum=300, unit="ث"),
            Field("ai_retry_count", "عدد إعادة المحاولة", "int", 2,
                  "إعادة المحاولة عند انقطاع مؤقت أو حد المعدّل فقط.",
                  minimum=0, maximum=5),
            Field("ai_shadow_mode", "وضع الظل", "bool", True,
                  "المستشار يراجع فقط — لا يغيّر قرارات المنصة."),
            Field("ai_memory_enabled", "تفعيل الذاكرة", "bool", True,
                  "حفظ سجل المراجعات للتدقيق."),
            Field("ai_evaluation_enabled", "تفعيل التقييم", "bool", True,
                  "قياس جودة المستشار بعد إغلاق الصفقات."),
            Field("ai_learning_enabled", "تفعيل التعلّم", "bool", True,
                  "تحويل التقييمات إلى دروس واقتراحات."),
            Field("ai_prompt_version", "إصدار الموجّه", "choice",
                  "advisor_prompt_v4",
                  "قالب الموجّه المستخدم للمراجعة.",
                  choices=_AI_PROMPT_CHOICES),
            Field("ai_strict_json", "JSON صارم", "bool", True,
                  "رفض أي استجابة ليست JSON صالحاً."),
            Field("ai_grounding_required", "التحقق من الأدلة", "bool", True,
                  "رفض المراجعات ذات الأدلة غير المؤسَّسة."),
            Field("ai_allow_experiments", "السماح بالتجارب المقترحة", "bool", True,
                  "السماح للمستشار باقتراح تجارب بحثية."),
            Field("ai_max_evidence_items", "أقصى عناصر أدلة", "int", 10,
                  "الحد الأقصى لعناصر الأدلة في الاستجابة.",
                  minimum=1, maximum=50),
            Field("ai_save_raw_responses", "حفظ الاستجابات الخام", "bool", False,
                  "حفظ الاستجابة الكاملة — للتدقيق فقط."),
            Field("ai_health_check_interval", "فترة فحص الصحة", "int", 300,
                  "ثوانٍ بين فحوص صحة المزوّد.",
                  minimum=60, maximum=3600, unit="ث"),
        ),
    ),
    Group(
        key="ai_local",
        title="الذكاء المحلي (Ollama)",
        note="استدلال محلي عبر Ollama — افتراضياً Claude فقط. فعّل الذكاء "
             "المحلي صراحةً. لا يغيّر قرارات المنصة.",
        fields=(
            Field("ai_local_enabled", "تفعيل الذكاء المحلي", "bool", False,
                  "السماح باستخدام Ollama/Qwen. بدون هذا الإعداد يبقى Claude فقط."),
            Field("ai_ollama_enabled", "تفعيل Ollama", "bool", False,
                  "الاتصال بخادم Ollama المحلي."),
            Field("ai_ollama_base_url", "عنوان Ollama", "text",
                  "http://127.0.0.1:11434",
                  "نقطة نهاية Ollama — افتراضياً المنفذ 11434."),
            Field("ai_local_model", "نموذج محلي", "choice", "qwen3:8b",
                  "نموذج Qwen المستخدم عبر Ollama.",
                  choices=ollama_model_choices()),
            Field("ai_execution_mode", "وضع التنفيذ", "choice", "claude_only",
                  "claude_only افتراضي — لا يُبدّل الإنتاج تلقائياً.",
                  choices=(
                      ("claude_only", "Claude فقط"),
                      ("local_only", "محلي فقط"),
                      ("local_first", "محلي أولاً"),
                      ("compare", "مقارنة Claude + Qwen"),
                  )),
            Field("ai_escalate_min_confidence", "حد التصعيد (ثقة)", "float", 40.0,
                  "في local_first: تصعيد إلى Claude إذا كانت الثقة أقل.",
                  minimum=0, maximum=100, step=1),
            Field("ai_escalate_grounding_below", "حد التصعيد (تأصيل)", "float", 50.0,
                  "في local_first: تصعيد إذا كان التأصيل أقل.",
                  minimum=0, maximum=100, step=1),
        ),
    ),
    Group(
        key="research_auto",
        title="البحث الكمّي التلقائي",
        note="تشغيل تجارب البحث تلقائياً عند توفر بيانات كافية — إنتاج أدلة فقط، "
             "لا يعدّل الاستراتيجية أو القرارات.",
        fields=(
            Field("research_auto_enabled", "تفعيل البحث التلقائي", "bool", True,
                  "تشغيل محفّزات البحث عند إغلاق الصفقات."),
            Field("research_min_new_trades", "حد الصفقات الجديدة", "int", 10,
                  "عدد الصفقات المحسومة الجديدة قبل تشغيل بحث تلقائي.",
                  minimum=1, maximum=500),
            Field("research_weekly_enabled", "بحث أسبوعي", "bool", True,
                  "تشغيل بحث مجدول أسبوعياً عند توفر بيانات."),
            Field("research_hypothesis_enabled", "محفّز فرضيات التعلّم", "bool", True,
                  "تشغيل بحث عند فرضية تعلّم عالية الثقة."),
            Field("research_failure_threshold", "حد الأنماط المتكررة", "int", 10,
                  "عدد حالات فشل AI المتكررة قبل بحث تلقائي.",
                  minimum=2, maximum=100),
            Field("research_min_closed_trades", "أدنى صفقات محسومة", "int", 20,
                  "الحد الأدنى للصفقات المطلوبة لتشغيل تجربة.",
                  minimum=5, maximum=1000),
            Field("research_min_group_size", "أدنى حجم مجموعة", "int", 5,
                  "الحد الأدنى لحجم مجموعة العلاج في التجربة.",
                  minimum=2, maximum=100),
            Field("research_min_comparison_size", "أدنى حجم مقارنة", "int", 5,
                  "الحد الأدنى لحجم خط الأساس.",
                  minimum=2, maximum=100),
            Field("research_hypothesis_min_confidence", "أدنى ثقة فرضية", "float", 60.0,
                  "الحد الأدنى لثقة فرضية التعلّم لمحفّز البحث.",
                  minimum=0, maximum=100, step=5),
        ),
    ),
    Group(
        key="prediction_auto",
        title="التنبؤ التلقائي",
        note="تدريب نماذج التنبؤ من الصفقات المحسومة — إنتاج أدلة فقط، لا يعدّل القرارات.",
        fields=(
            Field("prediction_auto_enabled", "تفعيل التدريب التلقائي", "bool", True,
                  "إعادة التدريب عند بلوغ عتبة صفقات جديدة."),
            Field("prediction_min_eligible_trades", "أدنى صفقات مؤهّلة", "int", 50,
                  "الحد الأدنى للصفقات المؤهّلة لبناء مجموعة التدريب.",
                  minimum=20, maximum=5000),
            Field("prediction_min_new_trades", "حد الصفقات الجديدة", "int", 20,
                  "عدد الصفقات الجديدة قبل إعادة التدريب.",
                  minimum=5, maximum=500),
            Field("prediction_min_test_samples", "أدنى عيّنة اختبار", "int", 5,
                  "الحد الأدنى لعيّنة الاختبار خارج العيّنة.",
                  minimum=3, maximum=100),
            Field("prediction_min_accuracy_improvement", "تحسّن الدقة المطلوب", "float", 0.02,
                  "الحد الأدنى لتحسّن الدقة مقابل خط الأساس الساذج.",
                  minimum=0, maximum=0.5, step=0.01),
            Field("prediction_walk_forward_enabled", "تحقق walk-forward", "bool", True,
                  "تفعيل التحقق الزمني قبل ترقية النموذج."),
        ),
    ),
)

FIELDS: dict[str, Field] = {f.key: f for g in GROUPS for f in g.fields}
DEFAULTS: dict[str, Any] = {k: f.default for k, f in FIELDS.items()}

# قيود بين الحقول لا يمكن التعبير عنها بحدّ أدنى وأقصى
ORDERED = (
    ("tier_high", "tier_mid", "حدّ السيولة العالية يجب أن يفوق المتوسطة"),
    ("tier_mid", "tier_low", "حدّ السيولة المتوسطة يجب أن يفوق المنخفضة"),
)


def coerce(key: str, raw: Any) -> tuple[Any, str | None]:
    """تحويل قيمة واحدة إلى نوعها مع رسالة خطأ عند التعذّر."""
    f = FIELDS.get(key)
    if f is None:
        return None, f"إعداد غير معروف: {key}"

    if f.kind == "bool":
        if isinstance(raw, bool):
            return raw, None
        return str(raw).strip().lower() in ("1", "true", "on", "yes", "نعم"), None

    if f.kind == "choice":
        value = str(raw)
        allowed = [c[0] for c in f.choices]
        if value not in allowed:
            return f.default, f"«{f.label}»: قيمة غير مسموحة"
        return value, None

    if f.kind == "text":
        value = str(raw).strip()
        # ═══ والمُهمَل يُقال عند الحفظ ═══
        #
        # ضاع ``15m`` من إعدادٍ مكتوبٍ بمسافات، بلا كلمة. والقيمة
        # تُحفظ كما كُتبت — التنبيه يدلّ ولا يمسح ما كتبه صاحبه.
        if f.key in ("sync_timeframes", "scan_timeframes") and value:
            try:
                from scanner import tf_prefs

                notes = tf_prefs.review(value)
            except Exception:  # noqa: BLE001
                notes = []
            if notes:
                return value, f"«{f.label}»: " + " · ".join(notes[:3])
        return value or str(f.default), None

    text = str(raw).strip().replace(",", "")
    if text == "":
        return f.default, None
    try:
        value = int(float(text)) if f.kind == "int" else float(text)
    except (TypeError, ValueError):
        return f.default, f"«{f.label}»: ليست رقماً"

    if f.minimum is not None and value < f.minimum:
        return f.minimum, f"«{f.label}»: رُفعت إلى الحدّ الأدنى {f.minimum:g}"
    if f.maximum is not None and value > f.maximum:
        return f.maximum, f"«{f.label}»: خُفضت إلى الحدّ الأقصى {f.maximum:g}"
    return value, None


def validate(raw: dict) -> tuple[dict, list[str]]:
    """يحوّل قاموساً خاماً إلى قيم صالحة مع قائمة تنبيهات.

    الحقول الغائبة تأخذ افتراضها بدل أن تُسقط الحفظ — نموذج ناقص من
    متصفّح قديم يجب ألا يعطّل بقية الإعدادات.
    """
    out: dict[str, Any] = {}
    notes: list[str] = []

    for key, f in FIELDS.items():
        if key in raw:
            value, note = coerce(key, raw[key])
            if note:
                notes.append(note)
        elif f.kind == "bool":
            # مربّع غير مؤشَّر لا يُرسَل أصلاً في HTML
            value = False
        else:
            value = f.default
        out[key] = value

    # Remap stale Claude model IDs to a valid catalog entry
    if out.get("ai_claude_model"):
        try:
            from scanner.ai_advisor.models_catalog import resolve_claude_model
            resolved = resolve_claude_model(str(out["ai_claude_model"]))
            if resolved != out["ai_claude_model"]:
                notes.append(f"نموذج Claude غير متاح — ضُبط إلى {resolved}")
                out["ai_claude_model"] = resolved
        except Exception:
            pass

    if out.get("ai_local_model"):
        resolved = resolve_ollama_model(str(out["ai_local_model"]))
        if resolved != out["ai_local_model"]:
            notes.append(f"نموذج Ollama غير متاح — ضُبط إلى {resolved}")
            out["ai_local_model"] = resolved

    mode = str(out.get("ai_execution_mode", "claude_only"))
    if mode not in EXECUTION_MODES:
        out["ai_execution_mode"] = "claude_only"
        notes.append("وضع التنفيذ غير صالح — ضُبط إلى claude_only")

    for high, low, message in ORDERED:
        if out.get(high) is not None and out.get(low) is not None:
            if out[high] <= out[low]:
                out[high] = out[low] * 2
                notes.append(f"{message} — ضُبط إلى {out[high]:,.0f}")

    if out.get("target_atr", 0) <= out.get("stop_atr", 0):
        out["target_atr"] = round(out["stop_atr"] * 2, 2)
        notes.append("الهدف يجب أن يتجاوز الوقف — ضُبط إلى "
                     f"{out['target_atr']:g}×ATR")

    return out, notes


def merged(stored: dict | None) -> dict:
    """القيم المحفوظة فوق الافتراضية — إعداد جديد يظهر بافتراضه بلا هجرة."""
    values = dict(DEFAULTS)
    for key, value in (stored or {}).items():
        if key in FIELDS:
            values[key] = value
    if values.get("ai_claude_model"):
        try:
            from scanner.ai_advisor.models_catalog import resolve_claude_model
            values["ai_claude_model"] = resolve_claude_model(str(values["ai_claude_model"]))
        except Exception:
            pass
    if values.get("ai_local_model"):
        values["ai_local_model"] = resolve_ollama_model(str(values["ai_local_model"]))
    return values


def tiers_from(values: dict) -> list[tuple[str, float, str]]:
    """عتبات السيولة بالشكل الذي تفهمه وحدة liquidity."""
    return [
        ("high", float(values.get("tier_high", DEFAULTS["tier_high"])), "عالية"),
        ("mid", float(values.get("tier_mid", DEFAULTS["tier_mid"])), "متوسطة"),
        ("low", float(values.get("tier_low", DEFAULTS["tier_low"])), "منخفضة"),
        ("micro", 0.0, "دقيقة"),
    ]
