from django.contrib import admin

from .models import ApiToken, RosterAudit, Student, SyncIssue, SyncLog


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = (
        "last_name", "first_name", "panthersoft_id",
        "email", "term", "status", "last_synced_at",
    )
    list_filter = ("status", "term")
    search_fields = ("first_name", "last_name", "panthersoft_id", "email")


@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = (
        "started_at", "status", "added", "updated", "deactivated", "finished_at",
    )
    list_filter = ("status",)


@admin.register(RosterAudit)
class RosterAuditAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "student", "changed_by")
    list_filter = ("action",)
    search_fields = ("changed_by", "student__panthersoft_id")

@admin.register(SyncIssue)
class SyncIssueAdmin(admin.ModelAdmin):
    list_display = ("created_at", "kind", "identifier", "sync_log")
    list_filter = ("kind",)
    search_fields = ("identifier",)

@admin.register(ApiToken)
class ApiTokenAdmin(admin.ModelAdmin):
    """Tokens are created with `manage.py create_api_token`; here they can be revoked."""

    list_display = ("name", "prefix", "is_active", "created_at", "last_used_at")
    list_filter = ("is_active",)
    fields = ("name", "prefix", "is_active", "created_at", "last_used_at")
    readonly_fields = ("name", "prefix", "created_at", "last_used_at")

    def has_add_permission(self, request):
        return False