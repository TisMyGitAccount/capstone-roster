import tempfile
from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .importing import run_csv_import
from .models import RosterAudit, Student, SyncLog
from .sources import DEMO_DIR
from .tests import rec, sid

TERM = "FA26"
COLUMNS = ("panthersoft_id", "first_name", "last_name", "email", "term")


def make_csv(records, header=COLUMNS, fields=COLUMNS, delimiter=",", encoding="utf-8"):
    lines = [delimiter.join(header)]
    for record in records:
        lines.append(delimiter.join(str(record[f]) for f in fields))
    return "\n".join(lines).encode(encoding)


class ImportTestCase(TestCase):
    """Every test starts with 30 active students imported from a CSV."""

    def setUp(self):
        self.base = [rec(n) for n in range(1, 31)]
        result = self.do_import(make_csv(self.base))
        self.assertEqual((result["status"], result["added"]), ("success", 30))

    def do_import(self, content, term=TERM, apply=True, user="tester", name="roster.csv"):
        return run_csv_import(
            content=content, filename=name, term=term, username=user, apply=apply
        )

    def active_count(self):
        return Student.objects.filter(status="active").count()


class CsvImportTests(ImportTestCase):
    def test_apply_adds_students_and_records_the_source(self):
        log = SyncLog.objects.first()
        self.assertIn("roster.csv", log.source)
        self.assertIn("tester", log.source)
        self.assertEqual(
            RosterAudit.objects.filter(action="added", changed_by="tester").count(), 30
        )

    def test_preview_changes_nothing(self):
        logs, audits = SyncLog.objects.count(), RosterAudit.objects.count()
        result = self.do_import(make_csv(self.base[:-1]), apply=False)
        self.assertEqual(result["mode"], "preview")
        self.assertEqual(result["deactivated"], 1)
        groups = {g["title"]: g for g in result["groups"]}
        self.assertEqual(groups["Deactivated"]["rows"][0][0], sid(30))
        self.assertEqual(self.active_count(), 30)
        self.assertEqual(SyncLog.objects.count(), logs)
        self.assertEqual(RosterAudit.objects.count(), audits)

    def test_apply_matches_the_preview(self):
        content = make_csv(self.base[:-1])
        preview = self.do_import(content, apply=False)
        applied = self.do_import(content, apply=True)
        keys = ("status", "added", "updated", "deactivated")
        self.assertEqual([preview[k] for k in keys], [applied[k] for k in keys])
        self.assertEqual(applied["deactivated"], 1)

    def test_export_style_headers_and_bom_are_accepted(self):
        changed = [dict(r) for r in self.base]
        changed[0]["email"] = "new.address@example.edu"
        header = ("Student ID", "First Name", "Last Name", "Email Address", "Term")
        result = self.do_import(b"\xef\xbb\xbf" + make_csv(changed, header=header))
        self.assertEqual((result["status"], result["updated"]), ("success", 1))
        self.assertEqual(
            Student.objects.get(panthersoft_id=sid(1)).email, "new.address@example.edu"
        )

    def test_semicolon_delimiter_is_detected(self):
        result = self.do_import(make_csv(self.base, delimiter=";"))
        self.assertEqual(result["status"], "success")
        self.assertEqual((result["added"], result["updated"], result["deactivated"]), (0, 0, 0))

    def test_extra_columns_are_ignored(self):
        records = [dict(r, notes="x") for r in self.base]
        columns = COLUMNS + ("notes",)
        result = self.do_import(make_csv(records, header=columns, fields=columns))
        self.assertEqual(result["status"], "success")
        self.assertEqual((result["added"], result["updated"]), (0, 0))

    def test_missing_column_fails_and_changes_nothing(self):
        columns = ("panthersoft_id", "first_name", "last_name", "term")
        result = self.do_import(make_csv(self.base, header=columns, fields=columns))
        self.assertEqual(result["status"], "failed")
        self.assertIn("email", result["message"])
        self.assertEqual(self.active_count(), 30)

    def test_non_utf8_file_is_rejected(self):
        result = self.do_import(make_csv([rec(40, "José")], encoding="cp1252"))
        self.assertEqual(result["status"], "failed")
        self.assertIn("UTF-8", result["message"])
        self.assertEqual(self.active_count(), 30)

    def test_wrong_term_is_rejected_and_names_the_terms_found(self):
        result = self.do_import(make_csv(self.base), term="SP26")
        self.assertEqual(result["status"], "failed")
        self.assertIn("SP26", result["message"])
        self.assertIn("FA26", result["message"])
        self.assertEqual(self.active_count(), 30)

    def test_rows_without_a_term_column_use_the_selected_term(self):
        columns = COLUMNS[:4]
        records = self.base + [rec(99)]
        result = self.do_import(make_csv(records, header=columns, fields=columns))
        self.assertEqual((result["status"], result["added"]), ("success", 1))
        self.assertEqual(Student.objects.get(panthersoft_id=sid(99)).term, "FA26")

    def test_blank_lines_are_skipped(self):
        result = self.do_import(make_csv(self.base) + b"\n\n,,,,\n")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["issues_total"], 0)

    def test_bad_rows_are_set_aside_not_applied(self):
        bad = [
            rec(51, panthersoft_id="S900051"),    # letters
            rec(52, panthersoft_id="9000052.0"),  # a spreadsheet turned it into a decimal
            rec(53, panthersoft_id="12345"),      # partial or leading zeros lost
        ]
        result = self.do_import(make_csv(self.base + bad))
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["issues_total"], 3)
        self.assertEqual({i["kind"] for i in result["issues"]}, {"Invalid ID"})
        self.assertEqual(result["added"], 0)
        self.assertEqual(Student.objects.count(), 30)

    def test_mass_drop_file_is_blocked(self):
        result = self.do_import(make_csv(self.base[:20]))
        self.assertEqual(result["status"], "partial")
        self.assertIn("Blocked", result["message"])
        self.assertEqual(self.active_count(), 30)


