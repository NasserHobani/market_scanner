"""نماذج قاعدة البيانات.

سبب حفظ كل مسح لا آخر نتيجة فقط: بدون تاريخ متراكم لا يمكن الإجابة على
السؤال الذي يحدد قيمة الأداة — «هل الماسح يتحسّن أم لا؟».
"""
from __future__ import annotations

from django.db import models


class ScanRun(models.Model):
    KINDS = [("scan", "مسح كامل"), ("adhoc", "تحليل مفرد")]

    market = models.CharField("السوق", max_length=32, db_index=True)
    # التمييز ضروري: تحليل رمز واحد من البحث يجب ألا يحلّ محلّ آخر مسح
    # كامل في اللوحة، وإلا ظهرت لوحة برمز واحد بدل مئات
    kind = models.CharField("النوع", max_length=8, choices=KINDS,
                            default="scan", db_index=True)
    timeframe = models.CharField("الفريم", max_length=8)
    started_at = models.DateTimeField("بدأ", auto_now_add=True, db_index=True)
    duration_seconds = models.FloatField("المدة", default=0.0)
    symbols_scanned = models.IntegerField("رموز مفحوصة", default=0)
    symbols_failed = models.IntegerField("رموز فاشلة", default=0)
    ready_count = models.IntegerField("مكتمل الشروط", default=0)

    # مصدر قائمة الرموز في هذه الدورة، وسبب الارتداد إن وقع.
    #
    # ═══ لماذا يُسجَّل ═══
    #
    # ملف السوق الأمريكي يقول ``universe: auto`` — أي كل الأسهم فوق
    # عشرين مليون دولار يومياً، قرابة سبعمئة سهم. وحين يتعثّر الاكتشاف
    # (مفتاح، شبكة، حدّ طلبات) ينزل المسح إلى قائمة الملف: **عشرة**
    # رموز.
    #
    # وكان هذا النزول يُكتب إلى ``stderr`` فقط. والمسح من اللوحة يعمل في
    # خيط، فلا يصل النصّ إلى أحد. فظلّ السوق الأمريكي يُمسَح على عشرة
    # أسهم طوال تاريخه — عشرة رموز متمايزة في كل السجلّ — واللوحة تبدو
    # سليمة.
    #
    # وهذا أخطر من العطب نفسه: نظام يعمل بربع طاقته ويقول إنه بخير.
    universe_source = models.CharField("مصدر الرموز", max_length=16,
                                       default="", blank=True)
    universe_note = models.CharField("ملاحظة الرموز", max_length=300,
                                     default="", blank=True)

    class Meta:
        verbose_name = "دورة مسح"
        verbose_name_plural = "دورات المسح"
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["market", "timeframe", "-started_at"])]

    def __str__(self) -> str:
        return f"{self.market} · {self.timeframe} · {self.started_at:%Y-%m-%d %H:%M}"


