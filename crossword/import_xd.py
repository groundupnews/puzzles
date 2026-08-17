#!/usr/bin/env python
"""Import one or more .xd crossword files into the database.

If a crossword with the same name already exists it is deleted and replaced.

Usage:
    python import_xd.py path/to/puzzle.xd [more.xd ...]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "puzzles.settings")

import django
django.setup()

from crossword.models import Crossword
from crossword.xd import parse_xd, save_crossword_from_xd


def import_file(path):
    with open(path, encoding="utf-8") as f:
        data = parse_xd(f.read())

    replacing = bool(data["name"] and Crossword.objects.filter(name=data["name"]).exists())
    crossword = save_crossword_from_xd(data, replace=True)
    num_entries = crossword.entries.count()
    action = "Replaced" if replacing else "Imported"
    print(f"{action}: {data['name']!r} ({crossword.num_rows}x{crossword.num_cols}, {num_entries} entries) → pk={crossword.pk}")
    return crossword


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python import_xd.py <file.xd> [file.xd ...]")
        sys.exit(1)

    ok = fail = 0
    for path in sys.argv[1:]:
        try:
            import_file(path)
            ok += 1
        except Exception as e:
            print(f"ERROR {path}: {e}")
            fail += 1

    if ok + fail > 1:
        print(f"\n{ok} imported, {fail} failed.")
    sys.exit(1 if fail else 0)
