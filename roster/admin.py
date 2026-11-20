from django.contrib import admin

from .models import RosterAudit, Student, SyncLog


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