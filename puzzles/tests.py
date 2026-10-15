"""Tests for the JSON API the news site's GroundUp Puzzles block reads.

Worth pinning down: a teaser never carries the answer, and an
unpublished puzzle is never announced.
"""

import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from crossword.models import Crossword
from groupup.models import GroupUp
from groupup.tests import published_puzzle as make_groupup
from quizzes.models import Question, Quiz
from streetwise.tests import make_district, make_puzzle as make_streetwise
from sudoku.models import Sudoku
from target.models import Target

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


def make_target(days=-1, **kwargs):
    defaults = dict(
        letters="lpractica",
        words="practical",
        published=timezone.now() + timezone.timedelta(days=days),
    )
    defaults.update(kwargs)
    return Target.objects.create(**defaults)


def make_quiz(days=-1, **kwargs):
    defaults = dict(
        name="Test quiz",
        published=timezone.now() + timezone.timedelta(days=days),
    )
    defaults.update(kwargs)
    return Quiz.objects.create(**defaults)


# Saving a Target draws its image into MEDIA_ROOT; keep the tests' out of
# the real one.
@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
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
        make_target()
        make_quiz()
        make_groupup()
        make_streetwise()
        puzzles = self.puzzles()
        for puzzle in puzzles.values():
            self.assertTrue(puzzle["url"].startswith("http"), puzzle["url"])

    def test_unpublished_puzzles_are_not_announced(self):
        make_crossword(days=7)
        make_sudoku(days=7)
        make_target(days=7)
        puzzles = self.puzzles()
        self.assertFalse(puzzles["crossword"]["available"])
        self.assertFalse(puzzles["sudoku"]["available"])
        self.assertFalse(puzzles["target"]["available"])
        self.assertIn("archive_url", puzzles["crossword"])

    def test_no_puzzles_at_all_is_not_an_error(self):
        puzzles = self.puzzles()
        self.assertFalse(puzzles["crossword"]["available"])
        self.assertFalse(puzzles["sudoku"]["available"])
        self.assertFalse(puzzles["target"]["available"])

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

    def test_target_teaser_carries_letters_but_not_the_words(self):
        make_target()
        target = self.puzzles()["target"]
        self.assertEqual(target["title"], "Target #1")
        self.assertEqual("".join(c["char"] for c in target["cells"]), "pracltica")
        self.assertTrue(target["cells"][4]["centre"])
        self.assertNotIn("words", target)
        self.assertNotIn("practical", self.client.get(reverse("api_puzzles")).content.decode())

    def test_streetwise_teaser_carries_no_place_and_no_result(self):
        make_streetwise()
        streetwise = self.puzzles()["streetwise"]
        self.assertEqual(streetwise["title"], "Streetwise #1")
        body = self.client.get(reverse("api_puzzles")).content.decode()
        for spoiler in ["Rosmead", "Cape Town", "Western Cape", "97090421", "AbC-dEf", "-33.99", "\"DA\"", "60.0"]:
            self.assertNotIn(spoiler, body)

    def test_quiz_teaser_carries_no_questions(self):
        quiz = make_quiz(description="This week's news.")
        Question.objects.create(quiz=quiz, question="Who won?", order=1)
        teaser = self.puzzles()["quiz"]
        self.assertEqual(teaser["title"], "Test quiz")
        self.assertEqual(teaser["description"], "This week's news.")
        self.assertIn(reverse("quiz_solve", args=[quiz.pk]), teaser["url"])
        self.assertNotIn("Who won?", self.client.get(reverse("api_puzzles")).content.decode())

    def test_groupup_teaser_carries_no_words_and_no_groups(self):
        groupup = make_groupup(name="Week one")
        teaser = self.puzzles()["groupup"]
        self.assertEqual(teaser["title"], "Week one")
        self.assertIn(reverse("groupup:solve", args=[groupup.pk]), teaser["url"])
        self.assertNotIn("groups", teaser)
        body = self.client.get(reverse("api_puzzles")).content.decode()
        for spoiler in ["Rivers", "Tugela", "Constitutional", "Diaper"]:
            self.assertNotIn(spoiler, body)

    def test_unpublished_quizzes_and_groupups_are_not_announced(self):
        make_quiz(days=7)
        GroupUp.objects.create(published=timezone.now() + timezone.timedelta(days=7))
        puzzles = self.puzzles()
        self.assertFalse(puzzles["quiz"]["available"])
        self.assertFalse(puzzles["groupup"]["available"])

    def test_one_puzzle_can_be_fetched_on_its_own(self):
        make_sudoku()
        response = self.client.get(reverse("api_puzzle", args=["sudoku"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "Sudoku #1234")

    def test_a_puzzle_we_do_not_serve_is_a_404(self):
        self.assertEqual(
            self.client.get(reverse("api_puzzle", args=["chess"])).status_code, 404
        )


# As above: GameRootTest saves Targets too.
@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class GameRootTest(TestCase):
    """/crossword/, /target/ and the rest open on the newest published
    puzzle; each game's list of past puzzles is under archive/."""

    def test_each_game_opens_on_its_newest_published_puzzle(self):
        def newest(make):
            make(days=-2)
            puzzle = make(days=-1)
            make(days=1)
            return puzzle

        district = make_district()  # Streetwise's puzzles share one
        for root, puzzle, detail in [
            ("crossword_latest", newest(make_crossword), "crossword_solve"),
            ("quiz_latest", newest(lambda days: Quiz.objects.create(
                published=timezone.now() + timezone.timedelta(days=days))), "quiz_solve"),
            ("groupup:latest", newest(lambda days: GroupUp.objects.create(
                published=timezone.now() + timezone.timedelta(days=days))), "groupup:solve"),
            ("target:latest", newest(lambda days: make_target(
                days, letters=f"target{days + 5:03}")), "target:detail"),
            ("streetwise:latest", newest(lambda days: make_streetwise(
                days, district=district)), "streetwise:detail"),
        ]:
            with self.subTest(root):
                self.assertRedirects(
                    self.client.get(reverse(root)),
                    reverse(detail, args=[puzzle.pk]),
                    fetch_redirect_response=False,
                )

    def test_sudoku_opens_on_its_newest_published_puzzle(self):
        # A sudoku's givens are unique, so vary the last one.
        make_sudoku(days=-2, puzzle=PUZZLE[:-1] + "1")
        sudoku = make_sudoku(days=-1)
        make_sudoku(days=1, puzzle=PUZZLE[:-1] + "2")
        self.assertEqual(self.client.get(reverse("sudoku:latest")).context["sudoku"], sudoku)

    def test_a_game_with_nothing_published_opens_its_archive(self):
        for root, archive in [
            ("crossword_latest", "crossword_select"),
            ("quiz_latest", "quiz_select"),
            ("groupup:latest", "groupup:list"),
            ("target:latest", "target:list"),
            ("sudoku:latest", "sudoku:list"),
            ("streetwise:latest", "streetwise:list"),
        ]:
            with self.subTest(root):
                self.assertRedirects(self.client.get(reverse(root)), reverse(archive))
