"""Puzzle previews shared by the games hub and the public JSON API.

Each function reduces a puzzle to just enough to draw a teaser -- the
crossword's shape and clue numbers, the Target's nine letters, the
Sudoku's givens -- and deliberately leaves out everything that would
spoil it. A teaser is an invitation to solve, so no answers pass through
here, and nothing that reaches these functions needs hiding again later.
"""

from crossword import grid


def grid_preview(crossword):
    """Rows of {block, number} cells for a crossword's teaser grid."""
    numbers = {
        slot.start: slot.number
        for slot in grid.slots(
            crossword.num_rows,
            crossword.num_cols,
            crossword.blocked_out_squares,
            crossword.cells,
        )
    }
    blocked = set(crossword.blocked_out_squares)
    return [
        [
            {
                "block": row * crossword.num_cols + col in blocked,
                "number": numbers.get(row * crossword.num_cols + col),
            }
            for col in range(crossword.num_cols)
        ]
        for row in range(crossword.num_rows)
    ]


def target_tile(target):
    """The nine letters for a Target tile, centre letter in the middle.

    The models are the ones the news site uses, where the tile didn't
    exist, so this works the arrangement out rather than the model.
    """
    if target is None:
        return None
    outer = list(target.letters[1:])
    cells = outer[:4] + [target.letters[0]] + outer[4:]
    return [{"char": c, "centre": i == 4} for i, c in enumerate(cells)]


def sudoku_tile(sudoku):
    """The givens, with blanks for the rest, for a Sudoku tile."""
    if sudoku is None:
        return None
    return [ch if ch != "0" else "" for ch in sudoku.puzzle]
