"""
Nathan wrote this code by hand. Claude made some improvements (adding a tie-breaker, the mean, to the words_freedom result).
It fetches the best words (answers) for a given slot (using the words_freedom method).
"""

from fnmatch import fnmatch


class WordIndex:
    """Precomputed lookups over a word list: words bucketed by length, and
    a glob->matches cache. Built once per distinct word list and shared by
    every Grid copied from it, so pattern-matching work done for one search
    branch is reused by every sibling branch instead of being redone.

    Tracks the word list's length so words appended to it after
    construction (as Grid.words is, e.g. in tests) still get indexed and
    considered -- mirrors the old behaviour of scanning grid.words live on
    every call."""

    def __init__(self, words):
        self._words = words
        self._indexed_count = 0
        self.by_length = {}
        self._glob_cache = {}
        self._sync()

    def _sync(self):
        if self._indexed_count == len(self._words):
            return
        for w in self._words[self._indexed_count :]:
            self.by_length.setdefault(len(w), []).append(w)
        self._indexed_count = len(self._words)
        self._glob_cache = {}  # newly indexed words can change past results

    def matches(self, glob):
        self._sync()
        if glob not in self._glob_cache:
            candidates = self.by_length.get(len(glob), [])
            self._glob_cache[glob] = [w for w in candidates if fnmatch(w, glob)]
        return self._glob_cache[glob]


