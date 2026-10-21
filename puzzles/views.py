from allauth.usersessions.models import UserSession
from django.conf import settings
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.sessions.models import Session
from django.shortcuts import redirect, render
from django.utils import timezone

from crossword.models import Crossword
from groupup.models import GroupUp
from puzzles import news
from puzzles.teasers import grid_preview, sudoku_tile, target_tile
from quizzes.models import Quiz
from streetwise.models import Streetwise
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
    groupups = GroupUp.objects.published()
    streetwises = Streetwise.objects.published()

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
            "groupup": groupups.order_by("-published").first(),
            "streetwise": streetwises.order_by("-published").first(),
            "sudoku": sudoku,
            "target": target,
            "target_tile": target_tile(target),
            "sudoku_tile": sudoku_tile(sudoku),
            "preview": grid_preview(crossword) if crossword else None,
            "greeting": _greeting(now),
        },
    )


# The news panels are HTML fragments that a page fetches once it wants
# them (GU.news() in game.js), rather than rendering them with the page,
# so a slow news site never holds up a game.


def news_after_game(request):
    """What a game shows once it's over: the stories readers spent
    longest on this week, and the newsletter."""
    return render(request, "news/after_game.html", {"stories": news.most_deeply_read()})


def news_latest(request):
    """Four stories for the bottom of the games hub: the two newest, then
    two that readers spent longest on this week (not repeating either of
    the new ones). Nothing at all when there are none, so the page leaves
    the panel hidden."""
    new = news.latest()[:2]
    shown = {story["url"] for story in new}
    deep = [story for story in news.most_deeply_read() if story["url"] not in shown][:2]
    stories = [{**story, "kicker": "Just published"} for story in new] + [
        {**story, "kicker": "Readers' pick", "image": news.picture(story["url"])}
        for story in deep
    ]
    return render(
        request,
        "news/latest.html",
        {"stories": stories, "news_site": settings.NEWS_SITE_URL},
    )


def news_top(request):
    """The week's most-read story, for the hub strip."""
    stories = news.most_read()
    return render(request, "news/top.html", {"story": stories[0] if stories else None})
