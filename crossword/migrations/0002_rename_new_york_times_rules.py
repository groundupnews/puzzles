from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("crossword", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(
            model_name="crossword",
            old_name="new_york_times_rules",
            new_name="requires_rotational_symmetry",
        ),
    ]
