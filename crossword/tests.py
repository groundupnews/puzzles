import json
import os
import string
import unittest
from datetime import timedelta

from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .grid import ACROSS, DOWN, slots
from .models import Clue, Crossword, Entry, Word
from .xd import parse_xd, render_xd, save_crossword_from_xd
from .xml_format import parse_xml


def make_user_with_perm(client, username="testuser"):
    """Create a user with can_generate_crosswords permission and log them in."""
    user = User.objects.create_user(username=username, password="testpass")
    perm = Permission.objects.get(codename="can_generate_crosswords")
    user.user_permissions.add(perm)
    client.login(username=username, password="testpass")
    return user


def make_crossword(**kwargs):
    """Creates a Crossword with sensible minimal defaults (a blank 1x3
    grid), overridable via kwargs. The default shape matches XD_1ROW."""
    defaults = dict(num_rows=1, num_cols=3, cells=["", "", ""], blocked_out_squares=[])
    defaults.update(kwargs)
    return Crossword.objects.create(**defaults)


# Minimal 1×3 xd puzzle used across several test classes.
XD_1ROW = (
    "Title: Test Puzzle\n"
    "Author: Test Author\n"
    "Editor: Test Editor\n"
    "Copyright: 2022 Test Co\n"
    "\n"
    "CAT\n"
    "\n"
    "A1. A feline ~ CAT\n"
)

# 3×3 puzzle with one across and one down slot sharing number 1.
XD_3X3 = (
    "Title: Mini Test\n"
    "Author: Tester\n"
    "\n"
    "CAT\n"
    "A##\n"
    "T##\n"
    "\n"
    "A1. Feline ~ CAT\n"
    "\n"
    "D1. Feline ~ CAT\n"
)


def _xml_puzzle(grid_cells, clues, title="", creator="", copyright_=""):
    """Builds a minimal Crossword Compiler XML document. grid_cells is a
    list of rows, each a list of (solution, is_block) tuples. clues is a
    list of (direction, number, text) tuples."""
    num_rows = len(grid_cells)
    num_cols = len(grid_cells[0])
    cells_xml = []
    for r, row in enumerate(grid_cells):
        for c, (solution, is_block) in enumerate(row):
            if is_block:
                cells_xml.append(f'<cell x="{c + 1}" y="{r + 1}" type="block"/>')
            else:
                cells_xml.append(
                    f'<cell x="{c + 1}" y="{r + 1}" solution="{solution}"/>'
                )

    clues_xml = []
    for direction in ("Across", "Down"):
        entries = [(n, t) for d, n, t in clues if d == direction]
        if not entries:
            continue
        clue_lines = "".join(f'<clue number="{n}">{t}</clue>' for n, t in entries)
        clues_xml.append(f"<clues><title>{direction}</title>{clue_lines}</clues>")

    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<crossword-compiler xmlns="http://crossword.info/xml/crossword-compiler">'
        '<rectangular-puzzle xmlns="http://crossword.info/xml/rectangular-puzzle">'
        f"<metadata><title>{title}</title><creator>{creator}</creator>"
        f"<copyright>{copyright_}</copyright></metadata>"
        f'<crossword><grid width="{num_cols}" height="{num_rows}">'
        + "".join(cells_xml)
        + "</grid>"
        + "".join(clues_xml)
        + "</crossword></rectangular-puzzle></crossword-compiler>"
    )


# Minimal 1×3 xml puzzle, same shape as XD_1ROW.
XML_1ROW = _xml_puzzle(
    [[("C", False), ("A", False), ("T", False)]],
    [("Across", 1, "A feline")],
    title="Test Puzzle",
    creator="Test Author",
    copyright_="2022 Test Co",
)

# 3×3 xml puzzle with one across and one down slot sharing number 1, same
# shape as XD_3X3.
XML_3X3 = _xml_puzzle(
    [
        [("C", False), ("A", False), ("T", False)],
        [("A", False), ("", True), ("", True)],
        [("T", False), ("", True), ("", True)],
    ],
    [("Across", 1, "Feline"), ("Down", 1, "Feline")],
    title="Mini Test",
    creator="Tester",
)


# ---------------------------------------------------------------------------
# Grid slot logic
# ---------------------------------------------------------------------------


class GridSlotTest(TestCase):
    """Tests for grid.slots(): detection, numbering, and completeness.
    generator.js and solver.js each hand-port this same logic client-side
    and must stay in sync with it."""

    def test_single_open_row(self):
        # A 1-row, 3-column grid with no blocked squares should produce exactly
        # one slot: 1 Across covering all three cells (indices 0, 1, 2).
        # Checks that a minimal grid is detected and numbered correctly.
        s = slots(1, 3, [], ["", "", ""])
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0].number, 1)
        self.assertEqual(s[0].direction, ACROSS)
        self.assertEqual(s[0].indices, (0, 1, 2))

    def test_isolated_cell_not_a_slot(self):
        # A single white cell surrounded by blocked squares on all sides should
        # not be counted as a slot, because a slot requires at least 2 consecutive
        # white cells. This guards against single-cell "answers" appearing in the grid.
        blocked = [0, 1, 2, 3, 5, 6, 7, 8]
        s = slots(3, 3, blocked, [""] * 9)
        self.assertEqual(s, [])

    def test_across_and_down_share_number(self):
        # When a cell starts both an across and a down slot, both slots get the
        # same number (standard crossword convention). In a 2x2 open grid, cell 0
        # starts 1 Across and 1 Down. The grid should have slots numbered 1, 2, 3
        # (not 1, 2, 3, 4), confirming the shared-number rule.
        s = slots(2, 2, [], ["", "", "", ""])
        numbers = {(slot.direction, slot.number) for slot in s}
        self.assertIn((ACROSS, 1), numbers)
        self.assertIn((DOWN, 1), numbers)
        self.assertEqual({slot.number for slot in s}, {1, 2, 3})

    def test_numbering_order_row_major(self):
        # Slot numbers are assigned in reading order (left to right, top to bottom).
        # In a 3x3 open grid the across slots start at cells 0, 3, 6 (the left edge
        # of each row) and the down slots start at cells 0, 1, 2 (the top row).
        # Checks that the numbering matches the expected reading-order assignment.
        s = slots(3, 3, [], [""] * 9)
        across_starts = {
            slot.number: slot.start for slot in s if slot.direction == ACROSS
        }
        down_starts = {slot.number: slot.start for slot in s if slot.direction == DOWN}
        self.assertEqual(across_starts, {1: 0, 4: 3, 5: 6})
        self.assertEqual(down_starts, {1: 0, 2: 1, 3: 2})

    def test_completeness_and_letters(self):
        # is_complete() should return True only when every cell in the slot holds
        # a letter. A slot with one empty cell is not complete, even if the other
        # cells are filled. Also checks that letters() reads the right cells.
        cells = ["C", "A", "T"]
        s = slots(1, 3, [], cells)
        self.assertEqual(s[0].letters(cells), "CAT")
        self.assertTrue(s[0].is_complete(cells))

        partial = ["C", "", "T"]
        s2 = slots(1, 3, [], partial)
        self.assertFalse(s2[0].is_complete(partial))

    def test_length(self):
        # length should equal the number of cells in the slot.
        s = slots(1, 5, [], [""] * 5)
        self.assertEqual(s[0].length, 5)


