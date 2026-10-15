import math
import re
from urllib.parse import urlencode

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone

# The parties a player can pick, in the order the buttons show them: the
# eight with the most votes nationally in 2024, by their short names, and
# the IEC's name for each. Any other winner is "Other".
PARTIES = {
    "ANC": "AFRICAN NATIONAL CONGRESS",
    "DA": "DEMOCRATIC ALLIANCE",
    "MK": "UMKHONTO WESIZWE",
    "EFF": "ECONOMIC FREEDOM FIGHTERS",
    "IFP": "INKATHA FREEDOM PARTY",
    "PA": "PATRIOTIC ALLIANCE",
    "ActionSA": "ACTIONSA",
    "VF Plus": "VRYHEIDSFRONT PLUS",
}
OTHER = "Other"
CHOICES = [*PARTIES, OTHER]
SHORT_NAMES = {iec: short for short, iec in PARTIES.items()}


def short_name(iec_name):
    """A party as the results show it: the short name for one with a
    button, the IEC's name in title case for any other."""
    return SHORT_NAMES.get(iec_name, iec_name.title())


class Council(models.Model):
    """A municipal council's seats after a local government election. Filled
    by `manage.py import_iec_councils`, never by hand."""

    code = models.CharField(max_length=8)  # the IEC's, e.g. "WC024"
    name = models.CharField(max_length=100)
    year = models.PositiveSmallIntegerField()
    # The IEC's party name -> seats won, leaving out parties with none.
    seats = models.JSONField(default=dict)
    independents = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["code", "-year"]
        constraints = [
            models.UniqueConstraint(fields=["code", "year"], name="one_council_per_election")
        ]

    def __str__(self):
        return f"{self.code} - {self.name}, {self.year}"

    def total(self):
        return sum(self.seats.values()) + self.independents

    def ranked(self):
        """[(party, seats)], biggest first, independents last."""
        ranked = sorted(self.seats.items(), key=lambda item: -item[1])
        parties = [(short_name(name), seats) for name, seats in ranked]
        if self.independents:
            parties.append(("Independents", self.independents))
        return parties

    def most_seats(self):
        return max(self.seats.values())

    def largest(self):
        """The party with the most seats. A few councils were tied, so it's a
        list."""
        most = self.most_seats()
        return [short_name(name) for name, seats in self.seats.items() if seats == most]

    def has_majority(self):
        return 2 * self.most_seats() > self.total()


class VotingDistrict(models.Model):
    """One IEC voting district and how it voted on the national ballot in
    2024. Filled by `manage.py import_iec_results`, never by hand."""

    number = models.CharField(max_length=8, unique=True)
    province = models.CharField(max_length=50)
    municipality = models.CharField(max_length=100)
    station = models.CharField(max_length=200, verbose_name="voting station")
    registered = models.PositiveIntegerField()
    spoilt = models.PositiveIntegerField()
    # The IEC's party name -> valid votes, leaving out parties with none.
    votes = models.JSONField(default=dict)

    class Meta:
        ordering = ["number"]

    def __str__(self):
        return f"{self.number}: {self.station.title()}, {self.municipality}"

    def place(self):
        """The municipality without the IEC's code: "Buffalo City", not
        "BUF - Buffalo City"."""
        return self.municipality.split(" - ", 1)[-1]

    def municipality_code(self):
        return self.municipality.split(" - ", 1)[0]

    def council(self):
        """The municipality's council after the latest local election
        imported, or None."""
        return Council.objects.filter(code=self.municipality_code()).first()

    def valid_votes(self):
        return sum(self.votes.values())

    def turnout(self):
        """Votes cast, spoilt ones included, as a percentage of those
        registered -- the IEC's own definition."""
        if not self.registered:
            return 0
        return 100 * (self.valid_votes() + self.spoilt) / self.registered

    def results(self):
        """[(party, percent of valid votes)], biggest first, with the
        parties players can pick by their short names."""
        valid = self.valid_votes() or 1
        ranked = sorted(self.votes.items(), key=lambda item: -item[1])
        return [(short_name(name), 100 * votes / valid) for name, votes in ranked]

    def is_tie(self):
        top = sorted(self.votes.values(), reverse=True)[:2]
        return len(top) == 2 and top[0] == top[1]

    def winner(self):
        """The answer: the winning party as a player would pick it, and its
        share of the vote."""
        name, votes = max(self.votes.items(), key=lambda item: item[1])
        return SHORT_NAMES.get(name, OTHER), 100 * votes / (self.valid_votes() or 1)


class StreetwiseQuerySet(models.QuerySet):
    def published(self):
        return self.filter(
            published__isnull=False, published__lte=timezone.now(), rejected=False
        )


