import json
import random
from datetime import datetime

from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView

from . import grid
from .cwutils.cwutils import Grid as CwutilsGrid
from .cwutils.cwutils import auto_complete as cwutils_auto_complete
from .forms import CrosswordCreateForm
from .models import Clue, Crossword, Entry, Word
from .xd import parse_xd, render_xd, save_crossword_from_xd
from .xml_format import parse_xml

PERM = "crossword.can_generate_crosswords"


def _clues_by_slot(crossword):
    """Map '1A'/'1D'-style slot labels to clue text, for slots that have one."""
    return {
        f"{e.number}{e.direction}": e.clue.clue
        for e in crossword.entries.select_related("clue")
        if e.clue
    }


class CrosswordCreateView(PermissionRequiredMixin, CreateView):
    permission_required = PERM
    """Add a new crossword.

    Presents a two-field form (grid size, NYT rules); the form creates a
    blank crossword with empty `cells` and `blocked_out_squares`. Redirects
    to the edit screen for the newly created crossword.
    """

    model = Crossword
    form_class = CrosswordCreateForm
    template_name = "crossword/add.html"

    def form_valid(self, form):
        # Overridden instead of using the usual success_url: the redirect
        # target (the edit page for this specific new pk) doesn't exist
        # until the object is saved, so it can't be a static class attribute.
        form.instance.owner = self.request.user
        self.object = form.save()
        return redirect("crossword_edit", pk=self.object.pk)


class CrosswordSelectView(ListView):
    """List crosswords.

    Generators see all crosswords, except private+unpublished crosswords
    they don't own. Everyone else sees only published ones.
    """

    model = Crossword
    template_name = "crossword/select.html"
    context_object_name = "crosswords"
    ordering = ["-date_modified"]

    def get_queryset(self):
        # Restricts the list to published crosswords for anyone without the
        # generate permission; generators see everything except other users'
        # private, unpublished drafts.
        qs = super().get_queryset().select_related("owner")
        user = self.request.user
        if not user.has_perm(PERM):
            qs = qs.published()
        else:
            unpublished = Q(published__isnull=True) | Q(published__gt=timezone.now())
            qs = qs.exclude(Q(private=True) & unpublished & ~Q(owner=user))
        return qs


@permission_required(PERM)
def crossword_edit(request, pk):
    """Render the editable crossword grid for the given crossword."""
    crossword = get_object_or_404(Crossword, pk=pk)
    if crossword.private and crossword.owner_id != request.user.id:
        raise Http404
    return render(
        request,
        "crossword/edit.html",
        {"crossword": crossword, "clues": _clues_by_slot(crossword)},
    )


@require_POST
def crossword_check(request, pk):
    """Check the solver's answers against the stored grid.

    Accepts JSON: mode ('letter'|'word'|'crossword'), cells (flat list),
    cursor (cell index), direction ('A'|'D').  Returns per-cell results
    without revealing the correct letters.
    """
    crossword = get_object_or_404(Crossword, pk=pk)
    if not crossword.is_published() and not request.user.has_perm(PERM):
        raise Http404

    payload = json.loads(request.body)
    mode = payload.get("mode")
    user_cells = payload.get("cells", [])
    cursor = payload.get("cursor", 0)
    direction = payload.get("direction", Entry.ACROSS)

    answer = crossword.cells
    if len(user_cells) != len(answer):
        return JsonResponse({"error": "cell count mismatch"}, status=400)

    blocked = set(crossword.blocked_out_squares)

    def check_cell(i):
        return {"index": i, "correct": bool(user_cells[i] and user_cells[i] == answer[i])}

    if mode == "letter":
        results = [] if cursor in blocked else [check_cell(cursor)]
    elif mode == "word":
        all_slots = grid.slots(
            crossword.num_rows, crossword.num_cols,
            crossword.blocked_out_squares, answer,
        )
        slot = next(
            (s for s in all_slots if s.direction == direction and cursor in s.indices),
            None,
        )
        results = [check_cell(i) for i in slot.indices] if slot else []
    elif mode == "crossword":
        results = [check_cell(i) for i in range(len(answer)) if i not in blocked]
    else:
        return JsonResponse({"error": "invalid mode"}, status=400)

    return JsonResponse({"results": results})