# ---------------------------------------------------------------------------
# Word model
# ---------------------------------------------------------------------------


class WordModelTest(TestCase):
    """Tests for Word's uppercase-A-Z-only validation, enforced by
    full_clean() in Word.save() rather than left to forms/admin alone."""

    def test_valid_word_saves(self):
        # A word containing only uppercase A-Z letters should save without error.
        # Uses a synthetic string not present in the loaded wordlist.
        w = Word(text="ZZZZZ")
        w.save()
        self.assertEqual(Word.objects.get(pk=w.pk).text, "ZZZZZ")

    def test_rejects_lowercase(self):
        # Lowercase letters are not allowed. The model calls full_clean() on save,
        # so this should raise ValidationError before touching the database.
        with self.assertRaises(ValidationError):
            Word(text="cat").save()

    def test_rejects_digits(self):
        # Digits are not allowed even when mixed with uppercase letters.
        with self.assertRaises(ValidationError):
            Word(text="CA7").save()


class CrosswordPrivateLinkUniquenessTest(TestCase):
    """private_link is the sole access control for crossword_private_solve,
    so the database must reject two rows sharing a value -- this guards
    against a repeat of the bug where AddField's callable default backfilled
    every pre-existing row with the same string (see migrations 0013/0014)."""

    fixtures = ["users.json"]

    def test_duplicate_private_link_raises_integrity_error(self):
        make_crossword(private_link="shared-secret")
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_crossword(private_link="shared-secret")


# ---------------------------------------------------------------------------
# Crossword create / save views
# ---------------------------------------------------------------------------


class CrosswordCreateViewTest(TestCase):
    """Tests for the "new crossword" form/view (CrosswordCreateForm +
    CrosswordCreateView)."""

    fixtures = ["users.json"]

    def setUp(self):
        make_user_with_perm(self.client)

    def test_post_creates_crossword_and_redirects_to_edit(self):
        # POSTing the "add crossword" form should create a Crossword in the database
        # with the right dimensions, initialise cells to the correct number of empty
        # strings, and redirect to the edit screen for that crossword.
        response = self.client.post(reverse("crossword_add"), {"size": 15})
        cw = Crossword.objects.get()
        self.assertRedirects(response, reverse("crossword_edit", args=[cw.pk]))
        self.assertEqual(cw.num_rows, 15)
        self.assertEqual(cw.num_cols, 15)
        self.assertEqual(len(cw.cells), 15 * 15)


