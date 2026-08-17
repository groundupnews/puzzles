"""Crossword Compiler XML format: parse.

Mirrors the shape of xd.py's parse_xd() so both feed the same
save_crossword_from_xd(). No render/export counterpart exists for this
format -- .xd is the only export target (see xd.render_xd).
"""
import xml.etree.ElementTree as ET


def _local(tag):
    """Strip the namespace prefix from a tag: "{uri}cell" -> "cell"."""
    return tag.rsplit("}", 1)[-1]


def _find_all(element, name):
    return [el for el in element.iter() if _local(el.tag) == name]


def _find_one(element, name):
    matches = _find_all(element, name)
    return matches[0] if matches else None


def parse_xml(content):
    """Parse a Crossword Compiler XML file string and return a dict of crossword data.

    Crossword Compiler XML (the crossword-compiler/rectangular-puzzle
    schema) describes the grid as one <cell x= y= solution= number=/>
    element per square ("block" type for a black square, "solution"
    holding the letter otherwise) and clues as <clues><title>Across or
    Down</title><clue number=...>text</clue>...</clues> blocks. The
    <word> elements' own "solution" attribute and each clue's "format"
    (the enumeration) duplicate the per-cell letters and are ignored --
    like the trailing "~ ANSWER" that parse_xd discards, the grid and the
    clue's "number" attribute are the source of truth. Returns the same
    shape as parse_xd(): name, authors, editors, copyright, date, size
    ({"rows", "cols"}), grid, blocked_out_squares, across_clues, down_clues.
    """
    root = ET.fromstring(content.encode("utf-8"))

    metadata = _find_one(root, "metadata")

    def meta_text(name):
        el = _find_one(metadata, name) if metadata is not None else None
        return (el.text or "").strip() if el is not None else ""

    grid_el = _find_one(root, "grid")
    num_cols = int(grid_el.get("width"))
    num_rows = int(grid_el.get("height"))

    cell_by_pos = {
        (int(cell.get("x")), int(cell.get("y"))): cell
        for cell in _find_all(grid_el, "cell")
    }

    cells = []
    blocked = []
    for row in range(num_rows):
        for col in range(num_cols):
            idx = row * num_cols + col
            cell = cell_by_pos.get((col + 1, row + 1))
            if cell is None or cell.get("type") == "block":
                cells.append("")
                blocked.append(idx)
            else:
                cells.append(cell.get("solution", "").upper())

    across_clues, down_clues = {}, {}
    for clues_el in _find_all(root, "clues"):
        title = "".join(_find_one(clues_el, "title").itertext()).strip().lower()
        target = across_clues if "across" in title else down_clues if "down" in title else None
        if target is None:
            continue
        for clue in _find_all(clues_el, "clue"):
            target[int(clue.get("number"))] = "".join(clue.itertext()).strip()

    return {
        "name": meta_text("title"),
        "authors": meta_text("creator"),
        "editors": "",
        "copyright": meta_text("copyright"),
        "date": "",
        "size": {"rows": num_rows, "cols": num_cols},
        "grid": cells,
        "blocked_out_squares": blocked,
        "across_clues": across_clues,
        "down_clues": down_clues,
    }
