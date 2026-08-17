import random
import string
from django.core.validators import RegexValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.models import User

# Claude: Why use a regex validator instead of Python's isupper?
# Claude response: Two reasons. (1) isupper() allows digits — "AB3".isupper() is True
# because all *cased* characters are uppercase. The regex ^[A-Z]+$ strictly permits
# only A-Z letters. (2) Django validators must be callable objects that raise
# ValidationError — you can't pass isupper directly to a field's validators list.
uppercase_az = RegexValidator(r"^[A-Z]+$", "Text must be uppercase A-Z only.")


class Word(models.Model):
    """A dictionary entry: one crossword answer string (which may itself be
    a multi-word phrase, stored with no spaces) available to fill a slot."""

    # Claude: Why is the max_length set to 64?
    # Claude response: It's a safe ceiling for crossword answers. The largest standard
    # grids are 21x21 (NYT Sunday), so the longest possible answer is 21 letters. 64
    # gives ample headroom without being unlimited. 32 would also work — 64 is somewhat
    # arbitrary but a common power-of-two choice.
    text = models.CharField(max_length=64, unique=True, validators=[uppercase_az])
    source_crossword = models.ForeignKey(
        "Crossword",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sourced_words",
    )
    exclude_from_recommendations = models.BooleanField(default=False)
    date_added = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # full_clean() runs field validators (including uppercase_az) before
        # every save, not just form-bound saves, so a Word created directly
        # in code (e.g. from crossword_save or an .xd import) can't bypass
        # the uppercase-A-Z rule the way skipping full_clean() would allow.
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.text


class Clue(models.Model):
    """One phrasing of a clue for a Word. A word may have several clues
    (from different crosswords/setters); (word, clue text) must be unique."""

    text = models.ForeignKey(Word, on_delete=models.CASCADE, related_name="clues")
    clue = models.TextField()
    source_crossword = models.ForeignKey(
        "Crossword",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sourced_clues",
    )
    date_added = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)

    class Meta:
        # Prevents the exact same clue text being stored twice for one word,
        # while still allowing several distinct clues per word.
        constraints = [
            models.UniqueConstraint(fields=["text", "clue"], name="unique_text_clue"),
        ]

    def __str__(self):
        return self.clue


def default_copyright():
    """Default value for Crossword.copyright, evaluated at save time (not
    import time) so the year is always current for newly created puzzles."""
    return f"(C) {timezone.now().year} GroundUp News"


def random_string(size=60, chars=string.ascii_letters + string.digits):
    return "".join(random.SystemRandom().choice(chars) for _ in range(size))


class CrosswordQuerySet(models.QuerySet):
    def published(self):
        """Crosswords with a publication datetime that has already passed.
        Used to filter what non-generator users are allowed to see."""
        return self.filter(published__isnull=False, published__lte=timezone.now())


class Crossword(models.Model):
    """A crossword puzzle: its dimensions, the block/letter grid (the
    source of truth -- see `cells` below), setter metadata, and publication
    status. `Entry` rows are a derived index over this grid's complete
    slots, not independent data."""

    name = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    authors = models.CharField(max_length=200, blank=True)
    editors = models.CharField(max_length=200, blank=True)
    copyright = models.CharField(max_length=200, default=default_copyright)
    date_added = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)
    published = models.DateTimeField(null=True, blank=True)
    num_rows = models.PositiveIntegerField()
    num_cols = models.PositiveIntegerField()
    blocked_out_squares = models.JSONField(default=list)
    cells = models.JSONField(default=list)
    requires_rotational_symmetry = models.BooleanField(default=True)
    owner = models.ForeignKey(
        User,
        default=1,
        on_delete=models.CASCADE,
    )
    private = models.BooleanField(default=False)
    private_link = models.CharField(max_length=60, default=random_string, unique=True)

    objects = CrosswordQuerySet.as_manager()

    class Meta:
        permissions = [("can_generate_crosswords", "Can generate crosswords")]

    def get_absolute_url(self):
        # Used by Django admin's "View on site" link (CrosswordAdmin sets
        # view_on_site = True) as well as anywhere else Django needs a
        # canonical URL for the object.
        return reverse("crossword_solve", args=[self.pk])

    def is_published(self):
        """True once `published` is set and that moment has passed."""
        return self.published is not None and self.published <= timezone.now()

    def __str__(self):
        return self.name or f"Crossword {self.pk}"


# Claude: We are tring to achieve two things: (a) store the, perhaps
# unfinished, crossword clues and answers and (b) have a database of clues and
# answers to show the crossword setter. But it seems there is something less
# than ideal in the design because we're duplicating information in the
# Crossword.cells field and the Entry table below. Having said that it's not clear to me
# that a more normalised design would come with fewer problems.
#
# Claude response: The duplication is real but intentional and defensible.
# Crossword.cells is the canonical grid state — a flat list of letters needed to render
# the grid efficiently without joins. Entry is the semantic layer — it names which word
# occupies which slot and links to clues and the word database.
# A fully normalised design (deriving cell contents from Entry rows) would require
# reconstructing the grid from slot positions on every render, and makes partial/in-progress
# grids awkward (cells with letters but no committed Entry yet). The main risk with the
# current design is that cells and Entry rows drift out of sync — worth adding a
# validation method on Crossword that checks consistency, but not a reason to redesign.


class Entry(models.Model):
    """A single numbered slot (crossword, number, direction) in a completed
    grid: which Word fills it and, optionally, which Clue is attached.
    Entries are derived from `Crossword.cells` on every save -- see
    grid.slots() and views.crossword_save -- not edited directly."""

    ACROSS = "A"
    DOWN = "D"
    DIRECTION_CHOICES = [(ACROSS, "Across"), (DOWN, "Down")]

    crossword = models.ForeignKey(
        Crossword, on_delete=models.CASCADE, related_name="entries"
    )
    word = models.ForeignKey(Word, on_delete=models.PROTECT, related_name="entries")
    clue = models.ForeignKey(
        Clue, on_delete=models.SET_NULL, null=True, blank=True, related_name="entries"
    )
    number = models.PositiveIntegerField()
    direction = models.CharField(max_length=1, choices=DIRECTION_CHOICES)

    class Meta:
        # A given slot (number + direction) in a given crossword can only
        # ever hold one word at a time -- this is what makes
        # Entry.objects.update_or_create(crossword=, number=, direction=)
        # in crossword_save() safe to call repeatedly.
        constraints = [
            models.UniqueConstraint(
                fields=["crossword", "number", "direction"],
                name="unique_crossword_number_direction",
            ),
        ]

    def __str__(self):
        return f"{self.number}{self.direction}: {self.word.text}"
