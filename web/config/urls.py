from django.contrib import admin
from django.urls import include, path

from dashboard.health import healthz

urlpatterns = [
    # قبل كل شيء: فاحص الحاوية ينادي هذا كل ثلاثين ثانية، ولا يجوز
    # أن يمرّ على وسيطٍ يستعلم أو يسجّل جلسة.
    path("healthz/", healthz, name="healthz"),
    path("admin/", admin.site.urls),
    path("", include("dashboard.urls")),
]
