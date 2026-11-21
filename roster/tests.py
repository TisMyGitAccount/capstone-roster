from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from .identity import normalize_id
from .models import RosterAudit, Student, SyncIssue, SyncLog
from .sources import MockPanthersoftSource, SourceError
from .sync import sync_roster

TERM = "FA26"


def sid(n):
    return str(9000000 + n)


def rec(n, first=None, last=None, **overrides):
    """Build one fake source record (7-digit numeric ID)."""
    record = {
        "panthersoft_id": sid(n),
        "first_name": first if first is not None else f"First{n}",
        "last_name": last if last is not None else f"Last{n}",
        "email": f"s{n}@example.edu",
        "term": TERM,
    }
    record.update(overrides)
    return record


class FakeSource:
    """In-memory stand-in for Panthersoft, used to control test scenarios."""

    def __init__(self, records=None, error=None):
        self.records = records or []
        self.error = error

    def fetch_enrolled(self, term):
        if self.error:
            raise self.error
        return self.records


class SeededRosterTestCase(TestCase):
    """Every test starts with 30 active students already on the roster."""

    def setUp(self):
        self.base = [rec(n) for n in range(1, 31)]
        log = sync_roster(FakeSource(self.base), TERM)
        self.assertEqual((log.status, log.added), ("success", 30))

    def sync(self, records):
        return sync_roster(FakeSource(records), TERM)

    def active_count(self):
        return Student.objects.filter(status=Student.Status.ACTIVE).count()

    def issue_count(self, kind):
        return SyncIssue.objects.filter(kind=kind).count()


