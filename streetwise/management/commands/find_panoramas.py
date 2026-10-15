import csv
import json
import random
import time
import urllib.parse
import urllib.request
from collections import defaultdict

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from streetwise import geometry
from streetwise.models import Streetwise, VotingDistrict

METADATA = "https://maps.googleapis.com/maps/api/streetview/metadata"
# How far to flatten the mix of winners. The ANC won about two in three
# districts; picking in proportion to the count raised to this power gives
# roughly 28% ANC, 18% DA, 17% MK, 13% IFP and the rest spread among the
# smaller parties.
FLATTEN = 0.3
TRIES = 8          # random spots to try in each district
SEARCH_RADIUS = 300  # metres around a spot to look for a panorama
MARGIN = 40        # metres a panorama must be inside its boundary
OLDEST = "2015"    # older imagery shows a street that may have changed


class Command(BaseCommand):
    help = (
        "Finds Google Street View panoramas inside voting districts, for a mix "
        "of winning parties, and writes them to a CSV for import_streetwise. "
        "Needs the IEC's 2024 voting-district boundaries as a shapefile "
        "(vd2024.shp, with its .dbf), and the Street View Static API enabled "
        "for the key; its metadata lookups are free."
    )

    def add_arguments(self, parser):
        parser.add_argument("boundaries", help="vd2024.shp")
        parser.add_argument("out", help="CSV to write")
        parser.add_argument("--count", type=int, default=300)
        parser.add_argument("--seed", type=int, default=2024)

    def handle(self, boundaries, out, count, seed, **options):
        self.key = getattr(settings, "GOOGLE_STREETVIEW_KEY", "") or settings.GOOGLE_MAPS_EMBED_KEY
        if not self.key:
            raise CommandError("Set GOOGLE_STREETVIEW_KEY or GOOGLE_MAPS_EMBED_KEY.")
        self.random = random.Random(seed)

        used = set(Streetwise.objects.values_list("district__number", flat=True))
        by_party = defaultdict(list)
        for district in VotingDistrict.objects.exclude(number__in=used):
            if not district.is_tie():
                by_party[district.winner()[0]].append(district)
        quotas = self.quotas(by_party, count)
        self.stdout.write("Aiming for " + ", ".join(f"{p} {n}" for p, n in quotas.items()))

        wanted = {d.number for districts in by_party.values() for d in districts}
        self.boundaries = geometry.read_boundaries(boundaries, wanted)
        self.stdout.write(f"Read {len(self.boundaries)} district boundaries.")

        found = []
        for party, quota in quotas.items():
            got = 0
            for district in self.spread(by_party[party]):
                if got == quota:
                    break
                pano = self.panorama(district)
                if pano:
                    found.append(pano)
                    got += 1
            self.stdout.write(f"{party}: {got} of {quota}")
            self.stdout.flush()

        self.random.shuffle(found)
        with open(out, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(found[0]) if found else ["district"])
            writer.writeheader()
            writer.writerows(found)
        self.stdout.write(f"Wrote {len(found)} puzzles to {out}.")

    def quotas(self, by_party, count):
        weights = {party: len(d) ** FLATTEN for party, d in by_party.items()}
        total = sum(weights.values())
        quotas = {
            party: min(len(by_party[party]), round(count * weight / total))
            for party, weight in sorted(weights.items(), key=lambda item: -item[1])
        }
        # Whatever the small parties can't fill goes to the biggest.
        biggest = next(iter(quotas))
        quotas[biggest] += count - sum(quotas.values())
        return quotas

    def spread(self, districts):
        """The districts in a random order that takes each province in turn,
        so one party's puzzles don't all come from the same place."""
        by_province = defaultdict(list)
        for district in districts:
            by_province[district.province].append(district)
        for group in by_province.values():
            self.random.shuffle(group)
        queues = list(by_province.values())
        while queues:
            for queue in list(queues):
                yield queue.pop()
                if not queue:
                    queues.remove(queue)

    def panorama(self, district):
        rings = self.boundaries.get(district.number)
        if not rings:
            return None
        west, south, east, north = geometry.bounds(rings)
        for _ in range(TRIES):
            lng, lat = self.random.uniform(west, east), self.random.uniform(south, north)
            if not geometry.contains(rings, lng, lat):
                continue
            meta = self.metadata(lat, lng)
            if meta.get("status") != "OK" or meta.get("copyright") != "© Google":
                continue
            if meta.get("date", "") < OLDEST:
                continue
            plat, plng = meta["location"]["lat"], meta["location"]["lng"]
            if not geometry.contains(rings, plng, plat):
                continue
            if geometry.distance_to_edge(rings, plng, plat) < MARGIN:
                continue
            return {
                "district": district.number,
                "pano": meta["pano_id"],
                "latitude": plat,
                "longitude": plng,
                "heading": self.random.randrange(360),
                "pitch": 0,
                "fov": 90,
                "notes": f"Found by find_panoramas. Imagery {meta['date']}.",
            }
        return None

    def metadata(self, lat, lng):
        query = urllib.parse.urlencode({
            "location": f"{lat},{lng}",
            "radius": SEARCH_RADIUS,
            "source": "outdoor",
            "key": self.key,
        })
        for attempt in range(3):
            try:
                with urllib.request.urlopen(f"{METADATA}?{query}", timeout=20) as response:
                    meta = json.load(response)
            except OSError:
                time.sleep(2 ** attempt)
                continue
            if meta.get("status") == "REQUEST_DENIED":
                raise CommandError(meta.get("error_message", "Google refused the request."))
            return meta
        return {}
