from allauth.usersessions.models import UserSession
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.sessions.models import Session
from django.shortcuts import redirect, render
from django.utils import timezone

from crossword.models import Crossword
from puzzles.teasers import grid_preview, sudoku_tile, target_tile
from quizzes.models import Quiz
from sudoku.models import Sudoku
from target.models import Target


@login_required
def logout_everywhere(request):
    if request.method != "POST":
        return render(request, "account/logout_everywhere.html")
    user_sessions = UserSession.objects.filter(user_id=request.user.pk)
    Session.objects.filter(
        session_key__in=user_sessions.values_list("session_key", flat=True)
    ).delete()
    user_sessions.delete()
    auth_logout(request)
    return redirect("home")


def _greeting(now):
    """Time-of-day greeting for the hub headline."""
    if now.hour < 12:
        return "Good morning"
    if now.hour < 18:
        return "Good afternoon"
    return "Good evening"


def games_hub(request):
    """The games hub: the newest crossword as the featured puzzle, then a
    tile per game.

    Each tile is drawn from the real puzzle behind it -- the crossword's
    shape, the Target's letters, the Sudoku's givens -- so the hub shows
    what's actually waiting rather than a stand-in.
    """
    crosswords = Crossword.objects.published()
    quizzes = Quiz.objects.published()
    sudokus = Sudoku.objects.published()
    targets = Target.objects.published()

    crossword = crosswords.order_by("-published").first()
    sudoku = sudokus.order_by("-published").first()
    target = targets.order_by("-published").first()
    now = timezone.localtime()
    return render(
        request,
        "home.html",
        {
            "crossword": crossword,
            "quiz": quizzes.order_by("-published").first(),
            "sudoku": sudoku,
            "target": target,
            "target_tile": target_tile(target),
            "sudoku_tile": sudoku_tile(sudoku),
            "preview": grid_preview(crossword) if crossword else None,
            "greeting": _greeting(now),
            "today": now,
            "puzzle_count": (
                crosswords.count() + sudokus.count() + targets.count()
            ),
        },
    )
