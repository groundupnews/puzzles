import csv
from datetime import datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from streetwise.models import Streetwise, VotingDistrict


class Command(BaseCommand):
    help = (
        "Adds Streetwise puzzles from a CSV with the columns district, pano, "
        "latitude, longitude, heading, pitch, fov and (optionally) notes, as "
        "find_panoramas writes. A panorama already in the system is skipped, "
        "so the same file can be imported twice. Puzzles come in unpublished "
        "unless --schedule-from is given."
    )

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument(
            "--schedule-from", metavar="YYYY-MM-DD",
            help="Publish the new puzzles one a day from this date, at midnight, "
            "in the file's order.")

    def handle(self, path, schedule_from, **options):
        start = None
        if schedule_from:
            try:
                day = datetime.strptime(schedule_from, "%Y-%m-%d").date()
            except ValueError:
                raise CommandError("--schedule-from is a date like 2026-11-01.")
            start = timezone.make_aware(datetime.combine(day, time()))

        try:
            with open(path, newline="", encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
        except OSError as error:
            raise CommandError(error)

        districts = VotingDistrict.objects.in_bulk(
            [row.get("district", "") for row in rows], field_name="number")
        existing = set(Streetwise.objects.values_list("pano", flat=True))
        puzzles, errors = [], []
        for line, row in enumerate(rows, start=2):
            if row.get("pano") and row["pano"] in existing:
                continue
            district = districts.get(row.get("district"))
            if district is None:
                errors.append(f"Line {line}: no voting district {row.get('district')!r}")
                continue
            try:
                puzzle = Streetwise(
                    district=district,
                    pano=row.get("pano", ""),
                    latitude=row.get("latitude"),
                    longitude=row.get("longitude"),
                    heading=row.get("heading") or 0,
                    pitch=row.get("pitch") or 0,
                    fov=row.get("fov") or 90,
                    notes=row.get("notes", ""),
                )
                if start:
                    puzzle.published = start + timedelta(days=len(puzzles))
                puzzle.full_clean()
            except (ValidationError, ValueError) as error:
                errors.append(f"Line {line}: {'; '.join(getattr(error, 'messages', [str(error)]))}")
                continue
            existing.add(puzzle.pano)
            puzzles.append(puzzle)

        if errors:
            raise CommandError("Nothing was imported:\n" + "\n".join(errors))
        with transaction.atomic():
            Streetwise.objects.bulk_create(puzzles)
        skipped = len(rows) - len(puzzles)
        self.stdout.write(
            f"Imported {len(puzzles)} puzzles"
            + (f", skipping {skipped} already in" if skipped else "")
            + ("." if not puzzles else f", published daily from {schedule_from}." if start else ", unpublished.")
        )
