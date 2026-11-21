from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import RosterAudit, Student, SyncLog

TRACKED_FIELDS = ("first_name", "last_name", "email", "term")
REQUIRED_FIELDS = ("panthersoft_id",) + TRACKED_FIELDS


def _validate(records):
    """Fail safe: refuse to sync from empty or malformed source data."""
    if not records:
        raise ValueError("Source returned no students; roster left unchanged.")
    seen_ids, seen_emails = set(), set()
    for rec in records:
        for field in REQUIRED_FIELDS:
            if not rec.get(field):
                raise ValueError(f"Record missing '{field}': {rec}")
        if rec["panthersoft_id"] in seen_ids:
            raise ValueError(f"Duplicate ID in source: {rec['panthersoft_id']}")
        if rec["email"] in seen_emails:
            raise ValueError(f"Duplicate email in source: {rec['email']}")
        seen_ids.add(rec["panthersoft_id"])
        seen_emails.add(rec["email"])


def _plan(records, term):
    """Work out what would change, without touching the database."""
    existing = {s.panthersoft_id: s for s in Student.objects.all()}
    source_ids = {r["panthersoft_id"] for r in records}

    to_add, to_update = [], []
    for rec in records:
        student = existing.get(rec["panthersoft_id"])
        if student is None:
            to_add.append(rec)
            continue
        changes = {
            f: [getattr(student, f), rec[f]]
            for f in TRACKED_FIELDS
            if getattr(student, f) != rec[f]
        }
        if student.status == Student.Status.INACTIVE:
            changes["status"] = [student.status, Student.Status.ACTIVE]
        if changes:
            to_update.append((student, rec, changes))

    # Phantoms: active in our copy, but no longer in the source
    to_deactivate = [
        s for s in existing.values()
        if s.term == term
        and s.status == Student.Status.ACTIVE
        and s.panthersoft_id not in source_ids
    ]
    return {"add": to_add, "update": to_update, "deactivate": to_deactivate}


def _apply(plan, term, now, by):
    for rec in plan["add"]:
        student = Student.objects.create(
            **{f: rec[f] for f in REQUIRED_FIELDS}, last_synced_at=now
        )
        RosterAudit.objects.create(
            student=student, action=RosterAudit.Action.ADDED, changed_by=by,
            details={f: rec[f] for f in REQUIRED_FIELDS},
        )

    for student, rec, changes in plan["update"]:
        for f in TRACKED_FIELDS:
            setattr(student, f, rec[f])
        if "status" in changes:
            student.status = Student.Status.ACTIVE
        student.last_synced_at = now
        student.save()
        RosterAudit.objects.create(
            student=student, action=RosterAudit.Action.UPDATED, changed_by=by,
            details={"changes": changes},
        )

    for student in plan["deactivate"]:
        student.status = Student.Status.INACTIVE
        student.save()
        RosterAudit.objects.create(
            student=student, action=RosterAudit.Action.DEACTIVATED, changed_by=by,
            details={"reason": "No longer present in source"},
        )

    # Everyone still active in this term was confirmed by the source just now
    Student.objects.filter(term=term, status=Student.Status.ACTIVE).update(
        last_synced_at=now
    )
    return len(plan["add"]), len(plan["update"]), len(plan["deactivate"])


def sync_roster(source, term, triggered_by="sync"):
    threshold = getattr(settings, "ROSTER_SYNC_DEACTIVATION_THRESHOLD", 0.10)
    log = SyncLog.objects.create(
        started_at=timezone.now(), status=SyncLog.Status.FAILED
    )
    try:
        records = source.fetch_enrolled(term)
        _validate(records)
        plan = _plan(records, term)

        active_count = Student.objects.filter(
            term=term, status=Student.Status.ACTIVE
        ).count()
        drop_count = len(plan["deactivate"])

        if active_count and drop_count / active_count > threshold:
            # Sanity threshold: hold the whole sync for admin review
            log.status = SyncLog.Status.PARTIAL
            log.error_message = (
                f"Blocked: this sync would deactivate {drop_count} of "
                f"{active_count} active students "
                f"({drop_count / active_count:.0%}), above the "
                f"{threshold:.0%} limit. No changes were applied."
            )
        else:
            with transaction.atomic():
                added, updated, deactivated = _apply(
                    plan, term, timezone.now(), triggered_by
                )
            log.added, log.updated, log.deactivated = added, updated, deactivated
            log.status = SyncLog.Status.SUCCESS
    except Exception as exc:
        # Any error rolls back the changes, so the old roster stays intact
        log.status = SyncLog.Status.FAILED
        log.error_message = str(exc)

    log.finished_at = timezone.now()
    log.save()
    return log