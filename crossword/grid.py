"""Slot detection and numbering for a crossword grid.

Pure logic, no Django dependency. Turns stored grid state (cells,
blocked_out_squares, dimensions) into numbered across/down slots.

Conventions:
- Cell index is row-major: index = row * num_cols + col.
- blocked_out_squares is the sole authority on which cells are black.
- A slot is a maximal run of >= 2 contiguous white cells in a row (across)
  or column (down). Isolated single white cells are not slots.
- A slot is complete when every cell in it holds a letter.
"""

from dataclasses import dataclass

ACROSS = "A"
DOWN = "D"

@dataclass(frozen=True)
class Slot:
    """A single numbered across or down run of white cells."""

    number: int
    direction: str  # ACROSS or DOWN
    start: int  # cell index of the first cell
    indices: tuple[int, ...]  # all cell indices, in reading order

    @property
    def length(self) -> int:
        """Number of cells the slot covers."""
        return len(self.indices)

    def letters(self, cells: list[str]) -> str:
        """The slot's current contents read in order, blanks included as ''."""
        return "".join(cells[i] for i in self.indices)

    def is_complete(self, cells: list[str]) -> bool:
        """True if every cell in the slot holds a letter (none are blank)."""
        # Claude: What does 'all' do?
        # Claude response: all(iterable) is a Python built-in that returns True if every
        # element in the iterable is truthy, False if any element is falsy. Here cells[i]
        # is a string — an empty string "" is falsy, any letter is truthy. So this returns
        # True only if every cell in the slot contains a letter (i.e. the slot is complete).
        return all(cells[i] for i in self.indices)


def slots(num_rows: int, num_cols: int, blocked_out_squares, cells) -> list[Slot]:
    """Return the numbered slots for the grid, in numbering order.

    Scans cells in row-major (reading) order. A cell starts a new number if
    it's white and either starts an across run (no white cell to its left,
    a white cell to its right) or a down run (no white cell above, a white
    cell below) -- standard crossword numbering convention. A cell that
    starts both gets one number shared by both the across and down slot.
    Runs of length 1 don't count as slots at all.
    """
    blocked = set(blocked_out_squares)

    def white(row: int, col: int) -> bool:
        """True if (row, col) is on the grid and not blocked. Off-grid
        coordinates count as not-white, so edge cells correctly look like
        they have no neighbour beyond the border."""
        if not (0 <= row < num_rows and 0 <= col < num_cols):
            return False
        return (row * num_cols + col) not in blocked

    result: list[Slot] = []
    number = 0
    for row in range(num_rows):
        for col in range(num_cols):
            if not white(row, col):
                continue

            starts_across = not white(row, col - 1) and white(row, col + 1)
            starts_down = not white(row - 1, col) and white(row + 1, col)
            if not (starts_across or starts_down):
                continue

            number += 1
            start = row * num_cols + col
            if starts_across:
                indices = []
                c = col
                while white(row, c):
                    indices.append(row * num_cols + c)
                    c += 1
                result.append(Slot(number, ACROSS, start, tuple(indices)))
            if starts_down:
                indices = []
                r = row
                while white(r, col):
                    indices.append(r * num_cols + col)
                    r += 1
                result.append(Slot(number, DOWN, start, tuple(indices)))

    return result
