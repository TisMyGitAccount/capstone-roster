from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from .dashboard import build_sync_banner, namesake_ids
from .models import RosterAudit, Student, SyncLog
from .sync import sync_roster
from .tests import FakeSource, rec, sid

TERM = "FA26"
LIST_URL = "/admin/roster/student/"


@override_settings(ROSTER_CURRENT_TERM=TERM, ROSTER_STALE_AFTER_HOURS=24)
class AdminTestCase(TestCase):
    """Every test starts with a logged-in superuser named 'boss'."""

    def setUp(self):
        self.base = [rec(n) for n in range(1, 31)]
        self.boss = get_user_model().objects.create_superuser(
            "boss", "boss@example.edu", "pw"
        )
        self.client.force_login(self.boss)

    def sync(self, records, label="csv: roster.csv (by boss)"):
        return sync_roster(FakeSource(records), TERM, source_label=label)

    def student(self, n):
        return Student.objects.get(panthersoft_id=sid(n))


class SyncBannerTests(AdminTestCase):
    def levels(self):
        return {level for level, _ in build_sync_banner()["lines"]}

    def text(self):
        return " ".join(text for _, text in build_sync_banner()["lines"])

    def test_empty_roster_says_nothing_has_been_imported(self):
        self.assertEqual(build_sync_banner()["lines"][0][0], "error")
        self.assertContains(self.client.get(LIST_URL), "No roster data")

    def test_fresh_import_shows_source_and_counts(self):
        self.sync(self.base)
        self.assertEqual(self.levels(), {"success"})
        self.assertIn("csv: roster.csv (by boss)", self.text())
        self.assertIn("30 active", self.text())
        self.assertContains(self.client.get(LIST_URL), "csv: roster.csv (by boss)")

    def test_stale_roster_is_flagged(self):
        self.sync(self.base)
        SyncLog.objects.update(finished_at=timezone.now() - timedelta(hours=30))
        self.assertIn("warning", self.levels())
        self.assertIn("out of date", self.text())

    def test_blocked_import_is_reported(self):
        self.sync(self.base)
        self.sync(self.base[:20])  # would drop 10 of 30
        self.assertIn("blocked for review", self.text())
        self.assertIn("warning", self.levels())

    def test_failed_import_is_an_error(self):
        self.sync(self.base)
        self.sync([])  # an empty file fails
        self.assertIn("error", self.levels())
        self.assertIn("failed", self.text())

    def test_set_aside_records_are_reported(self):
        self.sync(self.base + [rec(60, panthersoft_id="")])
        self.assertIn("set aside", self.text())

    def test_students_held_for_review_are_called_out(self):
        self.sync(self.base)
        Student.objects.filter(panthersoft_id=sid(2)).update(status="pending_review")
        self.assertIn("held for review", self.text())


class SameNameTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        self.sync(self.base + [rec(70, "Ana", "Lopez"), rec(71, "ANA", " lopez ")])

    def test_names_match_ignoring_case_and_spacing(self):
        self.assertEqual(namesake_ids(), {self.student(70).pk, self.student(71).pk})

    def test_same_name_in_another_term_is_not_flagged(self):
        Student.objects.create(
            panthersoft_id=sid(500), first_name="Ana", last_name="Lopez",
            email="old@example.edu", term="SP26", last_synced_at=timezone.now(),
        )
        self.assertEqual(len(namesake_ids()), 2)

    def test_filter_separates_namesakes_from_unique_names(self):
        yes = self.client.get(LIST_URL, {"same_name": "yes"})
        no = self.client.get(LIST_URL, {"same_name": "no"})
        self.assertEqual(yes.context["cl"].result_count, 2)
        self.assertEqual(no.context["cl"].result_count, 30)

    def test_list_marks_namesakes(self):
        response = self.client.get(LIST_URL, {"same_name": "yes"})
        self.assertContains(response, "Shared name", count=2)

    def test_banner_counts_namesakes(self):
        self.assertEqual(build_sync_banner()["namesakes"], 2)
        self.assertContains(self.client.get(LIST_URL), "share a name")


class StatusOverrideTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        self.sync(self.base)

    def post(self, numbers, **extra):
        ids = [str(self.student(n).pk) for n in numbers]
        data = {"action": "change_status", "_selected_action": ids, **extra}
        return self.client.post(LIST_URL, data)

    def test_action_first_shows_a_form_and_changes_nothing(self):
        response = self.post([1], index="0")
        self.assertContains(response, "Change student status")
        self.assertEqual(self.student(1).status, "active")
        self.assertFalse(RosterAudit.objects.filter(action="manual_override").exists())

    def test_reason_is_required(self):
        response = self.post([1], apply="1", new_status="pending_review", reason="")
        self.assertContains(response, "This field is required")
        self.assertEqual(self.student(1).status, "active")

    def test_a_short_reason_is_refused(self):
        response = self.post([1], apply="1", new_status="pending_review", reason="oops")
        self.assertContains(response, "at least 10 characters")
        self.assertEqual(self.student(1).status, "active")

    def test_override_changes_status_and_records_who_and_why(self):
        reason = "Student has a registration hold; confirmed by email"
        response = self.post([1, 2], apply="1", new_status="pending_review", reason=reason)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.student(1).status, "pending_review")
        self.assertEqual(self.student(2).status, "pending_review")
        entry = RosterAudit.objects.get(action="manual_override", student=self.student(1))
        self.assertEqual(entry.changed_by, "boss")
        self.assertEqual(
            entry.details,
            {"from": "active", "to": "pending_review", "reason": reason},
        )

    def test_students_already_at_that_status_are_skipped(self):
        self.post([1], apply="1", new_status="active", reason="No change is needed here")
        self.assertFalse(RosterAudit.objects.filter(action="manual_override").exists())

    def test_held_status_survives_a_later_import(self):
        self.post([2], apply="1", new_status="pending_review",
                  reason="Waiting on the registrar to confirm")
        log = self.sync(self.base)
        self.assertEqual((log.status, log.updated, log.deactivated), ("success", 0, 0))
        self.assertEqual(self.student(2).status, "pending_review")

    def test_source_still_wins_for_a_student_missing_from_the_file(self):
        self.sync(self.base[:-1])  # student 30 drops out
        self.assertEqual(self.student(30).status, "inactive")
        self.post([30], apply="1", new_status="active",
                  reason="Registrar says enrollment is pending")
        self.assertEqual(self.student(30).status, "active")
        self.sync(self.base[:-1])  # still absent from the source
        self.assertEqual(self.student(30).status, "inactive")
        actions = list(
            RosterAudit.objects.filter(student=self.student(30))
            .order_by("pk")
            .values_list("action", flat=True)
        )
        self.assertEqual(actions, ["added", "deactivated", "manual_override", "deactivated"])


class StudentAdminSafetyTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        self.sync(self.base)

    def test_existing_students_are_read_only_in_the_form(self):
        response = self.client.get(f"{LIST_URL}{self.student(1).pk}/change/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="first_name"')
        self.assertNotContains(response, 'name="status"')

    def test_students_cannot_be_deleted_in_the_admin(self):
        response = self.client.get(f"{LIST_URL}{self.student(1).pk}/delete/")
        self.assertEqual(response.status_code, 403)

    def test_manual_entry_is_audited_with_a_warning(self):
        response = self.client.post(f"{LIST_URL}add/", {
            "panthersoft_id": sid(700), "first_name": "Hand", "last_name": "Entered",
            "email": "hand@example.edu", "term": TERM, "status": "active",
            "last_synced_at_0": "2026-11-22", "last_synced_at_1": "10:00:00",
        }, follow=True)
        self.assertContains(response, "next import")
        entry = RosterAudit.objects.get(student__panthersoft_id=sid(700))
        self.assertEqual(entry.action, "added")
        self.assertTrue(entry.details["manual_entry"])


class AuditAdminTests(AdminTestCase):
    def test_audit_log_is_read_only_and_shows_the_reason(self):
        self.sync(self.base)
        entry = RosterAudit.objects.create(
            student=self.student(1), action="manual_override", changed_by="boss",
            details={"from": "active", "to": "pending_review",
                     "reason": "Registrar hold confirmed"},
        )
        response = self.client.get("/admin/roster/rosteraudit/")
        self.assertContains(response, "Registrar hold confirmed")
        self.assertEqual(self.client.get("/admin/roster/rosteraudit/add/").status_code, 403)
        delete_url = f"/admin/roster/rosteraudit/{entry.pk}/delete/"
        self.assertEqual(self.client.get(delete_url).status_code, 403)