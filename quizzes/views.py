import json
from datetime import datetime

from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from .models import Answer, Question, Quiz

PERM = "quizzes.can_generate_quizzes"


@permission_required(PERM)
@require_POST
def quiz_add(request):
    """Create a blank quiz (no fields to collect up front, unlike a
    crossword's grid size) and go straight to its edit screen."""
    quiz = Quiz.objects.create()
    return redirect("quiz_edit", pk=quiz.pk)


class QuizSelectView(PermissionRequiredMixin, ListView):
    """List quizzes for staff to manage. Unlike crossword's select view,
    this has no public/anonymous audience yet -- there's no quiz-taking
    page -- so the whole list is gated behind the generate permission."""

    permission_required = PERM
    model = Quiz
    template_name = "quizzes/select.html"
    context_object_name = "quizzes"
    ordering = ["-date_modified"]


@permission_required(PERM)
def quiz_edit(request, pk):
    """Render the editable quiz-builder screen for the given quiz."""
    quiz = get_object_or_404(Quiz, pk=pk)
    questions = [
        {
            "text": q.question,
            "answers": [
                {"text": a.answer, "correct": a.correct}
                for a in q.answer_set.order_by("order")
            ],
        }
        for q in quiz.question_set.order_by("order")
    ]
    return render(request, "quizzes/edit.html", {"quiz": quiz, "questions": questions})


@permission_required(PERM)
@require_POST
def quiz_save(request, pk):
    """Save the quiz for the given quiz.

    Accepts a JSON body: name, description, authors, editors, copyright,
    published, questions (a list of {text, answers: [{text, correct}]}, in
    display order). Unlike crossword_save, there's no separate `cells`
    source of truth to preserve partial progress in -- the Question/Answer
    rows themselves are the only record of a quiz's content, so every save
    simply deletes and recreates them from the posted list. This also
    sidesteps the (quiz, order) / (question, order) unique constraints,
    which reordering-in-place would otherwise transiently violate.

    A question or answer with blank (whitespace-only) text is dropped
    rather than saved, so idly clicking "Add question"/"Add answer" and
    saving without typing into it doesn't leave junk rows behind. Whether
    a question has a correct answer marked is not enforced here -- that's
    a non-blocking warning in the builder UI, not a save-time rule, so a
    setter can add a wrong answer before deciding on the right one.
    """
    quiz = get_object_or_404(Quiz, pk=pk)
    payload = json.loads(request.body)

    try:
        with transaction.atomic():
            quiz.name = payload.get("name", "")
            quiz.description = payload.get("description", "")
            quiz.authors = payload.get("authors", "")
            quiz.editors = payload.get("editors", "")
            quiz.copyright = payload.get("copyright", "")
            published_str = payload.get("published") or ""
            if published_str:
                dt = datetime.fromisoformat(published_str)
                quiz.published = dt if timezone.is_aware(dt) else timezone.make_aware(dt)
            else:
                quiz.published = None
            quiz.save()

            quiz.question_set.all().delete()

            order = 0
            for question in payload.get("questions", []):
                text = question.get("text", "").strip()
                if not text:
                    continue
                q = Question.objects.create(quiz=quiz, question=text, order=order)
                order += 1

                a_order = 0
                for answer in question.get("answers", []):
                    a_text = answer.get("text", "").strip()
                    if not a_text:
                        continue
                    Answer.objects.create(
                        question=q,
                        answer=a_text,
                        correct=bool(answer.get("correct")),
                        order=a_order,
                    )
                    a_order += 1
    except IntegrityError as e:
        return JsonResponse({"error": str(e)}, status=400)

    return JsonResponse({"status": "ok"})


@permission_required(PERM)
@require_POST
def quiz_delete(request, pk):
    """Permanently delete a quiz and return to the list.

    No server-side confirmation step -- the confirm() dialog on the
    delete button in select.html is the only guard against an accidental
    click (mirrors crossword_delete).
    """
    quiz = get_object_or_404(Quiz, pk=pk)
    quiz.delete()
    return redirect("quiz_select")