class Streetwise(models.Model):
    district = models.ForeignKey(
        VotingDistrict, on_delete=models.PROTECT, related_name="puzzles"
    )
    # The panorama, as Google's id for it. The coordinates are kept for
    # the editors and the result screen, and so a district's boundary can
    # one day be checked against them; the player's page never gets them.
    pano = models.CharField(
        max_length=200, blank=True, verbose_name="panorama id",
        help_text="Filled in from the Street View link. Without one, the "
        "nearest panorama to the coordinates is shown.")
    latitude = models.FloatField()
    longitude = models.FloatField()
    heading = models.FloatField(default=0, help_text="Compass bearing, 0 to 360.")
    pitch = models.FloatField(default=0, help_text="Up or down, -90 to 90.")
    fov = models.FloatField(
        default=90, verbose_name="field of view",
        help_text="Zoom, 10 (close) to 100 (wide).")
    published = models.DateTimeField(null=True, blank=True)
    rejected = models.BooleanField(
        default=False,
        help_text="The panorama gives the place away, or is otherwise unusable. "
        "Rejected puzzles are never published.")
    notes = models.TextField(blank=True, help_text="For editors only.")
    created = models.DateTimeField(auto_now_add=True, editable=False)
    modified = models.DateTimeField(auto_now=True, editable=False)

    objects = StreetwiseQuerySet.as_manager()

    class Meta:
        verbose_name = "Streetwise"
        verbose_name_plural = "Streetwise"
        ordering = [models.F("published").desc(nulls_first=True), "-modified"]

    def __str__(self):
        return f"Streetwise {self.pk}: {self.district}"

    def clean(self):
        if self.district_id and self.district.is_tie():
            raise ValidationError(
                {"district": "This district's vote was a tie for first place. Pick another."})
        if self.rejected and self.published:
            raise ValidationError(
                {"published": "A rejected panorama can't be published. "
                 "Clear the date, or untick Rejected."})

    def get_absolute_url(self):
        return reverse("streetwise:detail", args=[self.pk])

    def is_published(self):
        return (
            self.published is not None
            and self.published <= timezone.now()
            and not self.rejected
        )

    def number(self):
        """Its place in the run of published puzzles, by date. Counted
        rather than stored, so puzzles can be scheduled in any order."""
        if self.published is None:
            return None
        return Streetwise.objects.filter(
            published__isnull=False, published__lte=self.published, rejected=False
        ).count()

    def embed_url(self):
        """The Maps Embed API's Street View mode, pointed at the panorama."""
        params = {"key": settings.GOOGLE_MAPS_EMBED_KEY}
        if self.pano:
            params["pano"] = self.pano
        else:
            params["location"] = f"{self.latitude},{self.longitude}"
        params.update(heading=self.heading, pitch=self.pitch, fov=self.fov)
        return "https://www.google.com/maps/embed/v1/streetview?" + urlencode(params)

    def maps_url(self):
        """Where it is on Google Maps, for the result screen."""
        return (
            "https://www.google.com/maps/search/?"
            + urlencode({"api": 1, "query": f"{self.latitude},{self.longitude}"})
        )


def parse_street_view_link(link):
    """The position and view in a Street View link copied from Google Maps'
    address bar, e.g.

        https://www.google.com/maps/@-33.92,18.42,3a,75y,210h,95t/data=!3m6!1e1!3m4!1s<pano>!2e0...

    Returns a dict of the model's fields. Raises ValueError for a link
    that isn't a Street View one.
    """
    position = re.search(r"@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?),([^/?]*)", link)
    # A Street View link has an "<n>a" part ("3a", "155a"); a map link has
    # a zoom ("15z") instead.
    if not position or not re.search(r"(^|,)\d+(\.\d+)?a(,|$)", position[3]):
        raise ValueError("That isn't a Street View link.")
    fields = {"latitude": float(position[1]), "longitude": float(position[2])}
    for part in position[3].split(","):
        number, suffix = part[:-1], part[-1:]
        if not re.fullmatch(r"-?\d+(?:\.\d+)?", number):
            continue
        if suffix == "y":
            # Maps gives the field of view top to bottom; the embed wants
            # it side to side. Converted for the game's roughly 4:3 frame,
            # which takes Maps' default 75 to about the embed's 90.
            across = 2 * math.degrees(math.atan(math.tan(math.radians(float(number)) / 2) * 4 / 3))
            fields["fov"] = round(min(100, max(10, across)), 1)
        elif suffix == "h":
            fields["heading"] = float(number) % 360
        elif suffix == "t":
            # Maps measures tilt from straight down; the embed, pitch from
            # the horizon.
            fields["pitch"] = float(number) - 90
    pano = re.search(r"!1s([^!]+)!2e", link)
    fields["pano"] = pano[1] if pano else ""
    return fields
