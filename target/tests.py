import json

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from target.models import Target


def make_target(letters="practical", words=None, published=None, **kwargs):
    if words is None:
        words = ["practical", "carat", "clap", "canal"]
    return Target.objects.create(
        letters=letters,
        words="\r\n".join(words),
        published=published,
        **kwargs,
    )


class PublishingTest(TestCase):
    """Unpublished puzzles are for editors only, as on the news site."""

    def setUp(self):
        self.published = make_target(
            published=timezone.now() - timezone.timedelta(days=1))
        self.queued = make_target(
            letters="bacterium",
            words=["bacterium", "curb", "brace"],
            published=timezone.now() + timezone.timedelta(days=7))

    def test_published_puzzle_is_public(self):
        response = self.client.get(
            reverse("target:detail", args=[self.published.pk]))
        self.assertEqual(response.status_code, 200)

    def test_queued_puzzle_is_hidden(self):
        response = self.client.get(
            reverse("target:detail", args=[self.queued.pk]))
        self.assertEqual(response.status_code, 404)

    def test_editor_may_preview_queued_puzzle(self):
        editor = User.objects.create_user("editor", password="secret")
        editor.user_permissions.add(
            Permission.objects.get(codename="change_target"))
        self.client.force_login(editor)
        response = self.client.get(
            reverse("target:detail", args=[self.queued.pk]))
        self.assertEqual(response.status_code, 200)

    def test_list_shows_only_published_to_readers(self):
        response = self.client.get(reverse("target:list"))
        self.assertEqual(list(response.context["object_list"]),
                         [self.published])

    def test_latest_redirects_to_newest_published(self):
        response = self.client.get(reverse("target:latest"))
        self.assertRedirects(
            response, reverse("target:detail", args=[self.published.pk]),
            fetch_redirect_response=False)

    def test_number_assigned_on_publication(self):
        self.assertEqual(self.published.number, 1)


class AnswersStayOffThePageTest(TestCase):

    def test_page_carries_hashes_not_words(self):
        target = make_target(published=timezone.now())
        response = self.client.get(
            reverse("target:detail", args=[target.pk]))
        body = response.content.decode()
        self.assertNotIn("canal", body)
        self.assertIn(target.hashedWords()[0], body)

    def test_solution_shown_once_it_is_public(self):
        target = make_target(published=timezone.now(), public_solution=True)
        response = self.client.get(
            reverse("target:detail", args=[target.pk]))
        self.assertContains(response, "practical")


class HintTest(TestCase):

    def setUp(self):
        self.target = make_target(published=timezone.now())
        self.url = reverse("target:hint", args=[self.target.pk])

    def post(self, found):
        return self.client.post(
            self.url, json.dumps({"found": found}),
            content_type="application/json")

    def test_hint_gives_the_shortest_missing_word(self):
        # Never the nine-letter word while easier ones are still out there.
        word = self.post([]).json()["word"]
        self.assertEqual(word, "clap")

    def test_hint_skips_words_already_found(self):
        word = self.post(["clap", "carat", "canal"]).json()["word"]
        self.assertEqual(word, "practical")

    def test_no_word_left_to_give(self):
        found = ["practical", "carat", "clap", "canal"]
        self.assertIsNone(self.post(found).json()["word"])


class EditorViewsTest(TestCase):
    """The create/update/delete views the news site uses."""

    def setUp(self):
        self.editor = User.objects.create_user("editor", password="secret")
        self.editor.user_permissions.set(Permission.objects.filter(
            codename__in=["add_target", "change_target", "delete_target"]))
        self.client.force_login(self.editor)

    def test_readers_cannot_reach_the_editor(self):
        self.client.logout()
        response = self.client.get(reverse("target:create"))
        self.assertNotEqual(response.status_code, 200)

    def test_update_rejects_a_word_without_the_centre_letter(self):
        target = make_target(published=timezone.now())
        response = self.client.post(
            reverse("target:update", args=[target.pk]),
            {"letters": "practical",
             "words": "practical\r\ncarat\r\nclap\r\ncanal\r\nbrain",
             "publish_solution_after": 24,
             "tweet_text": "Try the latest GroundUp Target.",
             "clue": "", "rules": ""})
        self.assertEqual(response.status_code, 200)
        self.assertIn("words", response.context["form"].errors)

    def test_delete_view_renders(self):
        target = make_target(published=timezone.now())
        response = self.client.get(reverse("target:delete", args=[target.pk]))
        self.assertEqual(response.status_code, 200)
