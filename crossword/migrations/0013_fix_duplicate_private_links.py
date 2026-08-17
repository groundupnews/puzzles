import random
import string

from django.db import migrations


def random_string(size=60, chars=string.ascii_letters + string.digits):
    return "".join(random.SystemRandom().choice(chars) for _ in range(size))


def regenerate_private_links(apps, schema_editor):
    # 0012_crossword_private_link's AddField backfilled every pre-existing
    # row with a single value: a callable default is only evaluated once by
    # the schema editor to backfill existing rows, not per row, so every
    # Crossword that existed at that point ended up sharing one
    # private_link. Give each row its own value before 0014 makes the
    # column unique.
    Crossword = apps.get_model("crossword", "Crossword")
    seen = set()
    for crossword in Crossword.objects.all():
        new_value = random_string()
        while new_value in seen:
            new_value = random_string()
        seen.add(new_value)
        crossword.private_link = new_value
        crossword.save(update_fields=["private_link"])


class Migration(migrations.Migration):

    dependencies = [
        ("crossword", "0012_crossword_private_link"),
    ]

    operations = [
        migrations.RunPython(regenerate_private_links, migrations.RunPython.noop),
    ]
