# -*- coding: utf-8 -*-
"""تشغيل كل الفواحص والاختبارات دفعة واحدة:  python run_checks.py"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
PY = sys.executable

# ونحن أنفسنا قد نكون أنبوباً: ``python run_checks.py > log.txt``.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# ═══ لماذا يُفرَض ترميز الأبناء ═══
#
# على ويندوز يختار Python ترميز المخرَج من **نوع المخرَج** لا من
# محتواه: إن كان طرفيةً فـ UTF-8، وإن كان أنبوباً فصفحة النظام
# (cp1252 هنا). وكل فحص يعمل تحت ``capture_output=True`` — أي
# أنبوب. فالسطر ``print("✓ ...")`` الذي يعمل في الطرفية ينهار في
# الأنبوب بـ ``UnicodeEncodeError``.
#
# والخداع أنّ الانهيار يقع **بعد** أن يمرّ الاختبار كلّه: آخر سطر
# فيه هو طباعة النتيجة، فيخرج بالرمز 1 ويُحسَب فاشلاً وهو ناجح.
# فحصٌ يبلّغ عن نجاحه فيموت في الإبلاغ — والقائمة كلّها حمراء.
#
# ``PYTHONIOENCODING`` يحسم هذا للابن مهما كان مخرَجه. وتُقرأ
# مخرجاتهم بـ UTF-8 صراحةً للسبب نفسه معكوساً.
CHILD_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}

STEPS = [
    ("ترميز المخرَج", [PY, "tests_console.py"]),
    ("تسلسل JSON وnumpy", [PY, "tests_jsonsafe.py"]),
    ("قراءة ‎.env‎", [PY, "tests_env.py"]),
    ("أسماء غير معرّفة", [PY, "tools_check_names.py"]),
    ("قوالب Django", [PY, "tools_check_templates.py"]),
    ("نظام التصميم", [PY, "tools_check_design.py"]),
    ("مرشّحات الصفحات", [PY, "tests_filters_page.py"]),
    ("محرّك الجدولة", [PY, "tests_cron.py"]),
    ("نموذج التنبؤ", [PY, "tests_predictor.py"]),
    ("الصفقات الذهبية", [PY, "tests_golden.py"]),
    ("حظر الرموز", [PY, "tests_blocklist.py"]),
    ("الانضغاط والتمدّد", [PY, "tests_squeeze.py"]),
    ("استراتيجية ما قبل الانفجار", [PY, "tests_pes.py"]),
    ("المحفظة الورقية", [PY, "tests_paper.py"]),
    ("ترحيل PostgreSQL", [PY, "tests_pg_migration.py"]),
    ("النشر بـ Docker", [PY, "tests_docker.py"]),
    ("نقل البيانات إلى الخادم", [PY, "tests_ship.py"]),
    ("أقفال المزامنة", [PY, "tests_sync_locks.py"]),
    ("أعطال الخادم النظيف", [PY, "tests_fresh_server.py"]),
    ("لوحتا الزخم", [PY, "tests_oscillators.py"]),
    ("التقاء الزخم في PES", [PY, "tests_pes_momentum.py"]),
    ("نطاق نظام البتكوين", [PY, "tests_pes_btc_scope.py"]),
    ("‏Supertrend عاملاً وخطّاً", [PY, "tests_supertrend.py"]),
    ("من الأعلى للأسفل", [PY, "tests_topdown.py"]),
    ("‏4h مشتقّة من ياهو", [PY, "tests_yahoo_derived.py"]),
    ("القائمة الجانبية على الجوّال", [PY, "tests_mobile_rail.py"]),
    ("الذهب والنفط", [PY, "tests_commodities.py"]),
    ("سجلّ رصد PES", [PY, "tests_pes_history.py"]),
    ("امتداد فيبوناتشي", [PY, "tests_fib_extension.py"]),
    ("الفريمات: معروض ومَمسوح", [PY, "tests_timeframes.py"]),
    ("فجوة بيانات التدريب", [PY, "tools_dataset_gap.py"]),
    ("تنسيق الأرقام", [PY, "tools_check_numbers.py"]),
    ("عقد العوامل", [PY, "tools_check_factors.py"]),
    ("أثر الإعدادات", [PY, "tools_check_settings.py"]),
    ("مخطط الإعدادات", [PY, "tests_settings.py"]),
    ("النماذج والهجرات", [PY, "tools_check_migration.py"]),
    ("الجلب التراكمي", [PY, "tests_storage.py"]),
    ("نطاق البحث", [PY, "tests_search.py"]),
    ("المحوّرات والبنية", [PY, "tests_pivots.py"]),
    ("تحليل البتكوين", [PY, "tests_btc.py"]),
    ("الارتباط والتنويع", [PY, "tests_correlation.py"]),
    ("رصد الاختراق", [PY, "tests_breakout.py"]),
    ("الفوليوم و VWAP", [PY, "tests_volume.py"]),
    ("محوّل Alpaca", [PY, "tests_alpaca.py"]),
    ("محوّل سهمك", [PY, "tests_sahmk.py"]),
    ("دليل الشركات", [PY, "tests_companies.py"]),
    ("نموذج التنفيذ", [PY, "tests_execution.py"]),
    ("استشارة بالأدلّة", [PY, "tests_advice.py"]),
    ("لماذا قد تنجح", [PY, "tests_why.py"]),
    ("الامتناع لا يُترجَم موقفاً", [PY, "tests_no_opinion.py"]),
    ("المراجعة التلقائية بالأحكام", [PY, "tests_auto_review.py"]),
    ("ربط مراجعات الذكاء", [PY, "tests_ai_link.py"]),
    ("المحادثة الحيّة", [PY, "tests_ai_live.py"]),
    ("اتصال Ollama", [PY, "tests_ollama_conn.py"]),
    ("محرّك الصفقات", [PY, "tests_tracking.py"]),
    ("الاختبار الخلفي", [PY, "tests_recobt.py"]),
    ("طبقة الصفقات", [PY, "tests_trades.py"]),
    ("عامل الحسم", [PY, "tests_settlement.py"]),
    ("الازدحام والبيانات الميتة", [PY, "tests_crowding.py"]),
    ("مرشّح الصفقات", [PY, "tests_trade_filters.py"]),
    ("أوقات الصفقات", [PY, "tests_times.py"]),
    ("صيغة الشموع", [PY, "tests_storage_format.py"]),
    ("أوقات جلسات الأسواق", [PY, "tests_sessions.py"]),
    ("حالة بيانات السوق", [PY, "tests_sync_status.py"]),
    ("زمن المسح", [PY, "tests_scan_speed.py"]),
    ("قِمع المسح", [PY, "tools_scan_funnel.py", "crypto", "--limit", "3"]),
    ("الرموز المشطوبة", [PY, "tools_prune_dead.py", "--market", "saudi"]),
    # لم يكن مسجّلاً هنا — ولذلك بقيت علّة اللواحق (npz غير مرئيّ
    # لـ resolve_symbols) حيّةً بلا أن يصرخ شيء. اختبارٌ لا يُشغَّل
    # ليس اختباراً.
    ("مزامنة الشموع الخلفية", [PY, "tests_market_data_background_sync.py"]),
    ("التزامن والحجب", [PY, "tests_concurrency.py"]),
    ("قواعد الخروج", [PY, "tests_exits.py"]),
    ("تشريح الصفقات المحسومة", [PY, "tests_postmortem.py"]),
    ("مصدر قائمة الرموز", [PY, "tests_universe.py"]),
    ("ذاكرة كون الرموز", [PY, "tests_universe_cache.py"]),
    ("سياق المحلّل المضغوط", [PY, "tests_ai_analyst_context.py"]),
    ("هويّة المراجعات", [PY, "tests_review_identity.py"]),
    ("قفل قاعدة البيانات", [PY, "tests_dblock.py"]),
    ("حراسة الاستعلام الدوري", [PY, "tests_polling.py"]),
    ("تصفية اللوحة", ["node", "tests_filters.js"]),
    ("الراسم الاحتياطي", ["node", "tests_chart_fallback.js"]),
    ("ربط المستشار بالواجهة", ["node", "tests_advice_ui.js"]),
    ("تشغيل الشبكة", [PY, "tests_lan.py"]),

    # ═══ طبقة الذكاء والبحث ═══
    #
    # كانت هذه كلّها **خارج** القائمة: سبعةٌ وثلاثون ملف اختبار
    # مكتوباً ومحفوظاً ولا يشغّله شيء. وأحدها كان قد تعفّن فعلاً
    # (``tests_ai_model_registry`` يفحص ارتداداً صامتاً أُبطل عمداً).
    #
    # اختبارٌ لا يُشغَّل ليس اختباراً — هو توثيقٌ لنيّةٍ قديمة.
    ("المستشار الذكي", [PY, "tests_ai_advisor.py"]),
    ("تقييم المستشار", [PY, "tests_ai_advisor_evaluation.py"]),
    ("إثراء AIA-106", [PY, "tests_ai_aia106_enrichment.py"]),
    ("AIA-11", [PY, "tests_ai_aia11.py"]),
    ("AIA-12", [PY, "tests_ai_aia12.py"]),
    ("AIA-13 المحلّل العربي", [PY, "tests_ai_aia13.py"]),
    ("موفّر Claude", [PY, "tests_ai_claude_provider.py"]),
    ("وضع المقارنة", [PY, "tests_ai_compare_mode.py"]),
    ("قابلية التفسير", [PY, "tests_ai_explainability.py"]),
    ("التفسير بالعربية", [PY, "tests_ai_explainability_arabic.py"]),
    ("دمج الإشارات", [PY, "tests_ai_fusion.py"]),
    ("تعلّم الذكاء", [PY, "tests_ai_learning.py"]),
    ("تعلّم AIA-055", [PY, "tests_ai_learning_aia055.py"]),
    ("تنبّؤ التعلّم", [PY, "tests_ai_learning_prediction.py"]),
    ("الذكاء المحلّي", [PY, "tests_ai_local.py"]),
    ("سجلّ النماذج", [PY, "tests_ai_model_registry.py"]),
    ("موفّر Ollama", [PY, "tests_ai_ollama_provider.py"]),
    ("الحزمة الموحّدة", [PY, "tests_ai_unified_package.py"]),
    ("قرار الذكاء", [PY, "tests_decision_ai.py"]),
    ("ذكاء العوامل", [PY, "tests_feature_intelligence.py"]),
    ("الاستدلال العام", [PY, "tests_intelligence.py"]),
    ("قاعدة المعرفة", [PY, "tests_knowledge.py"]),
    ("أساس التعلّم الآلي", [PY, "tests_ml_foundation.py"]),
    ("الأمثلة", [PY, "tests_optimization.py"]),
    ("التنسيق", [PY, "tests_orchestration.py"]),
    ("خطّ المعالجة", [PY, "tests_pipeline.py"]),
    ("تكامل خطّ المعالجة", [PY, "tests_pipeline_integration.py"]),
    ("تحسين التنبّؤ", [PY, "tests_prediction_improvement.py"]),
    ("التنبّؤ", [PY, "tests_predictive.py"]),
    ("التعليل", [PY, "tests_reasoning.py"]),
    ("محرّك البحث", [PY, "tests_research_engine.py"]),
    ("منسّق البحث", [PY, "tests_research_orchestrator.py"]),
    ("المكوّنات المرئية", [PY, "tests_widgets.py"]),

    ("ترجمة Python", [PY, "-m", "compileall", "-q", "scanner", "web"]),
]

# اختبارات تحتاج Ollama حيّاً — تُشغَّل بـ ``--net``.
# فصلها ليس تساهلاً: خلطها بالباقي يجعل «فشل الفواحص» يعني
# «Ollama مطفأ» في أغلب الأحيان، فيُهمَل الإنذار كلّه.
NET_STEPS = [
    ("زمن تشغيل المستشار", [PY, "tests_ai_advisor_runtime.py"]),
    ("زمن تشغيل AIA-105", [PY, "tests_ai_aia105_runtime.py"]),
    ("عوامل AIA-10", [PY, "tests_ai_aia10_features.py"]),
    ("التشابه", [PY, "tests_similarity.py"]),
]

# ═══ الفواحص ليست في صورة Docker ═══
#
# ‏.dockerignore يستثني ``tests_*.py`` و``tools_*.py`` عمداً —
# لا محلّ لها على خادم. لكنّ هذا الملفّ **يدخل** الصورة (اسمه لا
# يطابق النمطين)، فصار سكربتاً لا يمكنه إلّا أن يفشل هناك: خمسون
# سطراً أحمر كلّها ``No such file``، ولا سطر يقول لماذا.
#
# وقائمةٌ حمراء بالكامل تُقرأ «النظام معطوب» لا «أنت في المكان
# الخطأ». فالتحقّق مرّةً قبل البدء، برسالةٍ تقول أين يُشغَّل.
_targets = [c[1] for _, c in STEPS if len(c) > 1 and str(c[1]).endswith(".py")]
_present = [t for t in _targets if (ROOT / t).exists()]
if len(_present) < max(1, len(_targets) // 2):
    print("✗ ملفّات الفواحص غير موجودة هنا "
          f"({len(_present)} من {len(_targets)}).")
    print()
    print("  إن كنت داخل حاوية: الصورة قديمة. الفواحص تدخل الصورة")
    print("  منذ إصلاح ‎.dockerignore‎ — فأعد البناء والنشر.")
    print()
    print("  وإن كنت على جهازك: شغّلها من جذر المشروع لا من مجلّدٍ آخر.")
    print(f"      cd {ROOT}")
    print("      python run_checks.py")
    sys.exit(2)

steps = list(STEPS)
if "--net" in sys.argv:
    steps += NET_STEPS
else:
    print(f"(تُخطَّى {len(NET_STEPS)} فواحص تحتاج Ollama — أضف --net لتشغيلها)\n")

# مهلة لكل فحص: بلا مهلة يعلّق فحصٌ واحدٌ الجولة كلّها بلا بيان.
TIMEOUT = 300

failed: list[str] = []
skipped: list[str] = []
for name, cmd in steps:
    # ═══ مفسّرٌ غائب ≠ فحصٌ فاشل ═══
    #
    # خطوةٌ تنادي ``node`` على خادمٍ بلا Node تطبع أثراً كاملاً
    # وتُحسَب فشلاً — فيبدو النظام معطوباً وهو سليم، ويُخلط
    # نقصُ البيئة بعطب الكود. والتمييز بينهما هو كل الفائدة.
    _exe = str(cmd[0])
    if _exe != PY and shutil.which(_exe) is None:
        print(f"· {name} — يحتاج «{_exe}» وهو غير مثبَّت، تُخطَّى")
        skipped.append(name)
        continue
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True,
                           text=True, timeout=TIMEOUT, env=CHILD_ENV,
                           encoding="utf-8", errors="replace")
        ok = r.returncode == 0
        out = (r.stdout + r.stderr).strip()[-1500:]
    except subprocess.TimeoutExpired:
        ok, out = False, f"تجاوز {TIMEOUT}ث بلا انتهاء"
    except FileNotFoundError as exc:
        ok, out = False, f"تعذّر التشغيل: {exc}"
    print(("✓ " if ok else "✗ ") + name)
    if not ok:
        failed.append(name)
        print(out)

print()
# المتخطَّى يُعلَن ولا يُبتلَع: «كل الفواحص ✓» مع خطوتين لم تعملا
# ادّعاءٌ أوسع من الحقيقة.
if skipped:
    print(f"· تُخطّيت {len(skipped)}: " + " · ".join(skipped))
print("✓ كل الفواحص" if not failed else "✗ فشل: " + " · ".join(failed))
sys.exit(1 if failed else 0)