@require_POST
def crossword_reveal(request, pk):
    """Return correct letters for the requested cells.

    Accepts JSON: mode ('letter'|'word'|'crossword'), cursor, direction.
    Returns per-cell correct letters; the client is responsible for marking
    revealed cells as incorrect for scoring purposes.
    """
    crossword = get_object_or_404(Crossword, pk=pk)
    if not crossword.is_published() and not request.user.has_perm(PERM):
        raise Http404

    payload = json.loads(request.body)
    mode = payload.get("mode")
    cursor = payload.get("cursor", 0)
    direction = payload.get("direction", Entry.ACROSS)

    answer = crossword.cells
    blocked = set(crossword.blocked_out_squares)

    def reveal_cell(i):
        return {"index": i, "letter": answer[i]}

    if mode == "letter":
        results = [] if cursor in blocked else [reveal_cell(cursor)]
    elif mode == "word":
        all_slots = grid.slots(
            crossword.num_rows, crossword.num_cols,
            crossword.blocked_out_squares, answer,
        )
        slot = next(
            (s for s in all_slots if s.direction == direction and cursor in s.indices),
            None,
        )
        results = [reveal_cell(i) for i in slot.indices] if slot else []
    elif mode == "crossword":
        results = [reveal_cell(i) for i in range(len(answer)) if i not in blocked]
    else:
        return JsonResponse({"error": "invalid mode"}, status=400)

    return JsonResponse({"results": results})


def crossword_solve(request, pk):
    """Detail/solver view.

    Available to everyone for published crosswords; generators can preview
    unpublished ones. Non-generators get a 404 for unpublished crosswords.
    """
    crossword = get_object_or_404(Crossword, pk=pk)
    if not crossword.is_published() and not request.user.has_perm(PERM):
        raise Http404
    return render(
        request,
        "crossword/detail.html",
        {"crossword": crossword, "clues": _clues_by_slot(crossword)},
    )


def crossword_private_solve(request, private_link):
    """Detail/solver view for an unpublished crossword's secret link.

    No permission check: knowing the link is the only access control.
    Once the crossword is published, the link just forwards to the
    standard solver page instead of continuing to serve its own copy.
    """
    crossword = get_object_or_404(Crossword, private_link=private_link)
    if crossword.is_published():
        return redirect("crossword_solve", pk=crossword.pk)
    return render(
        request,
        "crossword/detail.html",
        {"crossword": crossword, "clues": _clues_by_slot(crossword)},
    )


