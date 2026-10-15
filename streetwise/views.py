import json

from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from .models import CHOICES, Streetwise

ATTEMPTS = 5
# How many percentage points either side of the winner's share still
# counts as right.
TOLERANCE = 5
# One more after each miss, in this order.
HINTS = ["Province", "Municipality", "Voting station", "Runner-up"]


def _visible(request, pk):
    puzzle = get_object_or_404(Streetwise.objects.select_related("district"), pk=pk)
    if not puzzle.is_published() and not request.user.is_staff:
        raise Http404
    return puzzle


# A player's guesses are kept in their session, so a refresh can't hand
# them a fresh set, and nothing more of the answer reaches the browser
# than the guesses so far have earned.
def _guesses(request, puzzle):
    return request.session.get("streetwise", {}).get(str(puzzle.pk), [])


def _save_guesses(request, puzzle, guesses):
    played = request.session.get("streetwise", {})
    played[str(puzzle.pk)] = guesses
    request.session["streetwise"] = played


def grade(puzzle, party, percent):
    """'right', 'close' (the right party, but too far off) or 'wrong', and
    for 'close', whether the share is 'higher' or 'lower'."""
    winner, share = puzzle.district.winner()
    if party != winner:
        return "wrong", None
    if abs(percent - share) <= TOLERANCE:
        return "right", None
    return "close", "higher" if share > percent else "lower"


def hint(puzzle, n):
    district = puzzle.district
    if n == 0:
        return district.province
    if n == 1:
        return district.place()
    if n == 2:
        return district.station.title()
    results = district.results()
    return results[1][0] if len(results) > 1 else "Nobody"


def state(puzzle, guesses):
    """Everything the page shows, worked out afresh from the guesses."""
    graded = []
    for party, percent in guesses:
        result, direction = grade(puzzle, party, percent)
        graded.append(
            {"party": party, "percent": percent, "grade": result, "direction": direction}
        )
    won = any(g["grade"] == "right" for g in graded)
    finished = won or len(graded) >= ATTEMPTS
    # Once it's over, the result says all the hints do and more.
    shown = 0 if finished else min(len(graded), len(HINTS))
    data = {
        "guesses": graded,
        "attempts": ATTEMPTS,
        "won": won,
        "finished": finished,
        "hints": [{"label": HINTS[n], "text": hint(puzzle, n)} for n in range(shown)],
    }
    if finished:
        data["result"] = render_to_string(
            "streetwise/results.html", {"district": puzzle.district, "puzzle": puzzle}
        )
    return data


class StreetwiseListView(ListView):
    template_name = "streetwise/list.html"
    context_object_name = "puzzles"

    def get_queryset(self):
        if self.request.user.is_staff:
            puzzles = list(Streetwise.objects.select_related("district"))
        else:
            puzzles = list(Streetwise.objects.published())
        # Every number in one query, rather than one each.
        published = Streetwise.objects.published().order_by("published")
        numbers = {pk: n for n, pk in enumerate(published.values_list("pk", flat=True), 1)}
        for puzzle in puzzles:
            puzzle.num = numbers.get(puzzle.pk)
        return puzzles


def latest(request):
    puzzle = Streetwise.objects.published().order_by("-published").first()
    if puzzle is None:
        raise Http404
    return redirect("streetwise:detail", pk=puzzle.pk)


def detail(request, pk):
    puzzle = _visible(request, pk)
    return render(
        request,
        "streetwise/detail.html",
        {
            "puzzle": puzzle,
            "number": puzzle.number(),
            "choices": CHOICES,
            "attempts": ATTEMPTS,
            "tolerance": TOLERANCE,
            "state": state(puzzle, _guesses(request, puzzle)),
        },
    )


@require_POST
def guess(request, pk):
    puzzle = _visible(request, pk)
    try:
        data = json.loads(request.body)
        party, percent = data["party"], data["percent"]
    except (ValueError, KeyError, TypeError):
        return JsonResponse({"error": "A guess is a party and a percentage."}, status=400)
    if party not in CHOICES:
        return JsonResponse({"error": "Pick one of the parties."}, status=400)
    if not isinstance(percent, int) or isinstance(percent, bool) or not 0 <= percent <= 100:
        return JsonResponse({"error": "The percentage is a whole number, 0 to 100."}, status=400)

    guesses = _guesses(request, puzzle)
    if state(puzzle, guesses)["finished"]:
        return JsonResponse({"error": "This puzzle is finished."}, status=400)
    if [party, percent] in guesses:
        return JsonResponse({"error": "You've already tried that."}, status=400)
    guesses = guesses + [[party, percent]]
    _save_guesses(request, puzzle, guesses)
    return JsonResponse(state(puzzle, guesses))

