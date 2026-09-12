# برومبت Google Stitch — نظام تصميم موحّد لـ CS Edge

## كيف تستعمله

Stitch يعمل أفضل بالإنجليزية وبشاشةٍ واحدة في كل مرّة. فالملفّ
قسمان:

1. **البرومبت الأساسي** — الصقه أوّلاً ليؤسّس نظام التصميم.
2. **برومبت لكل شاشة** — الصق واحداً منها بعد الأساسي.

ولا تلصق الكلّ دفعةً واحدة: Stitch يخلط الشاشات حين يُعطى أكثر
من واحدة، والنتيجة تصميمٌ عامّ لا يصلح لأيّ منها.

**والقيود أهمّ من الرغبات.** أكثر ما يُفسد تصميم أدوات التداول
أنّ المصمّم يجعلها جميلةً وهي تكذب: رقمٌ بلا تغطية، ومؤشّرٌ أخضر
بلا عيّنة، وزرٌّ يبدو نشطاً وهو معطّل. فقسم `NON-NEGOTIABLE` أدناه
ليس تفصيلاً — هو المنتَج.

---

## ١) البرومبت الأساسي — الصقه أوّلاً

```
Design a professional desktop web application for a Saudi/crypto
market scanner and trade-tracking platform called "CS Edge".

LANGUAGE & DIRECTION
- The entire interface is ARABIC, right-to-left (RTL).
- All labels, headers, buttons, and table headers in Arabic.
- Numbers, ticker symbols, and timeframes stay Latin/Western
  digits (e.g. 2222.SR, BTCUSDT, 15m, 4h, 1d) and read
  left-to-right inside RTL text.
- Font: a clean Arabic UI face (IBM Plex Sans Arabic, Tajawal,
  or Noto Sans Arabic). Never a decorative or calligraphic face.

AUDIENCE
A single expert trader using this on a wide desktop monitor for
hours daily. Not a consumer app. Optimize for information density
and fast scanning, not for onboarding or delight.

THEME — dark, exact tokens
- Page background      #0f1115
- Card / surface       #161a24
- Raised surface       #1c2130
- Border               #262d3f
- Soft border          rgba(255,255,255,.05)
- Primary text         #e9ecf3
- Strong text          #ffffff
- Muted text           #97a0b5
- Up / profit / pass   #3ddc97   (tint rgba(61,220,151,.12))
- Down / loss / fail   #ff6b6b   (tint rgba(255,107,107,.12))
- Warning / caution    #e8c05a   (tint rgba(232,192,90,.12))
- Info / neutral       #6ba4ff   (tint rgba(107,164,255,.12))
- Corner radius        6px small, 9px default, 14px large
- Spacing scale        4 / 8 / 12 / 16 / 24 / 32 px

CRITICAL COLOR RULE
Green and red are reserved for MARKET DIRECTION and TRADE OUTCOME
only. Never use green for "saved successfully" or red for a
delete button. System status uses blue (info) and amber
(warning). A trader must be able to glance at any screen and know
that green always means "up or won".

LAYOUT
- Fixed right-hand vertical sidebar, 240px, collapsible to 64px
  icons. Sidebar is on the RIGHT because the layout is RTL.
- Sidebar items (Arabic): لوحة التشغيل · الماسح · الصفقات ·
  المراقبة · التحليلات · الأداء · البتكوين · مركز الذكاء ·
  مختبر البحث · تحسين الاستراتيجية · الإعدادات
- Top bar: page title on the right, global search in the middle,
  and on the left a market-data freshness chip and a scan-status
  chip.
- Content max-width 1600px, generous but dense.

COMPONENT LIBRARY to define
1. Stat card — small Arabic label above, large number below,
   optional delta chip. Used in rows of 4–6.
2. Data table — dense, 36px rows, sticky header, zebra-free,
   1px #262d3f row separators, numeric columns right-aligned
   with tabular figures, sortable headers.
3. Status chip — small pill, 4 variants (up / down / warn /
   info), always with a text label, never color alone.
4. Coverage bar — a thin horizontal bar with a percentage and a
   count like "28 / 326", used to show how complete a dataset is.
5. Progress panel — label, thin progress bar, "125/326", elapsed
   and estimated remaining time.
6. Empty state — icon, one Arabic sentence saying exactly what is
   missing, and one primary button that fixes it.
7. Degraded banner — amber outlined bar, transparent background,
   used when the system is running on incomplete data.
8. Candlestick chart panel — dark, green/red candles, volume
   histogram beneath, horizontal level lines with small labels.

NON-NEGOTIABLE — these define the product
- Every aggregate number is shown WITH its coverage. A sector
  average computed from 28 of 326 companies must display
  "التغطية 8.6%" next to it, and the table must be visibly
  de-emphasized (dimmed, amber banner) below a threshold. A
  confident-looking number over thin data is the single worst
  failure this interface can produce.
- Missing data is shown as "—" in muted grey. Never 0, never a
  blank cell, never a dash that looks like a value.
- A statistic from a small sample carries a ⚠ marker with a
  tooltip stating the sample size.
- Long operations never look frozen: they show a progress panel
  with a live counter and elapsed time.
- Every blocked or failed action states the REASON and the next
  action, in one Arabic sentence. Never a bare "خطأ".
- Disabled controls look clearly disabled and carry a tooltip
  explaining what would enable them.

TONE
Calm, factual, engineering-grade. No gradients, no glow, no
glassmorphism, no illustrations, no emoji. Flat surfaces, one
subtle border, color used only to carry meaning.
```

