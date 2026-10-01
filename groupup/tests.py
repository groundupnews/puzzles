import json
from datetime import timedelta

from django.contrib.auth.models import Permission, User
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import GroupUpForm
from .models import GroupUp

GROUPS = [
    {"label": "Rivers", "words": ["Orange", "Vaal", "Breede", "Tugela"]},
    {"label": "Courts", "words": ["High", "Labour", "Equality", "Constitutional"]},
    {"label": "Backwards words", "words": ["Straw", "Drawer", "Lived", "Diaper"]},
    {"label": "Sound like letters", "words": ["Queue", "Why", "Pea", "Ewe"]},
]


def make_user_with_perm(client):
    user = User.objects.create_user(username="setter", password="testpass")
    user.user_permissions.add(Permission.objects.get(codename="can_generate_groupups"))
    client.login(username="setter", password="testpass")
    return user


def form_data(groups=GROUPS, **meta):
    data = {"copyright": "GroundUp", **meta}
    for g, group in enumerate(groups):
        data[f"label_{g}"] = group["label"]
        for w, word in enumerate(group["words"]):
            data[f"word_{g}_{w}"] = word
    return data


def published_puzzle(**kwargs):
    return GroupUp.objects.create(
        groups=GROUPS, published=timezone.now() - timedelta(days=1), **kwargs
    )


class GroupUpFormTest(TestCase):
    def test_saves_groups_in_order(self):
        form = GroupUpForm(form_data(), instance=GroupUp.objects.create())
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().groups, GROUPS)

    def test_a_word_used_twice_is_rejected_whatever_its_case(self):
        groups = [dict(g) for g in GROUPS]
        groups[3] = {"label": "Sound like letters", "words": ["Queue", "Why", "Pea", "ORANGE"]}
        form = GroupUpForm(form_data(groups), instance=GroupUp.objects.create())
        self.assertFalse(form.is_valid())

    def test_a_draft_may_be_incomplete(self):
        form = GroupUpForm(form_data(GROUPS[:1]), instance=GroupUp.objects.create())
        self.assertTrue(form.is_valid(), form.errors)
        groups = form.save().groups
        self.assertEqual(groups[1], {"label": "", "words": ["", "", "", ""]})

    def test_an_incomplete_puzzle_cannot_be_given_a_publication_date(self):
        form = GroupUpForm(
            form_data(GROUPS[:3], published="2026-01-01T09:00"),
            instance=GroupUp.objects.create(),
        )
        self.assertFalse(form.is_valid())


class GroupUpEditViewTest(TestCase):
    def test_saves_and_returns_to_the_editor(self):
        make_user_with_perm(self.client)
        puzzle = GroupUp.objects.create()
        url = reverse("groupup:edit", args=[puzzle.pk])
        response = self.client.post(url, form_data(name="GroupUp 1"))
        self.assertRedirects(response, url)
        puzzle.refresh_from_db()
        self.assertEqual(puzzle.name, "GroupUp 1")
        self.assertEqual(puzzle.groups, GROUPS)

    def test_requires_permission(self):
        puzzle = GroupUp.objects.create()
        response = self.client.post(reverse("groupup:edit", args=[puzzle.pk]), form_data())
        self.assertEqual(response.status_code, 302)
        puzzle.refresh_from_db()
        self.assertEqual(puzzle.groups, [])


class GroupUpSolveViewTest(TestCase):
    def test_page_has_the_words_but_not_the_connections(self):
        # The groups are the answers: only groupup_check gives them out.
        puzzle = published_puzzle()
        response = self.client.get(reverse("groupup:solve", args=[puzzle.pk]))
        self.assertContains(response, "Orange")
        for group in GROUPS:
            self.assertNotContains(response, group["label"])

    def test_unpublished_puzzle_is_a_404_for_visitors(self):
        puzzle = GroupUp.objects.create(groups=GROUPS)
        response = self.client.get(reverse("groupup:solve", args=[puzzle.pk]))
        self.assertEqual(response.status_code, 404)

    def test_unpublished_puzzle_can_be_previewed_by_a_setter(self):
        make_user_with_perm(self.client)
        puzzle = GroupUp.objects.create(groups=GROUPS)
        response = self.client.get(reverse("groupup:solve", args=[puzzle.pk]))
        self.assertEqual(response.status_code, 200)


