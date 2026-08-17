"""xd crossword format: parse and render."""
import re
from datetime import datetime, timezone

from django.db import transaction

from crossword import grid as grid_module
from crossword.models import Clue, Crossword, Entry, Word


def parse_xd(content):
    """Parse an xd file string and return a dict of crossword data.

    xd is a plain-text format: a block of "Key: value" headers, a blank
    line, the grid itself (one line per row: a letter, "#" for a block, "."
    or lowercase for an empty/circled white cell), then across/down clue
    lines shaped "A1. clue text ~ ANSWER" / "D1. ...". The trailing "~
    ANSWER" is parsed but discarded -- the grid above is the source of
    truth for letters, so a mismatched or missing answer suffix is
    harmless. Returns a dict with keys: name, authors, editors, copyright,
    date, size ({"rows", "cols"}), grid (flat list of letters, "" for
    blanks), blocked_out_squares, across_clues and down_clues (each a dict
    of {number: clue text}).
    """
    lines = content.split("\n")
    i = 0

    # Headers: everything up to the first blank line
    headers = {}
    while i < len(lines) and lines[i].strip():
        if ":" in lines[i]:
            key, _, value = lines[i].partition(":")
            headers[key.strip().lower()] = value.strip()
        i += 1

    # Skip blank lines to grid
    while i < len(lines) and not lines[i].strip():
        i += 1

    # Grid rows: stop at first clue line (A1. / D1.)
    grid_rows = []
    while i < len(lines) and lines[i].strip() and not re.match(r"^[AD]\d+\.", lines[i]):
        grid_rows.append(lines[i])
        i += 1

    # Clues: answer after ~ is ignored (grid is the source of truth)
    across_clues, down_clues = {}, {}
    while i < len(lines):
        m = re.match(r"^([AD])(\d+)\.\s+(.*?)\s*~\s*[A-Za-z]+\s*$", lines[i])
        if m:
            direction = m.group(1).upper()
            number = int(m.group(2))
            (across_clues if direction == "A" else down_clues)[number] = m.group(3)
        i += 1

    num_rows = len(grid_rows)
    num_cols = len(grid_rows[0]) if grid_rows else 0

    cells = []
    blocked = []
    for r, row in enumerate(grid_rows):
        for c in range(num_cols):
            idx = r * num_cols + c
            ch = row[c] if c < len(row) else "#"
            if ch == "#":
                cells.append("")
                blocked.append(idx)
            else:
                # Lowercase = circled cell; . = empty white cell
                cells.append("" if ch == "." else ch.upper())

    return {
        "name": headers.get("title", ""),
        "authors": headers.get("author", ""),
        "editors": headers.get("editor", ""),
        "copyright": headers.get("copyright", ""),
        "date": headers.get("date", ""),
        "size": {"rows": num_rows, "cols": num_cols},
        "grid": cells,
        "blocked_out_squares": blocked,
        "across_clues": across_clues,
        "down_clues": down_clues,
    }


def render_xd(crossword):
    """Render a Crossword instance as an xd format string.

    Mirrors parse_xd's format: headers (Author/Editor lines omitted when
    blank), a blank line, the grid ("#" for blocks, "." for empty white
    cells, otherwise the letter), then across clues followed by down
    clues, each headed by a blank-line separator and only emitted at all
    if there's at least one entry in that direction. Entries without a
    clue still get a line, with the clue text left empty.
    """
    lines = [f"Title: {crossword.name}"]
    if crossword.authors:
        lines.append(f"Author: {crossword.authors}")
    if crossword.editors:
        lines.append(f"Editor: {crossword.editors}")
    lines.append(f"Copyright: {crossword.copyright}")
    lines.append(f"Date: {crossword.date_added.strftime('%Y-%m-%d')}")
    lines.append("")

    num_cols = crossword.num_cols
    cells = crossword.cells
    blocked = set(crossword.blocked_out_squares)

    for r in range(crossword.num_rows):
        row = ""
        for c in range(num_cols):
            idx = r * num_cols + c
            if idx in blocked:
                row += "#"
            elif cells[idx]:
                row += cells[idx]
            else:
                row += "."
        lines.append(row)

    across = list(
        crossword.entries.filter(direction=Entry.ACROSS)
        .select_related("word", "clue")
        .order_by("number")
    )
    down = list(
        crossword.entries.filter(direction=Entry.DOWN)
        .select_related("word", "clue")
        .order_by("number")
    )

    if across or down:
        lines.append("")
    for e in across:
        lines.append(f"A{e.number}. {e.clue.clue if e.clue else ''} ~ {e.word.text}")
    if across and down:
        lines.append("")
    for e in down:
        lines.append(f"D{e.number}. {e.clue.clue if e.clue else ''} ~ {e.word.text}")

    return "\n".join(lines)


def save_crossword_from_xd(data, replace=False):
    """Save parsed xd data (a dict from parse_xd) to the database.

    Creates the Crossword row, then -- exactly like crossword_save's own
    logic -- runs grid.slots() over the parsed grid and creates a Word,
    optional Clue, and Entry for every complete slot; partial slots are
    silently skipped. When replace=True and a crossword with the same name
    already exists, that old crossword is deleted first, so re-importing
    the same .xd file updates it in place rather than accumulating
    duplicates. Falls back to the model's default_copyright() when the xd
    file didn't specify one. Returns the new Crossword.
    """
    num_rows = data["size"]["rows"]
    num_cols = data["size"]["cols"]
    cells = data["grid"]
    blocked = data["blocked_out_squares"]

    create_kwargs = dict(
        name=data["name"],
        authors=data["authors"],
        editors=data["editors"],
        num_rows=num_rows,
        num_cols=num_cols,
        cells=cells,
        blocked_out_squares=blocked,
    )
    if data["copyright"]:
        create_kwargs["copyright"] = data["copyright"]
    if data.get("date"):
        create_kwargs["published"] = datetime.strptime(data["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)

    with transaction.atomic():
        if replace and data["name"]:
            Crossword.objects.filter(name=data["name"]).delete()

        crossword = Crossword.objects.create(**create_kwargs)

        complete = [
            s for s in grid_module.slots(num_rows, num_cols, blocked, cells)
            if s.is_complete(cells)
        ]
        for slot in complete:
            word, _ = Word.objects.get_or_create(text=slot.letters(cells))
            clue_text = (
                data["across_clues"].get(slot.number)
                if slot.direction == "A"
                else data["down_clues"].get(slot.number)
            )
            clue_obj = None
            if clue_text:
                clue_obj, _ = Clue.objects.get_or_create(text=word, clue=clue_text)
            Entry.objects.create(
                crossword=crossword,
                number=slot.number,
                direction=slot.direction,
                word=word,
                clue=clue_obj,
            )

    return crossword
