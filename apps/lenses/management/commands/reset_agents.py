from django.core.management.base import BaseCommand
from django.db import transaction

from apps.cmc.models import CmcCallLog
from apps.events.models import Event
from apps.lenses.models import Lens
from apps.notifications.models import Notification
from apps.users.models import User, UserPreference


class Command(BaseCommand):
    help = "Delete all agents, jobs, conversations, runs, events, and CMC logs. Keep user accounts."

    def handle(self, *args, **options):
        users = User.objects.count()
        with transaction.atomic():
            UserPreference.objects.update(active_lens=None)
            Notification.objects.all().delete()
            Event.objects.all().delete()
            CmcCallLog.objects.all().delete()
            deleted, _ = Lens.objects.all().delete()
        remaining = Lens.objects.count()
        self.stdout.write(
            f"Kept {users} user account(s). Deleted lens graph ({deleted} objects). Lenses remaining: {remaining}."
        )
