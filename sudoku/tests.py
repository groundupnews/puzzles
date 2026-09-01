from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from sudoku.models import Sudoku

PUZZLE = "0" * 81
SOLVED = "1" * 81


def make_sudoku(puzzle, difficulty=Sudoku.Difficulty.MEDIUM, days=0):
    return Sudoku.objects.create(
        puzzle=puzzle,
        solution=SOLVED,
        difficulty=difficulty,
        published=timezone.now() + timezone.timedelta(days=days),
    )


class PublishingTest(TestCase):
    """Unpublished puzzles are for staff only, as on the news site."""

    def setUp(self):
        self.published = make_sudoku("1" + "0" * 80, days=-1)
        self.queued = make_sudoku("2" + "0" * 80, days=7)

    def test_published_puzzle_is_public(self):
        response = self.client.get(
            reverse("sudoku:detail", args=[self.published.pk]))
        self.assertEqual(response.status_code, 200)

    def test_queued_puzzle_is_hidden(self):
        response = self.client.get(
            reverse("sudoku:detail", args=[self.queued.pk]))
        self.assertEqual(response.status_code, 404)

    def test_staff_may_preview_queued_puzzle(self):
        self.client.force_login(
            User.objects.create_user("editor", password="secret", is_staff=True))
        response = self.client.get(
            reverse("sudoku:detail", args=[self.queued.pk]))
        self.assertEqual(response.status_code, 200)

    def test_latest_shows_newest_published(self):
        response = self.client.get(reverse("sudoku:latest"))
        self.assertEqual(response.context["object"], self.published)

    def test_list_shows_only_published_to_readers(self):
        response = self.client.get(reverse("sudoku:list"))
        self.assertEqual(list(response.context["object_list"]),
                         [self.published])


class NavTest(TestCase):
    """Prev/next walk the archive, optionally within one difficulty."""

    def setUp(self):
        self.easy_old = make_sudoku("1" + "0" * 80,
                                    Sudoku.Difficulty.EASY, days=-30)
        self.hard_mid = make_sudoku("2" + "0" * 80,
                                    Sudoku.Difficulty.HARD, days=-20)
        self.easy_new = make_sudoku("3" + "0" * 80,
                                    Sudoku.Difficulty.EASY, days=-10)

    def nav(self, puzzle, direction, difficulty):
        return self.client.get(
            reverse("sudoku:nav", args=[puzzle.pk]),
            {"nav": direction, "diff": difficulty})

    def test_previous_at_any_level(self):
        response = self.nav(self.easy_new, "prev", "0")
        self.assertRedirects(
            response,
            reverse("sudoku:detail", args=[self.hard_mid.pk]) + "?diff=0",
            fetch_redirect_response=False)

    def test_previous_within_a_difficulty_skips_other_levels(self):
        response = self.nav(self.easy_new, "prev", Sudoku.Difficulty.EASY)
        self.assertRedirects(
            response,
            reverse("sudoku:detail", args=[self.easy_old.pk]) + "?diff=2",
            fetch_redirect_response=False)

    def test_no_neighbour_stays_put(self):
        response = self.nav(self.easy_old, "prev", "0")
        self.assertRedirects(
            response,
            reverse("sudoku:detail", args=[self.easy_old.pk]) + "?diff=0",
            fetch_redirect_response=False)
