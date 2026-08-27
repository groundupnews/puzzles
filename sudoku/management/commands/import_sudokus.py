from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from sudoku.models import Sudoku

VALID = set("0123456789")


class Command(BaseCommand):
    help = (
        "Import sudoku puzzles from a file of 'puzzle,difficulty,solution' "
        "lines, scheduling them one every --skip days from --start."
    )

    def add_arguments(self, parser):
        parser.add_argument("file")
        parser.add_argument(
            "--start",
            help="First publication date, YYYY-MM-DD. Defaults to today.",
        )
        parser.add_argument(
            "--skip",
            type=int,
            default=1,
            help="Days between consecutive puzzles (default 1).",
        )

    def handle(self, *args, **options):
        publish_at = timezone.now()
        if options["start"]:
            year, month, day = (int(p) for p in options["start"].split("-"))
            publish_at = publish_at.replace(year=year, month=month, day=day)
        step = timezone.timedelta(days=options["skip"])

        imported = skipped = 0
        # One transaction for the whole file, so a bad line partway
        # through doesn't leave half a schedule behind.
        with transaction.atomic():
            for number, line in enumerate(open(options["file"]), start=1):
                line = line.strip()
                if not line:
                    continue
                parts = line.split(",")
                if len(parts) != 3:
                    self.stderr.write(f"line {number}: expected 3 fields")
                    continue
                puzzle, difficulty, solution = (p.strip() for p in parts)
                if len(puzzle) != 81 or not set(puzzle) <= VALID:
                    self.stderr.write(f"line {number}: bad puzzle string")
                    continue
                if Sudoku.objects.filter(puzzle=puzzle).exists():
                    skipped += 1
                    continue
                Sudoku.objects.create(
                    puzzle=puzzle,
                    solution=solution,
                    difficulty=difficulty,
                    published=publish_at,
                )
                publish_at += step
                imported += 1

        self.stdout.write(f"Imported {imported} puzzles, skipped {skipped} duplicates.")
