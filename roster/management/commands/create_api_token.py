from django.core.management.base import BaseCommand, CommandError

from roster.models import ApiToken


class Command(BaseCommand):
    help = "Create a read-only API token for a consuming site. It is shown once."

    def add_arguments(self, parser):
        parser.add_argument(
            "--name", required=True, help="Which site this token is for."
        )

    def handle(self, *args, **options):
        name = options["name"].strip()
        if not name:
            raise CommandError("--name cannot be blank.")
        if ApiToken.objects.filter(name=name).exists():
            raise CommandError(
                f"A token named '{name}' already exists. "
                "Revoke it in the admin or pick another name."
            )
        token, raw = ApiToken.create_token(name)
        self.stdout.write(f"Created token for '{token.name}'.")
        self.stdout.write("Copy it now. It cannot be shown again.")
        self.stdout.write(f"Token: {raw}")