class ImportAdminTests(TestCase):
    URL = "/admin/roster/student/import/"

    def setUp(self):
        self.base = [rec(n) for n in range(1, 31)]
        boss = get_user_model().objects.create_superuser("boss", "boss@example.edu", "pw")
        self.client.force_login(boss)

    def upload(self, mode, name="roster.csv"):
        file = SimpleUploadedFile(name, make_csv(self.base), content_type="text/csv")
        return self.client.post(self.URL, {"file": file, "term": TERM, "mode": mode})

    def test_import_page_loads(self):
        response = self.client.get(self.URL)
        self.assertContains(response, "Import roster file")

    def test_changelist_links_to_the_import_page(self):
        response = self.client.get("/admin/roster/student/")
        self.assertContains(response, self.URL)

    def test_preview_upload_changes_nothing(self):
        response = self.upload("preview")
        self.assertContains(response, "nothing was changed")
        self.assertEqual(Student.objects.count(), 0)

    def test_apply_upload_adds_students(self):
        response = self.upload("apply")
        self.assertContains(response, "Import result")
        self.assertEqual(Student.objects.count(), 30)
        self.assertIn("boss", SyncLog.objects.first().source)

    def test_non_csv_file_is_rejected(self):
        response = self.upload("apply", name="roster.txt")
        self.assertContains(response, "Please upload a .csv file")
        self.assertEqual(Student.objects.count(), 0)

    def test_anonymous_user_is_redirected_to_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.URL).status_code, 302)

    def test_staff_without_permission_is_forbidden(self):
        clerk = get_user_model().objects.create_user("clerk", password="pw", is_staff=True)
        self.client.force_login(clerk)
        self.assertEqual(self.client.get(self.URL).status_code, 403)


class ImportCommandTests(TestCase):
    def write_file(self, directory):
        path = Path(directory) / "roster.csv"
        path.write_bytes(make_csv([rec(n) for n in range(1, 31)]))
        return path

    def test_previews_by_default(self):
        out = StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            call_command("import_roster_csv", str(self.write_file(tmp)), "--term", TERM, stdout=out)
        self.assertIn("PREVIEW", out.getvalue())
        self.assertEqual(Student.objects.count(), 0)

    def test_apply_changes_the_roster(self):
        out = StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            call_command(
                "import_roster_csv", str(self.write_file(tmp)),
                "--term", TERM, "--apply", stdout=out,
            )
        self.assertIn("added=30", out.getvalue())
        self.assertEqual(Student.objects.count(), 30)

    def test_missing_file_is_an_error(self):
        with self.assertRaises(CommandError):
            call_command("import_roster_csv", "no_such_file.csv", stdout=StringIO())


class SampleCsvTests(TestCase):
    def test_sample_files_work_in_sequence(self):
        call_command("make_sample_csv", stdout=StringIO())
        folder = DEMO_DIR / "csv"

        def run(name):
            return run_csv_import(
                content=(folder / name).read_bytes(), filename=name,
                term=TERM, username="tester", apply=True,
            )

        first = run("snapshot_1.csv")
        self.assertEqual((first["status"], first["added"]), ("success", 300))

        second = run("snapshot_2_export_style.csv")
        self.assertEqual(second["status"], "success")
        self.assertEqual((second["added"], second["deactivated"]), (13, 8))
        self.assertGreaterEqual(second["updated"], 5)

        dirty = run("snapshot_dirty.csv")
        self.assertEqual(dirty["status"], "success")
        self.assertEqual((dirty["added"], dirty["updated"], dirty["deactivated"]), (0, 0, 0))
        self.assertEqual(dirty["issues_total"], 8)

        self.assertEqual(run("snapshot_3_mass_drop.csv")["status"], "partial")

        bad = run("bad_missing_email.csv")
        self.assertEqual(bad["status"], "failed")
        self.assertIn("email", bad["message"])