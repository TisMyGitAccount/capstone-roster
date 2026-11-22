from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .models import ApiToken, Student, SyncLog
from .sync import sync_roster
from .tests import FakeSource, rec, sid

TERM = "FA26"


@override_settings(ROSTER_CURRENT_TERM=TERM, ROSTER_STALE_AFTER_HOURS=24)
class ApiTestCase(TestCase):
    """30 active students are synced in, and the client carries a valid token."""

    def setUp(self):
        self.base = [rec(n) for n in range(1, 31)]
        log = sync_roster(FakeSource(self.base), TERM)
        self.assertEqual((log.status, log.added), ("success", 30))
        self.token, self.raw = ApiToken.create_token("test-site")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.raw}")

    def get(self, path):
        return self.client.get(path)

    def lookup(self, student_id):
        return self.client.get(f"/api/roster/students/{student_id}/")


class ApiAuthTests(ApiTestCase):
    def test_no_credentials_is_rejected(self):
        self.assertEqual(APIClient().get("/api/roster/status/").status_code, 401)

    def test_invalid_token_is_rejected(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")
        self.assertEqual(client.get("/api/roster/status/").status_code, 401)

    def test_valid_token_is_accepted(self):
        self.assertEqual(self.get("/api/roster/status/").status_code, 200)
        self.token.refresh_from_db()
        self.assertIsNotNone(self.token.last_used_at)

    def test_revoked_token_is_rejected(self):
        self.token.is_active = False
        self.token.save()
        self.assertEqual(self.get("/api/roster/status/").status_code, 401)

    def test_tokens_are_stored_hashed(self):
        self.assertNotEqual(self.token.key_hash, self.raw)
        self.assertFalse(ApiToken.objects.filter(key_hash=self.raw).exists())
        self.assertEqual(len(self.token.key_hash), 64)

    def test_staff_session_is_accepted(self):
        staff = get_user_model().objects.create_user(
            "staff", password="pw", is_staff=True
        )
        client = APIClient()
        client.force_login(staff)
        self.assertEqual(client.get("/api/roster/status/").status_code, 200)

    def test_non_staff_session_is_forbidden(self):
        user = get_user_model().objects.create_user("plain", password="pw")
        client = APIClient()
        client.force_login(user)
        self.assertEqual(client.get("/api/roster/status/").status_code, 403)

    def test_create_api_token_command_prints_a_working_token_once(self):
        out = StringIO()
        call_command("create_api_token", "--name", "capstone-site", stdout=out)
        lines = [
            line for line in out.getvalue().splitlines()
            if line.startswith("Token: ")
        ]
        self.assertEqual(len(lines), 1)
        raw = lines[0].removeprefix("Token: ").strip()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw}")
        self.assertEqual(client.get("/api/roster/status/").status_code, 200)
        self.assertFalse(ApiToken.objects.filter(key_hash=raw).exists())

    def test_create_api_token_command_rejects_duplicate_names(self):
        with self.assertRaises(CommandError):
            call_command("create_api_token", "--name", "test-site", stdout=StringIO())