class ScanResult(models.Model):
    DECISIONS = [
        ("شراء قوي", "شراء قوي"), ("شراء", "شراء"), ("محايد", "محايد"),
        ("بيع", "بيع"), ("بيع قوي", "بيع قوي"),
    ]

    run = models.ForeignKey(ScanRun, on_delete=models.CASCADE, related_name="results")
    symbol = models.CharField("الرمز", max_length=32, db_index=True)
    market = models.CharField("السوق", max_length=32, db_index=True)
    timeframe = models.CharField("الفريم", max_length=8)
    candle_time = models.DateTimeField("وقت الشمعة", db_index=True)

    close = models.FloatField("الإغلاق")
    score = models.FloatField("النقاط", db_index=True)
    decision = models.CharField("القرار", max_length=16, choices=DECISIONS)

    confluence = models.IntegerField("عناصر الالتقاء", default=0)
    reasons = models.CharField("الأسباب", max_length=255, blank=True)
    htf = models.SmallIntegerField("الفريم الأعلى", default=0)
    ready = models.BooleanField("مكتمل الشروط", default=False, db_index=True)
    blocker = models.CharField("المانع", max_length=64, blank=True)

    rsi = models.FloatField("RSI", null=True, blank=True)
    rvol = models.FloatField("RVOL", null=True, blank=True)
    atr_pct = models.FloatField("ATR%", null=True, blank=True)
    chart_url = models.URLField("رابط الشارت", max_length=400, blank=True)

    # التوصية المحسوبة وقت المسح — تُحفظ لأن إعادة حسابها لاحقاً
    # ستعطي نتيجة مختلفة ببيانات أحدث، فتفقد قيمة الأرشيف
    action = models.CharField("نوع التوصية", max_length=12, default="none",
                              db_index=True)
    headline = models.CharField("التوصية", max_length=32, blank=True)
    entry = models.FloatField("الدخول", null=True, blank=True)
    stop = models.FloatField("الوقف", null=True, blank=True)
    target1 = models.FloatField("الهدف الأول", null=True, blank=True)
    rr = models.FloatField("العائد/المخاطرة", null=True, blank=True)
    trigger = models.CharField("شرط التفعيل", max_length=200, blank=True)
    candle_patterns = models.CharField("نماذج الشموع", max_length=160, blank=True)
    chart_pattern = models.CharField("النموذج السعري", max_length=48, blank=True)
    elliott = models.CharField("موجة إليوت", max_length=48, blank=True)
    confidence = models.FloatField("ثقة التوصية", default=0.0)
    grade = models.CharField("تصنيف التوصية", max_length=2, default="—")
    feature_snapshot_id = models.CharField("معرّف لقطة الخصائص", max_length=40,
                                           blank=True, db_index=True)
    pit_snapshot_id = models.CharField("معرّف لقطة PIT", max_length=48,
                                       blank=True, db_index=True)
    recommendation_id = models.CharField("معرّف التوصية", max_length=64,
                                         blank=True, db_index=True)
    compliance = models.CharField("التوافق الشرعي", max_length=16,
                                  default="unknown", db_index=True)
    compliance_reason = models.CharField("سبب التصنيف", max_length=300, blank=True)

    # السيولة ليست تفصيلاً تجميلياً: إشارة على زوج حجمه 300 ألف دولار
    # ليست كإشارة على زوج حجمه 500 مليون. أمر واحد كبير يحرّك الأول،
    # والانزلاق عند التنفيذ قد يبتلع الربح المتوقّع كله.
    quote_volume = models.FloatField("حجم 24س", null=True, blank=True, db_index=True)
    liquidity = models.CharField("السيولة", max_length=8, default="unknown",
                                 db_index=True)

    class Meta:
        verbose_name = "نتيجة"
        verbose_name_plural = "النتائج"
        ordering = ["-score"]
        indexes = [
            models.Index(fields=["market", "symbol", "-candle_time"]),
            models.Index(fields=["-candle_time", "-score"]),
        ]
        # الشمعة الواحدة للرمز الواحد لا تُسجَّل مرتين مهما تكرر المسح
        constraints = [
            models.UniqueConstraint(
                fields=["symbol", "market", "timeframe", "candle_time"],
                name="unique_symbol_candle",
            )
        ]

    def __str__(self) -> str:
        return f"{self.symbol} {self.score:.1f}"

    @property
    def htf_text(self) -> str:
        return {1: "صاعد", -1: "هابط"}.get(self.htf, "مختلط")


class SignalAlert(models.Model):
    result = models.ForeignKey(ScanResult, on_delete=models.CASCADE, related_name="alerts")
    symbol = models.CharField("الرمز", max_length=32, db_index=True)
    fired_at = models.DateTimeField("وقت الإشارة", auto_now_add=True, db_index=True)
    score = models.FloatField("النقاط")
    reasons = models.CharField("الأسباب", max_length=255, blank=True)
    notified = models.BooleanField("أُرسل تنبيه", default=False)

    class Meta:
        verbose_name = "إشارة"
        verbose_name_plural = "الإشارات"
        ordering = ["-fired_at"]

    def __str__(self) -> str:
        return f"{self.symbol} @ {self.score:.1f}"


class Watch(models.Model):
    """فرصة معلّقة تنتظر وصول السعر لمستوى الدخول.

    التمييز المهم: الإشارة صدرت على شمعة مغلقة، وهذا مجرد أمر تنفيذ عند
    مستوى محدد سلفاً. لسنا نولّد إشارة جديدة من حركة داخل الشمعة —
    نراقب بلوغ سعر قررناه بالفعل.
    """

    STATUS = [
        ("armed", "مسلّحة"), ("triggered", "تحققت"),
        ("expired", "منتهية"), ("cancelled", "ملغاة"),
    ]

    symbol = models.CharField("الرمز", max_length=32, db_index=True)
    market = models.CharField("السوق", max_length=32, db_index=True)
    timeframe = models.CharField("الفريم", max_length=8)
    side = models.CharField("الاتجاه", max_length=8, default="buy")

    entry = models.FloatField("سعر الدخول")
    stop = models.FloatField("الوقف")
    target1 = models.FloatField("الهدف", null=True, blank=True)
    rr = models.FloatField("العائد/المخاطرة", null=True, blank=True)
    grade = models.CharField("التصنيف", max_length=2, default="—")
    reasons = models.CharField("الأسباب", max_length=255, blank=True)
    trigger_text = models.CharField("شرط التفعيل", max_length=200, blank=True)

    status = models.CharField("الحالة", max_length=10, choices=STATUS,
                              default="armed", db_index=True)
    created_at = models.DateTimeField("أُنشئت", auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField("تنتهي", null=True, blank=True)
    triggered_at = models.DateTimeField("تحققت", null=True, blank=True)
    trigger_price = models.FloatField("سعر التحقق", null=True, blank=True)
    # تغذية السعر التي أطلقت التحقّق: sip تغطّي السوق كاملاً، و iex
    # بورصة واحدة (~2.5٪ من الحجم). يُسجَّل ليصير الفرق **قابلاً للقياس**
    # لاحقاً — مقارنة نتائج ما تحقّق على كلٍّ منهما — بدل أن يبقى ظنّاً.
    trigger_feed = models.CharField("تغذية التحقق", max_length=12, blank=True)
    notified = models.BooleanField("أُرسل تنبيه", default=False)
    last_price = models.FloatField("آخر سعر", null=True, blank=True)
    checked_at = models.DateTimeField("آخر فحص", null=True, blank=True)

    class Meta:
        verbose_name = "فرصة مراقَبة"
        verbose_name_plural = "الفرص المراقَبة"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["symbol", "market", "timeframe", "status"],
                condition=models.Q(status="armed"),
                name="one_armed_watch_per_symbol",
            )
        ]

    def __str__(self) -> str:
        return f"{self.symbol} @ {self.entry}"

    @property
    def distance_pct(self) -> float | None:
        if not self.last_price or not self.entry:
            return None
        return (self.last_price - self.entry) / self.entry * 100

    def reached(self, price: float) -> bool:
        """هل بلغ السعر مستوى الدخول؟"""
        return price <= self.entry if self.side == "buy" else price >= self.entry


