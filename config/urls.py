from functools import partial
from django.contrib import admin
from django.contrib.auth import views as auth
from django.urls import path, reverse_lazy
from core import views as core
from accounts import views as accounts
from items import views as items
from claims import views as claims
from dashboard import views as dashboard
from notifications import views as notifications
from reports.views import report
from ai_module.views import image_search

urlpatterns = [
    path("matches/image-search/", image_search, name="image_search"),
    path("", core.home, name="home"),
    path("privacy/", core.privacy, name="privacy"),
    path("accounts/register/", accounts.register, name="register"),
    path("accounts/login/", accounts.sign_in, name="login"),
    path("accounts/logout/", accounts.sign_out, name="logout"),
    path("accounts/profile/", accounts.profile, name="profile"),
    path("accounts/avatar/", core.avatar, name="avatar"),
    path(
        "accounts/password/",
        auth.PasswordChangeView.as_view(
            template_name="accounts/reset.html", success_url=reverse_lazy("profile")
        ),
        name="password_change",
    ),
    path(
        "accounts/reset/",
        accounts.SafePasswordResetView.as_view(
            success_url=reverse_lazy("password_reset_done")
        ),
        name="password_reset",
    ),
    path(
        "accounts/reset/sent/",
        auth.PasswordResetDoneView.as_view(template_name="accounts/reset_done.html"),
        name="password_reset_done",
    ),
    path(
        "accounts/reset/<uidb64>/<token>/",
        auth.PasswordResetConfirmView.as_view(
            template_name="accounts/reset_confirm.html"
        ),
        name="password_reset_confirm",
    ),
    path(
        "accounts/reset/complete/",
        auth.PasswordResetCompleteView.as_view(
            template_name="accounts/reset_complete.html"
        ),
        name="password_reset_complete",
    ),
    path("dashboard/", dashboard.dashboard, name="dashboard"),
    path("items/", items.item_list, name="item_list"),
    path("my-items/", items.item_list, {"mine": True}, name="my_items"),
    path("items/report/<str:item_type>/", items.report, name="report_item"),
    path("items/<int:pk>/", items.item_detail, name="item_detail"),
    path("items/<int:pk>/edit/", items.report, name="item_edit"),
    path("items/<int:pk>/close/", items.close_item, name="item_close"),
    path("images/<int:pk>/", items.item_image, name="item_image"),
    path("images/<int:pk>/remove/", items.remove_image, name="remove_image"),
    path("items/<int:item_id>/claim/", claims.create, name="claim_create"),
    path("claims/", claims.claim_list, name="claim_list"),
    path("claims/<int:pk>/", claims.detail, name="claim_detail"),
    path("claims/<int:pk>/cancel/", claims.cancel, name="claim_cancel"),
    path("claims/<int:pk>/evidence/", claims.evidence, name="claim_evidence"),
    path("matches/", dashboard.matches, name="matches"),
    path("notifications/", notifications.inbox, name="notifications"),
    path(
        "notifications/read-all/",
        notifications.mark_read,
        name="notifications_read_all",
    ),
    path(
        "notifications/<int:pk>/read/",
        notifications.mark_read,
        name="notification_read",
    ),
    path("portal/", dashboard.admin_dashboard, name="admin_dashboard"),
    path("portal/users/", dashboard.users, name="admin_users"),
    path("portal/users/<int:pk>/", dashboard.user_detail, name="admin_user_detail"),
    path(
        "portal/users/<int:pk>/toggle/", dashboard.user_action, name="admin_user_action"
    ),
    path("portal/items/", dashboard.admin_items, name="admin_items"),
    path(
        "portal/items/<int:pk>/action/", dashboard.item_action, name="admin_item_action"
    ),
    path("portal/claims/", dashboard.admin_claims, name="admin_claims"),
    path(
        "portal/claims/<int:pk>/action/",
        dashboard.claim_action,
        name="admin_claim_action",
    ),
    path("portal/categories/", dashboard.categories, name="admin_categories"),
    path(
        "portal/categories/<int:pk>/", dashboard.categories, name="admin_category_edit"
    ),
    path(
        "portal/categories/<int:pk>/delete/",
        dashboard.delete_category,
        name="admin_category_delete",
    ),
    path("portal/reports/", report, name="reports"),
    path(
        "portal/notifications/",
        dashboard.admin_notifications,
        name="admin_notifications",
    ),
    path("portal/audit/", dashboard.audit_logs, name="audit_logs"),
    path("portal/settings/", dashboard.system_settings, name="system_settings"),
    path("django-admin/", admin.site.urls),
]
handler403 = partial(core.error_page, status=403)
handler404 = partial(core.error_page, status=404)
handler500 = partial(core.error_page, status=500)
