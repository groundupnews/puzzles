import json
from datetime import timedelta

from django.contrib.auth.models import Permission, User
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .json_import import import_quiz_from_json
from .models import Answer, Question, Quiz


def make_user_with_perm(client, username="testuser"):
    """Create a user with can_generate_quizzes permission and log them in."""
    user = User.objects.create_user(username=username, password="testpass")
    perm = Permission.objects.get(codename="can_generate_quizzes")
    user.user_permissions.add(perm)
    client.login(username=username, password="testpass")
    return user


# ---------------------------------------------------------------------------
# Model constraints
# ---------------------------------------------------------------------------


class AnswerConstraintTest(TestCase):
    """Tests for Answer's one_correct_answer_per_question constraint: the DB
    enforces "at most one" (the "at least one" half is a non-blocking UI
    warning instead, not a constraint -- see quizzes_app_design memory)."""

    def setUp(self):
        quiz = Quiz.objects.create(name="Q")
        self.question = Question.objects.create(quiz=quiz, question="2+2?", order=0)

    def test_single_correct_answer_allowed(self):
        Answer.objects.create(question=self.question, answer="4", correct=True, order=0)
        Answer.objects.create(question=self.question, answer="5", correct=False, order=1)
        self.assertEqual(Answer.objects.filter(question=self.question, correct=True).count(), 1)

    def test_two_correct_answers_rejected(self):
        Answer.objects.create(question=self.question, answer="4", correct=True, order=0)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Answer.objects.create(question=self.question, answer="5", correct=True, order=1)


# ---------------------------------------------------------------------------
# quiz_add
# ---------------------------------------------------------------------------


class QuizAddViewTest(TestCase):
    def setUp(self):
        make_user_with_perm(self.client)

    def test_post_creates_blank_quiz_and_redirects_to_edit(self):
        response = self.client.post(reverse("quiz_add"))
        quiz = Quiz.objects.get()
        self.assertRedirects(response, reverse("quiz_edit", args=[quiz.pk]))
        self.assertEqual(quiz.name, "")
        self.assertFalse(Question.objects.exists())

    def test_get_not_allowed(self):
        response = self.client.get(reverse("quiz_add"))
        self.assertEqual(response.status_code, 405)


# ---------------------------------------------------------------------------
# quiz_edit
# ---------------------------------------------------------------------------


