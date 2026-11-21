from django.core.management.base import BaseCommand

from roster.models import RosterAudit, Student, SyncLog
from roster.sources import MockPanthersoftSource
from roster.sync import sync_roster


class Command(BaseCommand):
    help = "Sync the roster from a demo snapshot (simulated Panthersoft)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--snapshot", required=True,
            help="Snapshot file name, or 'fail' to simulate an outage.",
        )
        parser.add_argument("--term", default="FA26")
        parser.add_argument(
            "--reset", action="store_true",
            help="Delete all roster data before syncing (demo only).",
        )

    def handle(self, *args, **options):
        if options["reset"]:
            RosterAudit.objects.all().delete()
            SyncLog.objects.all().delete()
            Student.objects.all().delete()
            self.stdout.write("Roster reset.")

        source = MockPanthersoftSource(options["snapshot"])
        log = sync_roster(source, options["term"])

        summary = (
            f"Sync {log.status}: added={log.added}, "
            f"updated={log.updated}, deactivated={log.deactivated}"
        )
        for issue in log.issues.all()[:10]:
            self.stdout.write(f"  - {issue.kind}: {issue.identifier or '(no ID)'}")
        if log.status == "success":
            self.stdout.write(self.style.SUCCESS(summary))
        else:
            self.stdout.write(self.style.ERROR(summary))
            self.stdout.write(self.style.ERROR(log.error_message))