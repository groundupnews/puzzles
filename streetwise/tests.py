import csv
import json
import struct
import tempfile
import zipfile
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import geometry
from .management.commands.import_iec_councils import read_seats
from .models import Council, Streetwise, VotingDistrict, parse_street_view_link
from .views import ATTEMPTS, TOLERANCE

# DA 60%, ANC 30%, Rise Mzansi 10%.
VOTES = {
    "DEMOCRATIC ALLIANCE": 600,
    "AFRICAN NATIONAL CONGRESS": 300,
    "RISE MZANSI": 100,
}


def make_district(number="97090421", votes=VOTES):
    return VotingDistrict.objects.create(
        number=number,
        province="Western Cape",
        municipality="CPT - City of Cape Town",
        station="ROSMEAD CENTRAL PRIMARY SCHOOL",
        registered=2000,
        spoilt=10,
        votes=votes,
    )


# DA 135 of 231 seats, as Cape Town's council came out in 2021, roughly.
SEATS = {
    "DEMOCRATIC ALLIANCE": 135,
    "AFRICAN NATIONAL CONGRESS": 43,
    "ECONOMIC FREEDOM FIGHTERS": 10,
    "GOOD": 9,
    "CAPE COLOURED CONGRESS": 34,
}


def make_council(seats=SEATS, independents=0, year=2021):
    return Council.objects.create(
        code="CPT", name="City of Cape Town", year=year, seats=seats, independents=independents
    )


def make_puzzle(days=-1, district=None, **kwargs):
    return Streetwise.objects.create(
        district=district or make_district(),
        pano="AbC-dEf_123",
        latitude=-33.9935,
        longitude=18.476,
        published=None if days is None else timezone.now() + timedelta(days=days),
        **kwargs,
    )


class VotingDistrictTest(TestCase):
    def test_results_rank_the_parties_by_their_short_names(self):
        district = make_district()
        self.assertEqual(
            district.results(), [("DA", 60), ("ANC", 30), ("Rise Mzansi", 10)]
        )
        self.assertEqual(district.winner(), ("DA", 60))
        self.assertEqual(district.place(), "City of Cape Town")

    def test_turnout_counts_spoilt_votes(self):
        self.assertAlmostEqual(make_district().turnout(), 50.5)

    def test_a_party_with_no_button_wins_as_other(self):
        district = make_district(votes={"RISE MZANSI": 5, "DEMOCRATIC ALLIANCE": 1})
        self.assertEqual(district.winner()[0], "Other")

    def test_a_tied_district_cannot_be_a_puzzle(self):
        tied = make_district(votes={"DEMOCRATIC ALLIANCE": 5, "AFRICAN NATIONAL CONGRESS": 5})
        with self.assertRaises(ValidationError):
            Streetwise(district=tied, latitude=0, longitude=0).full_clean()


class CouncilTest(TestCase):
    def test_the_largest_party_and_its_seats(self):
        council = make_council(independents=1)
        self.assertEqual(council.largest(), ["DA"])
        self.assertEqual((council.most_seats(), council.total()), (135, 232))
        self.assertTrue(council.has_majority())
        self.assertEqual(council.ranked()[:2], [("DA", 135), ("ANC", 43)])
        self.assertEqual(council.ranked()[-1], ("Independents", 1))

    def test_a_party_with_no_button_is_named_in_full(self):
        council = make_council(seats={"NATIONAL FREEDOM PARTY": 9, "AFRICAN NATIONAL CONGRESS": 8, "GOOD": 2})
        self.assertEqual(council.largest(), ["National Freedom Party"])
        self.assertFalse(council.has_majority())

    def test_a_tied_council_has_two_largest_parties(self):
        council = make_council(seats={"AFRICAN NATIONAL CONGRESS": 48, "DEMOCRATIC ALLIANCE": 48, "GOOD": 24})
        self.assertEqual(sorted(council.largest()), ["ANC", "DA"])

    def test_a_district_finds_its_council_from_the_latest_election(self):
        district = make_district()
        self.assertIsNone(district.council())
        make_council()
        newer = make_council(year=2026)
        self.assertEqual(district.council(), newer)


