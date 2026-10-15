import io
import urllib.request

import xlrd
from django.core.management.base import BaseCommand, CommandError

from streetwise.models import Council, VotingDistrict

# The IEC's number for each local government election, as its results site
# files the reports.
ELECTIONS = {2021: 1091, 2026: 1887}
REPORT = (
    "https://results.elections.org.za/home/LGEPublicReports/{event}/"
    "Seat%20Calculation%20Detail/{folder}/{code}.xls"
)
# The site's folder for each province.
FOLDERS = {
    "Eastern Cape": "EC", "Free State": "FS", "Gauteng": "GP", "KwaZulu-Natal": "KN",
    "Limpopo": "NP", "Mpumalanga": "MP", "North West": "NW", "Northern Cape": "NC",
    "Western Cape": "WP",
}


def read_seats(rows):
    """Seats by party, and independents, from the rows of a Seat Calculation
    Detail report's second sheet. The columns move about from report to
    report, so each row is read by its label: a party's seats are the first
    number after its name. Checked against the report's own total."""
    seats, independents, total = {}, 0, None
    for row in rows:
        cells = [cell for cell in row if cell != ""]
        if not cells or not isinstance(cells[0], str):
            continue
        # A party that won more ward seats than its share of the vote is
        # marked "*"; double spaces creep into some names.
        label = " ".join(cells[0].replace("*", "").split())
        numbers = [int(cell) for cell in cells[1:] if isinstance(cell, float)]
        if label == "Independents":
            independents = sum(numbers)
        elif label == "Total Seats":
            total = numbers[-1]
        elif label not in ("Party Name", "Total Party Seats") and numbers and numbers[0]:
            seats[label] = numbers[0]
    if total is None or total != sum(seats.values()) + independents:
        raise ValueError("the seats don't add up to the total")
    return seats, independents


class Command(BaseCommand):
    help = (
        "Imports each municipal council's seats from the IEC's Seat Calculation "
        "Detail reports, for every municipality with voting districts (so run "
        "import_iec_results first). Running it again updates the councils "
        "already imported."
    )

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, choices=ELECTIONS, default=2021)

    def handle(self, year, **options):
        municipalities = (
            VotingDistrict.objects.order_by("municipality")
            .values_list("municipality", "province").distinct()
        )
        if not municipalities:
            raise CommandError("No voting districts yet: run import_iec_results first.")
        councils, missing = [], []
        for municipality, province in municipalities:
            code, name = municipality.split(" - ", 1)
            url = REPORT.format(event=ELECTIONS[year], folder=FOLDERS[province], code=code)
            try:
                seats, independents = read_seats(self.rows(url))
            except (OSError, ValueError, xlrd.XLRDError) as error:
                missing.append(f"{code} ({error})")
                continue
            councils.append(Council(
                code=code, name=name, year=year, seats=seats, independents=independents
            ))
        Council.objects.bulk_create(
            councils,
            update_conflicts=True,
            unique_fields=["code", "year"],
            update_fields=["name", "seats", "independents"],
        )
        self.stdout.write(f"Imported {len(councils)} councils from {year}.")
        if missing:
            self.stderr.write("Couldn't read: " + ", ".join(missing))

    def rows(self, url):
        """The rows of the report's second sheet, which has each party's
        seats."""
        request = urllib.request.Request(url, headers={"User-Agent": "GroundUp puzzles"})
        with urllib.request.urlopen(request, timeout=60) as response:
            # xlrd warns that the IEC's files are a few bytes short; they
            # read fine.
            book = xlrd.open_workbook(file_contents=response.read(), logfile=io.StringIO())
        sheet = book.sheet_by_index(1)
        return [sheet.row_values(n) for n in range(sheet.nrows)]

