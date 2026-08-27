from django.db import models
from django.urls import reverse
from django.utils import timezone


class SudokuQuerySet(models.QuerySet):
    def published(self):
        """Puzzles whose publication time has passed (mirrors
        CrosswordQuerySet.published)."""
        return self.filter(published__isnull=False, published__lte=timezone.now())


class Sudoku(models.Model):
    """One 9x9 puzzle. `puzzle` and `solution` are both 81-character
    strings in row-major order, with "0" for a blank -- flat strings are
    cheap to import in bulk and to hand to the browser in one go."""

    class Difficulty(models.TextChoices):
        UNKNOWN = "0", "Unknown"
        VERY_EASY = "1", "Very easy"
        EASY = "2", "Easy"
        MEDIUM = "3", "Medium"
        HARD = "4", "Hard"
        VERY_HARD = "5", "Very hard"
        EXTREMELY_HARD = "6", "Extremely hard"

    # The three difficulties the play screen offers as tabs. The importer
    # can supply any of the levels above; these are the ones a reader is
    # offered a choice between.
    TAB_DIFFICULTIES = [Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD]

    puzzle = models.CharField(max_length=81, unique=True)
    solution = models.CharField(max_length=81, blank=True)
    number = models.PositiveIntegerField(null=True, blank=True)
    difficulty = models.CharField(
        max_length=1, choices=Difficulty.choices, default=Difficulty.UNKNOWN
    )
    published = models.DateTimeField(null=True, blank=True)
    date_added = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)

    objects = SudokuQuerySet.as_manager()

    class Meta:
        ordering = ["-published"]
        permissions = [("can_generate_sudokus", "Can generate sudokus")]

    def get_absolute_url(self):
        return reverse("sudoku_solve", args=[self.pk])

    def is_published(self):
        """True once `published` is set and that moment has passed."""
        return self.published is not None and self.published <= timezone.now()

    def tile_digits(self):
        """The givens, with blanks for the rest, for the hub tile."""
        return [ch if ch != "0" else "" for ch in self.puzzle]

    def __str__(self):
        return f"Sudoku {self.pk} ({self.get_difficulty_display()})"
