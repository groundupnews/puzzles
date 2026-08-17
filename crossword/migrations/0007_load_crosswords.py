from pathlib import Path

from django.db import migrations

FIXTURES = Path(__file__).parent.parent / "fixtures"


def load_crosswords(apps, schema_editor):
    import sys
    if sys.argv[1:2] == ["test"]:
        return

    from crossword.xd import parse_xd, save_crossword_from_xd

    for path in sorted(FIXTURES.glob("*.xd")):
        data = parse_xd(path.read_text(encoding="utf-8"))
        if data["size"]["rows"]:
            save_crossword_from_xd(data, replace=False)


def unload_crosswords(apps, schema_editor):
    apps.get_model("crossword", "Crossword").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("crossword", "0006_crossword_authors_crossword_copyright_and_more"),
    ]

    operations = [
        migrations.RunPython(load_crosswords, unload_crosswords),
    ]