class GroupUpCheckViewTest(TestCase):
    def setUp(self):
        self.puzzle = published_puzzle()

    def _check(self, words):
        return self.client.post(
            reverse("groupup:check", args=[self.puzzle.pk]),
            data=json.dumps({"words": words}),
            content_type="application/json",
        )

    def test_a_group_in_any_order_is_correct(self):
        data = self._check(["Tugela", "Orange", "Breede", "Vaal"]).json()
        self.assertEqual(data, {"correct": True, **GROUPS[0]})

    def test_three_from_one_group_is_one_away(self):
        data = self._check(["Orange", "Vaal", "Breede", "High"]).json()
        self.assertEqual(data, {"correct": False, "one_away": True})

    def test_two_and_two_is_not_one_away(self):
        data = self._check(["Orange", "Vaal", "High", "Labour"]).json()
        self.assertEqual(data, {"correct": False, "one_away": False})

    def test_a_guess_must_be_four_different_words(self):
        self.assertEqual(self._check(["Orange", "Orange", "Vaal", "Breede"]).status_code, 400)
        self.assertEqual(self._check(["Orange"]).status_code, 400)

    def test_a_malformed_body_is_a_400(self):
        response = self.client.post(
            reverse("groupup:check", args=[self.puzzle.pk]),
            data="not json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_unpublished_puzzle_is_a_404_for_visitors(self):
        self.puzzle.published = None
        self.puzzle.save()
        self.assertEqual(self._check(GROUPS[0]["words"]).status_code, 404)


class GroupUpListViewTest(TestCase):
    def test_visitors_see_only_published_puzzles(self):
        published_puzzle(name="Published one")
        GroupUp.objects.create(name="Draft one")
        response = self.client.get(reverse("groupup:list"))
        self.assertContains(response, "Published one")
        self.assertNotContains(response, "Draft one")

    def test_setters_see_drafts_too(self):
        make_user_with_perm(self.client)
        GroupUp.objects.create(name="Draft one")
        self.assertContains(self.client.get(reverse("groupup:list")), "Draft one")


class GroupUpImportViewTest(TestCase):
    def setUp(self):
        make_user_with_perm(self.client)

    def _import(self, data):
        body = data if isinstance(data, str) else json.dumps(data)
        return self.client.post(reverse("groupup:import"), data=body, content_type="application/json")

    def test_imports_a_list_of_puzzles(self):
        response = self._import([
            {"name": "One", "published": "2026-01-01T06:00:00+02:00", "groups": GROUPS},
            {"name": "Two", "groups": GROUPS},
        ])
        self.assertEqual(response.json(), {"imported": 2})
        one, two = GroupUp.objects.order_by("name")
        self.assertEqual(one.name, "One")
        self.assertEqual(one.groups, GROUPS)
        self.assertIsNotNone(one.published)
        self.assertIsNone(two.published)

    def test_a_single_puzzle_need_not_be_in_a_list(self):
        self.assertEqual(self._import({"name": "One", "groups": GROUPS}).json(), {"imported": 1})

    def test_a_missing_copyright_gets_the_usual_default(self):
        self._import({"groups": GROUPS})
        self.assertEqual(GroupUp.objects.get().copyright, GroupUp().copyright)

    def test_one_bad_puzzle_stops_the_whole_import(self):
        # All or nothing, so a corrected file can be re-imported without
        # duplicating the puzzles that were fine the first time.
        clash = [dict(g) for g in GROUPS]
        clash[3] = {"label": "Clash", "words": ["Queue", "Why", "Pea", "Orange"]}
        response = self._import([{"name": "Good", "groups": GROUPS}, {"name": "Bad", "groups": clash}])
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.json()["errors"][0].startswith("Puzzle 2: "))
        self.assertFalse(GroupUp.objects.exists())

    def test_groups_must_be_four_groups_of_four_words(self):
        response = self._import({"groups": GROUPS[:3]})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Puzzle 1", response.json()["errors"][0])

    def test_invalid_json_and_an_empty_list_are_rejected(self):
        self.assertEqual(self._import("not json").status_code, 400)
        self.assertEqual(self._import([]).status_code, 400)

    def test_the_example_file_imports(self):
        example = finders.find("groupup/example.json")
        with open(example) as f:
            self.assertEqual(self._import(f.read()).json(), {"imported": 2})

    def test_requires_permission(self):
        self.client.logout()
        self.assertEqual(self._import([{"groups": GROUPS}]).status_code, 302)
        self.assertFalse(GroupUp.objects.exists())
