from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Deletes users who requested a login code (creating their account) "
        "but never completed a login within an hour."
    )

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(hours=1)
        stale_users = User.objects.filter(
            last_login__isnull=True,
            date_joined__lt=cutoff,
            is_staff=False,
            is_superuser=False,
        )
        count = stale_users.count()
        stale_users.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {count} stale unverified user(s)."))
