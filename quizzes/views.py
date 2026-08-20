import json
from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.db import IntegrityError, transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from .json_import import import_quiz_from_json
from .models import Answer, Question, Quiz

PERM = "quizzes.can_generate_quizzes"


@permission_required(PERM)
@require_POST
def quiz_add(request):
    """Create a blank quiz (no fields to collect up front, unlike a
    crossword's grid size) and go straight to its edit screen."""
    quiz = Quiz.objects.create()
    return redirect("quiz_edit", pk=quiz.pk)


class QuizSelectView(ListView):
    """List quizzes.

    Generators see every quiz, so they can find drafts to keep editing.
    Everyone else sees only published ones (mirrors CrosswordSelectView;
    quizzes have no private/owner concept, so there's no extra exclusion
    beyond the published filter).
    """

    model = Quiz
    template_name = "quizzes/select.html"
    context_object_name = "quizzes"
    ordering = ["-date_modified"]

    def get_queryset(self):
        qs = super().get_queryset()
        if not self.request.user.has_perm(PERM):
            qs = qs.published()
        return qs


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


def quiz_solve(request, pk):
    """Quiz-taking view.

    Available to everyone for published quizzes; generators can preview
    unpublished ones. Non-generators get a 404 for unpublished quizzes
    (mirrors crossword_solve). The seeded JSON deliberately omits which
    answer is correct -- quiz_check is the only place that's revealed,
    and only once the visitor has actually submitted an answer.
    """
    quiz = get_object_or_404(Quiz, pk=pk)
    if not quiz.is_published() and not request.user.has_perm(PERM):
        raise Http404
    questions = [
        {
            "id": q.pk,
            "text": q.question,
            "answers": [
                {"id": a.pk, "text": a.answer}
                for a in q.answer_set.order_by("order")
            ],
        }
        for q in quiz.question_set.order_by("order")
    ]
    return render(request, "quizzes/detail.html", {"quiz": quiz, "questions": questions})


@require_POST
def quiz_check(request, pk):
    """Score the solver's submitted answers.

    Accepts JSON: answers ({"<question id>": <selected answer id>, ...},
    one entry per question the visitor answered). Returns, for every
    question in the quiz, whether the selection was correct and which
    answer id actually was correct -- unlike crossword's check/reveal
    split, a quiz has nothing left to guess once it's been submitted, so
    there's no reason to withhold the answer at that point.

    A question with no correct answer marked (the setter hasn't finished
    it yet -- see quiz_save) can never be scored as correct.
    """
    quiz = get_object_or_404(Quiz, pk=pk)
    if not quiz.is_published() and not request.user.has_perm(PERM):
        raise Http404

    payload = json.loads(request.body)
    submitted = payload.get("answers", {})

    results = []
    score = 0
    questions = list(quiz.question_set.order_by("order"))
    for q in questions:
        correct_answer = q.answer_set.filter(correct=True).first()
        selected_id = submitted.get(str(q.pk))
        is_correct = correct_answer is not None and selected_id == correct_answer.pk
        if is_correct:
            score += 1
        results.append({
            "question_id": q.pk,
            "correct": is_correct,
            "correct_answer_id": correct_answer.pk if correct_answer else None,
        })

    return JsonResponse({"results": results, "score": score, "total": len(questions)})


@permission_required(PERM)
@require_POST
def quiz_import(request):
    """Create a quiz from an uploaded JSON file (see json_import.py for
    the expected shape and its best-effort, drop-and-report approach).

    Only a totally unparseable body is rejected outright; anything
    import_quiz_from_json() dropped along the way is instead reported as
    a Django message, which renders on the edit screen this redirects to
    (base.html already has a {% if messages %} block for it).
    """
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError("root of the JSON document must be an object")
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON file"}, status=400)

    quiz, warnings = import_quiz_from_json(data)
    for warning in warnings:
        messages.warning(request, warning)

    return JsonResponse({"redirect": reverse("quiz_edit", args=[quiz.pk])})


@permission_required(PERM)
def quiz_export(request, pk):
    """Return the quiz as a downloadable JSON file, in exactly the shape
    quiz_import/import_quiz_from_json expect -- so an exported file can be
    re-imported unchanged. Unlike crossword_xd's export (deliberately open
    to everyone), this is gated behind the generate permission: the export
    format includes which answer is correct for every question, the one
    thing quiz_solve/quiz_check are careful never to hand a solver up
    front.
    """
    quiz = get_object_or_404(Quiz, pk=pk)
    data = {
        "name": quiz.name,
        "authors": quiz.authors,
        "editors": quiz.editors,
        "copyright": quiz.copyright,
        "description": quiz.description,
        "published": quiz.published.isoformat() if quiz.published else None,
        "questions": [
            [
                q.question,
                [[a.answer, a.correct] for a in q.answer_set.order_by("order")],
            ]
            for q in quiz.question_set.order_by("order")
        ],
    }
    filename = (quiz.name or "quiz").replace('"', "")
    response = JsonResponse(data, json_dumps_params={"indent": 2})
    response["Content-Disposition"] = f'attachment; filename="{filename}.json"'
    return response