@permission_required(PERM)
@require_POST
def crossword_save(request, pk):
    """Save the grid for the given crossword.

    Accepts a JSON body: cells, blocked_out_squares, name, description,
    requires_rotational_symmetry, clues ({"1A": "clue text", ...}). cells is
    the source of truth and is always saved. Entry rows are derived from the
    complete slots; partial slots touch nothing but cells.
    """
    crossword = get_object_or_404(Crossword, pk=pk)
    if crossword.private and crossword.owner_id != request.user.id:
        raise Http404
    payload = json.loads(request.body)

    with transaction.atomic():
        crossword.cells = payload["cells"]
        crossword.blocked_out_squares = payload["blocked_out_squares"]
        crossword.name = payload.get("name", "")
        crossword.description = payload.get("description", "")
        crossword.authors = payload.get("authors", "")
        crossword.editors = payload.get("editors", "")
        crossword.copyright = payload.get("copyright", "")
        crossword.private = payload.get("private", False)
        crossword.requires_rotational_symmetry = payload.get("requires_rotational_symmetry", True)
        published_str = payload.get("published") or ""
        if published_str:
            dt = datetime.fromisoformat(published_str)
            crossword.published = dt if timezone.is_aware(dt) else timezone.make_aware(dt)
        else:
            crossword.published = None
        crossword.save()

        clues = payload.get("clues", {})
        cells = crossword.cells
        complete = [
            s
            for s in grid.slots(
                crossword.num_rows,
                crossword.num_cols,
                crossword.blocked_out_squares,
                cells,
            )
            if s.is_complete(cells)
        ]

        # Reconcile: drop entries no longer backed by a complete slot.
        keep = {(s.number, s.direction) for s in complete}
        keep_across = {n for n, d in keep if d == Entry.ACROSS}
        keep_down = {n for n, d in keep if d == Entry.DOWN}
        crossword.entries.exclude(
            Q(direction=Entry.ACROSS, number__in=keep_across)
            | Q(direction=Entry.DOWN, number__in=keep_down)
        ).delete()

        for slot in complete:
            word, _ = Word.objects.get_or_create(
                text=slot.letters(cells),
                defaults={"source_crossword": crossword},
            )

            clue_obj = None
            clue_text = clues.get(f"{slot.number}{slot.direction}")
            if clue_text:
                clue_obj, _ = Clue.objects.get_or_create(
                    text=word,
                    clue=clue_text,
                    defaults={"source_crossword": crossword},
                )

            Entry.objects.update_or_create(
                crossword=crossword,
                number=slot.number,
                direction=slot.direction,
                defaults={"word": word, "clue": clue_obj},
            )

    return JsonResponse({"status": "ok"})


FETCH_ANSWERS_PAGE_SIZE = 20


def _cwutils_grid_string(num_rows, num_cols, blocked, cells):
    """Render live grid state as the multi-line string cwutils.Grid expects
    ("#" block, "-" blank, else the letter)."""
    lines = []
    for r in range(num_rows):
        row = []
        for c in range(num_cols):
            i = r * num_cols + c
            row.append("#" if i in blocked else (cells[i] or "-"))
        lines.append("".join(row))
    return "\n" + "\n".join(lines) + "\n"