class PublicationTest(TestCase):
    def test_only_past_unrejected_puzzles_are_published(self):
        district = make_district()
        live = make_puzzle(district=district)
        make_puzzle(days=1, district=district)
        make_puzzle(days=None, district=district)
        make_puzzle(district=district, rejected=True)
        self.assertEqual(list(Streetwise.objects.published()), [live])

    def test_a_rejected_panorama_cannot_be_given_a_date(self):
        puzzle = make_puzzle(rejected=True)
        with self.assertRaises(ValidationError):
            puzzle.full_clean()

    def test_numbers_follow_the_publication_dates(self):
        district = make_district()
        later = make_puzzle(days=-1, district=district)
        earlier = make_puzzle(days=-3, district=district)
        self.assertEqual((earlier.number(), later.number()), (1, 2))

    def test_unpublished_puzzles_are_hidden_except_from_staff(self):
        district = make_district()
        for puzzle in [make_puzzle(days=1, district=district), make_puzzle(district=district, rejected=True)]:
            url = reverse("streetwise:detail", args=[puzzle.pk])
            self.assertEqual(self.client.get(url).status_code, 404)
        User.objects.create_user("editor", password="pw", is_staff=True)
        self.client.login(username="editor", password="pw")
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_latest_goes_to_the_newest_published_puzzle(self):
        self.assertRedirects(self.client.get(reverse("streetwise:latest")), reverse("streetwise:list"))
        district = make_district()
        make_puzzle(days=-2, district=district)
        newest = make_puzzle(days=-1, district=district)
        make_puzzle(days=1, district=district)
        self.assertRedirects(
            self.client.get(reverse("streetwise:latest")), newest.get_absolute_url()
        )


