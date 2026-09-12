from django.contrib import admin

from .models import ScanResult, ScanRun, SignalAlert, Watch


@admin.register(ScanRun)
class ScanRunAdmin(admin.ModelAdmin):
    list_display = ("market", "kind", "timeframe", "started_at", "symbols_scanned",
                    "ready_count", "duration_seconds")
    list_filter = ("market", "kind", "timeframe")
    date_hierarchy = "started_at"


@admin.register(ScanResult)
class ScanResultAdmin(admin.ModelAdmin):
    list_display = ("symbol", "market", "score", "decision", "confluence",
                    "ready", "compliance", "blocker", "candle_time")
    list_filter = ("market", "timeframe", "decision", "ready", "compliance")
    search_fields = ("symbol",)
    ordering = ("-candle_time", "-score")


@admin.register(SignalAlert)
class SignalAlertAdmin(admin.ModelAdmin):
    list_display = ("symbol", "score", "fired_at", "notified")
    list_filter = ("notified",)
    search_fields = ("symbol",)


@admin.register(Watch)
class WatchAdmin(admin.ModelAdmin):
    list_display = ("symbol", "market", "timeframe", "side", "entry", "last_price",
                    "status", "grade", "notified", "created_at", "expires_at")
    list_filter = ("status", "market", "timeframe", "side", "notified")
    search_fields = ("symbol",)
    actions = ["cancel_watches", "rearm_watches"]

    @admin.action(description="إلغاء المحدد")
    def cancel_watches(self, request, queryset):
        queryset.update(status="cancelled")

    @admin.action(description="إعادة تسليح المحدد")
    def rearm_watches(self, request, queryset):
        queryset.update(status="armed", triggered_at=None, notified=False)
