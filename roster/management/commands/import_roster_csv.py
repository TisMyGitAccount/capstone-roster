from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from roster.importing import default_term, run_csv_import


class Command(BaseCommand):
    help = "Import a roster CSV. Previews by default; add --apply to change the roster."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--term", default=None)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.is_file():
            raise CommandError(f"File not found: {path}")

        result = run_csv_import(
            content=path.read_bytes(),
            filename=path.name,
            term=options["term"] or default_term(),
            username="cli",
            apply=options["apply"],
        )
        self.stdout.write(
            f"{result['mode'].upper()}: {result['status']} "
            f"(added={result['added']}, updated={result['updated']}, "
            f"deactivated={result['deactivated']}, set aside={result['issues_total']})"
        )
        if result["message"]:
            self.stdout.write(result["message"])
        for issue in result["issues"][:10]:
            self.stdout.write(f"  - {issue['kind']}: {issue['identifier']}")
        if result["mode"] == "preview":
            self.stdout.write("Nothing was changed. Add --apply to apply this file.")