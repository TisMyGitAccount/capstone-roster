import os

from django.conf import settings
from django.db import transaction

from .models import RosterAudit
from .sources import CsvSource
from .sync import sync_roster

MAX_LISTED = 50
GROUP_TITLES = {"added": "Added", "updated": "Updated", "deactivated": "Deactivated"}


class _Rollback(Exception):
    """Raised on purpose to undo a preview."""


def default_term():
    return getattr(settings, "ROSTER_CURRENT_TERM", "FA26")


def _describe_issue(issue):
    parts = []
    for key, value in issue.details.items():
        if isinstance(value, (list, tuple)):
            value = ", ".join(str(v) for v in value) or "none"
        parts.append(f"{key.replace('_', ' ')}: {value}")
    return "; ".join(parts)


def _describe_change(entry):
    details = entry.details
    if entry.action == RosterAudit.Action.UPDATED:
        return "; ".join(
            f"{field}: {old} -> {new}"
            for field, (old, new) in details.get("changes", {}).items()
        )
    if entry.action == RosterAudit.Action.DEACTIVATED:
        return details.get("reason", "")
    return ""


def _summarize(log, mode):
    entries = RosterAudit.objects.filter(
        student__isnull=False,
        created_at__gte=log.started_at,
        created_at__lte=log.finished_at,
    ).select_related("student")

    rows = {action: [] for action in GROUP_TITLES}
    for entry in entries:
        if entry.action in rows:
            student = entry.student
            rows[entry.action].append((
                student.panthersoft_id,
                f"{student.first_name} {student.last_name}",
                _describe_change(entry),
            ))

    groups = []
    for action, title in GROUP_TITLES.items():
        found = sorted(rows[action])
        if found:
            groups.append({
                "title": title,
                "total": len(found),
                "rows": found[:MAX_LISTED],
                "hidden": max(0, len(found) - MAX_LISTED),
            })

    issues = [
        {
            "kind": issue.get_kind_display(),
            "identifier": issue.identifier or "(no ID)",
            "reason": _describe_issue(issue),
        }
        for issue in log.issues.all()
    ]
    return {
        "mode": mode,
        "status": log.status,
        "message": log.error_message,
        "source": log.source,
        "added": log.added,
        "updated": log.updated,
        "deactivated": log.deactivated,
        "groups": groups,
        "issues": issues[:MAX_LISTED],
        "issues_total": len(issues),
    }


def run_csv_import(content, filename, term, username, apply):
    """Import a CSV export. With apply=False, show what would happen and undo it."""
    term = term.strip().upper()
    source = CsvSource(content)
    label = f"csv: {os.path.basename(filename)} (by {username})"

    if apply:
        log = sync_roster(source, term, triggered_by=username, source_label=label)
        return _summarize(log, "applied")

    # Preview: run the real sync inside a transaction, read the outcome, undo it.
    result = None
    try:
        with transaction.atomic():
            log = sync_roster(source, term, triggered_by="preview", source_label=label)
            result = _summarize(log, "preview")
            raise _Rollback
    except _Rollback:
        pass
    return result