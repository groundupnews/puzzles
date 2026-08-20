import json
from datetime import timedelta

from django.contrib.auth.models import Permission, User
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

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
# QuizSelectView
# ---------------------------------------------------------------------------


class QuizSelectViewTest(TestCase):
    def test_requires_permission(self):
        response = self.client.get(reverse("quiz_select"))
        self.assertEqual(response.status_code, 302)

    def test_lists_quizzes_for_permitted_user(self):
        make_user_with_perm(self.client)
        Quiz.objects.create(name="A quiz")
        response = self.client.get(reverse("quiz_select"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A quiz")


# ---------------------------------------------------------------------------
# is_published
# ---------------------------------------------------------------------------


class QuizIsPublishedTest(TestCase):
    def test_unpublished_when_null(self):
        self.assertFalse(Quiz(published=None).is_published())

    def test_published_when_in_past(self):
        quiz = Quiz(published=timezone.now() - timedelta(days=1))
        self.assertTrue(quiz.is_published())

    def test_not_published_when_in_future(self):
        quiz = Quiz(published=timezone.now() + timedelta(days=1))
        self.assertFalse(quiz.is_published())
