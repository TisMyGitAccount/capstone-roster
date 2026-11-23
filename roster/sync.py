from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .identity import fallback_candidates, id_problem, normalize_id
from .models import RosterAudit, Student, SyncIssue, SyncLog

TRACKED_FIELDS = ("first_name", "last_name", "email", "term")
REQUIRED_FIELDS = ("panthersoft_id",) + TRACKED_FIELDS
Kind = SyncIssue.Kind


def _issue(kind, raw, identifier="", **details):
    return {
        "kind": kind,
        "identifier": str(identifier)[:100],
        "record": raw,
        "details": details,
    }


def _classify(records, students):
    """Split raw source records into usable records and quarantined issues.

    Returns (clean, present_ids, issues). present_ids holds every valid ID the
    source mentioned, even if its record was quarantined, so those students
    are not mistaken for phantoms and deactivated.
    """
    issues, present, by_id = [], set(), {}

    for raw in records:
        sid = normalize_id(raw.get("panthersoft_id"))

        if not sid:  # ID-01, ID-07..09, ID-15: no ID, so only suggest candidates
            ids = [m.panthersoft_id for m in fallback_candidates(raw, students)]
            kind = Kind.AMBIGUOUS if len(ids) > 1 else Kind.MISSING_ID
            issues.append(_issue(kind, raw, possible_matches=ids))
            continue

        problem = id_problem(sid)
        if problem:  # ID-05, ID-06, ID-16
            issues.append(_issue(Kind.INVALID_ID, raw, sid, reason=problem))
            continue

        present.add(sid)
        rec = {
            "panthersoft_id": sid,
            "first_name": " ".join(str(raw.get("first_name") or "").split()),
            "last_name": " ".join(str(raw.get("last_name") or "").split()),
            "email": str(raw.get("email") or "").strip().lower(),
            "term": str(raw.get("term") or "").strip(),
        }
        missing = [f for f in TRACKED_FIELDS if not rec[f]]
        if missing:
            issues.append(_issue(Kind.INVALID_RECORD, raw, sid, missing_fields=missing))
            continue
        by_id.setdefault(sid, []).append((raw, rec))

    # ID-11: the same ID twice is a duplicate. Neither copy is chosen (ID-15).
    unique = []
    for sid, pairs in by_id.items():
        if len(pairs) > 1:
            for raw, _ in pairs:
                issues.append(_issue(Kind.DUPLICATE, raw, sid, copies=len(pairs)))
        else:
            unique.append(pairs[0])

    # ID-14: one email can't belong to two different identities.
    source_emails = {}
    for _, rec in unique:
        source_emails.setdefault(rec["email"], []).append(rec["panthersoft_id"])
    roster_owners = {s.email.lower(): s.panthersoft_id for s in students}

    clean = []
    for raw, rec in unique:
        sid, email = rec["panthersoft_id"], rec["email"]
        others = [i for i in source_emails[email] if i != sid]
        owner = roster_owners.get(email)
        if others:
            issues.append(_issue(
                Kind.CONFLICT, raw, sid,
                reason="Email is used by another source record", other_ids=others,
            ))
        elif owner and owner != sid:
            issues.append(_issue(
                Kind.CONFLICT, raw, sid,
                reason="Email belongs to a different student on the roster",
                roster_id=owner,
            ))
        else:
            clean.append(rec)
    return clean, present, issues


def _plan(records, present_ids, term, students):
    """Work out what would change, without touching the database."""
    existing = {s.panthersoft_id: s for s in students}

    to_add, to_update = [], []
    for rec in records:
        student = existing.get(rec["panthersoft_id"])
        if student is None:
            to_add.append(rec)  # ID-12: the source is the authority
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

    # ID-13: on our roster but absent from the source
    to_deactivate = [
        s for s in students
        if s.term == term
        and s.status == Student.Status.ACTIVE
        and s.panthersoft_id not in present_ids
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


def sync_roster(source, term, triggered_by="sync", source_label=""):
    threshold = getattr(settings, "ROSTER_SYNC_DEACTIVATION_THRESHOLD", 0.10)
    reject_threshold = getattr(settings, "ROSTER_SYNC_REJECT_THRESHOLD", 0.10)
    log = SyncLog.objects.create(
        started_at=timezone.now(),
        status=SyncLog.Status.FAILED,
        source=source_label[:200],
    )
    issues = []
    try:
        records = source.fetch_enrolled(term)
        if not records:
            raise ValueError("Source returned no students; roster left unchanged.")

        students = list(Student.objects.all())
        clean, present_ids, issues = _classify(records, students)

        if len(issues) / len(records) > reject_threshold:
            bad = len(issues)
            issues = []
            raise ValueError(
                f"{bad} of {len(records)} source records were unusable, so the "
                "source format may have changed. No changes were applied."
            )

        plan = _plan(clean, present_ids, term, students)
        active_count = Student.objects.filter(
            term=term, status=Student.Status.ACTIVE
        ).count()
        drop_count = len(plan["deactivate"])

        if active_count and drop_count / active_count > threshold:
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
        issues = []
        log.status = SyncLog.Status.FAILED
        log.error_message = str(exc)

    if issues:
        SyncIssue.objects.bulk_create(SyncIssue(sync_log=log, **i) for i in issues)
    log.finished_at = timezone.now()
    log.save()
    return log