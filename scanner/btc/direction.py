# -*- coding: utf-8 -*-
"""نموذج اتجاه البتكوين — وقياسه مقابل خطوط أساس إلزامية.

═══ تحذير قبل أي سطر ═══

التنبّؤ باتجاه الشمعة القادمة أصعب مسألة في هذا الملف كله، والإجماع
البحثي أن العوائد قصيرة المدى قريبة جداً من العشوائية. فالغرض هنا ليس
إثبات أن النموذج يعمل، بل **قياس هل يتفوّق على الصدفة** — وهذا سؤال
له جواب قاطع.

ولذلك لا يُرجع هذا الملف دقّةً مجرّدة أبداً. كل نتيجة تأتي مقرونةً
بثلاثة خطوط أساس:

    عشوائي     : يخمّن بالتساوي
    الأغلبية   : يقول دائماً ما هو أكثر في التدريب
    الاستمرار  : يقول إن الشمعة القادمة كالسابقة

خطّ «الأغلبية» هو الأهمّ والأخبث: البتكوين صعد تاريخياً، فنسبة الشموع
الصاعدة تتجاوز 50٪ قليلاً. نموذج «يتعلّم» أن يقول «صاعد» دائماً يبلغ
دقّة 52٪ ويبدو ناجحاً — وهو لم يتعلّم شيئاً. مقارنته بالعشوائي وحده
تخفي هذا تماماً.

═══ Walk-Forward لا تقسيم عشوائي ═══

السلاسل الزمنية لا تُخلط. التدريب على 2026 والاختبار على 2023 تسريب
صريح للمستقبل. هنا: نافذة تدريب تتحرك للأمام، وكل تنبّؤ يُختبر على
بيانات **بعد** كل ما دُرِّب عليه.

═══ LightGBM اختياري ═══

إن لم يكن مثبَّتاً يعمل الملف ببديل بسيط (انحدار لوجستي بالنزول
التدرّجي، numpy خالص). والبديل ليس ترضية: إن تفوّق LightGBM على
النموذج البسيط بفارق ضئيل، فالتعقيد لا يشتري شيئاً — وهذه معلومة
تستحقّ المعرفة.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

try:                                    # اختياري بالكامل
    import lightgbm as lgb              # type: ignore
    HAS_LGB = True
except Exception:                       # noqa: BLE001
    lgb = None                          # type: ignore
    HAS_LGB = False


@dataclass
class Fold:
    train_end: int
    test_end: int
    n_train: int
    n_test: int
    accuracy: float
    base_rate: float
    predictions: np.ndarray = field(repr=False, default_factory=lambda: np.array([]))
    truth: np.ndarray = field(repr=False, default_factory=lambda: np.array([]))


@dataclass
class Result:
    name: str
    folds: list[Fold]
    accuracy: float
    baselines: dict[str, float]
    n_test: int
    edge: float          # الدقّة ناقص أفضل خطّ أساس
    ci_low: float
    ci_high: float
    beats_baseline: bool

    def summary(self) -> str:
        verdict = ("✓ يتفوّق على كل خطوط الأساس" if self.beats_baseline
                   else "✗ لا يتفوّق — النتيجة ضمن الصدفة")
        return (f"{self.name}: دقّة {self.accuracy * 100:.1f}% "
                f"({self.ci_low * 100:.1f}–{self.ci_high * 100:.1f}) على "
                f"{self.n_test} عيّنة · فارق {self.edge * 100:+.1f} نقطة · "
                f"{verdict}")


# ───────────────────────────── نموذج بسيط بلا مكتبات

def _logistic(x: np.ndarray, y: np.ndarray, *, epochs: int = 300,
              lr: float = 0.1) -> np.ndarray:
    """انحدار لوجستي بالنزول التدرّجي — numpy خالص.

    الخصائص تُعاير بمتوسط وانحراف **من التدريب وحده**؛ استعمال إحصاء
    الاختبار في المعايرة تسريب شائع لا يظهر إلا كأداء متفائل.
    """
    n, m = x.shape
    w = np.zeros(m + 1)
    xb = np.hstack([np.ones((n, 1)), x])
    for _ in range(epochs):
        z = xb @ w
        p = 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))
        w -= lr * (xb.T @ (p - y)) / max(1, n)
    return w


def _logistic_predict(w: np.ndarray, x: np.ndarray) -> np.ndarray:
    xb = np.hstack([np.ones((x.shape[0], 1)), x])
    z = xb @ w
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


# ───────────────────────────── التقييم

def _wilson(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = hits / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (c - m) / d), min(1.0, (c + m) / d)


def walk_forward(x: np.ndarray, y: np.ndarray, *, min_train: int = 400,
                 step: int = 60, use_lgb: bool = True,
                 seed: int = 0) -> Result:
    """تدريب متدحرج للأمام — كل تنبّؤ على بيانات لم تُرَ.

    ``min_train`` نافذة التدريب الأولى، و``step`` حجم كل نافذة اختبار.
    التدريب يتوسّع (كل الماضي) لا ينزلق: البتكوين يغيّر نظامه، وحصر
    التدريب في نافذة قصيرة يجعل النموذج ينسى الأنظمة السابقة.
    """
    ok = ~np.isnan(y) & ~np.isnan(x).any(axis=1)
    x, y = x[ok], y[ok]
    n = y.size
    folds: list[Fold] = []
    if n < min_train + step:
        return Result("غير كافٍ", [], 0.0, {}, 0, 0.0, 0.0, 0.0, False)

    # ‏``seed`` يبقى لبذرة النموذج وحدها — ولا مولّد عشوائيّ هنا
    # بعد أن صار خطّ الأساس العشوائي قيمتَه المتوقَّعة.
    all_pred: list[np.ndarray] = []
    all_true: list[np.ndarray] = []
    base_major: list[np.ndarray] = []
    base_persist: list[np.ndarray] = []

    end = min_train
    while end + step <= n:
        xa, ya = x[:end], y[:end]
        xb, yb = x[end:end + step], y[end:end + step]

        mu, sd = xa.mean(axis=0), xa.std(axis=0)
        sd[sd == 0] = 1.0
        if use_lgb and HAS_LGB:
            model = lgb.LGBMClassifier(
                n_estimators=200, learning_rate=0.05, num_leaves=15,
                min_child_samples=30, subsample=0.8, colsample_bytree=0.8,
                verbose=-1, random_state=seed)
            model.fit(xa, ya)
            prob = model.predict_proba(xb)[:, 1]
        else:
            w = _logistic((xa - mu) / sd, ya)
            prob = _logistic_predict(w, (xb - mu) / sd)
        pred = (prob >= 0.5).astype("float64")

        all_pred.append(pred)
        all_true.append(yb)
        # الأغلبية تُشتقّ من التدريب فقط — لا من الاختبار
        base_major.append(np.full(yb.size, 1.0 if ya.mean() >= 0.5 else 0.0))
        # الاستمرار: كالشمعة السابقة. أول عنصر يأخذ آخر تدريب.
        prev = np.concatenate(([ya[-1]], yb[:-1]))
        base_persist.append(prev)

        hits = float((pred == yb).sum())
        folds.append(Fold(end, end + step, end, yb.size,
                          hits / max(1, yb.size), float(ya.mean()),
                          pred, yb))
        end += step

    pred = np.concatenate(all_pred)
    truth = np.concatenate(all_true)
    n_test = truth.size
    acc = float((pred == truth).mean())

    # ═══ العشوائي قيمته المتوقَّعة لا رميةٌ واحدة ═══
    #
    # كان: ``rand = rng.integers(0, 2, n_test)`` ثمّ يُقاس. وهي
    # **عيّنةٌ واحدة** من موزّعٍ قيمته المتوقَّعة ٠٫٥ بالضبط —
    # وخطؤها المعياريّ على ٩٦٠ عيّنة نحو ١٫٦ نقطة، فتقع الرمية
    # بين ٤٧٪ و٥٣٪.
    #
    # وأثرُ ذلك ليس تجميلياً: ``best`` هو أعلى خطوط الأساس، وهو
    # السقف الذي يجب أن يتجاوزه حدُّ ثقة النموذج الأدنى. فحين
    # تحالف الحظّ الرمية بلغت ٥١٫٠٪ وصارت **أفضل خطّ أساس** —
    # فحُوكم النموذج على حظّ عملةٍ معدنية.
    #
    # والأسوأ أنّ ``seed`` ثابتٌ هنا لكنّ ``n_test`` يتغيّر مع كل
    # شمعةٍ جديدة، فيتغيّر خطّ الأساس بين تحديثٍ وآخر على البيانات
    # نفسها تقريباً. تقريرٌ لا يُعاد إنتاجه.
    #
    # والمخمّن العشوائي المتساوي دقّتُه المتوقَّعة ٥٠٪ مهما كانت
    # البيانات. فهذا هو الرقم.
    baselines = {
        "عشوائي": 0.50,
        "الأغلبية": float((np.concatenate(base_major) == truth).mean()),
        "الاستمرار": float((np.concatenate(base_persist) == truth).mean()),
    }
    best = max(baselines.values())
    lo, hi = _wilson(int((pred == truth).sum()), n_test)
    # التفوّق يعني أن **الحدّ الأدنى** لفاصل ثقة النموذج يتجاوز أفضل
    # خطّ أساس. مقارنة المتوسطات وحدها تعلن انتصاراً على فارق يذوب في
    # الضجيج.
    name = "LightGBM" if (use_lgb and HAS_LGB) else "انحدار لوجستي"
    # ``lo > best`` بين عددَي numpy يعيد ``np.bool_`` لا ``bool``.
    # يعبر كل شيء بلا شكوى — ``if`` والطباعة والمقارنة — حتى حدّ
    # التسلسل، فينهار ``/api/btc/refresh/`` برسالة تقول «‏bool غير
    # قابل للتسلسل» لأن ``np.bool_.__name__`` صار ``"bool"`` في
    # NumPy 2. الحقل موصوف ``bool`` في ``Result`` فليكن ``bool``.
    return Result(name, folds, float(acc), baselines, int(n_test),
                  float(acc - best), float(lo), float(hi), bool(lo > best))


def feature_importance(x: np.ndarray, y: np.ndarray, names: list[str],
                       *, seed: int = 0) -> list[tuple[str, float]]:
    """أهمية الخصائص بالتبديل: كم تنخفض الدقّة إن خُلطت خاصية واحدة.

    التبديل يُقاس على بيانات اختبار لا تدريب، فيقيس ما يعتمد عليه
    النموذج **فعلاً** لا ما استعمله في الحفظ.
    """
    ok = ~np.isnan(y) & ~np.isnan(x).any(axis=1)
    x, y = x[ok], y[ok]
    n = y.size
    if n < 200:
        return []
    cut = int(n * 0.7)
    xa, ya, xb, yb = x[:cut], y[:cut], x[cut:], y[cut:]
    mu, sd = xa.mean(axis=0), xa.std(axis=0)
    sd[sd == 0] = 1.0

    if HAS_LGB:
        model = lgb.LGBMClassifier(n_estimators=200, learning_rate=0.05,
                                   num_leaves=15, min_child_samples=30,
                                   verbose=-1, random_state=seed)
        model.fit(xa, ya)
        def score(z):
            return float((model.predict(z) == yb).mean())
    else:
        w = _logistic((xa - mu) / sd, ya)
        def score(z):
            p = _logistic_predict(w, (z - mu) / sd)
            return float(((p >= 0.5).astype("float64") == yb).mean())

    base = score(xb)
    rng = np.random.default_rng(seed)
    out: list[tuple[str, float]] = []
    for j, nm in enumerate(names):
        z = xb.copy()
        z[:, j] = rng.permutation(z[:, j])
        out.append((nm, base - score(z)))
    out.sort(key=lambda p: -p[1])
    return out