class Trade(models.Model):
    """صفقة متتبَّعة — ورقية أو يدوية.

    لماذا تُنسخ الخطة كاملة هنا بدل الإحالة إلى ScanResult:

    الغرض من السجل قياس أداء القرار **كما اتُّخذ لحظتها**. لو أحلنا إلى
    التحليل الحيّ لتغيّرت الأرقام كلما حسّنّا الخوارزمية، فيصير السؤال
    «كيف كان أداؤنا؟» بلا جواب ثابت. النسخة المجمّدة تجعل المقارنة بين
    نسختين من النظام ممكنة أصلاً.

    ولهذا أيضاً يُحفظ ``factors``: الأسباب نصّ حرّ يتغيّر صياغته، أمّا
    العوامل فمفاتيح ثابتة يمكن التجميع عليها بعد سنة.
    """

    SOURCES = [("auto", "آلية"), ("manual", "يدوية"),
               ("breakout", "اختراق")]
    STATUS = [
        ("pending", "تنتظر الدخول"), ("open", "مفتوحة"),
        ("won", "رابحة"), ("lost", "خاسرة"),
        ("expired", "لم تُفعَّل"), ("cancelled", "ملغاة"),
    ]

    source = models.CharField("المصدر", max_length=8, choices=SOURCES,
                              default="auto", db_index=True)
    symbol = models.CharField("الرمز", max_length=32, db_index=True)
    market = models.CharField("السوق", max_length=32, db_index=True)
    timeframe = models.CharField("الفريم", max_length=8, db_index=True)
    side = models.CharField("الاتجاه", max_length=8, default="buy")

    # ── الخطة المجمّدة ──
    entry = models.FloatField("الدخول المخطط")
    stop = models.FloatField("الوقف")
    target1 = models.FloatField("الهدف الأول")
    rr = models.FloatField("العائد/المخاطرة", null=True, blank=True)
    grade = models.CharField("التصنيف", max_length=2, default="—", db_index=True)
    score = models.FloatField("الدرجة", null=True, blank=True)
    confidence = models.FloatField("الثقة", default=0.0)
    action = models.CharField("نوع التوصية", max_length=12, default="none")
    reasons = models.CharField("الأسباب", max_length=255, blank=True)
    factors = models.JSONField("العوامل", default=list, blank=True)
    feature_snapshot_id = models.CharField("معرّف لقطة الخصائص", max_length=40,
                                           blank=True, db_index=True)
    pit_snapshot_id = models.CharField("معرّف لقطة PIT", max_length=48,
                                       blank=True, db_index=True)
    recommendation_id = models.CharField("معرّف التوصية", max_length=64,
                                         blank=True, db_index=True)
    decision_timestamp = models.DateTimeField("وقت القرار (PIT)", null=True, blank=True)
    feature_version = models.CharField("إصدار الميزات", max_length=16, blank=True, default="")

    # ── الحالة والنتيجة ──
    status = models.CharField("الحالة", max_length=10, choices=STATUS,
                              default="pending", db_index=True)
    signal_at = models.DateTimeField("وقت الإشارة", db_index=True)
    candle_time = models.DateTimeField("شمعة الإشارة")
    expires_at = models.DateTimeField("مهلة الدخول", null=True, blank=True)
    opened_at = models.DateTimeField("وقت التنفيذ", null=True, blank=True)
    closed_at = models.DateTimeField("وقت الخروج", null=True, blank=True)
    entry_price = models.FloatField("سعر التنفيذ", null=True, blank=True)
    exit_price = models.FloatField("سعر الخروج", null=True, blank=True)
    r_multiple = models.FloatField("مضاعف R", null=True, blank=True)
    best_r = models.FloatField("أقصى ربح غير محقّق", null=True, blank=True)
    worst_r = models.FloatField("أقصى تراجع", null=True, blank=True)
    bars_held = models.IntegerField("شموع الاحتفاظ", default=0)
    resolution_note = models.CharField("ملاحظة الحسم", max_length=120, blank=True)

    last_price = models.FloatField("آخر سعر", null=True, blank=True)
    checked_at = models.DateTimeField("آخر فحص", null=True, blank=True)
    note = models.CharField("ملاحظة", max_length=200, blank=True)

    class Meta:
        verbose_name = "صفقة"
        verbose_name_plural = "الصفقات"
        ordering = ["-signal_at"]
        indexes = [
            models.Index(fields=["source", "status", "-signal_at"]),
            models.Index(fields=["market", "timeframe", "status"]),
        ]
        # الإشارة الواحدة لا تفتح صفقتين آليتين مهما تكرر المسح على
        # الشمعة نفسها — والقيد على الشمعة لا على الوقت لأن المسح
        # قد يُعاد يدوياً عدة مرات داخل الشمعة نفسها
        constraints = [
            models.UniqueConstraint(
                fields=["source", "symbol", "market", "timeframe", "candle_time"],
                name="one_trade_per_signal_candle",
            )
        ]

    def __str__(self) -> str:
        return f"{self.symbol} {self.get_status_display()}"

    @property
    def is_closed(self) -> bool:
        return self.status in ("won", "lost")

    @property
    def risk(self) -> float:
        return abs(self.entry - self.stop)

    @property
    def unrealized_r(self) -> float | None:
        """R غير المحقّق للصفقات المفتوحة — تقدير من آخر سعر."""
        if self.status != "open" or not self.last_price or not self.entry_price:
            return None
        risk = abs(self.entry_price - self.stop)
        if risk <= 0:
            return None
        sign = 1 if self.side == "buy" else -1
        return round((self.last_price - self.entry_price) / risk * sign, 2)


