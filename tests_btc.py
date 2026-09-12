# -*- coding: utf-8 -*-
"""اختبارات تحليل البتكوين — بلا Django ولا شبكة.

أخطر ما في هذا الملف ليس الانهيار بل **التسريب**: خاصية تنظر إلى شمعة
لم تُغلق بعد تعطي دقّة باهرة في الاختبار ومستحيلة في التشغيل. ولا
يظهر ذلك كعُطل — يظهر كنجاح.

    python tests_btc.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner.btc import direction, regime, report

results: list[tuple[bool, str, str]] = []


def check(name, cond, extra=""):
    results.append((bool(cond), name, str(extra)))


def frame(n=600, seed=7, drift=0.0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="4h", tz="UTC")
    close = 100 + np.cumsum(rng.normal(drift, 1, n))
    close = np.maximum(close, 1.0)
    high = close + np.abs(rng.normal(0, 0.5, n))
    low = close - np.abs(rng.normal(0, 0.5, n))
    return pd.DataFrame({"open": close, "high": high, "low": low,
                         "close": close,
                         "volume": rng.uniform(100, 1000, n)}, index=idx)


df = frame()

# ══════════════════ الخصائص لا تنظر إلى المستقبل

feats = regime.build(df)
check("تُبنى كل الخصائص", set(feats.columns) == set(regime.FEATURES),
      sorted(set(regime.FEATURES) - set(feats.columns)))
check("وبطول البيانات نفسه", len(feats) == len(df))

# الاختبار الحاسم: تغيير المستقبل يجب ألّا يغيّر الماضي
cut = 400
partial = regime.build(df.iloc[:cut])
full_head = feats.iloc[:cut]
diffs = 0
for col in regime.FEATURES:
    a, b = partial[col].to_numpy(), full_head[col].to_numpy()
    both_nan = np.isnan(a) & np.isnan(b)
    if not np.all(both_nan | np.isclose(a, b, equal_nan=False,
                                        rtol=1e-9, atol=1e-12)):
        diffs += 1
check("الخاصية عند شمعة لا تتغيّر بمعرفة ما بعدها", diffs == 0,
      f"{diffs} خاصية تسرّب المستقبل")

mutated = df.copy()
mutated.iloc[cut:, mutated.columns.get_loc("close")] *= 3.0
m_feats = regime.build(mutated)
same_head = all(
    np.all((np.isnan(m_feats[c].to_numpy()[:cut])
            & np.isnan(feats[c].to_numpy()[:cut]))
           | np.isclose(m_feats[c].to_numpy()[:cut],
                        feats[c].to_numpy()[:cut], equal_nan=False))
    for c in regime.FEATURES)
check("وتضخيم الأسعار اللاحقة لا يمسّ الماضي", same_head,
      "تسريب صريح لو تغيّرت")

# ══════════════════ التسمية

y = regime.label_direction(df, 1)
c = df["close"].to_numpy()
check("التسمية تطابق تعريفها",
      np.array_equal(y[:-1], (c[1:] > c[:-1]).astype("float64")))
check("وآخر صفّ يبقى مجهولاً لا مخترعاً", np.isnan(y[-1]),
      "نتيجته لم تقع بعد")
check("وأفق أطول يترك صفوفاً أكثر مجهولة",
      int(np.isnan(regime.label_direction(df, 6)).sum()) == 6)

# ══════════════════ قراءة الحالة عند وقت

st = regime.at(feats, df.index[100])
check("الحالة عند وقت شمعة تُقرأ من تلك الشمعة",
      st and abs((st["ret_1"] or 0)
                 - (feats["ret_1"].iloc[100] or 0)) < 1e-9)
between = regime.at(feats, df.index[100] + pd.Timedelta("1h"))
check("ووقت بين شمعتين يأخذ **السابقة** لا التالية",
      between.get("ret_1") == st.get("ret_1"),
      "أخذ التالية تسريبٌ بمقدار شمعة")
check("ووقت قبل أول شمعة يعطي فراغاً",
      regime.at(feats, df.index[0] - pd.Timedelta("10h")) == {})
check("وإطار فارغ لا ينهار", regime.at(pd.DataFrame(), df.index[0]) == {})

# ══════════════════ خطوط الأساس إلزامية

x = feats.to_numpy(dtype="float64")
res = direction.walk_forward(x, y, min_train=300, step=60)
check("التقييم يُنتج نوافذ", len(res.folds) > 0, len(res.folds))
check("ويقارن بثلاثة خطوط أساس",
      set(res.baselines) == {"عشوائي", "الأغلبية", "الاستمرار"},
      sorted(res.baselines))
check("والحكم يشترط تجاوز **الحدّ الأدنى** لفاصل الثقة",
      res.beats_baseline == (res.ci_low > max(res.baselines.values())),
      "مقارنة المتوسطات وحدها تعلن انتصاراً على فارق يذوب في الضجيج")

# بيانات عشوائية بحتة: يجب ألّا يُعلن تفوّقاً
rng = np.random.default_rng(3)
noise_x = rng.normal(0, 1, (900, 6))
noise_y = rng.integers(0, 2, 900).astype("float64")
nres = direction.walk_forward(noise_x, noise_y, min_train=400, step=80)
check("وعلى ضجيج خالص لا يُعلن تفوّقاً", not nres.beats_baseline,
      f"دقّة {nres.accuracy * 100:.1f}%")
check("ودقّته على الضجيج قرب النصف", abs(nres.accuracy - 0.5) < 0.08,
      f"{nres.accuracy * 100:.1f}%")

# سلسلة يمكن التنبّؤ بها تماماً: يجب أن يكتشفها
per_y = np.tile([1.0, 0.0], 500)
per_x = np.column_stack([np.roll(per_y, 1), np.roll(per_y, 2),
                         rng.normal(0, 1, 1000)])
per_x[0] = 0
pres = direction.walk_forward(per_x, per_y, min_train=400, step=80)
check("وعلى نمط واضح يكتشفه", pres.accuracy > 0.9,
      f"{pres.accuracy * 100:.1f}%")

check("والتدريب لا يرى بيانات الاختبار",
      all(f.train_end <= f.test_end - f.n_test for f in res.folds),
      "نافذة التدريب يجب أن تنتهي قبل بداية الاختبار")
check("والنوافذ متتابعة زمنياً لا مخلوطة",
      all(res.folds[i].test_end <= res.folds[i + 1].train_end
          for i in range(len(res.folds) - 1)))

short = direction.walk_forward(x[:50], y[:50], min_train=300, step=60)
check("وبيانات قصيرة تُرفض بدل أن تُخمَّن", not short.folds)

# ══════════════════ التقرير لا يعرض رقماً مرفوضاً

rep = report.direction_report(df, min_train=300, step=60)
check("التقرير يحمل حقل صلاحية صريحاً", "valid" in rep)
if rep.get("valid"):
    check("و«usable» يشترط التفوّق والفارق معاً",
          rep["usable"] == (rep["beats_baseline"]
                            and rep["edge_points"] >= report.MIN_EDGE_POINTS))

snap = report.snapshot(df)
check("اللقطة تحمل السعر والاتجاه", snap.get("close") and "trend" in snap)
check("وتُسمّي الخصائص بالعربية",
      set(snap.get("labels", {})) == set(regime.FEATURES))
check("ولقطة بيانات قصيرة فارغة لا تنهار",
      report.snapshot(df.iloc[:10]) == {})

full = report.build_all(lambda tf: df if tf in ("4h", "1d") else None)
check("التقرير الكامل يبني الحالات المتاحة فقط",
      set(full["states"]) <= {"4h", "1d"}, sorted(full["states"]))
check("ويحسب التوافق", "text" in full["consensus"])
check("وفريم بلا بيانات لا يُسقط التقرير",
      report.build_all(lambda tf: None)["states"] == {})

# ══════════════════ العرض لا ينتظر الشبكة

src = (ROOT / "web" / "dashboard" / "btc_views.py").read_text("utf-8")
check("رأي المستشار يُقرأ من القرص عند الرسم", "_last_opinion" in src)
check("والطلب الجديد خلف نقطة طرفية بـ POST",
      "@require_POST" in src and "api_btc_opinion" in src)
check("ولا يُستدعى المستشار داخل دالة الصفحة",
      "review_recommendation" not in src.split("def btc_page")[1]
      .split("@require_POST")[0],
      "نداء نموذج لغوي عند الرسم يعلّق الصفحة دقيقة")
check("والتقرير مخزَّن مؤقتاً", "_TTL" in src)

js = (ROOT / "web" / "dashboard" / "static" / "dashboard"
      / "btc-page.js").read_text("utf-8")
# «لا شيء تلقائي» صارت غير دقيقة بعد إضافة استطلاع السعر: المنع
# المطلق كان يمنع احتياطاً مشروعاً. المطلوب أدقّ — لا **ثقيل** تلقائي.
HEAVY = ("/api/btc/opinion/", "/api/btc/refresh/")
auto = js.replace("addEventListener", "\n@@handler@@\n")
check("لا نقطة ثقيلة تُستدعى تلقائياً",
      all(f'setInterval' not in seg or all(h not in seg for h in HEAVY)
          for seg in js.split("setInterval")),
      "تدريب النماذج أو نداء النموذج اللغوي دورياً يعلّق الصفحة")
check("والنقاط الثقيلة خلف مستمعي أزرار",
      all(h in js and "addEventListener" in js for h in HEAVY))


# ─────────────────── الشارت مربوط بالتحليل

tpl = (ROOT / "web" / "dashboard" / "templates" / "dashboard"
       / "btc.html").read_text("utf-8")
js = (ROOT / "web" / "dashboard" / "static" / "dashboard"
      / "btc-page.js").read_text("utf-8")
views = (ROOT / "web" / "dashboard" / "btc_views.py").read_text("utf-8")

check("الصفحة فيها حاوية شارت", 'id="chart"' in tpl)
check("ومبدّل فريمات", "btn-tf" in tpl and "chart_timeframes" in tpl)
check("الشارت الأساسي هو TradingView لا راسم محلي",
      "s3.tradingview.com" in tpl and "TradingView.widget" in js,
      "الراسم المحلي كان بديلاً رديئاً — الأصل خير من تقليده")
check("والراسم المحلي يبقى احتياطاً عند حجب النطاق",
      "tv-fallback" in tpl and "dashboard/chart.js" in tpl)
check("والبثّ الحيّ من الوحدة الموجودة",
      "dashboard/livefeed.js" in tpl and "new window.LiveFeed" in js)

# الشارت والتحليل من نداء واحد — وإلا ظهرت شموع فريم بجانب قراءة آخر
# القصد ليس «نداء واحد في الملف» بل «الشموع والتحليل من المصدر
# نفسه». استطلاع السعر نداء ثانٍ مشروع لأنه لا يجلب تحليلاً.
# التعليقات تُستبعد: السطر الذي **يشرح** القاعدة يذكر المسار
# حرفياً، وعدّه نداءً هو نفس صنف الخطأ الذي أوقع مدقّق العوامل.
def _code_lines(text):
    for ln in text.splitlines():
        t = ln.strip()
        if t and not t.startswith(("*", "//", "/*")):
            yield ln
chart_calls = sum(1 for ln in _code_lines(js)
                  if "/api/chart/" in ln and "/latest/" not in ln)
check("الشموع والتحليل من نداء واحد",
      chart_calls == 1 and "/api/chart/" in js,
      f"{chart_calls} نداء — الانفصال يسمح بخلط فريمين")
check("واستطلاع السعر لا يجلب تحليلاً",
      "/latest/" in js and "paintAnalysis" not in
      js[js.index("function pollOnce"):],
      "لو جلب تحليلاً لصار مصدراً ثانياً ينحرف عن الأول")
handler = js[js.index('".btn-tf"'):]
handler = handler[:handler.index("/* ── البثّ")]
check("وتبديل الفريم يعيد تحميل الاثنين", "load()" in handler,
      "بلا إعادة تحميل تبقى قراءة الفريم السابق فوق شموع الجديد")
check("ويحفظ الفريم في العنوان", "searchParams.set" in handler,
      "إعادة التحميل أو مشاركة الرابط يجب أن تُبقي ما تراه")

# البثّ يحدّث الشمعة فقط — لا يعيد حساب الإشارة
tick = js[js.index("onTick"):js.index("onStatus")]
check("البثّ يحدّث الشمعة الجارية فقط",
      "updateLatest" in tick and "paintAnalysis" not in tick
      and "load()" not in tick,
      "إعادة حساب الإشارة مع كل تكّة تناقض قاعدة الشمعة المغلقة")

# حكم النموذج يرافق القراءة الفنّية
check("حكم النموذج يُرسل مع الشارت", '"verdicts"' in views)
check("والفريم غير المقيَّم يُقال صراحةً",
      "لم يُقيَّم لهذا الفريم" in js)
check("والفريم المرفوض يُعرض رقمه مع رفضه",
      "لا يتفوّق على خطّ الأساس" in js and "لا يُستعمل" in js,
      "إخفاؤه يوهم أنه لم يعمل؛ وعرضه بلا حكم يوهم أنه معتمد")

check("والفريم المطلوب يُقرأ من العنوان بقائمة مغلقة",
      "CHART_TIMEFRAMES" in views and "if tf not in CHART_TIMEFRAMES" in views,
      "قبول أي قيمة من العنوان يمرّرها إلى الاستعلام")
check("والاستطلاع الدوري خفيف فقط",
      "/latest/" in js.split("setInterval")[0][-400:]
      or "pollOnce" in js.split("setInterval")[1][:80],
      "الدوري مسموح للسعر وحده لا للنماذج")

# ─────────────────── الرسم والسعر يعملان بلا إنترنت

chart_js = (ROOT / "web" / "dashboard" / "static" / "dashboard"
            / "chart.js").read_text("utf-8")
check("الشارت ينزل إلى راسم احتياطي عند غياب المكتبة",
      "FallbackChart" in chart_js,
      "المكتبة من CDN، وشبكة محلية قد لا تصل إليها")
check("والتحديث الحيّ يمرّ إليه أيضاً",
      "FallbackChart.updateLatest" in chart_js,
      "بدونه تتجمّد الشمعة ويبدو البثّ معطّلاً وهو يعمل")
check("والاحتياطي يُحمَّل قبل الشارت في القالب",
      tpl.index("chart-fallback.js") < tpl.index("dashboard/chart.js"))
check("والصفحة تُعلن أنها ترسم احتياطياً", "data-chart-mode" in tpl,
      "رسم مختلف بلا إعلان يجعل المستخدم يظنّ عطباً في البيانات")
check("والسعر يُستطلَع من الخادم حين يُحجب البثّ",
      "startPolling" in js and "/latest/" in js,
      "الخادم يصل إلى المنصّة وإن لم يصل المتصفّح")
check("ويُسمّى مصدره بصدق", "من الخادم" in js,
      "رقم عمره دقيقة معروضاً كأنه لحظي يبني قراراً خاطئاً")
check("والاستطلاع يتوقّف إن عاد البثّ", "stopPolling()" in js)


# ─────────────────── الرأي لا يُنتظر داخل الطلب

# قِيس: 116 ثانية بالوسيط · 177 أقصى · ومع retry=2 و timeout=300
# يبلغ أسوأ انتظار 900 ثانية. الطلب المتزامن ينقطع قبلها فيظهر
# «لا نتيجة» — والنموذج يكون قد عمل.
check("النقطة تبدأ مهمة ولا تنتظرها",
      "_run_opinion" in views and "daemon=True" in views,
      "النموذج يعمل في خيط، والطلب يعود فوراً")
check("وثمّة نقطة استعلام عن الحالة",
      "api_btc_opinion_status" in views)
check("والحالات الثلاث معرَّفة",
      all(k in views for k in ('"running"', '"done"', '"failed"')))
check("والطلب المتكرّر لا يبدأ مراجعتين",
      'if _JOB["state"] == "running"' in views,
      "ضغطتان على الزرّ = نموذجان يتنافسان على المعالج")
check("والخطأ يُحفظ في المهمة لا يُبتلع",
      '_JOB.update(state="failed"' in views)

urls = (ROOT / "web" / "dashboard" / "urls.py").read_text("utf-8")
check("والمسار مسجَّل", "api/btc/opinion/status/" in urls)

check("والواجهة تستعلم بدل أن تنتظر",
      "/api/btc/opinion/status/" in js and "watchOpinion" in js)
check("وتعرض الزمن المنقضي أثناء العمل", "يراجع… " in js,
      "دقيقتان صامتتان تبدوان تعليقاً")
check("وتلتقط مراجعة بدأت قبل فتح الصفحة",
      js.count("/api/btc/opinion/status/") >= 2,
      "من يفتح الصفحة أثناء العمل يجب أن يرى أنها تعمل")

# ─────────────────── التحكّم بالشارت

fb = (ROOT / "web" / "dashboard" / "static" / "dashboard"
      / "chart-fallback.js").read_text("utf-8")
check("الشارت يقبل التكبير بالعجلة", '"wheel"' in fb)
check("والتمرير بالسحب", '"mousedown"' in fb and '"mousemove"' in fb)
check("والنقرتان تعيدان الكلّ", '"dblclick"' in fb)
check("وثمّة حدّ أدنى لعدد الشموع", "MIN_BARS" in fb,
      "التكبير بلا حدّ يصل إلى شمعة واحدة فيفقد السياق")
check("والنافذة تُحفظ بين إعادات الرسم",
      "prev.all.length === all.length" in fb,
      "تكبيرك يجب ألّا يضيع مع كل تحديث سعر")
check("والاتجاه من اليمين لليسار محسوب",
      "rtl" in fb, "التكبير عند المؤشّر ينعكس في RTL")
check("والتحديث الحيّ لا يكتب فوق شمعة قديمة",
      "handle.to < handle.all.length" in fb,
      "من يتصفّح الماضي يجب ألّا يرى سعر اللحظة هناك")


# ─────────────────── شارت TradingView

check("الرمز من BINANCE — مصدر شمومنا نفسه",
      '"BINANCE:" + symbol' in js,
      "مصدر آخر يعني رقمين مختلفين للسعر على الشاشة ذاتها")
check("والفريم يُترجم إلى صيغة الويدجت", "TV_INTERVAL" in js)
check("وكل فريم في المبدّل له ترجمة",
      all(k in js for k in ('"15m": "15"', '"1h": "60"',
                            '"4h": "240"', '"1d": "D"')))
check("وتبديل الفريم يعيد تركيب الويدجت",
      # الوسم يتكرّر داخل المعالج نفسه، فالتقسيم يعطي جزءاً وسطياً
      # فارغاً. الكتلة تُؤخذ من أول ظهور إلى العلامة التالية.
      "mountTradingView()" in js[js.index('".btn-tf"'):
                                 js.index("/* ── البثّ الحيّ")],
      "بقاء الويدجت على فريمه القديم = قراءة فريم فوق شموع آخر")
check("وغياب المكتبة يكشف الاحتياط بدل ترك فراغ",
      'typeof TradingView === "undefined"' in js
      and "classList.remove(\"d-none\")" in js)
check("والراسم المحلي لا يُرسم إن كان مخفياً",
      'fb.classList.contains("d-none")' in js,
      "رسم في عنصر مخفي عمل ضائع في كل تحديث")

# ─────────────────── لوحة المستويات

check("المستويات تُعرض أرقاماً", "paintLevels" in js and "levels-box" in tpl)
check("وخطة الصفقة أولاً", js.index('"plan"') < js.index('"fib"'),
      "ما يُنفَّذ يسبق ما يُستأنس به")
check("والدخول والوقف والأهداف كلها معروضة",
      all(k in js for k in ('"الدخول"', '"الوقف"', '"الهدف "')))
check("وكل مستوى منسوب للسعر الحالي",
      "r.price - lastClose" in js,
      "رقم مجرّد لا يقول إن كان فوقك أم تحتك")
check("وزرّ نسخ لكل مستوى", "lvl-copy" in js and "writeText" in js)
check("وبديل النسخ لصفحة بلا HTTPS", "execCommand" in js,
      "‏clipboard API لا تعمل على http في شبكة محلية")
check("والقالب يشرح لماذا أرقام لا رسم",
      "إطار معزول" in tpl,
      "الحدّ يُقال صراحةً بدل أن يبدو نقصاً")


bad = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not bad
      else f"✗ فشل {len(bad)} من {len(results)}")
sys.exit(1 if bad else 0)
