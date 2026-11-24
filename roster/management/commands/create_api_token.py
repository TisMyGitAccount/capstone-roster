from django.core.management.base import BaseCommand, CommandError

from roster.models import ApiToken


class Command(BaseCommand):
    help = "Create a read-only API token for a consuming site. It is shown once."

    def add_arguments(self, parser):
        parser.add_argument(
            "--name", required=True, help="Which site this token is for."
        )
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Delete an existing token with this name and issue a new one.",
        )

    def handle(self, *args, **options):
        name = options["name"].strip()
        if not name:
            raise CommandError("--name cannot be blank.")

        existing = ApiToken.objects.filter(name=name)
        if existing.exists():
            if not options["replace"]:
                raise CommandError(
                    f"A token named '{name}' already exists. Add --replace to "
                    "replace it, or pick another name."
                )
            existing.delete()
            self.stdout.write(f"Replaced the existing token named '{name}'.")

        token, raw = ApiToken.create_token(name)
        self.stdout.write(f"Created token for '{token.name}'.")
        self.stdout.write("Copy it now. It cannot be shown again.")
        self.stdout.write(f"Token: {raw}")