class Setting(models.Model):
    """إعداد واحد بقيمته — مفتاح ونصّ JSON.

    صفّ لكل مفتاح لا صفّ واحد بكل الإعدادات: إضافة إعداد جديد لا تحتاج
    هجرة، وحذف إعداد لا يُفقد البقية. والمخطط في
    ``scanner.settings_schema`` هو المرجع، وهذا مجرد مخزن.
    """

    key = models.CharField("المفتاح", max_length=64, unique=True)
    value = models.JSONField("القيمة", null=True, blank=True)
    updated_at = models.DateTimeField("آخر تعديل", auto_now=True)

    class Meta:
        verbose_name = "إعداد"
        verbose_name_plural = "الإعدادات"
        ordering = ["key"]

    def __str__(self) -> str:
        return f"{self.key} = {self.value}"


class Company(models.Model):
    """شركة مدرَجة ومعلوماتها — دليل السوق المستقلّ عن نتائج المسح.

    ═══ لماذا جدولٌ مستقلّ ═══

    ‏``ScanResult`` يقول «ماذا فعل السهم في هذه الدورة»، وهذا يقول
    «ما هذا السهم أصلاً». والخلط بينهما كان يعني أن معرفة اسم شركة
    تتطلّب مسحاً ناجحاً — فإن تعثّر المسح ضاع الدليل معه.

    وفصلُهما يسمح بالمسار الذي طلبتَه: تُجلَب الشركات أوّلاً فتصير
    السوق معروفة، ثمّ يُجلَب التاريخ على مهل.

    ═══ ولماذا الحقول قد تكون فارغة ═══

    ‏``/companies/`` مجاني عند سهمك، و‏``/quote/`` كذلك لرمزٍ واحد،
    أمّا الأساسيات (مكرّر الربحية ونحوه) فتحتاج باقة Starter. فما
    لا تعطيه الباقة يبقى ``None`` — ولا يُلفَّق ولا يُصفَّر: الصفر
    رقمٌ يُحسب عليه، والغياب حالةٌ تُعرَض.
    """

    market = models.CharField("السوق", max_length=16, db_index=True)
    symbol = models.CharField("الرمز", max_length=32, db_index=True)

    name_ar = models.CharField("الاسم", max_length=160, blank=True)
    name_en = models.CharField("Name", max_length=160, blank=True)
    sector = models.CharField("القطاع", max_length=120, blank=True)
    sub_market = models.CharField("السوق الفرعي", max_length=32, blank=True)
    security_type = models.CharField("نوع الورقة", max_length=32, blank=True)

    # لحظيّ (متأخّر ربع ساعة على الباقة المجانية)
    price = models.FloatField("السعر", null=True, blank=True)
    change_pct = models.FloatField("التغيّر ٪", null=True, blank=True)
    volume = models.FloatField("الحجم", null=True, blank=True)
    quote_value = models.FloatField("قيمة التداول", null=True, blank=True)

    # أساسيات — Starter فأعلى
    pe = models.FloatField("مكرّر الربحية", null=True, blank=True)
    eps = models.FloatField("ربحية السهم", null=True, blank=True)
    book_value = models.FloatField("القيمة الدفترية", null=True, blank=True)
    week52_high = models.FloatField("أعلى ٥٢ أسبوعاً", null=True, blank=True)
    week52_low = models.FloatField("أدنى ٥٢ أسبوعاً", null=True, blank=True)

    # حالة التاريخ — تُملأ من القرص لا من المزوّد
    candles = models.IntegerField("عدد الشموع", default=0)
    last_candle = models.DateTimeField("آخر شمعة", null=True, blank=True)

    info_updated_at = models.DateTimeField("آخر تحديث للمعلومات",
                                           null=True, blank=True)
    updated_at = models.DateTimeField("آخر تعديل", auto_now=True)

    class Meta:
        verbose_name = "شركة"
        verbose_name_plural = "الشركات"
        ordering = ["market", "symbol"]
        constraints = [
            models.UniqueConstraint(fields=["market", "symbol"],
                                    name="uniq_company_market_symbol"),
        ]
        indexes = [models.Index(fields=["market", "sector"])]

    def __str__(self) -> str:
        return f"{self.symbol} — {self.name_ar or self.name_en}"


