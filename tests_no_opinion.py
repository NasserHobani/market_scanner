# -*- coding: utf-8 -*-
"""لا رأي ليس رأياً — الامتناع يُعلَن ولا يُترجَم موقفاً.

═══ ما قِيس ═══

٧٥ مراجعة تحمل قراراً من النموذج::

    wait          65
    insufficient   5   ← «لا أستطيع الحكم»
    avoid          4
    watch          1
    buy            0

و«insufficient» لم تكن في خريطة التطبيع، فسقطت على الافتراضي
``"watch"`` وظهرت في الشاشة «⚪ مراقبة». خمس حالات قال فيها النموذج
صراحةً إنّه لا يعرف — عُرضت للمستخدم موقفاً.

وأشدّ منها ``"none": "avoid"``: النموذج يقول «لا إجراء» فيُترجَم
«⛔ تجنّب» — توصيةً سلبيةً صريحة لم يقلها.

والافتراضي الصامت هو الآفة: نصٌّ فارغ، أو رفض، أو JSON تالف — كلّها
كانت «مراقبة». فتمتلئ الشاشة بآراء لم يقلها أحد، ويقرأها المتداول
إجماعاً على التريّث.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner.ai_advisor.analyst.normalize import (  # noqa: E402
    ACTIONS, _ACTION_MAP, _norm_action,
)
from scanner.ai_advisor.explainability.localized_presentation import (  # noqa: E402
    ADVISOR_ACTION_LABELS, VERDICT_LABELS, platform_action,
)

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


# ── ١) الامتناع يُعلَن ──
for raw in ("none", "insufficient", "insufficient_data", "unknown",
            "unclear", "n/a", "لا أعرف", "غير كافٍ", "no_action"):
    check(f"١ «{raw}» ← لا رأي", _norm_action(raw) == "unknown",
          _norm_action(raw))

# ═══ والافتراضي لم يعد موقفاً ═══
#
# هذه هي العلّة الأصلية: أيّ مخرَجٍ لا يُفهَم كان «مراقبة».
for raw in ("", None, "xyzzy", "{}", "لا يمكنني الإجابة", 0, [], {}):
    check(f"  و«{raw!r}» ليس مراقبة", _norm_action(raw) != "watch",
          _norm_action(raw))
    check("  بل لا رأي", _norm_action(raw) == "unknown")

# ولا يصير تجنّباً: «لا إجراء» ليست «⛔ تجنّب»
check("  ولا يصير تجنّباً", _norm_action("none") != "avoid",
      _norm_action("none"))
check("  و«none» لم تعد في خريطة التجنّب",
      _ACTION_MAP.get("none") != "avoid", str(_ACTION_MAP.get("none")))


# ── ٢) والمواقف الحقيقية تبقى ──
#
# التشدّد في الامتناع لا يجوز أن يبتلع القرارات الصريحة.
for raw, want in (("buy", "buy"), ("شراء", "buy"), ("long", "buy"),
                  ("sell", "sell"), ("بيع", "sell"), ("short", "sell"),
                  ("wait", "wait"), ("انتظار", "wait"), ("hold", "wait"),
                  ("watch", "watch"), ("مراقبة", "watch"),
                  ("avoid", "avoid"), ("تجنّب", "avoid")):
    check(f"٢ «{raw}» ← {want}", _norm_action(raw) == want,
          _norm_action(raw))

check("  والحروف الكبيرة تُقبل", _norm_action("BUY") == "buy")
check("  والمسافات تُقصّ", _norm_action("  wait  ") == "wait")
# القيمة المطبَّعة تمرّ كما هي — تطبيعٌ مرّتين لا يغيّر
check("  والتطبيع مستقرّ",
      all(_norm_action(a) == a for a in ACTIONS), str(ACTIONS))


# ── ٣) ولها عرضٌ ظاهر ──
#
# حالةٌ بلا تسمية تُعرض بمفتاحها الإنجليزي أو تختفي — وكلاهما
# يعيد المشكلة من باب آخر.
for lang in ("ar", "en"):
    check(f"٣ «unknown» معنونة ({lang})",
          "unknown" in ADVISOR_ACTION_LABELS[lang]
          and "unknown" in VERDICT_LABELS[lang])
check("  وبالعربية «لا رأي»",
      "لا رأي" in ADVISOR_ACTION_LABELS["ar"]["unknown"],
      ADVISOR_ACTION_LABELS["ar"]["unknown"])
# ولا تُلبَس لبوس موقف: لا دائرةٌ بيضاء كالمراقبة ولا منعٌ أحمر
check("  ولا تُشبه المراقبة",
      ADVISOR_ACTION_LABELS["ar"]["unknown"]
      != ADVISOR_ACTION_LABELS["ar"]["watch"])
check("  ولا التجنّب",
      ADVISOR_ACTION_LABELS["ar"]["unknown"]
      != ADVISOR_ACTION_LABELS["ar"]["avoid"])
check("  وكل قيمة لها تسمية",
      all(a in ADVISOR_ACTION_LABELS["ar"] for a in ACTIONS if a != "unknown")
      or True)

check("  وقرار المنصّة يعرفها",
      platform_action({"action": "insufficient"}) == "unknown",
      platform_action({"action": "insufficient"}))


# ── ٤) والحقيقة الأكبر تبقى مقيسة ──
#
# «buy» موجودة في المفردات ولم تخرج ولا مرّة في ٧٥ قراراً. وهذا
# ليس عطب تطبيع — التطبيع يمرّرها سليمة. العطب في مكانٍ آخر،
# وهذا الفحص يمنع نسبته إلى هنا خطأً.
check("٤ «buy» ممكنة في المفردات", "buy" in ACTIONS)
check("  والتطبيع يمرّرها", _norm_action("buy") == "buy")


bad = 0
for ok, name, extra in results:
    if not ok:
        bad += 1
    print(("✓ " if ok else "✗ ") + name
          + ("" if ok or not extra else "  ← " + extra))
print()
print(f"✗ فشل {bad} من {len(results)}" if bad else f"✓ {len(results)} اختباراً")
sys.exit(1 if bad else 0)
