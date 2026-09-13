from django.core.management.base import BaseCommand

from apps.users.services import ensure_workspace_user


class Command(BaseCommand):
    help = "Ensure the workspace operator account exists. Does not seed lenses or market data."

    def handle(self, *args, **options):
        user = ensure_workspace_user()
        self.stdout.write(self.style.SUCCESS(f"Workspace ready: {user.email}"))
