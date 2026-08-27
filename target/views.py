import json

from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from .models import Target

PERM = "target.can_generate_targets"

GOOD = 0.75
VERY_GOOD = 0.9


class TargetSelectView(ListView):
    """The Target archive. Everyone sees published puzzles; editors also
    see the ones queued for future publication."""

    model = Target
    template_name = "target/select.html"
    context_object_name = "targets"

    def get_queryset(self):
        qs = super().get_queryset()
        if not self.request.user.has_perm(PERM):
            qs = qs.published()
        return qs


def target_latest(request):
    target = Target.objects.published().order_by("-published").first()
    if target is None:
        raise Http404("No Target has been published yet.")
    return redirect("target_solve", pk=target.pk)


def target_solve(request, pk):
    """Play screen. Editors can preview an unpublished puzzle; everyone
    else gets a 404 for one (mirrors crossword_solve).

    The answer list is handed over as hashes only, along with the counts
    the scoreboard needs, so the page can mark a guess right or wrong
    without carrying the answers.
    """
    target = get_object_or_404(Target, pk=pk)
    if not target.is_published() and not request.user.has_perm(PERM):
        raise Http404

    total = len(target.word_list())
    return render(
        request,
        "target/detail.html",
        {
            "target": target,
            "total": total,
            "good": round(GOOD * total),
            "very_good": round(VERY_GOOD * total),
            "hashed_words": json.dumps(target.hashed_words()),
        },
    )


@require_POST
def target_hint(request, pk):
    """Give away one answer the solver hasn't found.

    The page only ever holds hashes, so it can't pick a word to reveal by
    itself -- it sends what it has and the server names one it's missing.
    The shortest is chosen, so a hint never hands over the nine-letter word
    while easier ones are still out there.
    """
    target = get_object_or_404(Target, pk=pk)
    if not target.is_published() and not request.user.has_perm(PERM):
        raise Http404

    payload = json.loads(request.body or "{}")
    found = {w.lower() for w in payload.get("found", []) if isinstance(w, str)}
    missing = [w for w in target.word_list() if w not in found]
    if not missing:
        return JsonResponse({"word": None})
    return JsonResponse({"word": min(missing, key=len)})
