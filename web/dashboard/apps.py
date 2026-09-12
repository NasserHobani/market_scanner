import os

from django.apps import AppConfig


class DashboardConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dashboard"
    verbose_name = "لوحة الماسح"

    def ready(self):
        """تشغيل المسح التلقائي مع الخادم.

        شرطان مهمان:
          • RUN_MAIN: runserver يشغّل ready() مرتين (عملية إعادة التحميل
            وعملية العمل). بدون هذا الفحص يعمل خيطان ويتضاعف كل شيء.
          • الأوامر الإدارية: لا معنى لبدء المسح أثناء migrate أو shell.
        """
        import sys

        if os.environ.get("AUTO_SCAN", "1") != "1":
            return
        if os.environ.get("RUN_MAIN") != "true" and "runserver" in sys.argv:
            return                      # عملية إعادة التحميل، ليست العاملة
        # ``run_jobs`` يشغّل المستحقّ بنفسه؛ وبدء المحرّك معه
        # يعني محرّكين على قاعدة واحدة.
        skip = {"migrate", "makemigrations", "collectstatic", "shell",
                "createsuperuser", "test", "scan", "run_jobs"}
        if any(cmd in sys.argv for cmd in skip):
            return

        markets = [m.strip() for m in
                   os.environ.get("AUTO_SCAN_MARKETS", "crypto").split(",") if m.strip()]
        if not markets:
            return

        # فحص الهجرات يستعلم من قاعدة البيانات، وDjango يحذّر من ذلك
        # داخل ready(). نؤجّله إلى خيط يبدأ بعد اكتمال التهيئة.
        self._warn_migrations_later()

        # ═══ محرّك واحد بدل أربعة خيوط ═══
        #
        # كانت أربع حلقات مستقلّة: المسح والمزامنة والمراقبة والحسم.
        # كلٌّ بفترتها في متغيّر بيئة وحالتها في الذاكرة — فلا سجلّ
        # يبقى بعد إعادة التشغيل، ولا تغيير لفترةٍ بلا تحرير ملفّ.
        #
        # والمنطق لم يُمسّ: ``cron`` ينادي ``run_scan`` و``run_once``
        # و``check_once`` و``settle_once`` كما هي. والبذر يقرأ نفس
        # متغيّرات البيئة، فأوّل إقلاع بعد الترقية لا يغيّر سلوكاً.
        #
        # ‏SCHEDULER_ENGINE=legacy يعيد الخيوط الأربعة — مخرجٌ إن
        # ظهر عطبٌ في المحرّك، ولا يُحذف القديم قبل أن يُوثَق الجديد.
        # ‏off يوقف الجدولة داخل الخادم كلّها — لمن ربط الأمر
        # الخارجي ``run_jobs`` بمجدول النظام. وبلا هذا يعمل
        # المحرّكان معاً على قاعدة واحدة، فتُشغَّل المهمّة مرّتين.
        engine = os.environ.get("SCHEDULER_ENGINE", "cron").strip().lower()
        if engine == "off":
            return
        if engine == "legacy":
            self._start_legacy_loops(markets)
        else:
            from . import cron

            cron.start()

        self._activate_ai_production_settings()

    @staticmethod
    def _start_legacy_loops(markets: list) -> None:
        """الخيوط الأربعة القديمة — مخرجُ طوارئ لا مسارٌ افتراضي."""
        import os

        from . import market_sync_worker, monitor, scheduler, settlement

        if os.environ.get("MARKET_DATA_SYNC", "1") == "1":
            sync_markets = [
                m.strip() for m in
                os.environ.get("MARKET_SYNC_MARKETS",
                               ",".join(markets)).split(",")
                if m.strip()
            ] or markets
            market_sync_worker.start(sync_markets)

        scheduler.start(markets)

        if os.environ.get("WATCH_MONITOR", "1") == "1":
            monitor.start(int(os.environ.get("WATCH_INTERVAL_SECONDS", "300")))

        if os.environ.get("TRADE_SETTLEMENT", "1") == "1":
            settlement.start(
                int(os.environ.get("SETTLEMENT_INTERVAL_SECONDS", "180")))

    @staticmethod
    def _activate_ai_production_settings() -> None:
        """Persist Claude as active provider when API key is configured."""
        try:
            from scanner.ai_advisor.provider_config import (
                apply_production_defaults, load_config_raw,
            )
            from web.dashboard import appsettings

            raw = load_config_raw()
            effective = apply_production_defaults(raw)
            if (raw.default_provider != effective.default_provider
                    or raw.claude_enabled != effective.claude_enabled):
                appsettings.save({
                    "ai_default_provider": effective.default_provider,
                    "ai_claude_enabled": effective.claude_enabled,
                })
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _warn_migrations_later(delay: float = 3.0) -> None:
        """تحذير الهجرات المعلّقة بعد اكتمال تهيئة التطبيقات."""
        import threading

        def check():
            import time

            time.sleep(delay)
            if DashboardConfig._migrations_applied():
                return
            print("\n" + "=" * 58)
            print("  ! توجد هجرات غير مطبقة - بعض الميزات ستفشل")
            print("    شغل:  python web/manage.py migrate")
            print("=" * 58 + "\n", flush=True)

        threading.Thread(target=check, name="migration-check", daemon=True).start()

    @staticmethod
    def _migrations_applied() -> bool:
        """هل كل هجرات التطبيق مطبَّقة؟"""
        try:
            from django.db import connection
            from django.db.migrations.executor import MigrationExecutor

            executor = MigrationExecutor(connection)
            targets = executor.loader.graph.leaf_nodes("dashboard")
            return not executor.migration_plan(targets)
        except Exception:  # noqa: BLE001
            return True     # تعذّر الفحص لا يعني وجود مشكلة