class CrosswordSaveViewTest(TestCase):
    """Tests for crossword_save(): deriving Word/Clue/Entry rows from the
    posted grid, per the save-payload contract in crossword_spec.md."""

    fixtures = ["users.json"]

    def setUp(self):
        make_user_with_perm(self.client)
        self.cw = make_crossword()

    def _save(self, payload):
        """POSTs `payload` as JSON to this test's crossword's save URL."""
        return self.client.post(
            reverse("crossword_save", args=[self.cw.pk]),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_complete_slot_creates_word_and_entry(self):
        # When every cell in a slot is filled, saving should create a Word record
        # for the answer text and an Entry record linking that word to the crossword
        # slot. If a clue is provided it should be stored and linked to the entry.
        response = self._save(
            {
                "cells": ["C", "A", "T"],
                "blocked_out_squares": [],
                "name": "",
                "description": "",
                "clues": {"1A": "A feline"},
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Word.objects.filter(text="CAT").exists())
        entry = Entry.objects.get(crossword=self.cw, number=1, direction=Entry.ACROSS)
        self.assertEqual(entry.word.text, "CAT")
        self.assertEqual(entry.clue.clue, "A feline")

    def test_partial_slot_creates_no_entry(self):
        # A slot with at least one empty cell is not complete and should not
        # produce an Entry record. The cells are still saved to the grid.
        self._save(
            {
                "cells": ["C", "A", ""],
                "blocked_out_squares": [],
                "name": "",
                "description": "",
                "clues": {},
            }
        )
        self.assertFalse(Entry.objects.filter(crossword=self.cw).exists())

    def test_saves_requires_rotational_symmetry(self):
        # The symmetry toggle lives on the edit screen (not the create form),
        # so crossword_save is where it must actually get persisted.
        self.assertTrue(self.cw.requires_rotational_symmetry)
        self._save(
            {
                "cells": ["C", "A", "T"],
                "blocked_out_squares": [],
                "name": "",
                "description": "",
                "clues": {},
                "requires_rotational_symmetry": False,
            }
        )
        self.cw.refresh_from_db()
        self.assertFalse(self.cw.requires_rotational_symmetry)

    def test_new_word_gets_source_crossword(self):
        # A word that doesn't exist yet should have source_crossword set to the
        # crossword it was first saved from. Uses a synthetic word unlikely to
        # appear in any loaded fixture.
        cw = make_crossword(num_cols=5, cells=["Z", "Z", "Z", "Z", "Z"])
        response = self.client.post(
            reverse("crossword_save", args=[cw.pk]),
            data=json.dumps(
                {
                    "cells": ["Z", "Z", "Z", "Z", "Z"],
                    "blocked_out_squares": [],
                    "name": "",
                    "description": "",
                    "clues": {},
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Word.objects.get(text="ZZZZZ").source_crossword, cw)

    def test_existing_word_source_crossword_not_overwritten(self):
        # If the word already exists with a different source_crossword, saving it
        # again from another crossword should leave the original source intact.
        other_cw = make_crossword(num_cols=5, cells=["Z", "Z", "Z", "Z", "Z"])
        word, _ = Word.objects.get_or_create(text="ZZZZZ")
        word.source_crossword = other_cw
        word.save()
        cw = make_crossword(num_cols=5, cells=["Z", "Z", "Z", "Z", "Z"])
        self.client.post(
            reverse("crossword_save", args=[cw.pk]),
            data=json.dumps(
                {
                    "cells": ["Z", "Z", "Z", "Z", "Z"],
                    "blocked_out_squares": [],
                    "name": "",
                    "description": "",
                    "clues": {},
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(Word.objects.get(text="ZZZZZ").source_crossword, other_cw)

    def test_new_clue_gets_source_crossword(self):
        # A clue that doesn't exist yet should have source_crossword set to the
        # crossword it was first saved from.
        cw = make_crossword(num_cols=5, cells=["Z", "Z", "Z", "Z", "Z"])
        self.client.post(
            reverse("crossword_save", args=[cw.pk]),
            data=json.dumps(
                {
                    "cells": ["Z", "Z", "Z", "Z", "Z"],
                    "blocked_out_squares": [],
                    "name": "",
                    "description": "",
                    "clues": {"1A": "A test clue"},
                }
            ),
            content_type="application/json",
        )
        word = Word.objects.get(text="ZZZZZ")
        self.assertEqual(
            Clue.objects.get(text=word, clue="A test clue").source_crossword, cw
        )

    def test_existing_clue_source_crossword_not_overwritten(self):
        # If the clue already exists with a different source_crossword, saving it
        # again from another crossword should leave the original source intact.
        other_cw = make_crossword(num_cols=5, cells=["Z", "Z", "Z", "Z", "Z"])
        word, _ = Word.objects.get_or_create(text="ZZZZZ")
        clue = Clue.objects.create(
            text=word, clue="A test clue", source_crossword=other_cw
        )
        cw = make_crossword(num_cols=5, cells=["Z", "Z", "Z", "Z", "Z"])
        self.client.post(
            reverse("crossword_save", args=[cw.pk]),
            data=json.dumps(
                {
                    "cells": ["Z", "Z", "Z", "Z", "Z"],
                    "blocked_out_squares": [],
                    "name": "",
                    "description": "",
                    "clues": {"1A": "A test clue"},
                }
            ),
            content_type="application/json",
        )
        clue.refresh_from_db()
        self.assertEqual(clue.source_crossword, other_cw)

    def test_stale_entry_removed_when_slot_cleared(self):
        # If a previously complete slot is cleared, the corresponding Entry record
        # should be deleted on the next save. This keeps the Entry table in sync
        # with the actual grid contents.
        self._save(
            {
                "cells": ["C", "A", "T"],
                "blocked_out_squares": [],
                "name": "",
                "description": "",
                "clues": {},
            }
        )
        self.assertEqual(Entry.objects.filter(crossword=self.cw).count(), 1)
        self._save(
            {
                "cells": ["", "", ""],
                "blocked_out_squares": [],
                "name": "",
                "description": "",
                "clues": {},
            }
        )
        self.assertEqual(Entry.objects.filter(crossword=self.cw).count(), 0)


# ---------------------------------------------------------------------------
# Private-link solve view
# ---------------------------------------------------------------------------


class CrosswordPrivateSolveViewTest(TestCase):
    """Tests for crossword_private_solve(): the secret-link solver page for
    unpublished crosswords. No permission is required to use the link, but
    once the crossword is published the link just forwards to the normal
    solver page instead of continuing to serve its own copy."""

    fixtures = ["users.json"]

    def test_anonymous_user_can_solve_unpublished_crossword(self):
        cw = make_crossword(published=None)
        response = self.client.get(
            reverse("crossword_private_solve", args=[cw.private_link])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "crossword/detail.html")

    def test_unknown_private_link_returns_404(self):
        response = self.client.get(
            reverse("crossword_private_solve", args=["does-not-exist"])
        )
        self.assertEqual(response.status_code, 404)

    def test_published_crossword_redirects_to_standard_solver(self):
        cw = make_crossword(published=timezone.now() - timedelta(days=1))
        response = self.client.get(
            reverse("crossword_private_solve", args=[cw.private_link])
        )
        self.assertRedirects(response, reverse("crossword_solve", args=[cw.pk]))

    def test_future_published_crossword_still_served_directly(self):
        cw = make_crossword(published=timezone.now() + timedelta(days=1))
        response = self.client.get(
            reverse("crossword_private_solve", args=[cw.private_link])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "crossword/detail.html")


class CrosswordEditViewButtonTest(TestCase):
    """Tests for the "View" link on the edit screen: it should point at the
    private-link solver only for an unpublished crossword that has a
    private_link; every other case (published, or no private_link) falls
    back to the standard solver page."""

    fixtures = ["users.json"]

    def setUp(self):
        make_user_with_perm(self.client)

    def _view_link(self, cw):
        response = self.client.get(reverse("crossword_edit", args=[cw.pk]))
        content = response.content.decode()
        solve_href = reverse("crossword_solve", args=[cw.pk])
        private_solve_href = (
            reverse("crossword_private_solve", args=[cw.private_link])
            if cw.private_link
            else None
        )
        return solve_href in content, private_solve_href is not None and private_solve_href in content

    def test_unpublished_with_private_link_uses_private_solve(self):
        cw = make_crossword(published=None)
        solve_present, private_solve_present = self._view_link(cw)
        self.assertFalse(solve_present)
        self.assertTrue(private_solve_present)

    def test_published_uses_standard_solve(self):
        cw = make_crossword(published=timezone.now() - timedelta(days=1))
        solve_present, private_solve_present = self._view_link(cw)
        self.assertTrue(solve_present)
        self.assertFalse(private_solve_present)

    def test_unpublished_without_private_link_uses_standard_solve(self):
        cw = make_crossword(published=None, private_link="")
        solve_present, private_solve_present = self._view_link(cw)
        self.assertTrue(solve_present)
        self.assertFalse(private_solve_present)


# ---------------------------------------------------------------------------
# Fetch answers view
# ---------------------------------------------------------------------------


class FetchAnswersViewTest(TestCase):
    """Tests for fetch_answers(): glob matching, pagination, and the
    exclude_from_recommendations filter. Ranking by words_freedom() itself
    is covered separately in cwutils/test.py."""

    fixtures = ["users.json"]

    def setUp(self):
        make_user_with_perm(self.client)

    def _fetch(self, cw, cells, page=1):
        # cursor=0, direction=ACROSS selects the one across slot in these
        # single-row fixture grids.
        return self.client.post(
            reverse("fetch_answers", args=[cw.pk]),
            data=json.dumps(
                {
                    "cells": cells,
                    "blocked_out_squares": [],
                    "cursor": 0,
                    "direction": ACROSS,
                    "page": page,
                }
            ),
            content_type="application/json",
        )

    def test_returns_words_matching_glob_pattern(self):
        # Synthetic words starting with "ZZZ" are used to avoid collisions with
        # real words loaded by the wordlist migration. The blank final cell
        # means the slot pattern is effectively "ZZZ?".
        Word.objects.create(text="ZZZA")
        Word.objects.create(text="ZZZB")
        Word.objects.create(text="DDDA")
        cw = make_crossword(num_cols=4, cells=["", "", "", ""])

        data = self._fetch(cw, ["Z", "Z", "Z", ""]).json()
        self.assertCountEqual(data["answers"], ["ZZZA", "ZZZB"])

    def test_paginates_sorted_results(self):
        # 26 matches for the "ZZZ?" pattern (one per letter) is more than a
        # page's worth (20). This is a single-row grid, so every column is a
        # length-1 down slot that no dictionary word (minimum length 2) can
        # ever fill; every candidate ties at that same freedom score, so
        # cwutils' stable sort falls back to the order words were supplied in
        # (alphabetical, per the view's query). Page 1 should hold the first
        # 20 letters, page 2 the rest.
        letters = string.ascii_uppercase
        for letter in letters:
            Word.objects.create(text=f"ZZZ{letter}")
        cw = make_crossword(num_cols=4, cells=["", "", "", ""])

        page1 = self._fetch(cw, ["Z", "Z", "Z", ""], page=1).json()
        page2 = self._fetch(cw, ["Z", "Z", "Z", ""], page=2).json()

        self.assertEqual(page1["answers"], [f"ZZZ{c}" for c in letters[:20]])
        self.assertEqual(page1["total_pages"], 2)
        self.assertEqual(page2["answers"], [f"ZZZ{c}" for c in letters[20:]])

    def test_excludes_words_flagged_exclude_from_recommendations(self):
        # A word flagged exclude_from_recommendations should never be
        # offered as a fetch-answers candidate, even though it still
        # matches the glob pattern.
        Word.objects.create(text="ZZZA")
        Word.objects.create(text="ZZZB", exclude_from_recommendations=True)
        cw = make_crossword(num_cols=4, cells=["", "", "", ""])

        data = self._fetch(cw, ["Z", "Z", "Z", ""]).json()
        self.assertCountEqual(data["answers"], ["ZZZA"])


# ---------------------------------------------------------------------------
# Permission checks
# ---------------------------------------------------------------------------


class PermissionTest(TestCase):
    """A logged-in user without can_generate_crosswords is redirected from write endpoints."""

    fixtures = ["users.json"]

    def setUp(self):
        User.objects.create_user(username="noperm", password="testpass")
        self.client.login(username="noperm", password="testpass")

    def test_add_crossword_requires_permission(self):
        # A user without the permission should not be able to create a crossword.
        # PermissionRequiredMixin returns 403 for authenticated users lacking the permission.
        response = self.client.post(reverse("crossword_add"), {"size": 15})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Crossword.objects.exists())

    def test_save_crossword_requires_permission(self):
        # A user without the permission should not be able to save grid changes.
        # The view should redirect and leave the Entry table empty.
        cw = make_crossword()
        response = self.client.post(
            reverse("crossword_save", args=[cw.pk]),
            data=json.dumps(
                {
                    "cells": ["C", "A", "T"],
                    "blocked_out_squares": [],
                    "name": "",
                    "description": "",
                    "clues": {},
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Entry.objects.exists())


# ---------------------------------------------------------------------------
# parse_xd
# ---------------------------------------------------------------------------


class ParseXdTest(TestCase):
    """Tests for parse_xd(): the xd-format header/grid/clue parser."""

    fixtures = ["users.json"]

    def test_headers_parsed(self):
        # Title/Author/Editor/Copyright headers are read into their
        # corresponding dict keys.
        data = parse_xd(XD_1ROW)
        self.assertEqual(data["name"], "Test Puzzle")
        self.assertEqual(data["authors"], "Test Author")
        self.assertEqual(data["editors"], "Test Editor")
        self.assertEqual(data["copyright"], "2022 Test Co")

    def test_missing_optional_headers_are_empty(self):
        # Headers other than Title are optional; when absent, their dict
        # values default to "" rather than being missing or None.
        data = parse_xd("Title: X\n\nCAT\n")
        self.assertEqual(data["authors"], "")
        self.assertEqual(data["editors"], "")
        self.assertEqual(data["copyright"], "")

    def test_grid_dimensions(self):
        # size is derived from the grid block, not stated in a header.
        data = parse_xd(XD_1ROW)
        self.assertEqual(data["size"], {"rows": 1, "cols": 3})

    def test_grid_dimensions_2d(self):
        # Dimensions are read correctly for a grid with more than one row.
        data = parse_xd(XD_3X3)
        self.assertEqual(data["size"], {"rows": 3, "cols": 3})

    def test_cells_from_letters(self):
        # An all-letters grid row parses straight into uppercase cells with
        # no blocked squares.
        data = parse_xd(XD_1ROW)
        self.assertEqual(data["grid"], ["C", "A", "T"])
        self.assertEqual(data["blocked_out_squares"], [])

    def test_hash_produces_blocked_square(self):
        # # in the grid marks a blocked cell; its index goes into blocked_out_squares
        # and its cell value is "".
        data = parse_xd("Title: T\n\nC#T\n")
        self.assertEqual(data["grid"], ["C", "", "T"])
        self.assertEqual(data["blocked_out_squares"], [1])

    def test_dot_is_empty_white_cell(self):
        # . marks an empty white cell — not blocked, letter absent.
        data = parse_xd("Title: T\n\nC.T\n")
        self.assertEqual(data["grid"], ["C", "", "T"])
        self.assertEqual(data["blocked_out_squares"], [])

    def test_lowercase_circled_cell_uppercased(self):
        # Lowercase letters denote circled cells in xd format; they are stored
        # as uppercase in the grid just like normal cells.
        data = parse_xd("Title: T\n\nCaT\n\nA1. ~ CAT\n")
        self.assertEqual(data["grid"], ["C", "A", "T"])

    def test_across_clue_parsed(self):
        # An "A1. ..." line is parsed into across_clues keyed by number;
        # with no "D..." lines present, down_clues stays empty.
        data = parse_xd(XD_1ROW)
        self.assertEqual(data["across_clues"], {1: "A feline"})
        self.assertEqual(data["down_clues"], {})

    def test_across_and_down_clues_parsed(self):
        # Across and down clues are parsed independently even when they
        # share the same number (both are "1" here, for the shared cell).
        data = parse_xd(XD_3X3)
        self.assertEqual(data["across_clues"], {1: "Feline"})
        self.assertEqual(data["down_clues"], {1: "Feline"})

    def test_answer_after_tilde_ignored(self):
        # The answer after ~ in a clue line is ignored; the grid is the source
        # of truth for letters.
        data = parse_xd("Title: T\n\nCAT\n\nA1. A feline ~ WRONG\n")
        self.assertEqual(data["across_clues"], {1: "A feline"})

    def test_2d_blocked_squares(self):
        data = parse_xd(XD_3X3)
        # Row 1: A ## → indices 4, 5 blocked. Row 2: T ## → indices 7, 8 blocked.
        self.assertEqual(sorted(data["blocked_out_squares"]), [4, 5, 7, 8])


# ---------------------------------------------------------------------------
# parse_xml
# ---------------------------------------------------------------------------


class ParseXmlTest(TestCase):
    """Tests for parse_xml(): the Crossword Compiler XML parser. Mirrors
    ParseXdTest since both feed the same save_crossword_from_xd() shape."""

    fixtures = ["users.json"]

    def test_metadata_parsed(self):
        # <title>/<creator>/<copyright> map to name/authors/copyright; xml
        # has no editor field, so editors is always "".
        data = parse_xml(XML_1ROW)
        self.assertEqual(data["name"], "Test Puzzle")
        self.assertEqual(data["authors"], "Test Author")
        self.assertEqual(data["editors"], "")
        self.assertEqual(data["copyright"], "2022 Test Co")

    def test_missing_optional_metadata_is_empty(self):
        data = parse_xml(_xml_puzzle([[("C", False), ("A", False), ("T", False)]], []))
        self.assertEqual(data["name"], "")
        self.assertEqual(data["authors"], "")
        self.assertEqual(data["copyright"], "")

    def test_grid_dimensions(self):
        data = parse_xml(XML_1ROW)
        self.assertEqual(data["size"], {"rows": 1, "cols": 3})

    def test_grid_dimensions_2d(self):
        data = parse_xml(XML_3X3)
        self.assertEqual(data["size"], {"rows": 3, "cols": 3})

    def test_cells_from_solutions(self):
        data = parse_xml(XML_1ROW)
        self.assertEqual(data["grid"], ["C", "A", "T"])
        self.assertEqual(data["blocked_out_squares"], [])

    def test_block_type_produces_blocked_square(self):
        # A <cell type="block"/> marks a blocked cell; its index goes into
        # blocked_out_squares and its cell value is "".
        data = parse_xml(
            _xml_puzzle(
                [[("C", False), ("", True), ("T", False)]],
                [],
            )
        )
        self.assertEqual(data["grid"], ["C", "", "T"])
        self.assertEqual(data["blocked_out_squares"], [1])

    def test_across_clue_parsed(self):
        data = parse_xml(XML_1ROW)
        self.assertEqual(data["across_clues"], {1: "A feline"})
        self.assertEqual(data["down_clues"], {})

    def test_across_and_down_clues_parsed(self):
        # Across and down clues are parsed independently even when they
        # share the same number (both are "1" here, for the shared cell).
        data = parse_xml(XML_3X3)
        self.assertEqual(data["across_clues"], {1: "Feline"})
        self.assertEqual(data["down_clues"], {1: "Feline"})

    def test_2d_blocked_squares(self):
        data = parse_xml(XML_3X3)
        # Row 1: A## → indices 4, 5 blocked. Row 2: T## → indices 7, 8 blocked.
        self.assertEqual(sorted(data["blocked_out_squares"]), [4, 5, 7, 8])


# ---------------------------------------------------------------------------
# render_xd
# ---------------------------------------------------------------------------


class RenderXdTest(TestCase):
    """Tests for render_xd(): the counterpart to ParseXdTest, checking the
    xd text it produces from a Crossword instance."""

    fixtures = ["users.json"]

    def _cw_with_entry(self, **kwargs):
        """1×3 crossword with a single 1A entry, clue 'A feline'."""
        cw = make_crossword(name="Test Puzzle", cells=["C", "A", "T"], **kwargs)
        word, _ = Word.objects.get_or_create(text="CAT")
        clue = Clue.objects.create(text=word, clue="A feline")
        Entry.objects.create(
            crossword=cw, word=word, clue=clue, number=1, direction=Entry.ACROSS
        )
        return cw

    def test_title_header(self):
        # Title is always emitted, unlike the optional headers below.
        out = render_xd(self._cw_with_entry())
        self.assertIn("Title: Test Puzzle", out)

    def test_author_header_present_when_set(self):
        out = render_xd(self._cw_with_entry(authors="A Setter"))
        self.assertIn("Author: A Setter", out)

    def test_author_header_absent_when_blank(self):
        # A blank authors field should omit the header line entirely,
        # not emit "Author: ".
        out = render_xd(self._cw_with_entry(authors=""))
        self.assertNotIn("Author:", out)

    def test_editor_header_present_when_set(self):
        out = render_xd(self._cw_with_entry(editors="An Editor"))
        self.assertIn("Editor: An Editor", out)

    def test_editor_header_absent_when_blank(self):
        # Mirrors test_author_header_absent_when_blank for the Editor header.
        out = render_xd(self._cw_with_entry(editors=""))
        self.assertNotIn("Editor:", out)

    def test_copyright_header(self):
        # Unlike Author/Editor, Copyright is unconditional (the model
        # always has a value via default_copyright()), so it's covered
        # here rather than with a present/absent pair.
        out = render_xd(self._cw_with_entry(copyright="2022 Test"))
        self.assertIn("Copyright: 2022 Test", out)

    def test_grid_row_contains_letters(self):
        out = render_xd(self._cw_with_entry())
        self.assertIn("CAT", out)

    def test_blocked_cell_renders_as_hash(self):
        cw = make_crossword(cells=["C", "", "T"], blocked_out_squares=[1])
        out = render_xd(cw)
        self.assertIn("C#T", out)

    def test_empty_white_cell_renders_as_dot(self):
        # A cell that's white but has no letter yet (partial slot) renders
        # as "." -- distinct from "#" for an actual block.
        cw = make_crossword(cells=["", "", ""])
        out = render_xd(cw)
        self.assertIn("...", out)

    def test_across_clue_line(self):
        out = render_xd(self._cw_with_entry())
        self.assertIn("A1. A feline ~ CAT", out)

    def test_down_clue_line(self):
        cw = make_crossword(
            num_rows=3,
            num_cols=3,
            cells=["C", "A", "T", "A", "", "", "T", "", ""],
            blocked_out_squares=[4, 5, 7, 8],
        )
        word, _ = Word.objects.get_or_create(text="CAT")
        clue = Clue.objects.create(text=word, clue="Feline")
        Entry.objects.create(
            crossword=cw, word=word, clue=clue, number=1, direction=Entry.DOWN
        )
        out = render_xd(cw)
        self.assertIn("D1. Feline ~ CAT", out)

    def test_entry_without_clue_renders_empty_clue_text(self):
        # An entry with no clue object should still appear with an empty clue field.
        cw = make_crossword(cells=["C", "A", "T"])
        word, _ = Word.objects.get_or_create(text="CAT")
        Entry.objects.create(
            crossword=cw, word=word, clue=None, number=1, direction=Entry.ACROSS
        )
        out = render_xd(cw)
        self.assertIn("A1.  ~ CAT", out)

    def test_across_before_down(self):
        # The clues section always lists every across clue before any down
        # clue, regardless of entry creation order (both are created with
        # the same number 1 here).
        cw = make_crossword(
            num_rows=3,
            num_cols=3,
            cells=["C", "A", "T", "A", "", "", "T", "", ""],
            blocked_out_squares=[4, 5, 7, 8],
        )
        word, _ = Word.objects.get_or_create(text="CAT")
        clue = Clue.objects.create(text=word, clue="Feline")
        Entry.objects.create(
            crossword=cw, word=word, clue=clue, number=1, direction=Entry.ACROSS
        )
        Entry.objects.create(
            crossword=cw, word=word, clue=clue, number=1, direction=Entry.DOWN
        )
        out = render_xd(cw)
        self.assertLess(out.index("A1."), out.index("D1."))


# ---------------------------------------------------------------------------
# save_crossword_from_xd
# ---------------------------------------------------------------------------


class SaveCrosswordFromXdTest(TestCase):
    """Tests for save_crossword_from_xd(): building a Crossword (and its
    Word/Clue/Entry rows) from an already-parsed xd dict."""

    fixtures = ["users.json"]

    XD_DATA = {
        "name": "Test",
        "authors": "Author",
        "editors": "Editor",
        "copyright": "2022 Test",
        "size": {"rows": 1, "cols": 3},
        "grid": ["C", "A", "T"],
        "blocked_out_squares": [],
        "across_clues": {1: "A feline"},
        "down_clues": {},
    }

    def test_creates_crossword_with_correct_fields(self):
        # The straightforward, one-to-one fields (name/authors/editors/
        # dimensions/cells) are copied over from the parsed dict as-is.
        cw = save_crossword_from_xd(self.XD_DATA)
        self.assertEqual(cw.name, "Test")
        self.assertEqual(cw.authors, "Author")
        self.assertEqual(cw.editors, "Editor")
        self.assertEqual(cw.num_rows, 1)
        self.assertEqual(cw.num_cols, 3)
        self.assertEqual(cw.cells, ["C", "A", "T"])

    def test_creates_word_entry_and_clue(self):
        # A complete slot gets a real Word/Clue/Entry chain, same as a
        # normal save from the edit screen would produce.
        cw = save_crossword_from_xd(self.XD_DATA)
        entry = Entry.objects.get(crossword=cw, number=1, direction=Entry.ACROSS)
        self.assertEqual(entry.word.text, "CAT")
        self.assertEqual(entry.clue.clue, "A feline")

    def test_partial_slot_produces_no_entry(self):
        # Mirrors crossword_save()'s own rule: an incomplete slot is kept
        # in `cells` but produces no Entry.
        data = {**self.XD_DATA, "grid": ["C", "", "T"]}
        cw = save_crossword_from_xd(data)
        self.assertFalse(Entry.objects.filter(crossword=cw).exists())

    def test_uses_copyright_from_xd(self):
        cw = save_crossword_from_xd(self.XD_DATA)
        self.assertEqual(cw.copyright, "2022 Test")

    def test_falls_back_to_model_default_when_copyright_absent(self):
        # When the xd file has no copyright, the model's default_copyright()
        # callable should fill in a GroundUp News string.
        data = {**self.XD_DATA, "copyright": ""}
        cw = save_crossword_from_xd(data)
        self.assertIn("GroundUp News", cw.copyright)

    def test_replace_deletes_existing_crossword(self):
        # replace=True deletes any same-named crossword before creating the
        # new one, so re-saving from the same xd file updates in place.
        cw1 = save_crossword_from_xd(self.XD_DATA)
        cw2 = save_crossword_from_xd(self.XD_DATA, replace=True)
        self.assertFalse(Crossword.objects.filter(pk=cw1.pk).exists())
        self.assertTrue(Crossword.objects.filter(pk=cw2.pk).exists())

    def test_no_replace_keeps_existing_crossword(self):
        # Without replace=True (the default), saving the same data twice
        # creates two separate crosswords rather than colliding.
        save_crossword_from_xd(self.XD_DATA)
        save_crossword_from_xd(self.XD_DATA, replace=False)
        self.assertEqual(Crossword.objects.filter(name="Test").count(), 2)


# ---------------------------------------------------------------------------
# xd export view
# ---------------------------------------------------------------------------


class CrosswordXdExportViewTest(TestCase):
    """Tests for crossword_xd(): the .xd download endpoint, which is
    intentionally open to everyone regardless of login or permission."""

    fixtures = ["users.json"]

    def setUp(self):
        self.cw = make_crossword(name="My Puzzle", cells=["C", "A", "T"])
        word, _ = Word.objects.get_or_create(text="CAT")
        clue = Clue.objects.create(text=word, clue="A feline")
        Entry.objects.create(
            crossword=self.cw, word=word, clue=clue, number=1, direction=Entry.ACROSS
        )

    def test_status_200(self):
        response = self.client.get(reverse("crossword_xd", args=[self.cw.pk]))
        self.assertEqual(response.status_code, 200)

    def test_content_type_is_plain_text(self):
        response = self.client.get(reverse("crossword_xd", args=[self.cw.pk]))
        self.assertIn("text/plain", response["Content-Type"])

    def test_content_disposition_is_attachment_with_xd_filename(self):
        response = self.client.get(reverse("crossword_xd", args=[self.cw.pk]))
        cd = response["Content-Disposition"]
        self.assertIn("attachment", cd)
        self.assertIn("My Puzzle.xd", cd)

    def test_anonymous_user_can_export(self):
        # Export requires no login.
        response = self.client.get(reverse("crossword_xd", args=[self.cw.pk]))
        self.assertEqual(response.status_code, 200)

    def test_user_without_permission_can_export(self):
        # Mirrors test_anonymous_user_can_export: even a logged-in user
        # without can_generate_crosswords can still export.
        User.objects.create_user(username="noperm", password="testpass")
        self.client.login(username="noperm", password="testpass")
        response = self.client.get(reverse("crossword_xd", args=[self.cw.pk]))
        self.assertEqual(response.status_code, 200)

    def test_response_contains_title_header(self):
        # Sanity check that the response body is genuinely render_xd()'s
        # output, not just the right status/headers.
        body = self.client.get(
            reverse("crossword_xd", args=[self.cw.pk])
        ).content.decode()
        self.assertIn("Title: My Puzzle", body)

    def test_response_contains_clue_line(self):
        body = self.client.get(
            reverse("crossword_xd", args=[self.cw.pk])
        ).content.decode()
        self.assertIn("A1. A feline ~ CAT", body)


# ---------------------------------------------------------------------------
# xd import view
# ---------------------------------------------------------------------------


class CrosswordXdImportViewTest(TestCase):
    """Tests for crossword_import(): the .xd upload endpoint, gated behind
    can_generate_crosswords."""

    fixtures = ["users.json"]

    def setUp(self):
        make_user_with_perm(self.client)

    def _import(self, body=XD_1ROW):
        """POSTs `body` as a raw .xd file to the import endpoint."""
        return self.client.post(
            reverse("crossword_import"),
            data=body,
            content_type="text/plain; charset=utf-8",
        )

    def test_creates_crossword_with_correct_fields(self):
        response = self._import()
        self.assertEqual(response.status_code, 200)
        cw = Crossword.objects.get()
        self.assertEqual(cw.name, "Test Puzzle")
        self.assertEqual(cw.authors, "Test Author")
        self.assertEqual(cw.cells, ["C", "A", "T"])

    def test_creates_entry_and_clue(self):
        self._import()
        cw = Crossword.objects.get()
        entry = Entry.objects.get(crossword=cw, number=1, direction=Entry.ACROSS)
        self.assertEqual(entry.word.text, "CAT")
        self.assertEqual(entry.clue.clue, "A feline")

    def test_returns_redirect_url_to_edit_screen(self):
        # The client-side import flow (select.html) navigates to whatever
        # URL this response carries, straight into the edit screen.
        response = self._import()
        cw = Crossword.objects.get()
        self.assertEqual(
            response.json()["redirect"],
            reverse("crossword_edit", args=[cw.pk]),
        )

    def test_reimport_replaces_existing_crossword(self):
        # Importing the same puzzle twice should leave exactly one crossword
        # in the database (the old one deleted, a new one created).
        self._import()
        first_pk = Crossword.objects.get().pk
        self._import()
        self.assertEqual(Crossword.objects.count(), 1)
        self.assertNotEqual(Crossword.objects.get().pk, first_pk)

    def test_empty_body_returns_400(self):
        # An empty upload parses to a zero-row grid, which the view treats
        # as invalid input rather than silently creating an empty puzzle.
        response = self._import("")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Crossword.objects.exists())

    def test_anonymous_user_cannot_import(self):
        self.client.logout()
        response = self._import()
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Crossword.objects.exists())

    def test_user_without_permission_cannot_import(self):
        # Unlike export, import is a write action and requires the
        # generate permission even when logged in.
        self.client.logout()
        User.objects.create_user(username="noperm", password="testpass")
        self.client.login(username="noperm", password="testpass")
        response = self._import()
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Crossword.objects.exists())


# ---------------------------------------------------------------------------
# xml import view
# ---------------------------------------------------------------------------


class CrosswordXmlImportViewTest(TestCase):
    """Tests for crossword_import()'s xml branch: the X-Filename header
    picks parse_xml over parse_xd when it ends in .xml."""

    fixtures = ["users.json"]

    def setUp(self):
        make_user_with_perm(self.client)

    def _import(self, body=XML_1ROW, filename="puzzle.xml"):
        return self.client.post(
            reverse("crossword_import"),
            data=body,
            content_type="text/plain; charset=utf-8",
            HTTP_X_FILENAME=filename,
        )

    def test_creates_crossword_with_correct_fields(self):
        response = self._import()
        self.assertEqual(response.status_code, 200)
        cw = Crossword.objects.get()
        self.assertEqual(cw.name, "Test Puzzle")
        self.assertEqual(cw.authors, "Test Author")
        self.assertEqual(cw.cells, ["C", "A", "T"])

    def test_creates_entry_and_clue(self):
        self._import()
        cw = Crossword.objects.get()
        entry = Entry.objects.get(crossword=cw, number=1, direction=Entry.ACROSS)
        self.assertEqual(entry.word.text, "CAT")
        self.assertEqual(entry.clue.clue, "A feline")

    def test_filename_extension_is_case_insensitive(self):
        response = self._import(filename="puzzle.XML")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Crossword.objects.get().cells, ["C", "A", "T"])

    def test_missing_filename_falls_back_to_xd_parser(self):
        # No X-Filename header (older clients, or a direct API call) should
        # keep working exactly as it did before .xml support existed: the
        # body is parsed as .xd, so posting xml content here fails to parse
        # as xd's line-based grid and is rejected rather than silently
        # misread.
        response = self.client.post(
            reverse("crossword_import"),
            data=XML_1ROW,
            content_type="text/plain; charset=utf-8",
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_xml_returns_400(self):
        response = self._import(body="not xml")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Crossword.objects.exists())


# ---------------------------------------------------------------------------
# Round-trip: parse → save → render → re-parse
# ---------------------------------------------------------------------------


class XdRoundTripTest(TestCase):
    """Parse -> save -> render -> re-parse: checks parse_xd and render_xd
    agree with each other, beyond what testing each in isolation shows."""

    fixtures = ["users.json"]

    def test_grid_survives_round_trip(self):
        # After parsing, saving, and re-rendering, the re-parsed grid and blocked
        # squares should match the originally parsed values.
        original = parse_xd(XD_3X3)
        cw = save_crossword_from_xd(original)
        rendered = render_xd(cw)
        reparsed = parse_xd(rendered)
        self.assertEqual(reparsed["grid"], original["grid"])
        self.assertEqual(
            sorted(reparsed["blocked_out_squares"]),
            sorted(original["blocked_out_squares"]),
        )

    def test_clues_survive_round_trip(self):
        # Mirrors test_grid_survives_round_trip for the clue dicts.
        original = parse_xd(XD_3X3)
        cw = save_crossword_from_xd(original)
        rendered = render_xd(cw)
        reparsed = parse_xd(rendered)
        self.assertEqual(reparsed["across_clues"], original["across_clues"])
        self.assertEqual(reparsed["down_clues"], original["down_clues"])


# ---------------------------------------------------------------------------
# cwutils — bridges its standalone unittest suite into ./manage.py test
# ---------------------------------------------------------------------------


class CwutilsSuiteTest(unittest.TestCase):
    """cwutils/test.py is written to run standalone from inside cwutils/: it
    imports its sibling cwutils.py as a bare top-level module and opens
    "british-english" by a path relative to that directory. Discovering it
    with cwutils/ as top_level_dir satisfies the import, and running from
    that directory satisfies the file open.
    """

    def test_cwutils_suite_passes(self):
        cwutils_dir = os.path.join(os.path.dirname(__file__), "cwutils")
        suite = unittest.TestLoader().discover(
            start_dir=cwutils_dir, pattern="test.py", top_level_dir=cwutils_dir
        )
        result = unittest.TestResult()
        cwd = os.getcwd()
        os.chdir(cwutils_dir)
        try:
            suite.run(result)
        finally:
            os.chdir(cwd)
        if not result.wasSuccessful():
            problems = result.failures + result.errors
            details = "\n".join(f"{test}:\n{trace}" for test, trace in problems)
            self.fail(
                f"cwutils test suite: {len(problems)} failure(s)/error(s):\n{details}"
            )