class Slot:
    """One across or down run in a Grid: its position, length, the flat
    cell indices it covers, and matching helpers against the grid's word
    list. Constructed by Grid.calc_slots(); not usually built directly."""

    def _len_across(self):
        """Counts cells rightward from self.start until the row wraps
        (i % cols == 0) or a block is hit. Runs of length 1 aren't
        filtered out here -- Grid.calc_slots() does that afterwards."""
        len = 1
        for i in range(self.start + 1, self.start + self.grid.cols):
            if i % self.grid.cols == 0 or self.grid.cells[i] == "#":
                break
            len += 1
        return len

    def _len_down(self):
        """Counts cells downward from self.start (stepping by a full row
        width) until the grid ends or a block is hit."""
        len = 1
        for i in range(
            self.start + self.grid.cols, self.grid.rows * self.grid.cols, self.grid.cols
        ):
            if self.grid.cells[i] == "#":
                break
            len += 1
        return len

    def _set_cells(self):
        """Populates self.cells with the flat indices of every cell in the
        slot, in reading order, stepping by 1 (across) or by the grid's
        column count (down)."""
        self.cells = []
        if self.dir == "A":
            step = 1
        else:
            step = self.grid.cols
        start = self.start
        end = self.start + step * len(self)
        for i in range(start, end, step):
            self.cells.append(i)

    def __init__(self, grid, dir, id, row, col):
        """Builds the slot starting at (row, col) in `grid`, running in
        direction `dir` ("A" or "D"); computes its length and cell indices
        immediately so every other method can assume they're ready."""
        self.grid = grid
        self.dir = dir
        self.id = id
        self.row = row
        self.col = col
        self.start = row * grid.cols + col
        if self.dir == "A":
            self._len = self._len_across()
        else:
            self._len = self._len_down()
        self._set_cells()
        self._intersections = []

    def __len__(self):
        return self._len

    def __str__(self):
        # Debug representation: id+direction, start cell, every subsequent
        # cell index in the run, then the length in brackets.
        s = f"{self.id}{self.dir}: [{self.row}, {self.col}] ({self.start}"
        step = 1
        if self.dir == "D":
            step = self.grid.cols
        for i in range(self.start + step, self.start + len(self) * step, step):
            s += " " + str(i)
        s += f") [{len(self)}]"
        return s[:-1]

    def complete(self):
        for i in self.cells:
            if self.grid.cells[i] == "-":
                return False
        return True

    def intersections(self):
        """The perpendicular slot crossing each of this slot's cells, in
        cell order (across slots return their crossing down slots, and
        vice versa). A cell with no real crossing slot -- e.g. it sits in
        an isolated single-cell run -- contributes nothing to the result,
        so the returned list can be shorter than this slot's length."""
        result = []
        dir = "A" if self.dir == "D" else "D"
        for cell in self.cells:
            slot = self.grid.slot_for_cell(dir, cell)
            if slot:
                result.append(slot)
        return result

    def intersecting_cell_index(self, intersection):
        """Finds the shared grid cell between this slot and `intersection`,
        returning (index within intersection.cells, index within
        self.cells), or (-1, -1) if they don't actually cross."""
        for i in range(len(intersection.cells)):
            for j in range(len(self.cells)):
                if intersection.cells[i] == self.cells[j]:
                    return (i, j)
        return (-1, -1)

    def glob(self):
        """The slot's current contents as an fnmatch pattern: filled cells
        become their letter, blank cells ("-") become the "?" wildcard."""
        glob = [" "] * len(self)
        j = 0
        for i in self.cells:
            letter = self.grid.cells[i]
            glob[j] = "?" if letter == "-" else letter
            j += 1
        return "".join(glob)

    def words(self):
        """Every word in the grid's word list matching this slot's current
        glob pattern (i.e. the right length and consistent with any
        letters already filled in)."""
        return self.grid.word_index.matches(self.glob())

    def words_freedom(self):
        """Ranks this slot's candidate words (from words()) by how much
        freedom each leaves in its crossing slots, most promising first.

        For every candidate and every crossing slot that still has an
        unresolved (blank) intersecting cell, computes how many
        dictionary words of the right length could still fill that
        crossing if the candidate were placed -- already-filled crossings,
        and cells with no real crossing slot, are skipped entirely, so a
        candidate can end up with an empty score list. Results are cached
        per crossing pattern in the grid's WordIndex, shared across the
        whole search, since many candidates -- and many sibling search
        branches -- produce the same crossing pattern.

        Candidates are sorted by their worst (minimum) crossing score
        first, so a word that's fine everywhere except one badly
        constrained crossing loses to one that's evenly okay; the mean of
        all crossing scores breaks ties between candidates with the same
        worst score.

        Returns a list of (word, worst, mean) tuples -- the per-crossing
        scores themselves are only ever used to derive these two numbers,
        so there's no reason to hand the whole list back to callers. When
        the slot has no active crossings at all (every cell either already
        filled or structurally uncrossed, e.g. a run whose perpendicular
        run is length 1), every candidate is equally un-rankable: worst and
        mean are both None rather than a misleading 0 -- 0 would read as
        "this word is unusable" when really there's nothing to judge it
        against, and every candidate is left in words()' original order.
        See fetch_algorirthm.md for the original pseudocode this replaced.
        """

        def min_no_error(lst):
            try:
                return min(lst)
            except ValueError:
                return 0

        def mean(lst):
            return sum(lst) / len(lst) if lst else 0

        word_index = self.grid.word_index
        self_words = self.words()
        self_glob = self.glob()

        # (intersection, i, j) only depends on slot geometry and the
        # current grid state, not on the candidate word, so it's computed
        # once here rather than once per candidate per intersection.
        active_crossings = []
        for intersection in self.intersections():
            (i, j) = self.intersecting_cell_index(intersection)
            if self_glob[j] != "?":
                continue
            active_crossings.append((intersection, i, j))

        result = {}
        for word in self_words:
            scores = []
            for intersection, i, j in active_crossings:
                glob_list = list(intersection.glob())
                glob_list[i] = word[j]
                glob = "".join(glob_list)
                scores.append(len(word_index.matches(glob)))
            result[word] = scores

        arr = [(word, min_no_error(scores), mean(scores)) for word, scores in result.items()]
        arr = sorted(arr, key=lambda tpl: (tpl[1], tpl[2]), reverse=True)
        if not active_crossings:
            arr = [(word, None, None) for word, _, _ in arr]
        return arr

    def fill(self, word):
        assert len(word) == self._len
        for i in range(self._len):
            self.grid.cells[self.cells[i]] = word[i]

    def get(self):
        word = [" "] * len(self)
        for i in range(self._len):
            word[i] = self.grid.cells[self.cells[i]]
        return "".join(word)

    def clone_for(self, grid):
        """A copy of this slot bound to `grid` instead of its original
        grid. Geometry (dir/id/row/col/start/length/cells) never changes
        between a Grid and its copies, so it's carried over as-is rather
        than recomputed -- only the grid reference actually differs."""
        clone = Slot.__new__(Slot)
        clone.grid = grid
        clone.dir = self.dir
        clone.id = self.id
        clone.row = self.row
        clone.col = self.col
        clone.start = self.start
        clone._len = self._len
        clone.cells = self.cells
        clone._intersections = []
        return clone


