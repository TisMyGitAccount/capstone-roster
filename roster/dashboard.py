from collections import defaultdict

from django.utils import timezone

from .api import current_term, freshness
from .identity import normalize_text
from .models import Student, SyncLog


def namesake_ids():
    """IDs of students who share a name with another student in the same term.

    Names are compared ignoring case and extra spaces. This only flags; it
    never merges, because students who share a name are different people.
    """
    groups = defaultdict(list)
    rows = Student.objects.values_list("pk", "term", "first_name", "last_name")
    for pk, term, first, last in rows:
        first, last = normalize_text(first), normalize_text(last)
        if first and last:
            groups[(term, first, last)].append(pk)
    return {pk for pks in groups.values() if len(pks) > 1 for pk in pks}


def _when(moment):
    return timezone.localtime(moment).strftime("%Y-%m-%d %H:%M")


def _age(hours):
    if hours is None:
        return ""
    if hours < 1:
        return "less than an hour ago"
    if hours < 48:
        n = round(hours)
        return f"{n} hour{'s' if n != 1 else ''} ago"
    return f"{round(hours / 24)} days ago"


def build_sync_banner():
    """The status lines shown above the student list, as (level, text) pairs."""
    term = current_term()
    fresh = freshness()
    status = SyncLog.Status
    last_ok = (
        SyncLog.objects.filter(status=status.SUCCESS, finished_at__isnull=False)
        .order_by("-finished_at", "-pk")
        .first()
    )
    latest = SyncLog.objects.order_by("-started_at", "-pk").first()
    lines = []

    if latest is None:
        lines.append((
            "error",
            "No roster data has been imported yet. Use Import roster file to load an export.",
        ))
    else:
        if last_ok is None:
            lines.append(("error", "The roster has never been imported successfully."))
        else:
            lines.append((
                "warning" if fresh["stale"] else "success",
                f"Roster last confirmed {_when(last_ok.finished_at)} "
                f"({_age(fresh['age_hours'])}) from {last_ok.source or 'an unrecorded source'}.",
            ))
            if fresh["stale"]:
                lines.append((
                    "warning",
                    f"That is older than the {fresh['stale_after_hours']}-hour limit, so the "
                    "roster may be out of date. Import a fresh export.",
                ))
        if latest.status == status.PARTIAL:
            lines.append((
                "warning",
                f"The most recent import ({_when(latest.started_at)}) was blocked for review "
                f"and changed nothing: {latest.error_message}",
            ))
        elif latest.status == status.FAILED:
            lines.append((
                "error",
                f"The most recent import attempt ({_when(latest.started_at)}) failed and "
                f"changed nothing: {latest.error_message}",
            ))
        set_aside = latest.issues.count()
        if set_aside:
            lines.append((
                "warning",
                f"{set_aside} record(s) from the latest import were set aside and not "
                "applied. See Sync issues.",
            ))

    counts = {
        value: Student.objects.filter(term=term, status=value).count()
        for value in Student.Status.values
    }
    lines.append((
        "success",
        f"{term}: {counts['active']} active, {counts['inactive']} inactive, "
        f"{counts['pending_review']} held for review.",
    ))
    if counts["pending_review"]:
        lines.append((
            "warning",
            f"{counts['pending_review']} student(s) are held for review and are not "
            "eligible until an administrator resolves them.",
        ))

    namesakes = Student.objects.filter(term=term, pk__in=list(namesake_ids())).count()
    return {"term": term, "lines": lines, "namesakes": namesakes}