class IdentityRuleTests(SeededRosterTestCase):
    def test_ID_01_blank_id_is_quarantined_not_created(self):
        log = self.sync(self.base + [rec(50, panthersoft_id="")])
        self.assertEqual(log.status, "success")
        self.assertEqual(Student.objects.count(), 30)
        self.assertEqual(self.issue_count("missing_id"), 1)

    def test_ID_02_database_rejects_duplicate_ids(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Student.objects.create(
                    panthersoft_id=sid(1), first_name="X", last_name="Y",
                    email="other@example.edu", term=TERM,
                    last_synced_at=timezone.now(),
                )

    def test_ID_03_04_whitespace_does_not_change_identity(self):
        padded = [dict(r) for r in self.base]
        padded[0]["panthersoft_id"] = f"  {sid(1)}  "
        log = self.sync(padded)
        self.assertEqual((log.added, log.updated, log.deactivated), (0, 0, 0))
        self.assertEqual(Student.objects.count(), 30)
        self.assertEqual(SyncIssue.objects.count(), 0)

    def test_ID_05_letters_make_an_id_invalid_in_any_case(self):
        log = self.sync(self.base + [
            rec(51, panthersoft_id="S900051"),
            rec(52, panthersoft_id="s900052"),
        ])
        self.assertEqual(log.status, "success")
        self.assertEqual(self.issue_count("invalid_id"), 2)
        self.assertEqual(Student.objects.count(), 30)

    def test_ID_05_non_ascii_digits_are_invalid(self):
        arabic_indic = "\u0669\u0660\u0660\u0660\u0660\u0665\u0663"  # looks numeric
        self.sync(self.base + [rec(53, panthersoft_id=arabic_indic)])
        self.assertEqual(self.issue_count("invalid_id"), 1)
        self.assertEqual(Student.objects.count(), 30)

    def test_ID_06_partial_id_never_matches(self):
        self.sync(self.base + [
            rec(1, panthersoft_id="900000", email="partial@example.edu")
        ])
        self.assertEqual(self.issue_count("invalid_id"), 1)
        self.assertEqual(Student.objects.get(panthersoft_id=sid(1)).email, "s1@example.edu")
        self.assertEqual(Student.objects.count(), 30)

    def test_ID_07_08_09_fallback_suggests_but_never_merges(self):
        # ID-07: all components match -> one suggested candidate
        log = self.sync(self.base + [rec(60, "First3", "Last3", panthersoft_id="")])
        issue = SyncIssue.objects.get(sync_log=log)
        self.assertEqual(issue.kind, "missing_id")
        self.assertEqual(issue.details["possible_matches"], [sid(3)])

        # ID-08: only the first name matches -> no candidates
        log = self.sync(self.base + [rec(61, "First3", "Other", panthersoft_id="")])
        self.assertEqual(SyncIssue.objects.get(sync_log=log).details["possible_matches"], [])

        # ID-09: missing component -> no candidates
        log = self.sync(self.base + [rec(62, "First3", "", panthersoft_id="")])
        self.assertEqual(SyncIssue.objects.get(sync_log=log).details["possible_matches"], [])

        self.assertEqual(Student.objects.count(), 30)  # nothing was merged or created

    def test_ID_10_15_ambiguous_matches_select_nothing(self):
        anas = [rec(70, "Ana", "Lopez"), rec(71, "Ana", "Lopez")]
        self.sync(self.base + anas)
        log = self.sync(self.base + anas + [rec(72, "Ana", "Lopez", panthersoft_id="")])
        issue = SyncIssue.objects.get(sync_log=log)
        self.assertEqual(issue.kind, "ambiguous")
        self.assertEqual(sorted(issue.details["possible_matches"]), [sid(70), sid(71)])
        self.assertEqual(Student.objects.count(), 32)

    def test_ID_11_same_id_twice_is_classified_as_duplicate(self):
        log = self.sync(self.base + [dict(self.base[0])])
        self.assertEqual(log.status, "success")
        self.assertEqual(self.issue_count("duplicate"), 2)  # neither copy is chosen
        self.assertEqual(log.deactivated, 0)
        self.assertEqual(Student.objects.get(panthersoft_id=sid(1)).status, "active")

    def test_ID_12_new_source_record_is_added(self):
        log = self.sync(self.base + [rec(99)])
        self.assertEqual(log.added, 1)
        self.assertEqual(Student.objects.get(panthersoft_id=sid(99)).status, "active")
        self.assertTrue(RosterAudit.objects.filter(
            action="added", student__panthersoft_id=sid(99)).exists())

    def test_ID_13_roster_student_missing_from_source_is_deactivated(self):
        log = self.sync(self.base[:-1])
        self.assertEqual(log.deactivated, 1)
        self.assertEqual(Student.objects.get(panthersoft_id=sid(30)).status, "inactive")
        self.assertTrue(RosterAudit.objects.filter(action="deactivated").exists())

    def test_ID_14_email_owned_by_a_different_student_is_a_conflict(self):
        self.sync(self.base[:-1])  # student 30 becomes inactive
        log = self.sync(self.base[:-1] + [rec(55, email=rec(30)["email"])])
        issue = SyncIssue.objects.get(sync_log=log)
        self.assertEqual(issue.kind, "conflict")
        self.assertEqual(issue.details["roster_id"], sid(30))
        self.assertFalse(Student.objects.filter(panthersoft_id=sid(55)).exists())

    def test_ID_14_two_source_records_sharing_an_email_both_conflict(self):
        new = [rec(80), rec(81, email=rec(80)["email"])]
        self.sync(self.base + new)
        self.assertEqual(self.issue_count("conflict"), 2)
        self.assertEqual(Student.objects.count(), 30)

    def test_ID_16_significant_characters_are_never_stripped(self):
        self.assertEqual(normalize_id("  0012345 "), "0012345")
        self.assertEqual(normalize_id("900-0001"), "900-0001")
        self.assertNotEqual(normalize_id("0012345"), normalize_id("12345"))
        self.sync(self.base + [rec(90, panthersoft_id="900-0090")])
        self.assertEqual(self.issue_count("invalid_id"), 1)


class SafeguardTests(SeededRosterTestCase):
    def test_same_name_students_stay_separate(self):
        self.sync(self.base + [rec(80, "Ana", "Lopez"), rec(81, "Ana", "Lopez")])
        twins = Student.objects.filter(first_name="Ana", last_name="Lopez")
        self.assertEqual(twins.count(), 2)

    def test_info_change_is_updated_and_audited(self):
        changed = [dict(r) for r in self.base]
        changed[0]["email"] = "new.address@example.edu"
        log = self.sync(changed)
        self.assertEqual(log.updated, 1)
        self.assertEqual(
            Student.objects.get(panthersoft_id=sid(1)).email, "new.address@example.edu"
        )
        entry = RosterAudit.objects.get(action="updated")
        self.assertIn("email", entry.details["changes"])

    def test_returning_student_is_reactivated(self):
        self.sync(self.base[:-1])
        log = self.sync(self.base)
        self.assertEqual(log.status, "success")
        self.assertEqual(Student.objects.get(panthersoft_id=sid(30)).status, "active")

    def test_mass_drop_is_blocked(self):
        log = self.sync(self.base[:26])  # 4 of 30 = 13%
        self.assertEqual(log.status, "partial")
        self.assertIn("Blocked", log.error_message)
        self.assertEqual(self.active_count(), 30)

    def test_empty_source_leaves_roster_untouched(self):
        log = self.sync([])
        self.assertEqual(log.status, "failed")
        self.assertEqual(self.active_count(), 30)

    def test_source_outage_leaves_roster_untouched(self):
        log = sync_roster(FakeSource(error=SourceError("down")), TERM)
        self.assertEqual(log.status, "failed")
        self.assertEqual(self.active_count(), 30)

    def test_too_many_unusable_records_refuses_the_whole_sync(self):
        junk = [rec(n, panthersoft_id="") for n in range(40, 45)]  # 5 of 35 = 14%
        log = self.sync(self.base + junk)
        self.assertEqual(log.status, "failed")
        self.assertEqual(self.active_count(), 30)
        self.assertEqual(SyncIssue.objects.count(), 0)


class DemoSnapshotTests(TestCase):
    def test_demo_snapshots_in_sequence(self):
        log1 = sync_roster(MockPanthersoftSource("snapshot_1.json"), TERM)
        self.assertEqual((log1.status, log1.added), ("success", 300))

        log2 = sync_roster(MockPanthersoftSource("snapshot_2.json"), TERM)
        self.assertEqual(log2.status, "success")
        self.assertEqual(log2.added, 13)
        self.assertEqual(log2.deactivated, 8)
        self.assertGreaterEqual(log2.updated, 5)

        dirty = sync_roster(MockPanthersoftSource("snapshot_dirty.json"), TERM)
        self.assertEqual(dirty.status, "success")
        self.assertEqual((dirty.added, dirty.updated, dirty.deactivated), (0, 0, 0))
        kinds = {
            k: dirty.issues.filter(kind=k).count()
            for k in ("invalid_id", "missing_id", "ambiguous", "duplicate", "conflict")
        }
        self.assertEqual(kinds, {
            "invalid_id": 2, "missing_id": 1, "ambiguous": 1,
            "duplicate": 2, "conflict": 2,
        })

        log3 = sync_roster(MockPanthersoftSource("snapshot_3_mass_drop.json"), TERM)
        self.assertEqual(log3.status, "partial")

        log4 = sync_roster(MockPanthersoftSource("fail"), TERM)
        self.assertEqual(log4.status, "failed")

        active = Student.objects.filter(status="active").count()
        self.assertEqual(active, 305)  # 313 students in total, 8 of them inactive
        self.assertEqual(Student.objects.count(), 313)