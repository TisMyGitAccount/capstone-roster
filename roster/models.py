import hashlib
import secrets

from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone


class Student(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        PENDING_REVIEW = "pending_review", "Pending review"

    # Stable identity key. Names are display-only and never used to match students.
    panthersoft_id = models.CharField(
        max_length=20,
        unique=True,
        validators=[RegexValidator(r"^[0-9]+$", "Student IDs contain digits only.")],
    )
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


class SyncIssue(models.Model):
    """A source record that was set aside instead of being applied."""

    class Kind(models.TextChoices):
        INVALID_ID = "invalid_id", "Invalid ID"
        INVALID_RECORD = "invalid_record", "Missing required field"
        MISSING_ID = "missing_id", "Missing ID"
        DUPLICATE = "duplicate", "Duplicate ID in source"
        CONFLICT = "conflict", "Conflict"
        AMBIGUOUS = "ambiguous", "Ambiguous match"

    sync_log = models.ForeignKey(
        SyncLog, on_delete=models.CASCADE, related_name="issues"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    identifier = models.CharField(max_length=100, blank=True)
    record = models.JSONField(default=dict)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.kind}: {self.identifier or '(no ID)'}"


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


class ApiToken(models.Model):
    """A read-only access token for one consuming site. Only a hash is stored."""

    name = models.CharField(max_length=100, unique=True)  # which site it is for
    prefix = models.CharField(max_length=8, editable=False)
    key_hash = models.CharField(max_length=64, unique=True, editable=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.prefix}...)"

    @staticmethod
    def hash_key(raw):
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @classmethod
    def create_token(cls, name):
        """Returns (token, raw_key). The raw key is never stored."""
        raw = secrets.token_urlsafe(32)
        token = cls.objects.create(
            name=name, prefix=raw[:8], key_hash=cls.hash_key(raw)
        )
        return token, raw

    @classmethod
    def from_raw_key(cls, raw):
        token = cls.objects.filter(key_hash=cls.hash_key(raw), is_active=True).first()
        if token:
            cls.objects.filter(pk=token.pk).update(last_used_at=timezone.now())
        return token