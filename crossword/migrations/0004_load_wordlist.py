import re
from pathlib import Path

from django.db import migrations

WORDLIST = Path(__file__).parent.parent / "fixtures" / "wordlist.txt"
_valid = re.compile(r"^[A-Z]+$")


def load_words(apps, schema_editor):
    Word = apps.get_model("crossword", "Word")
    words = [
        Word(text=word)
        for line in WORDLIST.read_text().splitlines()
        if _valid.match(word := line.strip().upper()) and len(word) >= 2
    ]
    Word.objects.bulk_create(words, batch_size=1000, ignore_conflicts=True)


def unload_words(apps, schema_editor):
    apps.get_model("crossword", "Word").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("crossword", "0003_add_can_generate_crosswords_permission"),
    ]

    operations = [
        migrations.RunPython(load_words, unload_words),
    ]