---

## ٢) برومبتات الشاشات — واحدة في كل مرّة

### ٢-١ · الماسح (الشاشة الرئيسية)

```
Screen: "الماسح" (Market Scanner) — the main working screen.

Top: page title "الماسح" with a subtitle "ما الفرص المتاحة الآن
على السوق السعودي · يومي؟". Right of it, timeframe pills:
15m · 1h · 4h · 1d · 1w.

Filter bar (one dense wrapping row of small pill buttons):
- Group 1: الكل · فيها توصية · شراء الآن · شراء لاحقاً ·
  مكتمل الشروط
- Group 2 (Sharia compliance): الكل · متوافق · يحتاج مراجعة ·
  إخفاء غير المتوافق
- Group 3 (liquidity): كل السيولات · عالية · متوسطة+ ·
  بلا الدقيقة
- A rows-per-page select and, pushed to the far side, two
  buttons: "مزامنة البيانات" (secondary) and "فحص السوق الآن"
  (primary).

A collapsible card "دليل شركات السوق السعودي" showing on its
header "326 شركة · 291 لها تاريخ · 35 بلا تاريخ". When open it
contains two numbered action buttons, a progress panel, a sector
analysis table with a prominent coverage indicator, and a
searchable company table.

Five stat cards in a row: رموز مفحوصة · مكتمل الشروط ·
تعذّر جلبها · زمن المسح · آخر تحديث.

Main results table, dense, ~15 visible rows, columns right to
left: الرمز · التوصية · النقاط · الدخول · الوقف · الهدف · R:R ·
التقاء · الأسباب · الفريم الأعلى · إغلاق الشمعة · السعر الآن ·
الانزياح.
- الرمز is a link with a small expand chevron.
- التوصية is either a muted "لا توصية" or an amber-tinted chip
  with text like "شراء عند الارتداد A".
- النقاط is a signed number, green positive, red negative.
- الوقف red, الهدف green, الدخول neutral.
- التقاء shows "3/3" style fractions.
- Rows with no recommendation are visually quieter than rows
  with one — the eye must land on the actionable rows first.

Show one row EXPANDED: it reveals an inline candlestick chart
(about 180px tall) plus a compact analysis strip with labelled
values: النقاط · القرار · الالتقاء · الفريم الأعلى · RSI · RVOL ·
ATR% · شموع, then a recommendation line: دخول · وقف · هدف · ع/م ·
التقدير.
```

### ٢-٢ · الصفقات

```
Screen: "الصفقات" (Trades).

Stat cards: صفقات مفتوحة · معلّقة · رابحة · خاسرة · متوسّط R ·
نسبة الفوز — each with a small confidence interval in muted text
beneath the win-rate card, e.g. "[42–58%] · 287 صفقة".

Tabs: الكل · مفتوحة · معلّقة · محسومة · منتهية.

Table columns right to left: الرمز · السوق · الفريم · الاتجاه ·
الدخول · الوقف · الهدف · السعر الآن · R المحقّق · الحالة ·
تاريخ الفتح · تاريخ الحسم.
- R المحقّق is the emphasized column: green positive, red
  negative, always signed, two decimals.
- الحالة is a status chip: رابحة (green) · خاسرة (red) ·
  مفتوحة (blue) · معلّقة (amber) · منتهية (grey).

Each settled row has a "تشريح" button opening a side panel:
a verdict on DECISION QUALITY separate from OUTCOME, shown as a
2×2 matrix highlighting the current cell, with the cell
"قرار ضعيف · ربح" labelled "أخطر حالة". Below it, the entry-time
evidence, and explicitly what was NOT known at entry.
```

### ٢-٣ · التحليلات

```
Screen: "التحليلات" (Analytics) — post-mortem statistics.

A prominent coverage/sample header: "287 صفقة محسومة · 43.5%
نسبة فوز الأساس".

Section 1 — what separates winners from losers: a horizontal
bar chart of effect sizes (Cohen's d), bars extending right for
positive and left for negative from a center line, each labelled
in Arabic. Bars that survive multiple-comparison correction are
solid; those that do not are outlined and dimmed, with a legend
explaining the difference.

Section 2 — tag performance table: العلامة · العدد · نسبة الفوز ·
فاصل الثقة · p · الحكم. The حكم column reads either
"يفصل (بعد التصحيح)" in green or "ضمن الصدفة" in muted grey.
Rows below the minimum sample size carry a ⚠.

Section 3 — exit-rule simulation: a small table comparing exit
rules by average R, with the currently active rule marked.

Design intent: this screen must make it obvious which findings
are real and which are noise. The visual weight of a finding must
match its statistical strength, not its size.
```

