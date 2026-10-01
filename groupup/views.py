import json
import random

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.db import transaction
from django.db.models import F
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from .forms import GroupUpForm
from .models import WORDS, GroupUp

PERM = "groupup.can_generate_groupups"

SCORING = {
    "start": 1000,
    "mistake": 100,
    "grace_seconds": 15,
    "bonus_seconds": 45,
    "bonus_per_second": 10,
}
SCORING["bonus_max"] = (
    SCORING["bonus_seconds"] - SCORING["grace_seconds"]
) * SCORING["bonus_per_second"]


def _visible(request, pk):
    puzzle = get_object_or_404(GroupUp, pk=pk)
    if not puzzle.is_published() and not request.user.has_perm(PERM):
        raise Http404
    return puzzle


class GroupUpListView(ListView):
    model = GroupUp
    template_name = "groupup/list.html"
    context_object_name = "puzzles"
    ordering = [F("published").desc(nulls_first=True), "-date_modified"]

    def get_queryset(self):
        qs = super().get_queryset()
        if not self.request.user.has_perm(PERM):
            qs = qs.published()
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["latest"] = GroupUp.objects.published().order_by("-published").first()
        return context


@permission_required(PERM)
@require_POST
def groupup_add(request):
    puzzle = GroupUp.objects.create()
    return redirect("groupup:edit", pk=puzzle.pk)


@permission_required(PERM)
def groupup_edit(request, pk):
    puzzle = get_object_or_404(GroupUp, pk=pk)
    form = GroupUpForm(request.POST or None, instance=puzzle)
    if form.is_valid():
        form.save()
        messages.success(request, "Saved.")
        return redirect("groupup:edit", pk=puzzle.pk)
    return render(request, "groupup/edit.html", {"form": form, "puzzle": puzzle})


@permission_required(PERM)
@require_POST
def groupup_delete(request, pk):
    get_object_or_404(GroupUp, pk=pk).delete()
    return redirect("groupup:list")


@permission_required(PERM)
@require_POST
def groupup_import(request):
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"errors": ["The file isn't valid JSON."]}, status=400)

    puzzles = data if isinstance(data, list) else [data]
    if not puzzles:
        return JsonResponse({"errors": ["The file has no puzzles in it."]}, status=400)

    forms, errors = [], []
    for n, puzzle in enumerate(puzzles, start=1):
        try:
            form = GroupUpForm.from_json(puzzle)
        except ValueError as error:
            errors.append(f"Puzzle {n} {error}")
            continue
        if form.is_valid():
            forms.append(form)
        else:
            errors += [f"Puzzle {n}: {message}" for message in form.error_list()]
    if errors:
        return JsonResponse({"errors": errors}, status=400)

    with transaction.atomic():
        for form in forms:
            form.save()
    messages.success(request, f"Imported {len(forms)} puzzle{'' if len(forms) == 1 else 's'}.")
    return JsonResponse({"imported": len(forms)})


def groupup_solve(request, pk):
    puzzle = _visible(request, pk)
    words = puzzle.words()
    random.shuffle(words)
    return render(
        request,
        "groupup/detail.html",
        {"puzzle": puzzle, "words": words, "scoring": SCORING},
    )


@require_POST
def groupup_check(request, pk):
    puzzle = _visible(request, pk)
    try:
        guess = set(json.loads(request.body)["words"])
    except (ValueError, KeyError, TypeError):
        guess = set()
    if len(guess) != WORDS:
        return JsonResponse({"error": f"A guess is {WORDS} different words."}, status=400)

    closest = 0
    for group in puzzle.groups:
        shared = len(guess & set(group["words"]))
        if shared == WORDS:
            return JsonResponse({"correct": True, "label": group["label"], "words": group["words"]})
        closest = max(closest, shared)
    return JsonResponse({"correct": False, "one_away": closest == WORDS - 1})
