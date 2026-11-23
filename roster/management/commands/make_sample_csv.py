import csv
import json

from django.core.management.base import BaseCommand

from roster.sources import DEMO_DIR

FIELDS = ("panthersoft_id", "first_name", "last_name", "email", "term")


def load(name):
    return json.loads((DEMO_DIR / f"{name}.json").read_text(encoding="utf-8"))


def write(path, header, records, fields=FIELDS, encoding="utf-8"):
    with open(path, "w", encoding=encoding, newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for record in records:
            writer.writerow([record[f] for f in fields])


class Command(BaseCommand):
    help = "Write CSV versions of the demo snapshots, plus examples of messy files."

    def handle(self, *args, **options):
        out = DEMO_DIR / "csv"
        out.mkdir(exist_ok=True)

        for name in ("snapshot_1", "snapshot_2", "snapshot_dirty", "snapshot_3_mass_drop"):
            write(out / f"{name}.csv", FIELDS, load(name))

        # Looks like a real export: different header names and an Excel-style BOM.
        write(
            out / "snapshot_2_export_style.csv",
            ("Student ID", "First Name", "Last Name", "Email Address", "Term"),
            load("snapshot_2"),
            encoding="utf-8-sig",
        )

        # No email column, so the whole file is refused.
        no_email = tuple(f for f in FIELDS if f != "email")
        write(out / "bad_missing_email.csv", no_email, load("snapshot_2"), fields=no_email)

        self.stdout.write(self.style.SUCCESS(f"Wrote 6 files to {out}"))