"""Tests for the JSON API the news site's GroundUp Puzzles block reads.

Worth pinning down: a teaser never carries the answer, and an
unpublished puzzle is never announced.
"""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from crossword.models import Crossword
from sudoku.models import Sudoku

# Every cell holds a letter, so a leak would be obvious.
FILLED = ["C", "A", "T", "A", "B", "C", "T", "C", "D"]
PUZZLE = (
    "530070000"
    "600195000"
    "098000060"
    "800060003"
    "400803001"
    "700020006"
    "060000280"
    "000419005"
    "000080079"
)
SOLUTION = "9" * 81


def make_crossword(days=-1, **kwargs):
    defaults = dict(
        name="Test crossword",
        # Crossword.owner defaults to user 1, absent in a fresh test db.
        owner=User.objects.get_or_create(username="setter")[0],
        num_rows=3,
        num_cols=3,
        cells=list(FILLED),
        blocked_out_squares=[],
        published=timezone.now() + timezone.timedelta(days=days),
    )
    defaults.update(kwargs)
    return Crossword.objects.create(**defaults)


def make_sudoku(days=-1, **kwargs):
    defaults = dict(
        puzzle=PUZZLE,
        solution=SOLUTION,
        number=1234,
        difficulty=Sudoku.Difficulty.MEDIUM,
        published=timezone.now() + timezone.timedelta(days=days),
    )
    defaults.update(kwargs)
    return Sudoku.objects.create(**defaults)


class PuzzlesApiTest(TestCase):

    def puzzles(self):
        response = self.client.get(reverse("api_puzzles"))
        self.assertEqual(response.status_code, 200)
        return response.json()["puzzles"]

    def test_serves_the_newest_published_puzzle_of_each_kind(self):
        make_crossword(days=-2)
        newest = make_crossword(days=-1, name="Newest")
        make_sudoku()
        puzzles = self.puzzles()
        self.assertEqual(puzzles["crossword"]["title"], "Newest")
        self.assertIn(
            reverse("crossword_solve", args=[newest.pk]), puzzles["crossword"]["url"]
        )
        self.assertEqual(puzzles["sudoku"]["title"], "Sudoku #1234")
        self.assertEqual(puzzles["sudoku"]["difficulty"], "Medium")

    def test_urls_are_absolute_so_the_news_site_can_link_out(self):
        make_crossword()
        make_sudoku()
        puzzles = self.puzzles()
        for puzzle in puzzles.values():
            self.assertTrue(puzzle["url"].startswith("http"), puzzle["url"])

    def test_unpublished_puzzles_are_not_announced(self):
        make_crossword(days=7)
        make_sudoku(days=7)
        puzzles = self.puzzles()
        self.assertFalse(puzzles["crossword"]["available"])
        self.assertFalse(puzzles["sudoku"]["available"])
        self.assertIn("archive_url", puzzles["crossword"])

    def test_no_puzzles_at_all_is_not_an_error(self):
        puzzles = self.puzzles()
        self.assertFalse(puzzles["crossword"]["available"])
        self.assertFalse(puzzles["sudoku"]["available"])

    def test_crossword_teaser_carries_shape_and_numbers_but_no_letters(self):
        make_crossword(blocked_out_squares=[4])
        grid = self.puzzles()["crossword"]["grid"]
        self.assertEqual(len(grid), 3)
        self.assertEqual(len(grid[0]), 3)
        self.assertTrue(grid[1][1]["block"])
        self.assertEqual(grid[0][0]["number"], 1)
        for row in grid:
            for cell in row:
                self.assertEqual(set(cell), {"block", "number"})

    def test_crossword_teaser_carries_both_descriptions(self):
        # The news site's block is a teaser, so it wants the short blurb,
        # but the long one is served too for callers that show more.
        make_crossword(
            short_description="Three letters, one cat.",
            description="A gentle start to the week.",
        )
        crossword = self.puzzles()["crossword"]
        self.assertEqual(crossword["short_description"], "Three letters, one cat.")
        self.assertEqual(crossword["description"], "A gentle start to the week.")

    def test_sudoku_teaser_carries_givens_but_not_the_solution(self):
        make_sudoku()
        sudoku = self.puzzles()["sudoku"]
        self.assertEqual(len(sudoku["cells"]), 81)
        self.assertEqual(sudoku["cells"][0], "5")
        self.assertEqual(sudoku["cells"][2], "")  # a blank, not its answer
        self.assertNotIn("solution", sudoku)
        self.assertNotIn(SOLUTION, self.client.get(reverse("api_puzzles")).content.decode())

    def test_one_puzzle_can_be_fetched_on_its_own(self):
        make_sudoku()
        response = self.client.get(reverse("api_puzzle", args=["sudoku"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "Sudoku #1234")

    def test_a_puzzle_we_do_not_serve_is_a_404(self):
        # Target moves here later; until then the news site plays its own.
        self.assertEqual(
            self.client.get(reverse("api_puzzle", args=["target"])).status_code, 404
        )
