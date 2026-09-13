import time

from django.core.management.base import BaseCommand
from django.db import connection
from django.db.utils import OperationalError


class Command(BaseCommand):
    help = "Wait until the database accepts connections."

    def handle(self, *args, **options):
        for _ in range(30):
            try:
                connection.ensure_connection()
                self.stdout.write("Database ready.")
                return
            except OperationalError:
                time.sleep(1)
        raise SystemExit("Database did not become ready.")
