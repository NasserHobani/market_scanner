from django.urls import path

from . import ai_live_views
from . import concurrency, postmortem_views, btc_views, views
from . import widget_views
from . import ai_explainability_views as ai_views
from . import ai_local_views
from . import research_orchestrator_views as research_orch_views
from . import predictive_views
from . import snapshot_views
from . import market_sync_views
from . import companies_views
from . import advice_views
from . import block_views
from . import pes_history_views
from . import paper_views
from . import pes_views
from . import topdown_views
from . import squeeze_views
from . import golden_views
from . import job_views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),

    # ═══ دليل الشركات ═══
    # الجلب على مرحلتين: الشركات (رخيص ومجاني) ثمّ التاريخ (غالٍ).
    # وربطهما في نداء واحد يعني أن تعثّر الثاني يُضيّع الأوّل.
    path("api/companies/", companies_views.api_companies,
         name="api_companies"),
    path("api/companies/fetch/", companies_views.api_companies_fetch,
         name="api_companies_fetch"),
    path("api/companies/history/", companies_views.api_companies_history,
         name="api_companies_history"),
    path("api/companies/status/", companies_views.api_companies_status,
         name="api_companies_status"),
    path("api/companies/sectors/", companies_views.api_companies_sectors,
         name="api_companies_sectors"),

    # ═══ الاستشارة ═══
    # الأدلّة نقطةٌ مستقلّة عن الحكم: الأرقام من سجلّك لا تحتاج
    # نموذجاً، فعطلُه لا يحجبها.
    path("api/advice/evidence/", advice_views.api_advice_evidence,
         name="api_advice_evidence"),
    path("api/advice/settled/", advice_views.api_advice_settled,
         name="api_advice_settled"),
    path("api/advice/prospective/", advice_views.api_advice_prospective,
         name="api_advice_prospective"),
    path("api/advice/status/", advice_views.api_advice_status,
         name="api_advice_status"),
    # ═══ المحفظة الورقية ═══
    path("paper/", paper_views.paper_page, name="paper"),
    path("api/paper/", paper_views.api_paper, name="api_paper"),
    path("api/paper/settings/", paper_views.api_paper_settings,
         name="api_paper_settings"),
    path("api/paper/reset/", paper_views.api_paper_reset,
         name="api_paper_reset"),
    path("api/paper/tick/", paper_views.api_paper_tick, name="api_paper_tick"),
    path("api/paper/<int:trade_id>/close/", paper_views.api_paper_close,
         name="api_paper_close"),

    # ═══ استراتيجية ما قبل الانفجار ═══
    path("pes/", pes_views.pes_page, name="pes"),
    path("api/pes/", pes_views.api_pes, name="api_pes"),
    path("api/pes/refresh/", pes_views.api_pes_refresh, name="api_pes_refresh"),
    # ═══ من الأعلى للأسفل: أسبوعيّ ← يوميّ ← 4س ═══
    path("topdown/", topdown_views.topdown_page, name="topdown"),
    path("api/topdown/", topdown_views.api_topdown, name="api_topdown"),
    path("api/topdown/refresh/", topdown_views.api_topdown_refresh,
         name="api_topdown_refresh"),

    # سجلّ الرصد: متى رُصد الرمز وماذا جرى بعده
    path("pes/history/", pes_history_views.history_page, name="pes_history"),
    path("api/pes/history/", pes_history_views.api_pes_history,
         name="api_pes_history"),
    path("api/pes/history/refresh/",
         pes_history_views.api_pes_history_refresh,
         name="api_pes_history_refresh"),

    # ═══ الانضغاط والتمدّد ═══
    path("squeeze/", squeeze_views.squeeze_page, name="squeeze"),
    path("api/squeeze/", squeeze_views.api_squeeze, name="api_squeeze"),
    path("api/squeeze/refresh/", squeeze_views.api_squeeze_refresh,
         name="api_squeeze_refresh"),

    # ═══ الرموز المحظورة ═══
    path("blocked/", block_views.blocked_page, name="blocked"),
    path("api/blocked/", block_views.api_blocked, name="api_blocked"),
    path("api/blocked/add/", block_views.api_block_add, name="api_block_add"),
    path("api/blocked/check/", block_views.api_block_check,
         name="api_block_check"),
    path("api/blocked/<int:block_id>/remove/", block_views.api_block_remove,
         name="api_block_remove"),
    path("api/blocked/<int:block_id>/toggle/", block_views.api_block_toggle,
         name="api_block_toggle"),

    # ═══ الصفقات الذهبية ═══
    path("golden/", golden_views.golden_page, name="golden"),
    path("api/golden/", golden_views.api_golden, name="api_golden"),

    # ═══ المهامّ المجدولة ═══
    path("jobs/", job_views.jobs_page, name="jobs"),
    path("api/jobs/", job_views.api_jobs, name="api_jobs"),
    path("api/jobs/seed/", job_views.api_jobs_seed, name="api_jobs_seed"),
    path("api/jobs/<int:job_id>/runs/", job_views.api_job_runs,
         name="api_job_runs"),
    path("api/jobs/<int:job_id>/run/", job_views.api_job_run_now,
         name="api_job_run_now"),
    path("api/jobs/<int:job_id>/toggle/", job_views.api_job_toggle,
         name="api_job_toggle"),
    path("api/jobs/<int:job_id>/save/", job_views.api_job_save,
         name="api_job_save"),

    path("api/verdicts/", advice_views.api_verdicts_list,
         name="api_verdicts_list"),
    path("api/verdicts/<str:verdict_id>/", advice_views.api_verdict_detail,
         name="api_verdict_detail"),
    path("scanner/", views.scanner, name="scanner"),
    path("trades/", views.trades, name="trades"),
    path("analytics/", views.analytics, name="analytics"),
    path("optimization/", views.optimization, name="optimization"),
    path("settings/", views.settings_page, name="settings"),
    path("ai/", views.ai, name="ai"),
    path("btc/", btc_views.btc_page, name="btc"),
    path("api/ai/live/", ai_live_views.api_ai_live, name="api_ai_live"),
    # تشريح الصفقات المحسومة: القياس فوري، والتفسير مهمّة خلفية
    path("api/concurrency/", concurrency.api_concurrency,
         name="api_concurrency"),
    path("api/postmortem/", postmortem_views.api_postmortem,
         name="api_postmortem"),
    path("api/postmortem/ai/", postmortem_views.api_postmortem_ai,
         name="api_postmortem_ai"),
    path("api/postmortem/ai/status/", postmortem_views.api_postmortem_ai_status,
         name="api_postmortem_ai_status"),
    # فحص صفقة مفردة: البطاقة فورية، والتقييم مهمّة خلفية بنتيجة محجوبة
    path("api/trade/<int:trade_id>/card/", postmortem_views.api_trade_card,
         name="api_trade_card"),
    path("api/trade/<int:trade_id>/review/", postmortem_views.api_trade_review,
         name="api_trade_review"),
    path("api/trade/<int:trade_id>/review/status/",
         postmortem_views.api_trade_review_status,
         name="api_trade_review_status"),
    path("api/btc/opinion/", btc_views.api_btc_opinion, name="api_btc_opinion"),
    path("api/btc/refresh/", btc_views.api_btc_refresh, name="api_btc_refresh"),
    path("api/btc/opinion/status/", btc_views.api_btc_opinion_status,
         name="api_btc_opinion_status"),
    path("search/", views.search, name="search"),
    path("watches/", views.watches, name="watches"),
    path("api/watches/", views.api_watches, name="api_watches"),
    path("api/check/", views.api_check_now, name="api_check_now"),
    path("api/telegram-test/", views.api_telegram_test, name="api_telegram_test"),
    path("api/ai-advisor/test-connection/", views.api_ai_advisor_test_connection,
         name="api_ai_advisor_test_connection"),
    path("symbol/<str:market>/<str:symbol>/", views.symbol_detail, name="symbol"),
    path("api/results/", views.api_results, name="api_results"),
    path("api/history/<str:market>/<str:symbol>/", views.api_history, name="api_history"),
    path("api/chart/<str:market>/<str:symbol>/", views.api_chart, name="api_chart"),
    path("api/outlook/<str:market>/<str:symbol>/", views.api_outlook, name="api_outlook"),
    path("api/scan/", views.api_scan_now, name="api_scan_now"),
    path("api/scan/status/", views.api_scan_status, name="api_scan_status"),
    path("api/market-data/sync/status/", market_sync_views.api_market_sync_status,
         name="api_market_sync_status"),
    path("api/market-data/sync/", market_sync_views.api_market_sync_now,
         name="api_market_sync_now"),
    path("api/market-data/sync/worker/", market_sync_views.api_market_sync_worker_status,
         name="api_market_sync_worker_status"),
    path("api/chart/<str:market>/<str:symbol>/latest/", market_sync_views.api_chart_latest,
         name="api_chart_latest"),
    path("api/quotes/", views.api_quotes, name="api_quotes"),
    path("api/stats/", views.api_stats, name="api_stats"),
    path("performance/", views.performance, name="performance"),
    path("research/", views.research, name="research"),
    path("api/track/", views.api_track, name="api_track"),
    path("api/trade/<int:trade_id>/cancel/", views.api_trade_cancel,
         name="api_trade_cancel"),
    path("api/performance/", views.api_performance, name="api_performance"),
    path("api/research/", views.api_research, name="api_research"),
    path("api/research/status/", research_orch_views.api_research_status,
         name="api_research_status"),
    path("api/research/jobs/", research_orch_views.api_research_jobs,
         name="api_research_jobs"),
    path("api/research/run/", research_orch_views.api_research_run,
         name="api_research_run"),
    path("api/research/run/<str:job_id>/", research_orch_views.api_research_run_job,
         name="api_research_run_job"),
    path("api/prediction/status/", predictive_views.api_prediction_status,
         name="api_prediction_status"),
    path("api/prediction/readiness/", predictive_views.api_prediction_readiness,
         name="api_prediction_readiness"),
    path("api/prediction/jobs/", predictive_views.api_prediction_jobs,
         name="api_prediction_jobs"),
    path("api/prediction/train/", predictive_views.api_prediction_train,
         name="api_prediction_train"),
    path("api/prediction/promote/<str:model_id>/", predictive_views.api_prediction_promote,
         name="api_prediction_promote"),
    path("api/snapshots/runtime/", snapshot_views.api_snapshot_runtime,
         name="api_snapshot_runtime"),
    path("api/research/export/", views.api_research_export, name="api_research_export"),
    path("api/settle/", views.api_settle_now, name="api_settle_now"),
    path("api/repair-times/", views.api_repair_times,
         name="api_repair_times"),
    path("api/optimization/run/", views.api_optimization_run, name="api_optimization_run"),
    # Explainable AI (AIA-05)
    path("api/ai/reviews/", ai_views.api_ai_reviews_list, name="api_ai_reviews_list"),
    path("api/ai/reviews/live/", ai_views.api_ai_reviews_live, name="api_ai_reviews_live"),
    path("api/ai/reviews/<str:review_id>/", ai_views.api_ai_review_detail, name="api_ai_review_detail"),
    path("api/ai/reviews/<str:review_id>/export/", ai_views.api_ai_review_export, name="api_ai_review_export"),
    path("api/ai/providers/", ai_views.api_ai_provider_stats, name="api_ai_provider_stats"),
    path("api/ai/manual-analysis/", ai_views.api_ai_manual_analysis, name="api_ai_manual_analysis"),
    # Local AI (AIA-06)
    path("api/ai/local/health/", ai_local_views.api_ai_local_health, name="api_ai_local_health"),
    path("api/ai/local/test/", ai_local_views.api_ai_local_test, name="api_ai_local_test"),
    path("api/ai/local/models/", ai_local_views.api_ai_local_models, name="api_ai_local_models"),
    path("api/ai/local/status/", ai_local_views.api_ai_local_status, name="api_ai_local_status"),
    path("api/ai/local/leaderboard/", ai_local_views.api_ai_local_leaderboard,
         name="api_ai_local_leaderboard"),
    path("api/ai/local/comparisons/", ai_local_views.api_ai_local_comparisons,
         name="api_ai_local_comparisons"),
    path("api/backfill-liquidity/", views.api_backfill_liquidity,
         name="api_backfill_liquidity"),
    # Widget endpoints — independent lightweight loads
    path("api/widgets/health/", widget_views.api_widget_health, name="api_widget_health"),
    path("api/widgets/trends/", widget_views.api_widget_trends, name="api_widget_trends"),
    path("api/widgets/experiments/", widget_views.api_widget_experiments, name="api_widget_experiments"),
    path("api/widgets/factors/", widget_views.api_widget_factors, name="api_widget_factors"),
    path("api/widgets/confidence/", widget_views.api_widget_confidence, name="api_widget_confidence"),
    path("api/widgets/baselines/", widget_views.api_widget_baselines, name="api_widget_baselines"),
    path("api/widgets/splits/", widget_views.api_widget_splits, name="api_widget_splits"),
    path("api/widgets/trades/", widget_views.api_widget_trades, name="api_widget_trades"),
    path("api/widgets/open-trades/", widget_views.api_widget_open_trades, name="api_widget_open_trades"),
    path("api/widgets/settlement/", widget_views.api_widget_settlement, name="api_widget_settlement"),
    path("api/widgets/scanner/summary/", widget_views.api_widget_scanner_summary,
         name="api_widget_scanner_summary"),
    path("api/widgets/alerts/", widget_views.api_widget_alerts, name="api_widget_alerts"),
    path("api/widgets/optimization-summary/", widget_views.api_widget_optimization_summary,
         name="api_widget_optimization_summary"),
    path("api/widgets/ai-platform/", widget_views.api_widget_ai_platform,
         name="api_widget_ai_platform"),
    path("api/widgets/ai-advisor/", widget_views.api_widget_ai_advisor,
         name="api_widget_ai_advisor"),
    path("api/widgets/ai-advisor-evaluation/", widget_views.api_widget_ai_advisor_evaluation,
         name="api_widget_ai_advisor_evaluation"),
    path("api/widgets/ai-learning/", widget_views.api_widget_ai_learning,
         name="api_widget_ai_learning"),
    path("api/widgets/ai-review-timeline/", ai_views.api_widget_ai_review_timeline,
         name="api_widget_ai_review_timeline"),
]
