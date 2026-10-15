"""Read-only JSON API describing the latest puzzle of each kind."""

from django.http import Http404, JsonResponse
from django.urls import reverse
from django.utils import timezone

from crossword.models import Crossword
from groupup.models import GroupUp
from puzzles.teasers import grid_preview, sudoku_tile, target_tile
from quizzes.models import Quiz
from sudoku.models import Sudoku
from target.models import Target


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


def _target(request):
    """The newest published Target: its nine letters.

    `words` holds the answers and is deliberately not served.
    """
    target = Target.objects.published().order_by("-published").first()
    archive = request.build_absolute_uri(reverse("target:list"))
    if target is None:
        return {"available": False, "archive_url": archive}
    return {
        "available": True,
        "url": request.build_absolute_uri(
            reverse("target:detail", args=[target.pk])
        ),
        "archive_url": archive,
        "title": f"Target #{target.number}",
        "number": target.number,
        "clue": target.clue,
        "published": target.published.isoformat(),
        # 9 entries in row-major order, the centre letter (the one every
        # word must use) fifth: {"char": str, "centre": bool}.
        "cells": target_tile(target),
    }


def _quiz(request):
    """The newest published news quiz: its name and blurb.

    The questions and answers are deliberately not served.
    """
    quiz = Quiz.objects.published().order_by("-published").first()
    archive = request.build_absolute_uri(reverse("quiz_select"))
    if quiz is None:
        return {"available": False, "archive_url": archive}
    return {
        "available": True,
        "url": request.build_absolute_uri(reverse("quiz_solve", args=[quiz.pk])),
        "archive_url": archive,
        "title": quiz.name or "News Quiz",
        "description": quiz.description,
        "published": quiz.published.isoformat(),
    }


def _groupup(request):
    """The newest published GroupUp: its name and blurb.

    `groups` holds the words and their groupings -- the whole answer --
    and is deliberately not served.
    """
    groupup = GroupUp.objects.published().order_by("-published").first()
    archive = request.build_absolute_uri(reverse("groupup:list"))
    if groupup is None:
        return {"available": False, "archive_url": archive}
    return {
        "available": True,
        "url": request.build_absolute_uri(
            reverse("groupup:solve", args=[groupup.pk])
        ),
        "archive_url": archive,
        "title": groupup.name or "GroupUp",
        "description": groupup.description,
        "published": groupup.published.isoformat(),
    }


PUZZLES = {
    "crossword": _crossword,
    "groupup": _groupup,
    "quiz": _quiz,
    "sudoku": _sudoku,
    "target": _target,
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