class GuessTest(TestCase):
    def setUp(self):
        self.puzzle = make_puzzle()

    def guess(self, party, percent, status=200):
        response = self.client.post(
            reverse("streetwise:guess", args=[self.puzzle.pk]),
            json.dumps({"party": party, "percent": percent}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status, response.content)
        return response.json()

    def test_a_guess_must_be_a_listed_party_and_a_whole_percentage(self):
        for party, percent in [("Nope", 50), ("DA", "50"), ("DA", 101), ("DA", -1), ("DA", True)]:
            self.guess(party, percent, status=400)
        self.assertEqual(self.guess("ANC", 50)["guesses"][0]["grade"], "wrong")

    def test_the_share_must_be_within_the_tolerance(self):
        self.assertEqual(TOLERANCE, 5)
        close = self.guess("DA", 54)["guesses"][-1]
        self.assertEqual((close["grade"], close["direction"]), ("close", "higher"))
        close = self.guess("DA", 66)["guesses"][-1]
        self.assertEqual((close["grade"], close["direction"]), ("close", "lower"))
        state = self.guess("DA", 55)
        self.assertTrue(state["won"])
        self.assertTrue(state["finished"])

    def test_each_miss_earns_the_next_hint(self):
        labels = [
            [h["label"] for h in self.guess("EFF", n)["hints"]] for n in range(1, 5)
        ]
        self.assertEqual(labels[0], ["Province"])
        self.assertEqual(labels[-1], ["Province", "Municipality", "Voting station", "Runner-up"])
        self.assertEqual(self.guess("EFF", 9)["hints"], [])  # finished: the result says it all

    def test_guesses_run_out(self):
        for n in range(ATTEMPTS):
            state = self.guess("EFF", n)
        self.assertTrue(state["finished"])
        self.assertFalse(state["won"])
        self.guess("DA", 60, status=400)

    def test_the_same_guess_twice_does_not_cost_a_turn(self):
        self.guess("EFF", 10)
        self.guess("EFF", 10, status=400)
        self.assertEqual(len(self.guess("EFF", 11)["guesses"]), 2)

    def test_the_result_is_only_sent_once_it_is_over(self):
        self.assertNotIn("result", self.guess("ANC", 30))
        result = self.guess("DA", 60)["result"]
        self.assertIn("Rosmead Central Primary School", result)
        self.assertIn("60.0%", result)

    def test_the_result_shows_the_councils_largest_party(self):
        make_council()
        result = self.guess("DA", 60)["result"]
        self.assertIn("2021 Municipal Election", result)
        self.assertIn("135 of 231 seats", result)
        self.assertIn("with a majority", result)

    def test_a_refresh_keeps_the_guesses(self):
        self.guess("ANC", 30)
        page = self.client.get(self.puzzle.get_absolute_url())
        self.assertEqual(len(page.context["state"]["guesses"]), 1)

    def test_the_page_gives_nothing_away_before_the_guessing(self):
        # The panorama is shown by its id, so not even the coordinates are
        # in the page.
        page = self.client.get(self.puzzle.get_absolute_url()).content.decode()
        for spoiler in ["Rosmead", "Cape Town", "Western Cape", "97090421", "60.0", "-33.99"]:
            self.assertNotIn(spoiler, page)


class StreetViewLinkTest(TestCase):
    def test_reads_the_view_and_panorama(self):
        fields = parse_street_view_link(
            "https://www.google.com/maps/@-33.9258,18.4232,3a,75y,210.5h,95t"
            "/data=!3m6!1e1!3m4!1sAbC-dEf_123!2e0!7i16384!8i8192"
        )
        self.assertEqual(fields, {
            "latitude": -33.9258, "longitude": 18.4232, "fov": 91.3,
            "heading": 210.5, "pitch": 5, "pano": "AbC-dEf_123",
        })

    def test_reads_a_link_copied_from_google_maps(self):
        fields = parse_street_view_link(
            "https://www.google.com/maps/@-33.8832241,18.714603,155a,15.2y,161.82h,83.07t"
            "/data=!3m7!1e1!3m5!1sUbEv7Ekc3tRO1qx4UkKv3w!2e0!6shttps:%2F%2Fstreetviewpixels-pa"
            ".googleapis.com%2Fv1%2Fthumbnail%3Fcb_client%3Dmaps_sv.tactile%26w%3D900%26h%3D600"
            "%26pitch%3D6.934406869391395%26panoid%3DUbEv7Ekc3tRO1qx4UkKv3w%26yaw%3D161.82308729182677"
            "!7i16384!8i8192?entry=ttu&g_ep=EgoyMDI2MTAwNC4wIKXMDSoASAFQAw%3D%3D"
        )
        self.assertEqual(fields["pano"], "UbEv7Ekc3tRO1qx4UkKv3w")
        self.assertEqual((fields["latitude"], fields["longitude"]), (-33.8832241, 18.714603))
        self.assertEqual((fields["heading"], fields["fov"]), (161.82, 20.2))
        self.assertAlmostEqual(fields["pitch"], -6.93)

    def test_a_map_link_is_not_a_street_view_link(self):
        with self.assertRaises(ValueError):
            parse_street_view_link("https://www.google.com/maps/@-33.92,18.42,15z")


HEADER = (
    "Province,Municipality,VD_Number,VS_Name,Registered_Population,"
    "Spoilt_Votes,Total_Valid_Votes,sPartyName,Party_Votes,Generated_Datetime\n"
)
ROWS = [
    "Western Cape,CPT - City of Cape Town,97090421,ROSMEAD SCHOOL,2000,10,1000,DEMOCRATIC ALLIANCE,600,x",
    "Western Cape,CPT - City of Cape Town,97090421,ROSMEAD SCHOOL,2000,10,1000,UMKHONTO WESIZWE ,400,x",
    "Western Cape,CPT - City of Cape Town,97090421,ROSMEAD SCHOOL,2000,10,1000,ACTIONSA,0,x",
    "Free State,FS181 - Masilonyana,22630126,KLIPPAN FARM,50,0,0,DEMOCRATIC ALLIANCE,0,x",
    "Out of Country,Out of Country,99999999,LONDON,10,0,5,DEMOCRATIC ALLIANCE,5,x",
]


class ImportTest(TestCase):
    def run_import(self, text, zipped=False):
        directory = Path(tempfile.mkdtemp())
        path = directory / "National.csv"
        path.write_text("﻿" + text, encoding="utf-8")
        if zipped:
            with zipfile.ZipFile(directory / "National.zip", "w") as archive:
                archive.write(path, "National.csv")
            path = directory / "National.zip"
        call_command("import_iec_results", str(path), stdout=StringIO())

    def test_imports_each_district_once_with_its_votes(self):
        self.run_import(HEADER + "\n".join(ROWS), zipped=True)
        district = VotingDistrict.objects.get()
        self.assertEqual(district.number, "97090421")
        self.assertEqual(district.votes, {"DEMOCRATIC ALLIANCE": 600, "UMKHONTO WESIZWE": 400})
        self.assertEqual(district.winner(), ("DA", 60))

    def test_importing_again_updates_rather_than_duplicates(self):
        self.run_import(HEADER + ROWS[0])
        self.run_import(HEADER + ROWS[0].replace(",600,", ",700,"))
        self.assertEqual(VotingDistrict.objects.get().votes, {"DEMOCRATIC ALLIANCE": 700})

    def test_refuses_a_file_that_is_not_the_iec_one(self):
        with self.assertRaises(CommandError):
            self.run_import("Name,Votes\nDA,1\n")


# The second sheet of a Seat Calculation Detail report, as xlrd reads it:
# blank cells are "", numbers are floats, and the columns shift about.
SEAT_ROWS = [
    ["", "", "Party Name", "Total Party Seats (x)", "Ward Seats (y)", "PR List Seats (x-y)", ""],
    ["", "", "AFRICAN NATIONAL CONGRESS *", 8.0, 8.0, 0, ""],
    ["", "", "CONGRESS  OF THE PEOPLE", 0, 0, 0, ""],
    ["", "", "DEMOCRATIC ALLIANCE", 5.0, 1.0, 4.0, ""],
    ["", "", "Total Party Seats", 13.0, 9.0, 4.0, ""],
    ["", "", "Independents", "", 1.0, "", ""],
    ["", "", "Total Seats", "", 10.0, 4.0, 14.0],
    ["", "Note: This report refers to the Local Government Municipal Structures Act 117 of 1998", "", "", "", "", ""],
]


class ImportCouncilsTest(TestCase):
    def run_import(self, rows):
        with mock.patch(
            "streetwise.management.commands.import_iec_councils.Command.rows",
            return_value=rows,
        ) as fetch:
            call_command("import_iec_councils", stdout=StringIO(), stderr=StringIO())
        return fetch

    def test_reads_each_partys_seats_and_the_independents(self):
        self.assertEqual(
            read_seats(SEAT_ROWS),
            ({"AFRICAN NATIONAL CONGRESS": 8, "DEMOCRATIC ALLIANCE": 5}, 1),
        )

    def test_refuses_seats_that_do_not_add_up(self):
        with self.assertRaises(ValueError):
            read_seats(SEAT_ROWS[:5] + SEAT_ROWS[6:])

    def test_imports_a_council_for_each_municipality_with_districts(self):
        make_district()
        fetch = self.run_import(SEAT_ROWS)
        fetch.assert_called_once_with(
            "https://results.elections.org.za/home/LGEPublicReports/1091/"
            "Seat%20Calculation%20Detail/WP/CPT.xls"
        )
        council = Council.objects.get()
        self.assertEqual((council.code, council.name, council.year), ("CPT", "City of Cape Town", 2021))
        self.assertEqual(council.total(), 14)
        self.run_import(SEAT_ROWS[:1] + SEAT_ROWS[3:4] + [["Total Seats", 5.0]])
        self.assertEqual(Council.objects.get().seats, {"DEMOCRATIC ALLIANCE": 5})


def write_shapefile(path, polygons):
    """A minimal polygon shapefile: {district number: [ring, ...]}."""
    records = []
    for number, rings in polygons.items():
        points = [p for ring in rings for p in ring]
        starts, n = [], 0
        for ring in rings:
            starts.append(n)
            n += len(ring)
        xs, ys = [x for x, _ in points], [y for _, y in points]
        content = (
            struct.pack("<i4d2i", 5, min(xs), min(ys), max(xs), max(ys), len(rings), len(points))
            + struct.pack(f"<{len(rings)}i", *starts)
            + b"".join(struct.pack("<2d", *p) for p in points)
        )
        records.append(struct.pack(">2i", len(records) + 1, len(content) // 2) + content)
    path.with_suffix(".shp").write_bytes(b"\0" * 100 + b"".join(records))
    header = struct.pack("<4xIHH20x", len(polygons), 32 + 32 + 1, 1 + 8)
    field = b"VDNumber".ljust(11, b"\0") + b"N" + b"\0" * 4 + bytes([8, 0]) + b"\0" * 14
    rows = b"".join(b" " + number.encode() for number in polygons)
    path.with_suffix(".dbf").write_bytes(header + field + b"\x0d" + rows)


# A district about 1.1 km a side, with a 100 m hole in the middle.
SQUARE = [(18.0, -34.0), (18.01, -34.0), (18.01, -33.99), (18.0, -33.99)]
HOLE = [(18.0045, -33.9955), (18.0055, -33.9955), (18.0055, -33.9945), (18.0045, -33.9945)]


class GeometryTest(TestCase):
    def test_reads_the_districts_asked_for(self):
        path = Path(tempfile.mkdtemp()) / "vd2024.shp"
        write_shapefile(path, {"97090421": [SQUARE], "11111111": [SQUARE]})
        self.assertEqual(geometry.read_boundaries(path, {"97090421"}), {"97090421": [SQUARE]})

    def test_inside_outside_and_holes(self):
        rings = [SQUARE, HOLE]
        self.assertTrue(geometry.contains(rings, 18.002, -33.998))
        self.assertFalse(geometry.contains(rings, 18.02, -33.998))
        self.assertFalse(geometry.contains(rings, 18.005, -33.995))

    def test_distance_to_the_boundary_in_metres(self):
        # 0.001 degrees of longitude in from the west edge, at 34 degrees south.
        self.assertAlmostEqual(geometry.distance_to_edge([SQUARE], 18.001, -33.995), 92, delta=1)


class FindPanoramasTest(TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "vd2024.shp"
        polygons = {}
        winners = ["DEMOCRATIC ALLIANCE"] * 3 + ["INKATHA FREEDOM PARTY"] * 2
        for n, winner in enumerate(winners):
            number = f"9000000{n}"
            make_district(number=number, votes={winner: 10, "ACTIONSA": 1})
            polygons[number] = [[(x + n, y) for x, y in SQUARE]]
        write_shapefile(self.path, polygons)
        self.out = self.path.with_name("found.csv")

    def run_command(self, metadata):
        with mock.patch(
            "streetwise.management.commands.find_panoramas.Command.metadata",
            lambda command, lat, lng: metadata(lat, lng),
        ), self.settings(GOOGLE_MAPS_EMBED_KEY="test"):
            call_command("find_panoramas", str(self.path), str(self.out), count=4, stdout=StringIO())
        with open(self.out) as f:
            return list(csv.DictReader(f))

    def test_finds_a_mix_of_winners_with_panoramas_inside_their_districts(self):
        def metadata(lat, lng):
            return {"status": "OK", "copyright": "© Google", "date": "2023-05",
                    "pano_id": f"p{lat:.6f}", "location": {"lat": lat, "lng": lng}}
        rows = self.run_command(metadata)
        self.assertEqual(len(rows), 4)
        winners = {VotingDistrict.objects.get(number=row["district"]).winner()[0] for row in rows}
        self.assertEqual(winners, {"DA", "IFP"})
        for row in rows:
            rings = geometry.read_boundaries(self.path, {row["district"]})[row["district"]]
            self.assertTrue(geometry.contains(rings, float(row["longitude"]), float(row["latitude"])))

    def test_rejects_panoramas_outside_the_district_or_not_by_google(self):
        def outside(lat, lng):
            return {"status": "OK", "copyright": "© Google", "date": "2023-05",
                    "pano_id": "x", "location": {"lat": lat, "lng": lng + 0.5}}

        def someone_else(lat, lng):
            return {"status": "OK", "copyright": "© A. Person", "date": "2023-05",
                    "pano_id": "x", "location": {"lat": lat, "lng": lng}}
        self.assertEqual(self.run_command(outside), [])
        self.assertEqual(self.run_command(someone_else), [])


class ImportStreetwiseTest(TestCase):
    def run_import(self, rows, *args):
        path = Path(tempfile.mkdtemp()) / "puzzles.csv"
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        call_command("import_streetwise", str(path), *args, stdout=StringIO())

    def row(self, pano, district="97090421"):
        return {"district": district, "pano": pano, "latitude": "-33.99", "longitude": "18.47",
                "heading": "90", "pitch": "0", "fov": "90", "notes": "Imagery 2023-05."}

    def test_imports_unpublished_and_skips_ones_already_in(self):
        make_district()
        self.run_import([self.row("a"), self.row("b")])
        self.run_import([self.row("b"), self.row("c")])
        self.assertEqual(sorted(Streetwise.objects.values_list("pano", flat=True)), ["a", "b", "c"])
        self.assertFalse(Streetwise.objects.published().exists())

    def test_schedules_one_a_day(self):
        make_district()
        self.run_import([self.row("a"), self.row("b")], "--schedule-from", "2026-11-01")
        dates = [timezone.localtime(p.published).date().isoformat()
                 for p in Streetwise.objects.order_by("published")]
        self.assertEqual(dates, ["2026-11-01", "2026-11-02"])

    def test_a_bad_row_stops_the_whole_import(self):
        make_district()
        with self.assertRaises(CommandError):
            self.run_import([self.row("a"), self.row("b", district="12345678")])
        self.assertFalse(Streetwise.objects.exists())
