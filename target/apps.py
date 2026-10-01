from django.apps import AppConfig


class TargetConfig(AppConfig):
    # The news site's migrations, and the table they built, use a 32-bit
    # id; keep it rather than follow the project's BigAutoField default.
    default_auto_field = 'django.db.models.AutoField'
    name = 'target'
