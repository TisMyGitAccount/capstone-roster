from django.db import models


class Student(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        PENDING_REVIEW = "pending_review", "Pending review"

    # Stable identity key. Names are display-only and never used to match students.
    panthersoft_id = models.CharField(max_length=20, unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    term = models.CharField(max_length=10)  # e.g. "FA26"
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    last_synced_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["last_name", "first_name"]
        indexes = [models.Index(fields=["term", "status"])]

    def __str__(self):
        return f"{self.last_name}, {self.first_name} ({self.panthersoft_id})"


class SyncLog(models.Model):
    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        PARTIAL = "partial", "Partial (needs review)"

    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices)
    added = models.IntegerField(default=0)
    updated = models.IntegerField(default=0)
    deactivated = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Sync {self.started_at:%Y-%m-%d %H:%M} ({self.status})"


class RosterAudit(models.Model):
    class Action(models.TextChoices):
        ADDED = "added", "Added"
        UPDATED = "updated", "Updated"
        DEACTIVATED = "deactivated", "Deactivated"
        MANUAL_OVERRIDE = "manual_override", "Manual override"

    student = models.ForeignKey(
        Student, null=True, on_delete=models.SET_NULL, related_name="audit_entries"
    )
    action = models.CharField(max_length=30, choices=Action.choices)
    changed_by = models.CharField(max_length=100)  # "sync" or an admin username
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} by {self.changed_by} at {self.created_at:%Y-%m-%d %H:%M}"