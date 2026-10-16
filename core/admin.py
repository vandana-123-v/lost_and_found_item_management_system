from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from accounts.models import User
from items.models import Item, Category
from claims.models import Claim
from notifications.models import Notification
from ai_module.models import AIAnalysis, MatchSuggestion
from .models import AuditLog, ContactMessage


@admin.register(User)
class AccountsAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Profile", {"fields": ("full_name", "phone", "avatar")}),
    )

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return False


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


for model in [
    Item,
    Category,
    Claim,
    Notification,
    AIAnalysis,
    MatchSuggestion,
    AuditLog,
    ContactMessage,
]:
    admin.site.register(model, ReadOnlyAdmin)
admin.site.site_header = "Lost & Found • Development administration"
