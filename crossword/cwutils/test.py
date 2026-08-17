import unittest
from cwutils import Grid, Slot, auto_complete
import re

WORD_RE = re.compile(r"^[A-Z]+$")


def get_words(path="british-english"):
    """Loads the real dictionary word list, uppercased, keeping only
    entries that are pure A-Z (so hyphenated/apostrophe'd dictionary
    entries are excluded -- they'd never match a crossword slot anyway)."""
    with open(path, encoding="utf-8") as f:
        return [word for line in f if WORD_RE.match(word := line.strip().upper())]


class TestGrid(unittest.TestCase):
    """Tests Grid parsing and slot geometry using two same-shaped grids:
    cw1 has real letters, cw2 has the identical block pattern but blank
    cells -- so any test that should be content-independent (e.g. the
    slots themselves) is checked as identical across both."""

    cw1 = """
#BIB#
BIERS
ON#IS
OGLED
#OOF#
"""

    cw2 = """
#---#
-----
--#--
-----
#---#
"""

    cw3 = """
#BI-#
BIERS
ON#IS
OGLED
#OO-#
"""

    def setUp(self):
        self.grid1 = Grid(self.cw1, get_words())
        self.grid2 = Grid(self.cw2, get_words())
        self.grid3 = Grid(self.cw3, get_words())

    def test_grid(self):
        # Both grids share the dictionary and the same dimensions, but
        # aren't equal as Slot objects (different Grid instances), even
        # though their geometry matches -- see test_slots below for that.
        self.assertEqual(self.grid1.rows, 5)
        self.assertEqual(self.grid1.cols, 5)
        self.assertGreater(len(self.grid1.words), 1000)
        self.assertEqual(self.grid2.rows, 5)
        self.assertEqual(self.grid2.cols, 5)
        self.assertEqual(self.grid1.words, self.grid2.words)
        self.assertNotEqual(self.grid1.slots, self.grid2.slots)

    def test_copy(self):
        grid_copy = Grid(str(self.grid1), get_words())
        self.assertEqual(grid_copy.cells, self.grid1.cells)
        grid_copy = self.grid3.copy()
        self.assertEqual(grid_copy.cells, self.grid3.cells)

    def test_slots(self):
        # Walks every slot cwutils finds in cw1, checking its id,
        # direction, start position and length against the puzzle's known
        # geometry (hand-derived from the cw1 layout above) -- this is
        # what pins down calc_slots()'s numbering and ordering behaviour.
        # The final loop then re-checks the same geometry against cw2,
        # confirming slot detection only depends on the block pattern, not
        # on which letters (if any) fill the white cells.
        self.assertEqual(self.grid1.slots[0].id, 1)
        self.assertEqual(self.grid1.slots[0].dir, "A")
        self.assertEqual(self.grid1.slots[0].row, 0)
        self.assertEqual(self.grid1.slots[0].col, 1)
        self.assertEqual(self.grid1.slots[0].start, 1)
        self.assertEqual(len(self.grid1.slots[0]), 3)

        self.assertEqual(self.grid1.slots[1].id, 4)
        self.assertEqual(self.grid1.slots[1].dir, "A")
        self.assertEqual(self.grid1.slots[1].row, 1)
        self.assertEqual(self.grid1.slots[1].col, 0)
        self.assertEqual(self.grid1.slots[1].start, 5)
        self.assertEqual(len(self.grid1.slots[1]), 5)

        self.assertEqual(self.grid1.slots[2].id, 6)
        self.assertEqual(self.grid1.slots[2].dir, "A")
        self.assertEqual(self.grid1.slots[2].row, 2)
        self.assertEqual(self.grid1.slots[2].col, 0)
        self.assertEqual(self.grid1.slots[2].start, 10)
        self.assertEqual(len(self.grid1.slots[2]), 2)

        self.assertEqual(self.grid1.slots[3].id, 7)
        self.assertEqual(self.grid1.slots[3].dir, "A")
        self.assertEqual(self.grid1.slots[3].row, 2)
        self.assertEqual(self.grid1.slots[3].col, 3)
        self.assertEqual(self.grid1.slots[3].start, 13)
        self.assertEqual(len(self.grid1.slots[3]), 2)

        self.assertEqual(self.grid1.slots[4].id, 8)
        self.assertEqual(self.grid1.slots[4].dir, "A")
        self.assertEqual(self.grid1.slots[4].row, 3)
        self.assertEqual(self.grid1.slots[4].col, 0)
        self.assertEqual(self.grid1.slots[4].start, 15)
        self.assertEqual(len(self.grid1.slots[4]), 5)

        self.assertEqual(self.grid1.slots[5].id, 10)
        self.assertEqual(self.grid1.slots[5].dir, "A")
        self.assertEqual(self.grid1.slots[5].row, 4)
        self.assertEqual(self.grid1.slots[5].col, 1)
        self.assertEqual(self.grid1.slots[5].start, 21)
        self.assertEqual(len(self.grid1.slots[5]), 3)

        self.assertEqual(self.grid1.slots[6].id, 1)
        self.assertEqual(self.grid1.slots[6].dir, "D")
        self.assertEqual(self.grid1.slots[6].row, 0)
        self.assertEqual(self.grid1.slots[6].col, 1)
        self.assertEqual(self.grid1.slots[6].start, 1)
        self.assertEqual(len(self.grid1.slots[6]), 5)

        self.assertEqual(self.grid1.slots[7].id, 2)
        self.assertEqual(self.grid1.slots[7].dir, "D")
        self.assertEqual(self.grid1.slots[7].row, 0)
        self.assertEqual(self.grid1.slots[7].col, 2)
        self.assertEqual(self.grid1.slots[7].start, 2)
        self.assertEqual(len(self.grid1.slots[7]), 2)

        self.assertEqual(self.grid1.slots[8].id, 3)
        self.assertEqual(self.grid1.slots[8].dir, "D")
        self.assertEqual(self.grid1.slots[8].row, 0)
        self.assertEqual(self.grid1.slots[8].col, 3)
        self.assertEqual(self.grid1.slots[8].start, 3)
        self.assertEqual(len(self.grid1.slots[8]), 5)

        self.assertEqual(self.grid1.slots[9].id, 4)
        self.assertEqual(self.grid1.slots[9].dir, "D")
        self.assertEqual(self.grid1.slots[9].row, 1)
        self.assertEqual(self.grid1.slots[9].col, 0)
        self.assertEqual(self.grid1.slots[9].start, 5)
        self.assertEqual(len(self.grid1.slots[9]), 3)

        self.assertEqual(self.grid1.slots[10].id, 5)
        self.assertEqual(self.grid1.slots[10].dir, "D")
        self.assertEqual(self.grid1.slots[10].row, 1)
        self.assertEqual(self.grid1.slots[10].col, 4)
        self.assertEqual(self.grid1.slots[10].start, 9)
        self.assertEqual(len(self.grid1.slots[10]), 3)

        self.assertEqual(self.grid1.slots[11].id, 9)
        self.assertEqual(self.grid1.slots[11].dir, "D")
        self.assertEqual(self.grid1.slots[11].row, 3)
        self.assertEqual(self.grid1.slots[11].col, 2)
        self.assertEqual(self.grid1.slots[11].start, 17)
        self.assertEqual(len(self.grid1.slots[11]), 2)

        self.assertEqual(len(self.grid1.slots), len(self.grid2.slots))

        tuples = zip(self.grid1.slots, self.grid2.slots)
        for t in tuples:
            self.assertEqual(t[0].dir, t[1].dir)
            self.assertEqual(t[0].id, t[1].id)
            self.assertEqual(len(t[0]), len(t[1]))
            self.assertEqual(t[0].cells, t[1].cells)

    def test_intersection_slots(self):
        # Checks intersections() returns the correct crossing slots (in
        # cell order) and that intersecting_cell_index() correctly locates
        # the shared cell within each pair of crossing slots.
        intersections = self.grid1.slots[0].intersections()
        self.assertEqual(len(intersections), 3)
        self.assertEqual(intersections[0].dir, "D")
        self.assertEqual(intersections[1].dir, "D")
        self.assertEqual(intersections[2].dir, "D")
        self.assertEqual(intersections[0].id, 1)
        self.assertEqual(intersections[1].id, 2)
        self.assertEqual(intersections[2].id, 3)
        intersections = self.grid1.slots[3].intersections()
        self.assertEqual(len(intersections), 2)
        i = self.grid1.slots[3].intersecting_cell_index(intersections[0])
        self.assertEqual(i, (2, 0))

        i = self.grid1.slots[3].intersecting_cell_index(intersections[1])
        self.assertEqual(i, (1, 1))

    def test_complete_check(self):
        incomplete_slots = [s for s in self.grid3.slots if not s.complete()]
        self.assertEqual(len(self.grid3.slots), 12)
        self.assertEqual(len(incomplete_slots), 3)