@permission_required(PERM)
@require_POST
def fetch_answers(request, pk):
    """Return a page of Word matches for the current slot, ranked by
    cwutils.Slot.words_freedom(): candidates that leave the most freedom in
    their hardest-constrained crossing slot rank first.

    The client sends the live, possibly-unsaved grid state, since the match
    should reflect what's on screen rather than the last save: `cells`,
    `blocked_out_squares`, `cursor` (a cell index inside the target slot),
    `direction` ("A"/"D"), and `page` (1-indexed, 20 per page).

    Alongside `answers`, returns a same-length `metrics` array (each entry
    `{"worst": int, "mean": float}`, or `{"worst": null, "mean": null}` per
    word when the slot has no active crossing to rank by) and a
    `ranked_by_freedom` flag, so the client can show the freedom scores
    behind the ranking.
    """
    crossword = get_object_or_404(Crossword, pk=pk)
    payload = json.loads(request.body)
    cells = payload.get("cells", [])
    blocked = set(payload.get("blocked_out_squares", []))
    cursor = payload.get("cursor", 0)
    direction = payload.get("direction", Entry.ACROSS)
    try:
        page = int(payload.get("page", 1))
    except (TypeError, ValueError):
        page = 1
    page = max(page, 1)

    grid_string = _cwutils_grid_string(crossword.num_rows, crossword.num_cols, blocked, cells)
    words = list(
        Word.objects.exclude(exclude_from_recommendations=True)
        .order_by("text")
        .values_list("text", flat=True)
    )
    slot = CwutilsGrid(grid_string, words).slot_for_cell(direction, cursor)

    texts = []
    metrics = []
    ranked_by_freedom = False
    if slot:
        ranked = slot.words_freedom()
        ranked_by_freedom = True
        texts = [word for word, _, _ in ranked]
        metrics = [{"worst": worst, "mean": mean} for _, worst, mean in ranked]

    total_pages = -(-len(texts) // FETCH_ANSWERS_PAGE_SIZE)  # ceil div
    start = (page - 1) * FETCH_ANSWERS_PAGE_SIZE
    return JsonResponse({
        "answers": texts[start : start + FETCH_ANSWERS_PAGE_SIZE],
        "metrics": metrics[start : start + FETCH_ANSWERS_PAGE_SIZE],
        "ranked_by_freedom": ranked_by_freedom,
        "page": page,
        "total_pages": total_pages,
    })


@permission_required(PERM)
@require_POST
def crossword_auto_complete(request, pk):
    """Try to fill every remaining blank cell via cwutils' depth-first
    auto_complete search, using the live (possibly unsaved) grid state.

    Accepts JSON: cells, blocked_out_squares. Returns `cells` reflecting
    whatever cwutils came up with (unchanged from the input where it
    couldn't complete a slot) and a `complete` flag for whether every slot
    ended up filled.
    """
    crossword = get_object_or_404(Crossword, pk=pk)
    payload = json.loads(request.body)
    cells = payload.get("cells", [])
    blocked = set(payload.get("blocked_out_squares", []))

    grid_string = _cwutils_grid_string(crossword.num_rows, crossword.num_cols, blocked, cells)
    words = list(
        Word.objects.exclude(exclude_from_recommendations=True)
        .order_by("text")
        .values_list("text", flat=True)
    )
    solved = cwutils_auto_complete(CwutilsGrid(grid_string, words))

    result_cells = [
        "" if i in blocked else ("" if letter == "-" else letter)
        for i, letter in enumerate(solved.cells)
    ]
    return JsonResponse({"cells": result_cells, "complete": solved.complete()})


@permission_required(PERM)
def fetch_clues(request, pk):
    """Return up to 10 clue texts for the current complete word.

    The client sends `word`. If empty (slot incomplete), the result is empty.
    """
    word_text = request.GET.get("word", "")
    clues = []
    if word_text:
        clues = list(
            Clue.objects.filter(text__text=word_text).values_list("clue", flat=True)
        )
    if len(clues) > 10:
        clues = random.sample(clues, 10)
    return JsonResponse({"clues": sorted(clues)})


@permission_required(PERM)
@require_POST
def crossword_delete(request, pk):
    """Permanently delete a crossword and return to the list.

    No server-side confirmation step -- the confirm() dialog on the delete
    button in select.html is the only guard against an accidental click.
    """
    crossword = get_object_or_404(Crossword, pk=pk)
    crossword.delete()
    return redirect("crossword_select")


def crossword_xd(request, pk):
    """Return the crossword as a downloadable .xd file."""
    crossword = get_object_or_404(Crossword, pk=pk)
    filename = (crossword.name or "crossword").replace('"', "")
    response = HttpResponse(render_xd(crossword), content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}.xd"'
    return response


@permission_required(PERM)
@require_POST
def crossword_import(request):
    """Create or replace a crossword from an uploaded .xd or .xml file.

    Accepts a plain-text .xd body or a Crossword Compiler .xml body; the
    X-Filename header's extension picks which parser to use. Returns JSON
    with a redirect URL on success, or an error message on failure.
    """
    filename = request.headers.get("X-Filename", "")
    parse = parse_xml if filename.lower().endswith(".xml") else parse_xd
    try:
        data = parse(request.body.decode("utf-8"))
        if not data["size"]["rows"]:
            raise ValueError("empty grid")
    except Exception:
        return JsonResponse({"error": "Invalid file"}, status=400)

    crossword = save_crossword_from_xd(data, replace=True)
    return JsonResponse({"redirect": reverse("crossword_edit", args=[crossword.pk])})
