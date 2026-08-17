from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("crossword", "0004_load_wordlist"),
    ]

    operations = [
        migrations.RenameField(
            model_name="crossword",
            old_name="publication_datetime",
            new_name="published",
        ),
    ]
