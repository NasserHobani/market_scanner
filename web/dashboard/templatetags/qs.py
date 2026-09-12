"""بناء روابط تُبدّل معاملاً واحداً وتُبقي الباقي.

الحاجة: مبدّل الفريم في الشريط العلوي كان يبني «?market=..&tf=..» من الصفر،
فيضيع «q» و«symbol» في صفحة البحث ويعود المستخدم إلى صفحة فارغة.
"""
from django import template
from django.utils.http import urlencode

register = template.Library()


@register.simple_tag(takes_context=True)
def qs_set(context, **kwargs) -> str:
    """يعيد سلسلة استعلام كاملة مع تبديل/حذف المفاتيح الممرّرة.

    القيمة None تحذف المفتاح. تُستدعى: {% qs_set tf=tf.key %}
    """
    request = context.get("request")
    params = request.GET.copy() if request is not None else {}
    try:
        params = params.copy()
    except AttributeError:  # dict عادي في الاختبارات
        params = dict(params)
    for key, value in kwargs.items():
        # النصّ الفارغ يحذف أيضاً: قوالب Django لا تعرف القيمة None،
        # فـ {% qs_set market=None %} يصل هنا نصّاً فارغاً لا None
        if value is None or value == "":
            params.pop(key, None)
        else:
            params[key] = value
    pairs = params.lists() if hasattr(params, "lists") else \
        [(k, [v]) for k, v in params.items()]
    flat = [(k, v) for k, values in pairs for v in values]
    return ("?" + urlencode(flat)) if flat else ""


@register.simple_tag(takes_context=True)
def qs_hidden(context, *owned) -> str:
    """حقول مخفيّة تحمل مرشّحات العنوان التي لا يملكها النموذج.

    ═══ لماذا ═══

    نموذج ‏GET يرسل حقوله وحدها. فبحثٌ بالرمز داخل نموذجٍ لا يحمل
    ``source`` و``status`` يمحوهما من العنوان — يضغط المستخدم
    «طبّق» فتقفز الصفحة من «محسومة · يدوية» إلى الافتراضي، ويبدو
    أنّ البحث أعاد نتائج خاطئة وهو أعاد نطاقاً آخر.

    والأسماء الممرّرة هي ما **يملكه** النموذج فتُستثنى: حقلٌ
    مخفيّ باسمٍ له خانة ظاهرة يُرسل مرّتين، والخادم يأخذ الأولى —
    أي القيمة القديمة.
    """
    from django.utils.html import format_html, format_html_join

    request = context.get("request")
    if request is None:
        return ""
    skip = set(owned)
    pairs = [(k, v) for k in request.GET
             for v in request.GET.getlist(k)
             if k not in skip and v != ""]
    if not pairs:
        return ""
    return format_html_join(
        "\n", '<input type="hidden" name="{}" value="{}">', pairs)