class QuizEditViewTest(TestCase):
    def setUp(self):
        make_user_with_perm(self.client)

    def test_seeds_questions_and_answers_in_order(self):
        quiz = Quiz.objects.create(name="Capitals")
        q1 = Question.objects.create(quiz=quiz, question="Capital of France?", order=0)
        Answer.objects.create(question=q1, answer="Paris", correct=True, order=0)
        Answer.objects.create(question=q1, answer="Lyon", correct=False, order=1)

        response = self.client.get(reverse("quiz_edit", args=[quiz.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Paris")

    def test_requires_permission(self):
        self.client.logout()
        quiz = Quiz.objects.create()
        response = self.client.get(reverse("quiz_edit", args=[quiz.pk]))
        self.assertEqual(response.status_code, 302)


# ---------------------------------------------------------------------------
# quiz_save
# ---------------------------------------------------------------------------


class QuizSaveViewTest(TestCase):
    def setUp(self):
        make_user_with_perm(self.client)
        self.quiz = Quiz.objects.create()

    def _save(self, payload):
        return self.client.post(
            reverse("quiz_save", args=[self.quiz.pk]),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_creates_questions_and_answers_in_order(self):
        response = self._save(
            {
                "name": "Capitals",
                "questions": [
                    {
                        "text": "Capital of France?",
                        "answers": [
                            {"text": "Paris", "correct": True},
                            {"text": "Lyon", "correct": False},
                        ],
                    },
                    {
                        "text": "Capital of Japan?",
                        "answers": [
                            {"text": "Osaka", "correct": False},
                            {"text": "Tokyo", "correct": True},
                        ],
                    },
                ],
            }
        )
        self.assertEqual(response.status_code, 200)
        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.name, "Capitals")

        questions = list(Question.objects.filter(quiz=self.quiz).order_by("order"))
        self.assertEqual([q.question for q in questions], ["Capital of France?", "Capital of Japan?"])
        self.assertEqual([q.order for q in questions], [0, 1])

        france_answers = list(questions[0].answer_set.order_by("order"))
        self.assertEqual([a.answer for a in france_answers], ["Paris", "Lyon"])
        self.assertTrue(france_answers[0].correct)
        self.assertFalse(france_answers[1].correct)

    def test_resave_replaces_old_questions(self):
        self._save({"questions": [{"text": "First?", "answers": []}]})
        self.assertEqual(Question.objects.filter(quiz=self.quiz).count(), 1)

        self._save({"questions": [{"text": "Second?", "answers": []}]})
        questions = Question.objects.filter(quiz=self.quiz)
        self.assertEqual(questions.count(), 1)
        self.assertEqual(questions.get().question, "Second?")

    def test_blank_question_dropped(self):
        self._save({"questions": [{"text": "  ", "answers": []}]})
        self.assertFalse(Question.objects.filter(quiz=self.quiz).exists())

    def test_blank_answer_dropped(self):
        self._save(
            {
                "questions": [
                    {"text": "Real question?", "answers": [{"text": "  ", "correct": False}]}
                ]
            }
        )
        question = Question.objects.get(quiz=self.quiz)
        self.assertFalse(question.answer_set.exists())

    def test_question_with_no_correct_answer_is_still_saved(self):
        # Enforcement of "exactly one correct answer" is a UI warning, not a
        # save-time rule -- a setter can add a wrong answer before deciding
        # on the right one.
        self._save(
            {
                "questions": [
                    {"text": "Undecided?", "answers": [{"text": "Maybe", "correct": False}]}
                ]
            }
        )
        question = Question.objects.get(quiz=self.quiz)
        self.assertEqual(question.answer_set.count(), 1)
        self.assertFalse(question.answer_set.get().correct)

    def test_duplicate_question_text_returns_400(self):
        response = self._save(
            {
                "questions": [
                    {"text": "Same?", "answers": []},
                    {"text": "Same?", "answers": []},
                ]
            }
        )
        self.assertEqual(response.status_code, 400)

    def test_sets_published(self):
        response = self._save(
            {"questions": [], "published": "2026-01-01T00:00:00+00:00"}
        )
        self.assertEqual(response.status_code, 200)
        self.quiz.refresh_from_db()
        self.assertIsNotNone(self.quiz.published)

    def test_clears_published(self):
        self.quiz.published = timezone.now()
        self.quiz.save()
        self._save({"questions": [], "published": None})
        self.quiz.refresh_from_db()
        self.assertIsNone(self.quiz.published)

    def test_requires_permission(self):
        self.client.logout()
        response = self._save({"questions": []})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Question.objects.filter(quiz=self.quiz).exists())


# ---------------------------------------------------------------------------
# quiz_delete
# ---------------------------------------------------------------------------


class QuizDeleteViewTest(TestCase):
    def setUp(self):
        make_user_with_perm(self.client)

    def test_deletes_and_redirects(self):
        quiz = Quiz.objects.create()
        response = self.client.post(reverse("quiz_delete", args=[quiz.pk]))
        self.assertRedirects(response, reverse("quiz_select"))
        self.assertFalse(Quiz.objects.filter(pk=quiz.pk).exists())

    def test_requires_permission(self):
        self.client.logout()
        quiz = Quiz.objects.create()
        response = self.client.post(reverse("quiz_delete", args=[quiz.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Quiz.objects.filter(pk=quiz.pk).exists())


# ---------------------------------------------------------------------------
# import_quiz_from_json
# ---------------------------------------------------------------------------


class ImportQuizFromJsonTest(TestCase):
    def test_imports_metadata_and_questions(self):
        quiz, warnings = import_quiz_from_json({
            "name": "Geo",
            "authors": "Jane",
            "published": "2026-01-01T00:00:00+00:00",
            "questions": [
                ["Capital of France?", [["Paris", True], ["Lyon", False]]],
                ["2 + 2?", [["3", False], ["4", True]]],
            ],
        })
        self.assertEqual(warnings, [])
        self.assertEqual(quiz.name, "Geo")
        self.assertEqual(quiz.authors, "Jane")
        self.assertIsNotNone(quiz.published)
        questions = list(quiz.question_set.order_by("order"))
        self.assertEqual([q.question for q in questions], ["Capital of France?", "2 + 2?"])
        paris = questions[0].answer_set.get(answer="Paris")
        self.assertTrue(paris.correct)

    def test_missing_optional_fields_default_to_blank(self):
        quiz, warnings = import_quiz_from_json({"questions": []})
        self.assertEqual(warnings, [])
        self.assertEqual(quiz.name, "")
        self.assertEqual(quiz.authors, "")
        self.assertEqual(quiz.editors, "")
        self.assertEqual(quiz.copyright, "")
        self.assertEqual(quiz.description, "")
        self.assertIsNone(quiz.published)

    def test_missing_questions_key_imports_empty_quiz_with_no_warning(self):
        quiz, warnings = import_quiz_from_json({"name": "Empty"})
        self.assertEqual(warnings, [])
        self.assertFalse(quiz.question_set.exists())

    def test_malformed_question_entry_dropped_and_warned(self):
        quiz, warnings = import_quiz_from_json({"questions": ["not a tuple", ["Real?", [["Yes", True]]]]})
        self.assertEqual(quiz.question_set.count(), 1)
        self.assertEqual(quiz.question_set.get().question, "Real?")
        self.assertTrue(any("malformed" in w for w in warnings))

    def test_blank_question_text_dropped_and_warned(self):
        quiz, warnings = import_quiz_from_json({"questions": [["  ", [["A", True]]]]})
        self.assertFalse(quiz.question_set.exists())
        self.assertTrue(any("blank text" in w for w in warnings))

    def test_duplicate_question_text_dropped_and_warned(self):
        quiz, warnings = import_quiz_from_json({
            "questions": [
                ["Same?", [["A", True]]],
                ["Same?", [["B", True]]],
            ]
        })
        self.assertEqual(quiz.question_set.count(), 1)
        self.assertTrue(any("duplicate question text" in w for w in warnings))

    def test_malformed_answer_entry_dropped_and_warned(self):
        quiz, warnings = import_quiz_from_json({
            "questions": [["Q?", ["not a tuple", ["Good", True]]]]
        })
        question = quiz.question_set.get()
        self.assertEqual(question.answer_set.count(), 1)
        self.assertTrue(any("malformed" in w for w in warnings))

    def test_blank_answer_text_dropped_and_warned(self):
        quiz, warnings = import_quiz_from_json({"questions": [["Q?", [["  ", True], ["Good", False]]]]})
        question = quiz.question_set.get()
        self.assertEqual(question.answer_set.count(), 1)
        self.assertTrue(any("blank text" in w for w in warnings))

    def test_duplicate_answer_text_dropped_and_warned(self):
        quiz, warnings = import_quiz_from_json({
            "questions": [["Q?", [["Same", True], ["Same", False]]]]
        })
        question = quiz.question_set.get()
        self.assertEqual(question.answer_set.count(), 1)
        self.assertTrue(any("duplicate answer" in w for w in warnings))

    def test_second_correct_answer_downgraded_and_warned(self):
        quiz, warnings = import_quiz_from_json({
            "questions": [["Q?", [["First", True], ["Second", True]]]]
        })
        question = quiz.question_set.get()
        self.assertEqual(question.answer_set.filter(correct=True).count(), 1)
        self.assertTrue(question.answer_set.get(answer="First").correct)
        self.assertFalse(question.answer_set.get(answer="Second").correct)
        self.assertTrue(any("more than one answer marked correct" in w for w in warnings))

    def test_no_correct_answer_warned_but_kept(self):
        quiz, warnings = import_quiz_from_json({"questions": [["Q?", [["A", False], ["B", False]]]]})
        question = quiz.question_set.get()
        self.assertEqual(question.answer_set.count(), 2)
        self.assertTrue(any("no correct answer marked" in w for w in warnings))

    def test_non_list_questions_field_warned_and_ignored(self):
        quiz, warnings = import_quiz_from_json({"questions": "not a list"})
        self.assertFalse(quiz.question_set.exists())
        self.assertTrue(any("not a list" in w for w in warnings))


# ---------------------------------------------------------------------------
# quiz_import
# ---------------------------------------------------------------------------


class QuizImportViewTest(TestCase):
    def setUp(self):
        make_user_with_perm(self.client)

    def _import(self, data):
        return self.client.post(
            reverse("quiz_import"),
            data=json.dumps(data),
            content_type="application/json",
        )

    def test_creates_quiz_and_redirects_to_edit(self):
        response = self._import({
            "name": "Geo",
            "questions": [["Capital of France?", [["Paris", True]]]],
        })
        self.assertEqual(response.status_code, 200)
        quiz = Quiz.objects.get()
        self.assertEqual(response.json()["redirect"], reverse("quiz_edit", args=[quiz.pk]))
        self.assertEqual(quiz.name, "Geo")

    def test_warnings_surfaced_as_messages_on_next_page(self):
        response = self._import({"questions": [["Q?", [["A", False]]]]})
        redirect_url = response.json()["redirect"]
        page = self.client.get(redirect_url)
        messages = [str(m) for m in page.context["messages"]]
        self.assertTrue(any("no correct answer marked" in m for m in messages))

    def test_invalid_json_returns_400(self):
        response = self.client.post(
            reverse("quiz_import"), data="not json", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Quiz.objects.exists())

    def test_non_object_json_returns_400(self):
        response = self._import(["not", "an", "object"])
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Quiz.objects.exists())

    def test_requires_permission(self):
        self.client.logout()
        response = self._import({"questions": []})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Quiz.objects.exists())


# ---------------------------------------------------------------------------
# quiz_export
# ---------------------------------------------------------------------------


class QuizExportViewTest(TestCase):
    def setUp(self):
        make_user_with_perm(self.client)
        self.quiz = Quiz.objects.create(name="Geo Quiz", authors="Jane")
        q = Question.objects.create(quiz=self.quiz, question="Capital of France?", order=0)
        Answer.objects.create(question=q, answer="Paris", correct=True, order=0)
        Answer.objects.create(question=q, answer="Lyon", correct=False, order=1)

    def test_returns_json_matching_import_shape(self):
        response = self.client.get(reverse("quiz_export", args=[self.quiz.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        data = response.json()
        self.assertEqual(data["name"], "Geo Quiz")
        self.assertEqual(data["authors"], "Jane")
        self.assertIsNone(data["published"])
        self.assertEqual(
            data["questions"],
            [["Capital of France?", [["Paris", True], ["Lyon", False]]]],
        )

    def test_content_disposition_is_attachment_with_json_filename(self):
        response = self.client.get(reverse("quiz_export", args=[self.quiz.pk]))
        cd = response["Content-Disposition"]
        self.assertIn("attachment", cd)
        self.assertIn("Geo Quiz.json", cd)

    def test_requires_permission(self):
        self.client.logout()
        response = self.client.get(reverse("quiz_export", args=[self.quiz.pk]))
        self.assertEqual(response.status_code, 302)

    def test_export_then_import_round_trips(self):
        exported = self.client.get(reverse("quiz_export", args=[self.quiz.pk])).json()
        quiz, warnings = import_quiz_from_json(exported)
        self.assertEqual(warnings, [])
        self.assertEqual(quiz.name, self.quiz.name)
        self.assertEqual(
            [(q.question, [(a.answer, a.correct) for a in q.answer_set.order_by("order")])
             for q in quiz.question_set.order_by("order")],
            [(q.question, [(a.answer, a.correct) for a in q.answer_set.order_by("order")])
             for q in self.quiz.question_set.order_by("order")],
        )


# ---------------------------------------------------------------------------
# QuizSelectView
# ---------------------------------------------------------------------------


class QuizSelectViewTest(TestCase):
    """Mirrors CrosswordSelectViewTest's dual-audience rule: anonymous
    visitors see only published quizzes; generators see everything."""

    def test_anonymous_sees_only_published_quizzes(self):
        Quiz.objects.create(name="Published", published=timezone.now() - timedelta(days=1))
        Quiz.objects.create(name="Draft", published=None)
        response = self.client.get(reverse("quiz_select"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Published")
        self.assertNotContains(response, "Draft")

    def test_permitted_user_sees_unpublished_quizzes_too(self):
        make_user_with_perm(self.client)
        Quiz.objects.create(name="A quiz")
        response = self.client.get(reverse("quiz_select"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A quiz")


# ---------------------------------------------------------------------------
# is_published
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# quiz_solve
# ---------------------------------------------------------------------------


class QuizSolveViewTest(TestCase):
    def _make_quiz(self, **kwargs):
        quiz = Quiz.objects.create(**kwargs)
        q = Question.objects.create(quiz=quiz, question="Capital of France?", order=0)
        Answer.objects.create(question=q, answer="Paris", correct=True, order=0)
        Answer.objects.create(question=q, answer="Lyon", correct=False, order=1)
        return quiz

    def test_published_quiz_visible_to_anonymous(self):
        quiz = self._make_quiz(published=timezone.now() - timedelta(days=1))
        response = self.client.get(reverse("quiz_solve", args=[quiz.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Paris")

    def test_unpublished_quiz_404s_for_anonymous(self):
        quiz = self._make_quiz(published=None)
        response = self.client.get(reverse("quiz_solve", args=[quiz.pk]))
        self.assertEqual(response.status_code, 404)

    def test_unpublished_quiz_visible_to_permitted_user(self):
        make_user_with_perm(self.client)
        quiz = self._make_quiz(published=None)
        response = self.client.get(reverse("quiz_solve", args=[quiz.pk]))
        self.assertEqual(response.status_code, 200)

    def test_seeded_json_omits_which_answer_is_correct(self):
        # The whole point of quiz_check existing separately: the initial
        # page load must not let a visitor read the answer key out of the
        # page source before attempting the quiz.
        quiz = self._make_quiz(published=timezone.now() - timedelta(days=1))
        response = self.client.get(reverse("quiz_solve", args=[quiz.pk]))
        self.assertNotContains(response, "correct")


# ---------------------------------------------------------------------------
# quiz_check
# ---------------------------------------------------------------------------


class QuizCheckViewTest(TestCase):
    def setUp(self):
        self.quiz = Quiz.objects.create(published=timezone.now() - timedelta(days=1))
        self.q1 = Question.objects.create(quiz=self.quiz, question="Capital of France?", order=0)
        self.paris = Answer.objects.create(question=self.q1, answer="Paris", correct=True, order=0)
        self.lyon = Answer.objects.create(question=self.q1, answer="Lyon", correct=False, order=1)
        self.q2 = Question.objects.create(quiz=self.quiz, question="Capital of Japan?", order=1)
        self.tokyo = Answer.objects.create(question=self.q2, answer="Tokyo", correct=True, order=0)

    def _check(self, answers):
        return self.client.post(
            reverse("quiz_check", args=[self.quiz.pk]),
            data=json.dumps({"answers": answers}),
            content_type="application/json",
        )

    def test_scores_correct_and_wrong_answers(self):
        response = self._check({str(self.q1.pk): self.paris.pk, str(self.q2.pk): self.tokyo.pk})
        data = response.json()
        self.assertEqual(data["score"], 2)
        self.assertEqual(data["total"], 2)
        self.assertTrue(all(r["correct"] for r in data["results"]))

    def test_wrong_answer_scored_as_incorrect_and_reveals_correct_id(self):
        response = self._check({str(self.q1.pk): self.lyon.pk, str(self.q2.pk): self.tokyo.pk})
        data = response.json()
        self.assertEqual(data["score"], 1)
        q1_result = next(r for r in data["results"] if r["question_id"] == self.q1.pk)
        self.assertFalse(q1_result["correct"])
        self.assertEqual(q1_result["correct_answer_id"], self.paris.pk)

    def test_unanswered_question_scored_as_incorrect(self):
        response = self._check({str(self.q1.pk): self.paris.pk})
        data = response.json()
        self.assertEqual(data["score"], 1)
        self.assertEqual(data["total"], 2)

    def test_question_with_no_correct_answer_never_scores(self):
        q3 = Question.objects.create(quiz=self.quiz, question="Undecided?", order=2)
        maybe = Answer.objects.create(question=q3, answer="Maybe", correct=False, order=0)
        response = self._check({str(q3.pk): maybe.pk})
        result = next(r["correct"] for r in response.json()["results"] if r["question_id"] == q3.pk)
        self.assertFalse(result)

    def test_unpublished_quiz_404s_for_anonymous(self):
        self.quiz.published = None
        self.quiz.save()
        response = self._check({})
        self.assertEqual(response.status_code, 404)


class QuizIsPublishedTest(TestCase):
    def test_unpublished_when_null(self):
        self.assertFalse(Quiz(published=None).is_published())

    def test_published_when_in_past(self):
        quiz = Quiz(published=timezone.now() - timedelta(days=1))
        self.assertTrue(quiz.is_published())

    def test_not_published_when_in_future(self):
        quiz = Quiz(published=timezone.now() + timedelta(days=1))
        self.assertFalse(quiz.is_published())
