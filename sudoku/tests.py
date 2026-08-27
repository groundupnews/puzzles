from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Sudoku

PUZZLE = ("530070000" "600195000" "098000060"
          "800060003" "400803001" "700020006"
          "060000280" "000419005" "000080079")
SOLUTION = ("534678912" "672195348" "198342567"
            "859761423" "426853791" "713924856"
            "961537284" "287419635" "345286179")


def make(published=True, difficulty=Sudoku.Difficulty.MEDIUM, puzzle=PUZZLE):
    return Sudoku.objects.create(
        puzzle=puzzle,
        solution=SOLUTION,
        difficulty=difficulty,
        published=timezone.now() if published else None,
    )


class PublicationTests(TestCase):
    def test_unpublished_puzzle_is_hidden(self):
        sudoku = make(published=False)
        self.assertFalse(sudoku.is_published())
        response = self.client.get(reverse("sudoku_solve", args=[sudoku.pk]))
        self.assertEqual(response.status_code, 404)

    def test_editor_can_preview_unpublished_puzzle(self):
        sudoku = make(published=False)
        user = User.objects.create_user("editor", password="x")
        user.user_permissions.add(Permission.objects.get(codename="can_generate_sudokus"))
        self.client.force_login(user)
        response = self.client.get(reverse("sudoku_solve", args=[sudoku.pk]))
        self.assertEqual(response.status_code, 200)

    def test_archive_lists_only_published_for_readers(self):
        published = make()
        make(published=False, puzzle=SOLUTION)
        response = self.client.get(reverse("sudoku_select"))
        self.assertEqual(list(response.context["sudokus"]), [published])


class LatestTests(TestCase):
    def test_latest_redirects_to_newest_puzzle(self):
        make(difficulty=Sudoku.Difficulty.EASY)
        newest = make(difficulty=Sudoku.Difficulty.HARD, puzzle=SOLUTION)
        response = self.client.get(reverse("sudoku_latest"))
        self.assertRedirects(
            response, reverse("sudoku_solve", args=[newest.pk]), fetch_redirect_response=False
        )

    def test_latest_honours_requested_difficulty(self):
        easy = make(difficulty=Sudoku.Difficulty.EASY)
        make(difficulty=Sudoku.Difficulty.HARD, puzzle=SOLUTION)
        response = self.client.get(reverse("sudoku_latest"), {"difficulty": Sudoku.Difficulty.EASY})
        self.assertRedirects(
            response, reverse("sudoku_solve", args=[easy.pk]), fetch_redirect_response=False
        )

    def test_latest_falls_back_when_difficulty_has_no_puzzles(self):
        # The hub links here unconditionally, so this must stay playable.
        only = make(difficulty=Sudoku.Difficulty.EASY)
        response = self.client.get(reverse("sudoku_latest"), {"difficulty": Sudoku.Difficulty.HARD})
        self.assertRedirects(
            response, reverse("sudoku_solve", args=[only.pk]), fetch_redirect_response=False
        )

    def test_latest_404s_when_nothing_is_published(self):
        self.assertEqual(self.client.get(reverse("sudoku_latest")).status_code, 404)


class PlayScreenTests(TestCase):
    def test_tabs_flag_the_current_and_the_empty_levels(self):
        sudoku = make(difficulty=Sudoku.Difficulty.MEDIUM)
        response = self.client.get(reverse("sudoku_solve", args=[sudoku.pk]))
        tabs = {tab["value"]: tab for tab in response.context["tabs"]}
        self.assertTrue(tabs[Sudoku.Difficulty.MEDIUM]["current"])
        self.assertTrue(tabs[Sudoku.Difficulty.MEDIUM]["available"])
        self.assertFalse(tabs[Sudoku.Difficulty.HARD]["available"])
