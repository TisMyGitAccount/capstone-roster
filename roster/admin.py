from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import BooleanField, Case, Value, When
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path

from .dashboard import build_sync_banner, namesake_ids
from .forms import RosterImportForm, StatusOverrideForm
from .importing import run_csv_import
from .models import ApiToken, RosterAudit, Student, SyncIssue, SyncLog


class SameNameFilter(admin.SimpleListFilter):
    title = "same name"
    parameter_name = "same_name"

    def lookups(self, request, model_admin):
        return [
            ("yes", "Shares a name with another student"),
            ("no", "Name is unique"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(pk__in=list(namesake_ids()))
        if self.value() == "no":
            return queryset.exclude(pk__in=list(namesake_ids()))
        return queryset


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    change_list_template = "admin/roster/student/change_list.html"
    list_display = (
        "last_name", "first_name", "panthersoft_id", "email",
        "term", "status", "namesake", "last_synced_at",
    )
    list_filter = ("status", "term", SameNameFilter)
    search_fields = ("first_name", "last_name", "panthersoft_id", "email")
    actions = ["change_status"]

    # --- list display -------------------------------------------------

    def get_queryset(self, request):
        ids = list(namesake_ids())
        return super().get_queryset(request).annotate(
            has_namesake=Case(
                When(pk__in=ids, then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            )
        )

    @admin.display(description="Same name", ordering="has_namesake")
    def namesake(self, obj):
        return "Shared name" if getattr(obj, "has_namesake", False) else ""

    def changelist_view(self, request, extra_context=None):
        extra_context = dict(extra_context or {})
        extra_context["sync_banner"] = build_sync_banner()
        return super().changelist_view(request, extra_context=extra_context)

    # --- edits must go through the audited paths ----------------------

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()  # a student can still be entered by hand
        return (
            "panthersoft_id", "first_name", "last_name", "email", "term",
            "status", "last_synced_at", "created_at", "updated_at",
        )

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            RosterAudit.objects.create(
                student=obj,
                action=RosterAudit.Action.ADDED,
                changed_by=request.user.get_username(),
                details={"manual_entry": True, "panthersoft_id": obj.panthersoft_id},
            )
            messages.warning(
                request,
                "Entered by hand. The next import will deactivate this student "
                "unless the source lists them.",
            )

    # --- status override with a required reason -----------------------

    @admin.action(
        description="Change status (a reason is required)",
        permissions=["change"],
    )
    def change_status(self, request, queryset):
        if "apply" in request.POST:
            form = StatusOverrideForm(request.POST)
            if form.is_valid():
                changed, total = self._apply_override(request, queryset, form.cleaned_data)
                label = Student.Status(form.cleaned_data["new_status"]).label
                if changed:
                    messages.success(request, f"Changed {changed} student(s) to {label}.")
                    messages.warning(
                        request,
                        "The source is still the authority: a later import can reverse "
                        "this if the source disagrees (for example, an active student "
                        "missing from the file is deactivated again). The change and "
                        "your reason are in the audit log.",
                    )
                if total - changed:
                    messages.info(
                        request, f"{total - changed} student(s) already had that status."
                    )
                return HttpResponseRedirect(request.get_full_path())
        else:
            form = StatusOverrideForm()

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Change student status",
            "form": form,
            "students_shown": list(queryset[:20]),
            "total": queryset.count(),
            "selected": request.POST.getlist(helpers.ACTION_CHECKBOX_NAME),
            "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
            "select_across": request.POST.get("select_across", "0"),
            "cancel_url": request.get_full_path(),
        }
        return TemplateResponse(request, "roster/change_status.html", context)

    def _apply_override(self, request, queryset, data):
        new_status, reason = data["new_status"], data["reason"]
        who = request.user.get_username()
        changed = 0
        with transaction.atomic():
            students = list(queryset)
            for student in students:
                if student.status == new_status:
                    continue
                old_status = student.status
                student.status = new_status
                student.save(update_fields=["status", "updated_at"])
                RosterAudit.objects.create(
                    student=student,
                    action=RosterAudit.Action.MANUAL_OVERRIDE,
                    changed_by=who,
                    details={"from": old_status, "to": new_status, "reason": reason},
                )
                changed += 1
        return changed, len(students)

    # --- CSV import ---------------------------------------------------

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
    """The audit log is read-only: entries can't be added, edited, or deleted."""

    list_display = ("created_at", "action", "student", "changed_by", "summary")
    list_filter = ("action",)
    search_fields = ("changed_by", "student__panthersoft_id")

    @admin.display(description="Details")
    def summary(self, obj):
        details = obj.details or {}
        if obj.action == RosterAudit.Action.MANUAL_OVERRIDE:
            return f"{details.get('from')} -> {details.get('to')}: {details.get('reason', '')}"
        if obj.action == RosterAudit.Action.UPDATED:
            return "; ".join(
                f"{field}: {old} -> {new}"
                for field, (old, new) in details.get("changes", {}).items()
            )
        if obj.action == RosterAudit.Action.DEACTIVATED:
            return details.get("reason", "")
        if details.get("manual_entry"):
            return "Entered by hand"
        return ""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ApiToken)
class ApiTokenAdmin(admin.ModelAdmin):
    """Tokens are created with `manage.py create_api_token`; here they can be revoked."""

    list_display = ("name", "prefix", "is_active", "created_at", "last_used_at")
    list_filter = ("is_active",)
    fields = ("name", "prefix", "is_active", "created_at", "last_used_at")
    readonly_fields = ("name", "prefix", "created_at", "last_used_at")

    def has_add_permission(self, request):
        return False