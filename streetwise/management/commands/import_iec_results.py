import csv
import io
import zipfile

from django.core.management.base import BaseCommand, CommandError

from streetwise.models import VotingDistrict

SOURCE = (
    "https://results.elections.org.za/home/NPEPublicReports/1334/"
    "National%20Ballot/Downloadable%20Results/National.zip"
)
COLUMNS = {
    "Province", "Municipality", "VD_Number", "VS_Name", "Registered_Population",
    "Spoilt_Votes", "sPartyName", "Party_Votes",
}


class Command(BaseCommand):
    help = (
        "Imports the IEC's 2024 national-ballot results by voting district, "
        f"from {SOURCE} (the zip, or the National.csv inside it). "
        "Running it again updates the districts already imported."
    )

    def add_arguments(self, parser):
        parser.add_argument("path", help="National.zip or National.csv")

    def handle(self, path, **options):
        districts = {}
        for row in self.rows(path):
            if row["Province"] == "Out of Country":
                continue
            number = row["VD_Number"].strip()
            district = districts.get(number)
            if district is None:
                district = districts[number] = VotingDistrict(
                    number=number,
                    province=row["Province"].strip(),
                    municipality=row["Municipality"].strip(),
                    station=row["VS_Name"].strip(),
                    registered=int(row["Registered_Population"]),
                    spoilt=int(row["Spoilt_Votes"]),
                    votes={},
                )
            votes = int(row["Party_Votes"])
            if votes:
                district.votes[row["sPartyName"].strip()] = votes

        # A couple of districts recorded no votes at all; there's nothing to
        # guess there.
        counted = [district for district in districts.values() if district.votes]
        VotingDistrict.objects.bulk_create(
            counted,
            batch_size=1000,
            update_conflicts=True,
            unique_fields=["number"],
            update_fields=[
                "province", "municipality", "station", "registered", "spoilt", "votes",
            ],
        )
        self.stdout.write(
            f"Imported {len(counted)} voting districts; skipped "
            f"{len(districts) - len(counted)} with no votes."
        )

    def rows(self, path):
        """The CSV's rows, from the zip the IEC serves or the CSV in it."""
        try:
            if zipfile.is_zipfile(path):
                with zipfile.ZipFile(path) as archive:
                    with archive.open(archive.namelist()[0]) as raw:
                        yield from self.read(io.TextIOWrapper(raw, encoding="utf-8-sig"))
            else:
                with open(path, encoding="utf-8-sig", newline="") as text:
                    yield from self.read(text)
        except OSError as error:
            raise CommandError(error)

    def read(self, text):
        reader = csv.DictReader(text)
        missing = COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise CommandError(
                "Not the IEC's results-by-voting-district file: no "
                + ", ".join(sorted(missing)) + " column."
            )
        yield from reader