class StudentLookupTests(ApiTestCase):
    def test_active_student_is_eligible(self):
        response = self.lookup(sid(1))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "active")
        self.assertTrue(response.data["eligible"])
        self.assertEqual(response.data["student"]["panthersoft_id"], sid(1))
        self.assertFalse(response.data["data_freshness"]["stale"])
        self.assertIsNone(response.data["warning"])

    def test_padded_id_finds_the_same_student(self):
        response = self.client.get(f"/api/roster/students/%20%20{sid(1)}%20/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["student"]["panthersoft_id"], sid(1))

    def test_letters_make_the_id_invalid_not_missing(self):
        response = self.lookup("S" + sid(1))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["status"], "invalid_id")
        self.assertFalse(response.data["eligible"])
        self.assertNotIn("student", response.data)

    def test_partial_id_is_invalid_and_never_matches(self):
        response = self.lookup(sid(1)[:5])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["status"], "invalid_id")
        self.assertNotIn("student", response.data)

    def test_unknown_well_formed_id_is_not_found(self):
        response = self.lookup(sid(999))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["status"], "not_found")
        self.assertFalse(response.data["eligible"])

    def test_inactive_student_is_not_eligible_and_says_why(self):
        sync_roster(FakeSource(self.base[:-1]), TERM)  # student 30 drops
        response = self.lookup(sid(30))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "inactive")
        self.assertFalse(response.data["eligible"])
        self.assertIn("Last confirmed", response.data["reason"])

    def test_active_student_from_another_term_is_not_eligible(self):
        Student.objects.create(
            panthersoft_id=sid(500), first_name="Old", last_name="Term",
            email="old@example.edu", term="SP26", last_synced_at=timezone.now(),
        )
        response = self.lookup(sid(500))
        self.assertEqual(response.data["status"], "active")
        self.assertFalse(response.data["eligible"])
        self.assertIn("SP26", response.data["reason"])
        self.assertIn(TERM, response.data["reason"])

    def test_pending_review_student_is_not_eligible(self):
        Student.objects.filter(panthersoft_id=sid(2)).update(status="pending_review")
        response = self.lookup(sid(2))
        self.assertEqual(response.data["status"], "pending_review")
        self.assertFalse(response.data["eligible"])
        self.assertIn("review", response.data["reason"].lower())

    def test_stale_data_is_flagged_but_still_answered(self):
        SyncLog.objects.update(finished_at=timezone.now() - timedelta(hours=30))
        response = self.lookup(sid(1))
        self.assertTrue(response.data["data_freshness"]["stale"])
        self.assertIn("out of date", response.data["warning"])
        self.assertTrue(response.data["eligible"])

    def test_never_synced_roster_is_flagged(self):
        SyncLog.objects.all().delete()
        response = self.lookup(sid(1))
        self.assertTrue(response.data["data_freshness"]["stale"])
        self.assertIsNone(response.data["data_freshness"]["last_successful_sync_at"])
        self.assertIn("never", response.data["warning"])

    def test_api_is_read_only(self):
        response = self.client.post(f"/api/roster/students/{sid(1)}/", {})
        self.assertEqual(response.status_code, 405)


class RosterStatusTests(ApiTestCase):
    def test_status_reports_counts_and_latest_sync(self):
        data = self.get("/api/roster/status/").data
        self.assertEqual(data["current_term"], TERM)
        self.assertEqual(data["students_in_current_term"]["active"], 30)
        self.assertEqual(data["latest_sync"]["status"], "success")
        self.assertEqual(data["latest_sync"]["added"], 30)
        self.assertFalse(data["data_freshness"]["stale"])

    def test_blocked_sync_is_visible_but_data_is_not_called_stale(self):
        sync_roster(FakeSource(self.base[:20]), TERM)  # would drop 10 of 30
        data = self.get("/api/roster/status/").data
        self.assertEqual(data["latest_sync"]["status"], "partial")
        self.assertIn("Blocked", data["latest_sync"]["message"])
        self.assertFalse(data["data_freshness"]["stale"])
        self.assertEqual(data["students_in_current_term"]["active"], 30)


class StudentListTests(ApiTestCase):
    def test_default_list_is_the_current_term_only(self):
        Student.objects.create(
            panthersoft_id=sid(500), first_name="Old", last_name="Term",
            email="old@example.edu", term="SP26", last_synced_at=timezone.now(),
        )
        data = self.get("/api/roster/students/").data
        self.assertEqual(data["count"], 30)
        self.assertEqual(len(data["results"]), 30)

    def test_status_filter(self):
        sync_roster(FakeSource(self.base[:-1]), TERM)
        data = self.get("/api/roster/students/?status=inactive").data
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["panthersoft_id"], sid(30))

    def test_unknown_status_value_is_rejected(self):
        response = self.get("/api/roster/students/?status=enrolled")
        self.assertEqual(response.status_code, 400)

    def test_pagination(self):
        data = self.get("/api/roster/students/?page_size=10").data
        self.assertEqual(data["count"], 30)
        self.assertEqual(len(data["results"]), 10)
        self.assertIsNotNone(data["next"])

    def test_list_includes_freshness(self):
        data = self.get("/api/roster/students/").data
        self.assertIn("data_freshness", data)
        self.assertEqual(data["current_term"], TERM)