class TestMatching(unittest.TestCase):
    """Tests glob()/words() against the real dictionary, using a grid with
    a couple of cells pre-filled so the glob pattern has fixed letters as
    well as wildcards."""

    cw1 = """
#---#
--A-Y
--#--
-----
#---#
"""

    def setUp(self):
        self.grid1 = Grid(self.cw1, get_words())

    def test_glob(self):
        # The blank cells in each slot become "?", and the two pre-filled
        # letters ("A" and "Y") pass straight through into the pattern.
        slot = self.grid1.slot_for_cell("A", 5)
        self.assertEqual(type(slot), Slot)
        if slot:
            glob = slot.glob()
            self.assertEqual(glob, "??A?Y")
        slot = self.grid1.slot_for_cell("D", 2)
        self.assertEqual(type(slot), Slot)
        if slot:
            glob = slot.glob()
            self.assertEqual(glob, "?A")

    def test_match(self):
        # Only checks the match count is "plausibly large" against the
        # real dictionary, not an exact word list -- that's covered by the
        # hand-built fixtures in TestWordsFreedom below.
        slot = self.grid1.slot_for_cell("A", 5)
        if slot:
            words = slot.words()
            self.assertGreater(len(words), 30)
        slot = self.grid1.slot_for_cell("D", 2)
        if slot:
            words = slot.words()
            self.assertGreater(len(words), 15)

    def test_words_freedom(self):
        # No assertion here -- this just exercises words_freedom() against
        # the real dictionary so it's caught if it raises. The
        # exactly-verified behaviour lives in TestWordsFreedom below.
        self.grid1.slots[1].words_freedom()
        print(self.grid1.slots[1].words_freedom())