class Grid:
    """A crossword grid parsed from a plain-text layout, with its numbered
    Slots and (optionally) a word list to match candidates against."""

    words = []  # fallback when __init__ isn't given a word list

    def __init__(self, string: str, words=None):
        """Parses `string` (one grid row per line; "#" for a block, "-" for
        a blank white cell, A-Z for a filled cell) into a flat cell list,
        infers rows/cols from the line breaks and longest line, and
        computes the grid's numbered slots. `words` is the dictionary
        words() and words_freedom() will match candidates against."""
        if words:
            self.words = words
        self.word_index = WordIndex(self.words)
        self.cells = []
        rows = 0
        cols = 0
        max_cols = 0
        for c in string:
            if c == "#" or c == "-" or (c >= "A" and c <= "Z"):
                self.cells.append(c)
                cols += 1
            if c == "\n" and cols > 0:
                rows += 1
                if cols > max_cols:
                    max_cols = cols
                cols = 0
        self.rows = rows
        self.cols = max_cols
        self.slots = sorted(
            self.calc_slots(), key=lambda slot: f"{slot.dir}{slot.id:03}"
        )
        self._build_cell_slot_index()

    def _I(self, r: int, c: int):
        """Flat cell index for (row, col), asserting both are in bounds."""
        assert r >= 0 and r < self.rows and c >= 0 and c < self.cols
        return r * self.cols + c

    def __str__(self):
        # Renders the grid back out as one line of cell characters per row.
        result = ""
        for r in range(self.rows):
            for c in range(self.cols):
                result += self.cells[self._I(r, c)]
            result += "\n"
        return result

    def calc_slots(self):
        """Builds every Slot in the grid, numbered and ordered the way
        Grid.__init__ expects (see the sort key there: across slots first,
        then down, each ordered by id).

        Scans cells in row-major order. A slot is started at a cell
        whenever there's no white cell immediately to its left (across) or
        above it (down) -- edges of the grid count as "no white cell"
        there, same as a block would. Unlike grid.py's slots(), this does
        not check whether the run is actually longer than one cell before
        creating the Slot; instead every candidate start gets a Slot
        object, and the final list comprehension drops any whose computed
        length (via Slot.__len__) turns out to be 1. A cell that starts
        both an across and a down slot shares one id between them, exactly
        as standard crossword numbering requires.
        """

        # Records that cell (r, c) starts a slot in direction `dir`, using
        # the number not yet incremented for this cell. inc_slot_num flags
        # that at least one slot started here, so the outer loop bumps
        # slot_num once per cell rather than once per direction.
        def push_slot(dir, r, c):
            nonlocal inc_slot_num
            nonlocal slots
            inc_slot_num = True
            slots.append(Slot(grid=self, dir=dir, id=slot_num, row=r, col=c))

        inc_slot_num = False
        slots = []
        slot_num = 1
        for r in range(self.rows):
            for c in range(self.cols):
                inc_slot_num = False
                cell = self.cells[self._I(r, c)]
                if cell == "#":
                    continue
                if c == 0:
                    push_slot("A", r, c)
                if r == 0:
                    push_slot("D", r, c)
                if c > 0 and self.cells[self._I(r, c - 1)] == "#":
                    push_slot("A", r, c)
                if r > 0 and self.cells[self._I(r - 1, c)] == "#":
                    push_slot("D", r, c)
                if inc_slot_num:
                    slot_num += 1
        return [slot for slot in slots if len(slot) > 1]

    def _build_cell_slot_index(self):
        """Maps (dir, cell) -> the slot covering it, so slot_for_cell() is
        an O(1) lookup instead of scanning every slot's cell list. Rebuilt
        once whenever slots are (re)computed -- geometry is invariant
        across copies, but each copy's slots are distinct objects bound to
        that copy's grid, so the index can't simply be shared."""
        self._cell_slot = {}
        for slot in self.slots:
            for cell in slot.cells:
                self._cell_slot[(slot.dir, cell)] = slot

    def slot_for_cell(self, dir, cell):
        """The slot running in `dir` that covers flat cell index `cell`,
        or None if there isn't one (e.g. `cell` is blocked, or its run in
        that direction is only one cell long and so isn't a real slot)."""
        return self._cell_slot.get((dir, cell))

    def copy(self):
        """A copy with its own independent `cells`, safe to mutate without
        affecting the original -- used constantly by auto_complete's
        search to branch without disturbing the caller's grid. Block
        layout never changes between a grid and its copies, so slot
        geometry is cloned rather than recomputed from a re-parsed string,
        and the shared word_index (built once, off the word list, which
        also never changes) is reused as-is."""
        new_grid = Grid.__new__(Grid)
        new_grid.words = self.words
        new_grid.word_index = self.word_index
        new_grid.rows = self.rows
        new_grid.cols = self.cols
        new_grid.cells = list(self.cells)
        new_grid.slots = [slot.clone_for(new_grid) for slot in self.slots]
        new_grid._build_cell_slot_index()
        return new_grid

    def complete(self):
        for s in self.slots:
            if s.complete() is False:
                return False
        return True

import time
MAX_ATTEMPTS = 500

# This is still work in progress
def auto_complete(grid):

    attempt = 0

    def auto_complete_(grid):
        nonlocal attempt
        attempt +=1 
        if attempt >= MAX_ATTEMPTS:
            print("Returning grid after max attempts", attempt)
            return grid
        g = grid.copy()
        slots = [s for s in g.slots if not s.complete()]
        answers = [s.get() for s in g.slots if s.complete()]
        for s in slots:
            if s.complete():
                continue
            blank = s.get()
            words = [w[0] for w in s.words_freedom() if (w[1] is None or w[1] > 0) and w[0] not in answers][:20]
            for word in words:
                s.fill(word)
                h = auto_complete_(g)
                if attempt >= MAX_ATTEMPTS:
                    print("Returning h after max attempts", attempt)
                    return h
                if h.complete():
                    print("Returning h", attempt)
                    return h
            s.fill(blank)
        print("Returning g", attempt)
        return g

    start_time = time.perf_counter()
    result = auto_complete_(grid)
    end_time = time.perf_counter()
    execution_time = end_time - start_time
    print(f"Execution time: {execution_time:.6f} seconds")
    return result