class ScheduledJob(models.Model):
    """مهمّة مجدولة — على غرار ``ir.cron`` في أودو.

    ═══ لماذا في القاعدة لا في الشيفرة ═══

    كانت الحلقات الأربع (المسح · المزامنة · المراقبة · الحسم) خيوطاً
    مستقلّة، كلٌّ بحالتها في الذاكرة وفترتها في متغيّر بيئة. فمعرفة
    «متى مُسح السوق السعودي آخر مرّة» تتطلّب قراءة السجلّات، وتغيير
    فترةٍ يتطلّب تحرير ملفّ وإعادة تشغيل، وكل شيء يُمحى عند إعادة
    التشغيل.

    وهنا الجدولة **بيانات**: تُقرأ وتُعدَّل وتُوقَف من الواجهة، وتبقى.

    ═══ next_run هو الحقيقة ═══

    الموعد القادم محفوظ لا محسوب. فالخادم إن أُغلق يومين ثمّ فُتح،
    يجد المهمّة مستحقّة فيشغّلها مرّة واحدة — لا خمسمئة مرّة تعويضاً
    عن اليومين. انظر ``cron.advance``.
    """

    INTERVAL_TYPES = [
        ("minutes", "دقيقة"),
        ("hours", "ساعة"),
        ("days", "يوم"),
    ]
    STATUSES = [
        ("ok", "نجحت"),
        ("fail", "فشلت"),
        ("skipped", "تُخطّيت"),
        ("running", "تعمل الآن"),
        ("never", "لم تعمل بعد"),
    ]

    # ═══ code مقابل handler ═══
    #
    # ``handler`` يشير إلى الدالّة، و``code`` يميّز المهمّة. فمسح
    # الكريبتو ومسح السعودي معالجهما واحد ومهمّتاهما اثنتان — ولو
    # كان المفتاح هو المعالج لما أمكن جدولة سوقين بفترتين.
    code = models.CharField("المفتاح", max_length=64, unique=True)
    handler = models.CharField("المعالج", max_length=32, db_index=True)
    name = models.CharField("الاسم", max_length=120)
    active = models.BooleanField("نشِطة", default=True, db_index=True)

    interval_number = models.PositiveIntegerField("كل", default=5)
    interval_type = models.CharField("الوحدة", max_length=10,
                                     choices=INTERVAL_TYPES,
                                     default="minutes")
    # وسائط المعالج — مثل {"market": "crypto"}
    payload = models.JSONField("الوسائط", default=dict, blank=True)
    # الأصغر أوّلاً عند استحقاق مهمّتين معاً
    priority = models.IntegerField("الأولوية", default=10)

    next_run = models.DateTimeField("الموعد القادم", db_index=True)

    last_run_at = models.DateTimeField("آخر تشغيل", null=True, blank=True)
    last_duration_ms = models.IntegerField("المدّة (ms)", null=True, blank=True)
    last_status = models.CharField("آخر حالة", max_length=10,
                                   choices=STATUSES, default="never")
    last_message = models.CharField("آخر رسالة", max_length=300, blank=True)

    run_count = models.IntegerField("مرّات التشغيل", default=0)
    fail_count = models.IntegerField("مرّات الفشل", default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "مهمّة مجدولة"
        verbose_name_plural = "المهامّ المجدولة"
        ordering = ["priority", "code"]
        indexes = [models.Index(fields=["active", "next_run"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"

    @property
    def interval_seconds(self) -> int:
        """الفترة بالثواني — والصفر يُمنع.

        فترةٌ صفرية تجعل ``advance`` تدور بلا نهاية بحثاً عن موعدٍ
        بعد الآن. والحدّ الأدنى ثلاثون ثانية: أقصر من ذلك يُغرق
        المزوّدين ولا يفيد — أقصر شمعة عندنا خمس عشرة دقيقة.
        """
        unit = {"minutes": 60, "hours": 3600, "days": 86400}
        return max(30, int(self.interval_number or 1)
                   * unit.get(self.interval_type, 60))

    @property
    def is_due(self) -> bool:
        from django.utils import timezone

        return bool(self.active and self.next_run
                    and self.next_run <= timezone.now())


class JobRun(models.Model):
    """سطرٌ لكل تشغيل — السجلّ الذي كان مفقوداً.

    الحالة كانت في الذاكرة وحدها: تُعاد تشغيل الخادم فيُمحى كل
    شيء، فلا يُعرف هل عمل المسح ليلة أمس ولا لماذا فشل. والسؤال
    «منذ متى وهذا معطّل؟» لا جواب له بلا سجلّ.
    """

    job = models.ForeignKey(ScheduledJob, on_delete=models.CASCADE,
                            related_name="runs")
    started_at = models.DateTimeField("البداية", db_index=True)
    duration_ms = models.IntegerField("المدّة (ms)", default=0)
    status = models.CharField("الحالة", max_length=10,
                              choices=ScheduledJob.STATUSES, default="ok")
    message = models.CharField("الرسالة", max_length=300, blank=True)
    # يدويّ أم بالجدولة — للتمييز في السجلّ
    manual = models.BooleanField("يدويّ", default=False)

    class Meta:
        verbose_name = "تشغيل مهمّة"
        verbose_name_plural = "سجلّ التشغيل"
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["job", "-started_at"])]

    def __str__(self) -> str:
        return f"{self.job_id} · {self.started_at:%Y-%m-%d %H:%M} · {self.status}"


class BlockedSymbol(models.Model):
    """رمزٌ حظره المستخدم — فلا يُمسح ولا يُحلَّل ولا تُفتح عليه صفقة.

    ═══ الفرق عن الفرز الشرعي ═══

    ``scanner/compliance.py`` **يفرز ولا يحكم**: يصنّف مبدئياً بقواعد
    مكتوبة ويقول «يحتاج مراجعة». وهو لا يمنع شيئاً — الرمز يُمسح
    ويُحلَّل ويظهر في النتائج موسوماً.

    وهذا الجدول قرارٌ **للمستخدم** لا للنظام: هو من حكم، والنظام
    ينفّذ. ولذلك يُحفظ معه مصدرُ الحكم (هيئة، فتوى، مؤشّر) — لا
    ليوثّق البرنامج نفسه، بل ليتذكّر صاحبه لماذا حظر ومتى يراجع.

    والنظام لا يفتي: لا يضيف رمزاً هنا من تلقائه أبداً.

    ═══ ولماذا الحظر لا الإخفاء ═══

    الإخفاء يترك الرمز يُجلب ويُحلَّل ثمّ يُطوى في العرض — فيُستهلك
    وقت المسح، وتبقى الصفقة قابلة للفتح من مسارٍ آخر. والحظر يقطعه
    من الجذر: من قائمة الرموز قبل أوّل نداء شبكة.
    """

    SCOPES = [
        ("exact", "هذا الرمز فقط"),
        # ‏AAVE يحظر AAVEUSDT — الأصل واحد واللاحقة تسعيرة
        ("base", "الأصل وكل أزواجه"),
    ]

    market = models.CharField("السوق", max_length=32, db_index=True)
    symbol = models.CharField("الرمز", max_length=32, db_index=True)
    scope = models.CharField("النطاق", max_length=8, choices=SCOPES,
                             default="base")
    reason = models.CharField("السبب", max_length=200, blank=True)
    # مَن حكم: هيئة، فتوى، مؤشّر متوافق. النظام لا يملأه من نفسه.
    source = models.CharField("المصدر", max_length=200, blank=True)
    note = models.TextField("ملاحظة", blank=True)
    active = models.BooleanField("مفعَّل", default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "رمز محظور"
        verbose_name_plural = "الرموز المحظورة"
        ordering = ["market", "symbol"]
        constraints = [
            models.UniqueConstraint(fields=["market", "symbol"],
                                    name="uniq_blocked_market_symbol"),
        ]
        indexes = [models.Index(fields=["market", "active"])]

    def __str__(self) -> str:
        return f"{self.symbol} ({self.market})"


class PaperAccount(models.Model):
    """محفظة ورقية — تنفيذٌ محاكى بمالٍ غير حقيقي.

    ═══ ما تفعله وما لا تدّعيه ═══

    تأخذ إشارات النظام وتنفّذها بقواعد إدارة مخاطر مكتوبة، وتحسب
    رسوم بينانس على الدخول والخروج. فتعرف: **لو نفّذتُ ما يقوله
    النظام بانضباط، أين كنت الآن؟**

    ولا تدّعي أنّها تُحقّق هدفها. الهدف حدٌّ يوقف الفتح عند بلوغه،
    لا وعدٌ ببلوغه. وقد تنتهي المحفظة تحت رأس مالها — وهذا خبرٌ
    يستحقّ أن يُعرف قبل المال الحقيقي لا بعده.

    ═══ والفرق عن الاختبار الخلفي ═══

    الاختبار الخلفي يمرّ على التاريخ دفعةً واحدة. وهذه تمشي مع
    الزمن الحقيقي: تفتح اليوم وتُقيَّم غداً، فلا تعرف ما لم يكن
    معروفاً وقت الفتح.
    """

    name = models.CharField("الاسم", max_length=80, default="محفظة تجريبية")
    active = models.BooleanField("نشِطة", default=True, db_index=True)

    initial_balance = models.FloatField("رأس المال", default=10000.0)
    balance = models.FloatField("النقد المتاح", default=10000.0)

    # ═══ الإعدادات في حقلٍ واحد ═══
    #
    # إضافة إعدادٍ جديد لا تحتاج هجرة. والقيم الافتراضية في
    # ``paper.DEFAULTS`` — والمخزّن هنا ما غيّره المستخدم فقط.
    settings = models.JSONField("الإعدادات", default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "محفظة ورقية"
        verbose_name_plural = "المحافظ الورقية"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.balance:.2f})"


class PaperTrade(models.Model):
    """صفقة في المحفظة الورقية — بكمّيتها ورسومها.

    الرسوم تُحفظ منفصلةً عن الربح: صفقةٌ ربحت ‎0.08٪‎ ورسومها
    ‎0.2٪‎ خاسرة، وخلطُهما يُظهرها رابحة.
    """

    STATUSES = [
        ("open", "مفتوحة"),
        ("won", "رابحة"),
        ("lost", "خاسرة"),
        ("cancelled", "أُلغيت"),
    ]

    account = models.ForeignKey(PaperAccount, on_delete=models.CASCADE,
                                related_name="trades")
    symbol = models.CharField("الرمز", max_length=32, db_index=True)
    market = models.CharField("السوق", max_length=32, db_index=True)
    timeframe = models.CharField("الفريم", max_length=8, blank=True)
    side = models.CharField("الاتجاه", max_length=8, default="buy")
    source = models.CharField("المصدر", max_length=32, blank=True)

    entry = models.FloatField("سعر الدخول")
    stop = models.FloatField("الوقف")
    target = models.FloatField("الهدف", null=True, blank=True)
    quantity = models.FloatField("الكمّية", default=0.0)
    notional = models.FloatField("قيمة المركز", default=0.0)
    # المخاطرة المخطَّطة بالنقد — أساس حساب R
    risk_amount = models.FloatField("المخاطرة", default=0.0)

    exit_price = models.FloatField("سعر الخروج", null=True, blank=True)
    exit_reason = models.CharField("سبب الخروج", max_length=40, blank=True)

    fee_in = models.FloatField("رسوم الدخول", default=0.0)
    fee_out = models.FloatField("رسوم الخروج", default=0.0)
    # الربح **بعد** الرسوم — وهو الوحيد الذي يدخل الرصيد
    pnl = models.FloatField("الربح الصافي", default=0.0)
    r_multiple = models.FloatField("مضاعف R", null=True, blank=True)

    status = models.CharField("الحالة", max_length=10, choices=STATUSES,
                              default="open", db_index=True)
    opened_at = models.DateTimeField("وقت الفتح", db_index=True)
    closed_at = models.DateTimeField("وقت الإغلاق", null=True, blank=True)
    last_price = models.FloatField("آخر سعر", null=True, blank=True)
    note = models.CharField("ملاحظة", max_length=200, blank=True)

    class Meta:
        verbose_name = "صفقة ورقية"
        verbose_name_plural = "الصفقات الورقية"
        ordering = ["-opened_at"]
        indexes = [models.Index(fields=["account", "status"])]

    def __str__(self) -> str:
        return f"{self.symbol} {self.status}"


class PesDetection(models.Model):
    """رصدُ ‏PES ومسارُه بعده — سجلٌّ يقول: هل هذا يعمل؟

    ═══ لماذا يُسجَّل المسار لا الحكم ═══

    السؤال «هل انفجرت؟» جوابُه يتوقّف على تعريف «انفجرت». وعتبةٌ
    مخبوزة في الكود — ‎+8٪‎ مثلاً — تعني أنّ تغيير رأيك إلى ‎+12٪‎
    يُبطل كل ما جُمع ويبدأ القياس من الصفر.

    فيُحفظ هنا **المسار** كاملاً: أقصى ارتفاع ومتى بلغه، وأقصى
    تراجع، وهل عُبِرت المقاومة، وهل تمدّد التقلّب. والعتبة بعد ذلك
    مرشِّحٌ في الشاشة يحرّكه المستخدم فتتغيّر النسبة أمامه.

    وهذا يجعل السجلّ يجيب أسئلةً لم تُطرح بعد.

    ═══ ولماذا لا تُخزَّن نسبة النجاح ═══

    لا عمود «نجح». النسبة تُحسب من المسار عند العرض — فرقمٌ مخزَّن
    يصير قديماً بصمت حين تتغيّر العتبة، ويبقى معروضاً كأنّه صحيح.

    ═══ وصفٌّ واحد لكل رصد ═══

    المسح يعمل كل ربع ساعة. ورمزٌ يبقى ‏PRE_BREAKOUT ثلاثة أيّام
    يُنتج ٢٨٨ صفّاً لو سُجّل في كل دورة — فتغرق أيّ إحصاءٍ في
    تكرار الحالة الواحدة. فالتسجيل عند **دخول** الحالة وحده،
    ويحرسه القيد أدناه.
    """

    OUTCOMES = [
        ("watching", "قيد المتابعة"),
        ("settled", "اكتمل المدى"),
        ("no_data", "تعذّرت المتابعة"),
    ]

    symbol = models.CharField("الرمز", max_length=32, db_index=True)
    market = models.CharField("السوق", max_length=32, db_index=True)
    state = models.CharField("الحالة عند الرصد", max_length=24, db_index=True)
    state_label = models.CharField("وصف الحالة", max_length=40, blank=True)

    # ═══ لحظة الرصد ═══
    #
    # ``candle_time`` شمعةُ القرار لا وقت المسح: المسح قد يعمل بعد
    # إغلاق الشمعة بدقائق أو بساعتين، وقياسُ المسار من وقت المسح
    # يخلط تأخّر الجدولة بحركة السوق.
    detected_at = models.DateTimeField("وقت الرصد", db_index=True)
    candle_time = models.DateTimeField("شمعة الرصد", db_index=True)
    price = models.FloatField("السعر عند الرصد")

    # سياق الرصد — يُحفظ كي يُقارَن لاحقاً بما جرى
    score = models.FloatField("نقاط PES", default=0.0)
    confidence = models.FloatField("الثقة", default=1.0)
    family_count = models.IntegerField("عدد العائلات", default=0)
    momentum_score = models.FloatField("التقاء الزخم", default=0.0)
    momentum_label = models.CharField("مرتبة الزخم", max_length=80, blank=True)
    resistance = models.FloatField("المقاومة", null=True, blank=True)
    distance_pct = models.FloatField("بعد المقاومة ٪", null=True, blank=True)
    btc_label = models.CharField("نظام BTC", max_length=16, blank=True)
    reasons = models.CharField("السبب", max_length=300, blank=True)

    # ═══ المسار الأمامي — يُملأ بعد الرصد ═══
    #
    # كلّها من شمعاتٍ **بعد** ``candle_time`` حصراً.
    bars_seen = models.IntegerField("شمعات متابَعة", default=0)
    max_gain_pct = models.FloatField("أقصى ارتفاع ٪", null=True, blank=True)
    max_gain_at = models.DateTimeField("وقت أقصى ارتفاع",
                                       null=True, blank=True)
    hours_to_max = models.FloatField("ساعات حتى القمّة",
                                     null=True, blank=True)
    # أقصى تراجع **قبل** بلوغ القمّة: ارتفاعٌ بعد نزولٍ ٢٠٪ لا
    # يُدرَك عملياً — الوقف يضربك قبله.
    max_drawdown_pct = models.FloatField("أقصى تراجع ٪",
                                         null=True, blank=True)
    broke_resistance = models.BooleanField("اخترق المقاومة", default=False)
    broke_at = models.DateTimeField("وقت الاختراق", null=True, blank=True)
    volatility_expanded = models.BooleanField("تمدّد التقلّب", default=False)

    outcome = models.CharField("حال المتابعة", max_length=12,
                               choices=OUTCOMES, default="watching",
                               db_index=True)
    settled_at = models.DateTimeField("وقت الاكتمال", null=True, blank=True)
    note = models.CharField("ملاحظة", max_length=200, blank=True)

    class Meta:
        verbose_name = "رصد PES"
        verbose_name_plural = "سجلّ رصد PES"
        ordering = ["-detected_at"]
        constraints = [
            # الحارس البنيوي ضدّ التكرار. والمنطق يمنعه أيضاً، لكنّ
            # القيد هنا يمنعه ولو أُعيد تشغيل مسحين معاً — وقد
            # حدث: محرّك الخادم والأمر الخارجي في اللحظة نفسها.
            models.UniqueConstraint(
                fields=["symbol", "market", "state", "candle_time"],
                name="uniq_pes_detection"),
        ]
        indexes = [
            models.Index(fields=["market", "state", "-detected_at"]),
            models.Index(fields=["outcome", "-detected_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.symbol} {self.state} {self.detected_at:%Y-%m-%d}"
