import hashlib

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import generator
from .models import Target

# "kaseflorw": centre k, with falsework as the nine-letter answer.
LETTERS = "kaseflorw"
WORDS = "falsework\nforks\nkales\nwalks"


def make(published=True, letters=LETTERS, words=WORDS):
    return Target.objects.create(
        letters=letters,
        words=words,
        published=timezone.now() if published else None,
    )


class ModelTests(TestCase):
    def test_word_list_ignores_blank_lines(self):
        target = make(words="falsework\n\n  forks  \n")
        self.assertEqual(target.word_list(), ["falsework", "forks"])

    def test_hashed_words_hides_the_answers(self):
        target = make()
        hashes = target.hashed_words()
        self.assertEqual(len(hashes), 4)
        self.assertIn(hashlib.sha256(b"forks").hexdigest(), hashes)
        self.assertNotIn("forks", hashes)

    def test_nine_letter_word_and_centre(self):
        target = make()
        self.assertEqual(target.nine_letter_word(), "falsework")
        self.assertEqual(target.centre(), "k")

    def test_number_is_assigned_on_first_publication(self):
        first = make()
        second = make(letters="tuvwxyzab")
        self.assertEqual(first.number, 1)
        self.assertEqual(second.number, 2)

    def test_unpublished_puzzle_is_not_numbered(self):
        self.assertIsNone(make(published=False).number)


class PublicationTests(TestCase):
    def test_unpublished_puzzle_is_hidden(self):
        target = make(published=False)
        response = self.client.get(reverse("target_solve", args=[target.pk]))
        self.assertEqual(response.status_code, 404)

    def test_editor_can_preview_unpublished_puzzle(self):
        target = make(published=False)
        user = User.objects.create_user("editor", password="x")
        user.user_permissions.add(Permission.objects.get(codename="can_generate_targets"))
        self.client.force_login(user)
        response = self.client.get(reverse("target_solve", args=[target.pk]))
        self.assertEqual(response.status_code, 200)

    def test_play_screen_ships_hashes_not_words(self):
        target = make()
        response = self.client.get(reverse("target_solve", args=[target.pk]))
        body = response.content.decode()
        self.assertIn(hashlib.sha256(b"falsework").hexdigest(), body)
        self.assertNotIn("forks", body)

    def test_scoring_thresholds(self):
        target = make()  # four answers
        response = self.client.get(reverse("target_solve", args=[target.pk]))
        self.assertEqual(response.context["total"], 4)
        self.assertEqual(response.context["good"], 3)  # 75%
        self.assertEqual(response.context["very_good"], 4)  # 90%, rounded


class GeneratorTests(TestCase):
    def test_solve_finds_only_words_the_grid_can_spell(self):
        words = ["falsework", "forks", "flare", "oak", "kale"]
        found = generator.solve(LETTERS, words)
        self.assertIn("falsework", found)
        self.assertIn("forks", found)
        self.assertNotIn("flare", found)  # no centre letter
        self.assertNotIn("oak", found)  # the caller's list is already filtered
        self.assertIn("kale", found)

    def test_solve_respects_letter_counts(self):
        # One "s" in the grid, so a word needing two can't be made.
        self.assertEqual(generator.solve("kseabcdfg", ["kiss", "kabs"]), ["kabs"])

    def test_inflected_forms_are_excluded(self):
        # The rules shipped with each puzzle promise none of these.
        stems = {"fork", "ark", "dry", "cook", "clas"}
        for word in ["forks", "arks", "dries", "cooks"]:
            self.assertTrue(generator._is_inflected(word, stems), word)

    def test_words_merely_ending_in_s_are_kept(self):
        stems = {"fork", "ark", "dry"}
        for word in ["class", "bliss", "chaos", "octopus"]:
            self.assertFalse(generator._is_inflected(word, stems), word)

    def test_hint_names_the_shortest_missing_word(self):
        target = make()  # falsework, forks, kales, walks
        url = reverse("target_hint", args=[target.pk])
        response = self.client.post(
            url, {"found": ["forks"]}, content_type="application/json"
        )
        # Shortest first, so a hint never spends the nine-letter word early.
        self.assertEqual(response.json()["word"], "kales")

    def test_hint_returns_nothing_once_everything_is_found(self):
        target = make()
        response = self.client.post(
            reverse("target_hint", args=[target.pk]),
            {"found": target.word_list()},
            content_type="application/json",
        )
        self.assertIsNone(response.json()["word"])

    def test_hint_404s_for_an_unpublished_puzzle(self):
        target = make(published=False)
        response = self.client.post(
            reverse("target_hint", args=[target.pk]), {}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 404)

    def test_hash_word_matches_sha256(self):
        self.assertEqual(
            generator.hash_word("falsework"), hashlib.sha256(b"falsework").hexdigest()
        )
