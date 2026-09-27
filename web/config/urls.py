from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from dashboard.health import healthz

urlpatterns = [
    # قبل كل شيء: فاحص الحاوية ينادي هذا كل ثلاثين ثانية، ولا يجوز
    # أن يمرّ على وسيطٍ يستعلم أو يسجّل جلسة.
    path("healthz/", healthz, name="healthz"),
    # ═══ الدخول والخروج ═══
    #
    # ‏``LoginView`` من Django لا واحدةٌ مكتوبة بيد: التحقّق من
    # كلمة السرّ ومقارنتها بزمنٍ ثابت وتدوير الجلسة بعد الدخول
    # كلّها أشياء يسهل أن تُكتب خطأً، وهي مكتوبةٌ هناك صحيحة.
    path("accounts/login/",
         auth_views.LoginView.as_view(
             template_name="dashboard/login.html",
             redirect_authenticated_user=True),
         name="login"),
    path("accounts/logout/",
         auth_views.LogoutView.as_view(), name="logout"),
    path("admin/", admin.site.urls),
    path("", include("dashboard.urls")),
]
