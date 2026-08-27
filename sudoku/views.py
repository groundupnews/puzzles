from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView

from .models import Sudoku

PERM = "sudoku.can_generate_sudokus"


class SudokuSelectView(ListView):
    """The sudoku archive. Everyone sees published puzzles; editors also
    see the ones queued for future publication."""

    model = Sudoku
    template_name = "sudoku/select.html"
    context_object_name = "sudokus"

    def get_queryset(self):
        qs = super().get_queryset()
        if not self.request.user.has_perm(PERM):
            qs = qs.published()
        return qs


def _latest(difficulty=None):
    qs = Sudoku.objects.published()
    if difficulty:
        qs = qs.filter(difficulty=difficulty)
    return qs.order_by("-published").first()


def sudoku_latest(request):
    """Today's puzzle, at the difficulty asked for if there is one.

    The hub links here unconditionally, so an empty difficulty falls back
    to the newest puzzle at any level rather than 404ing.
    """
    difficulty = request.GET.get("difficulty")
    sudoku = _latest(difficulty) or _latest()
    if sudoku is None:
        raise Http404("No sudoku has been published yet.")
    return redirect("sudoku_solve", pk=sudoku.pk)


def sudoku_solve(request, pk):
    """Play screen. Editors can preview an unpublished puzzle; everyone
    else gets a 404 for one (mirrors crossword_solve)."""
    sudoku = get_object_or_404(Sudoku, pk=pk)
    if not sudoku.is_published() and not request.user.has_perm(PERM):
        raise Http404

    # Tabs point at the newest puzzle of each level.
    counts = {
        d: Sudoku.objects.published().filter(difficulty=d).exists()
        for d in Sudoku.TAB_DIFFICULTIES
    }
    tabs = [
        {
            "value": d,
            "label": Sudoku.Difficulty(d).label,
            "current": d == sudoku.difficulty,
            "available": counts[d],
        }
        for d in Sudoku.TAB_DIFFICULTIES
    ]
    return render(
        request,
        "sudoku/detail.html",
        {"sudoku": sudoku, "tabs": tabs},
    )
