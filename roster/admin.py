from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.template.response import TemplateResponse
from django.urls import path

from .forms import RosterImportForm
from .importing import run_csv_import
from .models import ApiToken, RosterAudit, Student, SyncIssue, SyncLog


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    change_list_template = "admin/roster/student/change_list.html"
    list_display = (
        "last_name", "first_name", "panthersoft_id",
        "email", "term", "status", "last_synced_at",
    )
    list_filter = ("status", "term")
    search_fields = ("first_name", "last_name", "panthersoft_id", "email")

    def get_urls(self):
        custom = [
            path(
                "import/",
                self.admin_site.admin_view(self.import_view),
                name="roster_student_import",
            ),
        ]
        return custom + super().get_urls()

    def import_view(self, request):
        if not (self.has_add_permission(request) and self.has_change_permission(request)):
            raise PermissionDenied

        result = None
        if request.method == "POST":
            form = RosterImportForm(request.POST, request.FILES)
            if form.is_valid():
                upload = form.cleaned_data["file"]
                result = run_csv_import(
                    content=upload.read(),
                    filename=upload.name,
                    term=form.cleaned_data["term"],
                    username=request.user.get_username(),
                    apply=form.cleaned_data["mode"] == "apply",
                )
        else:
            form = RosterImportForm()

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Import roster file",
            "form": form,
            "result": result,
        }
        return TemplateResponse(request, "roster/import.html", context)


@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = (
        "started_at", "status", "source", "added", "updated",
        "deactivated", "finished_at",
    )
    list_filter = ("status",)


@admin.register(SyncIssue)
class SyncIssueAdmin(admin.ModelAdmin):
    list_display = ("created_at", "kind", "identifier", "sync_log")
    list_filter = ("kind",)
    search_fields = ("identifier",)


@admin.register(RosterAudit)
class RosterAuditAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "student", "changed_by")
    list_filter = ("action",)
    search_fields = ("changed_by", "student__panthersoft_id")


@admin.register(ApiToken)
class ApiTokenAdmin(admin.ModelAdmin):
    """Tokens are created with `manage.py create_api_token`; here they can be revoked."""

    list_display = ("name", "prefix", "is_active", "created_at", "last_used_at")
    list_filter = ("is_active",)
    fields = ("name", "prefix", "is_active", "created_at", "last_used_at")
    readonly_fields = ("name", "prefix", "created_at", "last_used_at")

    def has_add_permission(self, request):
        return False