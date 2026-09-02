"""Read-only JSON API describing the latest puzzle of each kind."""

from django.http import Http404, JsonResponse
from django.urls import reverse
from django.utils import timezone

from crossword.models import Crossword
from puzzles.teasers import grid_preview, sudoku_tile
from sudoku.models import Sudoku


def _crossword(request):
    """The newest published crossword: its grid shape and clue numbers."""
    crossword = Crossword.objects.published().order_by("-published").first()
    archive = request.build_absolute_uri(reverse("crossword_select"))
    if crossword is None:
        return {"available": False, "archive_url": archive}
    return {
        "available": True,
        "url": request.build_absolute_uri(
            reverse("crossword_solve", args=[crossword.pk])
        ),
        "archive_url": archive,
        "title": crossword.name or "Today's crossword",
        "short_description": crossword.short_description,
        "description": crossword.description,
        "published": crossword.published.isoformat(),
        "num_rows": crossword.num_rows,
        "num_cols": crossword.num_cols,
        # Row-major rows of {"block": bool, "number": int|null}. Cell
        # letters are not included :P
        "grid": grid_preview(crossword),
    }


def _sudoku(request):
    """The newest published sudoku: its givens, with blanks for the rest.

    `solution` is a field on the model and is deliberately not served.
    """
    sudoku = Sudoku.objects.published().order_by("-published").first()
    archive = request.build_absolute_uri(reverse("sudoku:list"))
    if sudoku is None:
        return {"available": False, "archive_url": archive}
    return {
        "available": True,
        "url": request.build_absolute_uri(
            reverse("sudoku:detail", args=[sudoku.pk])
        ),
        "archive_url": archive,
        "title": f"Sudoku #{sudoku.number}" if sudoku.number else "Sudoku",
        "number": sudoku.number,
        "difficulty": sudoku.get_difficulty_display(),
        "published": sudoku.published.isoformat(),
        # 81 entries in row-major order: a digit as a string where the
        # puzzle gives one, "" where the solver has to fill it in.
        "cells": sudoku_tile(sudoku),
    }


PUZZLES = {
    "crossword": _crossword,
    "sudoku": _sudoku,
}


def all_puzzles(request):
    """Every puzzle in one request -- what the news site's block fetches."""
    return JsonResponse(
        {
            "generated": timezone.now().isoformat(),
            "site": request.build_absolute_uri(reverse("home")),
            "puzzles": {name: build(request) for name, build in PUZZLES.items()},
        }
    )


def one_puzzle(request, name):
    """A single puzzle, for callers that want just the one."""
    if name not in PUZZLES:
        raise Http404(f"No such puzzle: {name}")
    return JsonResponse(
        {"generated": timezone.now().isoformat(), **PUZZLES[name](request)}
    )