### ٢-٤ · لوحة التشغيل

```
Screen: "لوحة التشغيل" (Operations Dashboard) — system health.

Grid of market cards, one per market (crypto · السوق الأمريكي ·
السوق السعودي). Each card shows:
- Market name and an open/closed chip ("السوق مفتوح" green /
  "مغلق · يفتح الأحد 10:00" grey).
- A freshness distribution bar segmented into حديث / متأخّر /
  حرج / بلا ملف / مشطوب with counts.
- Last scan: "#108 · قبل ساعتين · 326 رمزاً".
- Symbol universe source chip: "دليل الشركات" / "اكتشاف تلقائي" /
  "الكون المحفوظ" / "قائمة الملف" — the last two amber.

Below: a background-jobs panel listing running tasks with live
progress bars, and a recent-events log with timestamps, where
warnings are amber and errors red.

This screen answers one question: "is the system actually
working, or does it only look like it?" Design it so a silent
failure is impossible to miss.
```

### ٢-٥ · صفحة الرمز

```
Screen: symbol detail page for e.g. "2222.SR — أرامكو السعودية".

Header: symbol, Arabic company name, sector, sub-market chip
(تاسي / نمو), current price with change, and timeframe pills.

Large candlestick chart (~460px) with a volume histogram beneath.
Overlays: VWAP line, volume-profile histogram drawn horizontally
on the left edge with POC / VAH / VAL marked, and horizontal
support/resistance lines with small right-side labels.

Right column of compact info cards:
- التوصية: action, دخول / وقف / هدف, R:R, التقدير.
- التقييم: score, decision, الالتقاء, الفريم الأعلى.
- المؤشّرات: RSI · RVOL · ATR% · موضع السعر من منطقة القيمة.
- الأساسيات: مكرّر الربحية · ربحية السهم · نطاق 52 أسبوعاً —
  showing "—" for any value the data plan does not provide.

Tabs beneath the chart: الصفقات السابقة · تحليل الذكاء ·
البيانات.
```

### ٢-٦ · الإعدادات

```
Screen: "الإعدادات" (Settings).

Left-side (RTL: right-side) vertical section nav: الأسواق ·
المصادر والمفاتيح · عتبات التقييم · إدارة المخاطر · التنبيهات ·
الذكاء الاصطناعي · الأداء.

Form style: label above field, a one-line Arabic explanation
beneath each field in muted text, and — where relevant — the
measured consequence of the setting, e.g. beneath "عدد العمّال":
"القياس على جهازك: 66 ms للرمز · 300 رمز ≈ 20ث".

API-key fields are masked, showing only length and status chip
("مضبوط · 58 حرفاً" green, or "غير مضبوط" amber), with a
"اختبار الاتصال" button beside each that reports per-endpoint
results, e.g. "‏/companies/‎ متاح · ‏/historical/‎ يحتاج باقة
Starter".

Sticky footer bar: "حفظ التغييرات" primary, "استعادة الافتراضي"
text button, and unsaved-change count.
```

---

## ٣) ما تطلبه من Stitch بعد التصميم

اطلب منه صراحةً:

```
Export the design system as CSS custom properties matching the
token names I gave, and give me the component specs (padding,
font size, line height, border, state colors) for: stat card,
data table row, status chip, coverage bar, progress panel,
empty state, degraded banner.
```

هذه الخطوة هي التي تجعله **معياراً** لا صورة: التوكِنات تدخل
`design-system.css` مباشرةً، ومواصفات المكوّنات تصير المرجع الذي
يُقاس عليه أي عنصر جديد.

---

## ٤) ملاحظة على الحدود

Stitch يصمّم الشكل لا السلوك. وأربعة أشياء في هذا النظام سلوكٌ
لا شكل، فلا تتوقّع منه أن يحلّها:

- **متى يُعرَض الرقم ومتى يُحجب** — قاعدة التغطية منطقٌ في
  الخادم، والتصميم يعرض نتيجتها.
- **ما الذي يُعدّ عيّنةً كافية** — رقمٌ إحصائي لا خيار بصري.
- **ترتيب مصادر البيانات عند التعثّر** — الدليل ثمّ الاكتشاف ثمّ
  المحفوظ ثمّ الملف.
- **الفرق بين «متأخّر» و«مشطوب»** — تصنيفٌ يُحسب بزمن السوق.

خذ منه الشكل، واحتفظ بهذه في الشيفرة حيث تُختبر.
