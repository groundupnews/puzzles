from django.core.management.base import BaseCommand

from allauth.usersessions.models import UserSession


class Command(BaseCommand):
    help = "Logs out every user by ending all tracked sessions."

    def handle(self, *args, **options):
        sessions = UserSession.objects.all()
        count = sessions.count()
        for session in sessions:
            session.end()
        self.stdout.write(self.style.SUCCESS(f"Logged out {count} session(s)."))
