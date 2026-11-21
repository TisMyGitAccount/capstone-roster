import re

from django.conf import settings

# Identity components for the fallback when a record has no ID (ID-07).
FALLBACK_FIELDS = ("first_name", "last_name")


def expected_length():
    return getattr(settings, "ROSTER_ID_LENGTH", 7)


def normalize_id(raw):
    """ID-03/04/05: trim whitespace only.

    IDs are digits, which have no case. Nothing else is stripped or
    rewritten (ID-16), so leading zeros and hyphens stay significant.
    """
    return "" if raw is None else str(raw).strip()


def id_problem(sid):
    """Return why a non-blank, normalized ID is unusable, or None if it's fine."""
    if not re.fullmatch(r"[0-9]+", sid):  # explicit 0-9: rejects letters and Unicode digits
        return "Student IDs contain only the digits 0-9"
    if len(sid) != expected_length():  # ID-06: partial IDs never match
        return (
            f"Student IDs must be exactly {expected_length()} digits "
            "(partial IDs never match)"
        )
    return None


def normalize_text(raw):
    return " ".join(str(raw or "").split()).casefold()


def fallback_candidates(record, students):
    """ID-07/08/09: students whose identity components ALL match.

    A missing component matches nothing. Results are suggestions for an
    admin and are never merged automatically.
    """
    wanted = {f: normalize_text(record.get(f)) for f in FALLBACK_FIELDS}
    if not all(wanted.values()):
        return []
    return [
        s for s in students
        if all(normalize_text(getattr(s, f)) == wanted[f] for f in FALLBACK_FIELDS)
    ]