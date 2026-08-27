from django.core.validators import RegexValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from . import generator

lowercase_az = RegexValidator(r"^[a-z]+$", "Letters must be lowercase a-z only.")

DEFAULT_RULES = """Make words of at least four letters using the grid letters at most once.
The centre letter must be in every word.
There's one nine-letter word.

Except possibly for the nine-letter word:
- There are no plurals ending in s. (But geese would be allowed.)
- There are no third-person singular verbs ending in s (e.g. cooks in 'he cooks bobotie').
- There are no proper nouns.

The nine-letter word often has a South African flavour."""


class TargetQuerySet(models.QuerySet):
    def published(self):
        """Puzzles whose publication time has passed (mirrors
        CrosswordQuerySet.published)."""
        return self.filter(published__isnull=False, published__lte=timezone.now())


class Target(models.Model):
    """One nine-letter puzzle.

    `letters` is the grid with the centre letter first; `words` is the
    answer list, one word per line. The answers never reach the browser in
    the clear -- see hashed_words().
    """

    letters = models.CharField(max_length=9, unique=True, validators=[lowercase_az])
    words = models.TextField(blank=True, help_text="One answer per line.")
    clue = models.CharField(max_length=150, blank=True, help_text="Leave blank if no clue.")
    rules = models.TextField(default=DEFAULT_RULES, blank=True)
    number = models.PositiveIntegerField(null=True, blank=True)
    published = models.DateTimeField(null=True, blank=True)
    date_added = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)

    objects = TargetQuerySet.as_manager()

    class Meta:
        ordering = ["-published"]
        permissions = [("can_generate_targets", "Can generate targets")]

    def get_absolute_url(self):
        return reverse("target_solve", args=[self.pk])

    def is_published(self):
        """True once `published` is set and that moment has passed."""
        return self.published is not None and self.published <= timezone.now()

    def word_list(self):
        return [w.strip().lower() for w in self.words.splitlines() if w.strip()]

    def hashed_words(self):
        """SHA-256 of every answer, so the play screen can check a guess
        by hashing it without the page ever containing the words."""
        return [generator.hash_word(w) for w in self.word_list()]

    def nine_letter_word(self):
        return next((w for w in self.word_list() if len(w) == 9), "")

    def centre(self):
        """The letter every answer has to use."""
        return self.letters[0] if self.letters else ""

    def tile_letters(self):
        """The nine letters for the hub tile, centre in the middle."""
        outer = list(self.letters[1:])
        cells = outer[:4] + [self.centre()] + outer[4:]
        return [{"char": c, "centre": i == 4} for i, c in enumerate(cells)]

    def __str__(self):
        return f"Target {self.number or self.pk}: {self.letters}"

    def save(self, *args, **kwargs):
        # Numbered in publication order, assigned once.
        if self.published and not self.number:
            latest = Target.objects.exclude(pk=self.pk).order_by("-number").first()
            self.number = (latest.number or 0) + 1 if latest else 1
        super().save(*args, **kwargs)