# Claude added these tests
class TestWordsFreedom(unittest.TestCase):
    """Hand-built grids and word lists (not the real dictionary) so every
    expected score can be verified exactly rather than just bounded."""

    def test_ranks_by_worst_crossing_freedom_and_excludes_length_one_slots(self):
        # Row 0 is the target across slot, glob "?A?" (middle letter fixed).
        # Column 0 is blocked directly below row 0, so its down run is
        # length 1 -- not a real slot -- and must be excluded from scoring.
        # Column 1's down crossing always lands on the fixed middle letter,
        # so it never contributes. Column 2 has a real length-2 down run
        # and is the only crossing that should affect the ranking.
        #
        # If the length-1 run at column 0 were not excluded, every
        # candidate would pick up a spurious 0 from it (no 1-letter words
        # exist) and all four would tie at 0 instead of being ranked.
        grid = Grid("\n-A-\n#--\n", ["CAT", "MAT", "BAG", "RAN", "TO", "TI", "GO"])
        across = grid.slot_for_cell("A", 0)

        self.assertEqual(len(across.intersections()), 2)
        self.assertEqual(
            across.words_freedom(),
            [("CAT", 2, 2), ("MAT", 2, 2), ("BAG", 1, 1), ("RAN", 0, 0)],
        )

    def test_fully_resolved_slot_scores_zero_without_error(self):
        # Every cell of the target slot already holds a letter, so no
        # crossing is unresolved. words_freedom() must not raise (min() of
        # an empty list) and should report worst/mean as None -- there's no
        # crossing to judge the word against, so 0 would be misleading.
        grid = Grid("\nAT\n--\n", ["AT"])
        across = grid.slot_for_cell("A", 0)

        self.assertEqual(across.words_freedom(), [("AT", None, None)])

    def test_slot_with_no_crossings_at_all_scores_zero_without_error(self):
        # A single-row grid has no real down slots at all (every column
        # run is length 1, so none qualify as a slot). words_freedom()
        # must still return a result per candidate instead of raising, with
        # worst/mean of None rather than a misleading 0.
        grid = Grid("\n---\n", ["CAT", "DOG"])
        across = grid.slot_for_cell("A", 0)

        self.assertEqual(
            across.words_freedom(), [("CAT", None, None), ("DOG", None, None)]
        )

    def test_no_matching_words_returns_empty(self):
        # When words() itself finds nothing, words_freedom() should return
        # an empty list rather than erroring or returning a placeholder.
        grid = Grid("\nA-\n--\n", ["ZOO"])  # wrong length, doesn't match "A?"
        across = grid.slot_for_cell("A", 0)

        self.assertEqual(across.words_freedom(), [])

    def test_ties_on_worst_crossing_are_broken_by_mean(self):
        # ABC and ABD share their first two letters, so they get identical
        # scores on the first two crossings; they differ only in the third
        # letter, where ABD's crossing ("D?") has more matches than ABC's
        # ("C?"). Both tie at min=1, but ABD has the better mean and should
        # be ranked first -- without the tie-break they'd keep self_words'
        # original order (ABC before ABD).
        words = ["ABC", "ABD", "AT", "BE", "CO", "CA", "DO", "DA", "DE", "DI", "DU"]
        grid = Grid("\n---\n---\n", words)
        across = grid.slot_for_cell("A", 0)

        self.assertEqual(
            across.words_freedom(),
            [("ABD", 1, 7 / 3), ("ABC", 1, 4 / 3)],
        )


class TestAutoComplete(unittest.TestCase):
    cw1 = """
#BI-#
BIERS
ON#IS
OGLED
#OO-#
"""

    cw2 = """
#BIB#
BIERS
ON#IS
OGLED
#OOF#
"""

    cw3 = """
#---#
-----
--#--
-----
#---#
"""

    def setUp(self):
        self.grid1 = Grid(self.cw1, get_words())
        self.grid1.words.append("OOF")
        self.grid2 = Grid(self.cw3, get_words())

    def test_auto_complete(self):
        g = auto_complete(self.grid1)
        self.assertTrue(g.complete())
        self.assertEqual(g.cells, Grid(self.cw2, get_words()).cells)
        g = auto_complete(self.grid2)
        print(g)


if __name__ == "__main__":
    unittest.main()
