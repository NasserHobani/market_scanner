# -*- coding: utf-8 -*-
"""عناصر التنقّل — مصدرٌ واحد لكل صفحة.

═══ لماذا هنا لا في القالب ═══

كانت الروابط مكتوبة في ``base.html`` مرّة لسطح المكتب. وأيّ نسخة
ثانية للجوّال تعني قائمتين تتباعدان: يُضاف رابطٌ في إحداهما ويُنسى
في الأخرى، فيصير التنقّل مختلفاً باختلاف عرض الشاشة — وهو عطبٌ لا
يظهر إلّا لمن يفتح الصفحة على جهازٍ آخر.

فالقائمة بيانات، والقالب يرسمها.

═══ والأيقونات رسمٌ مضمَّن ═══

خطّ الأيقونات (Material Symbols) يعرض **اسم الأيقونة نصّاً** إن لم
يُحمَّل — «dashboard» و«swap_horiz» وسط واجهة عربية. والرسم
المضمَّن لا شبكة له فلا يفشل.

وحدُّ الخطّ ‎2px‎ وأطرافه مستديرة، كما ينصّ نظام التصميم.
"""
from __future__ import annotations

# ترتيب مراحل العمل: راقب ← جِد ← نفّذ ← افهم ← حسّن.
# و``gap`` يفصل المرحلة عن التي تليها بصرياً.
NAV = (
    ("dashboard", "لوحة التشغيل", "/",
     '<path d="M4 4h7v7H4zM13 4h7v4h-7zM13 10h7v10h-7zM4 13h7v7H4z"/>',
     False),
    ("scanner", "الماسح", "/scanner/",
     '<path d="M4 19V9M9 19V5M14 19v-6"/>'
     '<circle cx="18.5" cy="8.5" r="3"/><path d="M20.8 10.8L23 13"/>',
     False),
    ("golden", "الصفقات الذهبية", "/golden/",
     '<path d="M12 3l2.6 5.6 6.1.8-4.5 4.2 1.2 6.1L12 16.8 6.6 19.7l1.2-6.1'
     'L3.3 9.4l6.1-.8z"/>',
     False),
    ("pes", "ما قبل الانفجار", "/pes/",
     '<path d="M12 2v6M12 16v6M2 12h6M16 12h6"/>'
     '<circle cx="12" cy="12" r="3.5"/>',
     False),
    ("pes_history", "سجلّ الرصد", "/pes/history/",
     '<path d="M12 8v5l3 2"/><path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1"/>'
     '<path d="M3 4v4h4"/>',
     False),
    ("squeeze", "قياس الانضغاط", "/squeeze/",
     '<path d="M13 2L4.5 13H11l-1 9 8.5-11H12z"/>',
     False),
    # قائمةٌ بأسطر: جردٌ لا تحليل
    ("symbols", "دليل الرموز", "/symbols/",
     '<path d="M4 6h16M4 12h16M4 18h10"/><circle cx="19" cy="18" r="2"/>',
     False),
    # لبِنات: استراتيجيةٌ تُبنى من شروط
    ("strategies", "بناء الاستراتيجيات", "/strategies/",
     '<path d="M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4z"/>'
     '<path d="M16.5 16.5v4M14.5 18.5h4"/>',
     False),
    # أعمدة: لوحة البطاقات
    ("board", "لوحة الاستراتيجيات", "/board/",
     '<path d="M3 4h5v16H3zM10 4h5v11h-5zM17 4h4v7h-4z"/>',
     True),
    # ثلاثة أسهمٍ نازلة: أسبوعيّ ← يوميّ ← ٤س
    ("topdown", "من الأعلى للأسفل", "/topdown/",
     '<path d="M4 5h16M7 12h10M10 19h4"/>'
     '<path d="M12 5v14"/>',
     False),
    ("watches", "المراقبة", "/watches/",
     '<path d="M2 12s3.6-6 10-6 10 6 10 6-3.6 6-10 6-10-6-10-6z"/>'
     '<circle cx="12" cy="12" r="2.5"/>',
     True),
    ("paper", "المحفظة الورقية", "/paper/",
     '<path d="M3 7h18v12H3z"/><path d="M3 7l3-3h12l3 3"/>'
     '<circle cx="12" cy="13" r="2"/>',
     False),
    ("trades", "الصفقات", "/trades/",
     '<path d="M4 8h13l-3-3M20 16H7l3 3"/>',
     True),
    ("ai", "مركز الذكاء", "/ai/",
     '<path d="M12 3a4 4 0 0 0-4 4v1a3 3 0 0 0 0 6v2a3 3 0 0 0 3 3h1z"/>'
     '<path d="M12 3a4 4 0 0 1 4 4v1a3 3 0 0 1 0 6v2a3 3 0 0 1-3 3h-1z"/>',
     False),
    ("btc", "البتكوين", "/btc/",
     '<path d="M9 5v14M13 5v14M7 8h7a3 3 0 0 1 0 6H7h7a3 3 0 0 1 0 6H7V8z"/>',
     False),
    ("analytics", "التحليلات", "/analytics/",
     '<path d="M4 20V6M10 20v-9M16 20v-5M22 20H2"/>',
     True),
    ("research", "مختبر البحث", "/research/",
     '<path d="M9 3v6l-5 9a2 2 0 0 0 1.7 3h12.6a2 2 0 0 0 1.7-3l-5-9V3"/>'
     '<path d="M8 3h8M7.5 15h9"/>',
     False),
    ("jobs", "المهامّ المجدولة", "/jobs/",
     '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
     True),
    ("blocked", "الرموز المحظورة", "/blocked/",
     '<circle cx="12" cy="12" r="9"/><path d="M5.6 5.6l12.8 12.8"/>',
     False),
    ("optimization", "تحسين الاستراتيجية", "/optimization/",
     '<path d="M12 3v3M12 18v3M3 12h3M18 12h3"/>'
     '<circle cx="12" cy="12" r="4"/><path d="M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1"/>',
     False),
)


def nav(request) -> dict:
    """عناصر الشريط الجانبي.

    الماسح وحده يحمل السوق والفريم في رابطه: العودة إليه من صفحةٍ
    أخرى يجب أن تُعيدك إلى السوق الذي كنت فيه لا إلى الافتراضي.
    """
    market = request.GET.get("market") or ""
    tf = request.GET.get("tf") or ""
    items = []
    for key, label, href, icon, gap in NAV:
        if key == "scanner" and market:
            href = f"/scanner/?market={market}" + (f"&tf={tf}" if tf else "")
        items.append({"key": key, "label": label, "href": href,
                      "icon": icon, "gap": gap})
    return {"nav_items": items}
