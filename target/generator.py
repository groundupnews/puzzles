"""Target puzzle generation, carried over from the version on the main
GroundUp site.

A puzzle is nine letters, the first of which is the centre. The answer
list is every dictionary word of four to nine letters that uses the centre
letter and no letter more often than the grid supplies it.
"""

import hashlib
import random
from pathlib import Path

WORDS_DIR = Path(__file__).resolve().parent / "static" / "target" / "words"
BAN_FILES = ["offensive.1", "offensive.2", "profane.1", "profane.3"]

# words.txt holds nothing shorter than four letters, so it can't answer
# "is fork a word?" when deciding whether forks is a plural. The crossword
# app's dictionary goes all the way down and is already in the repo.
STEM_DICTIONARY = (
    Path(__file__).resolve().parent.parent / "crossword" / "cwutils" / "british-english"
)

MIN_LENGTH = 4
GRID_SIZE = 9


def hash_word(word):
    """The hash the browser compares a guess against. Shipping hashes
    rather than the word list is what stops the answers being read
    straight out of the page source."""
    return hashlib.sha256(word.encode("utf-8")).hexdigest()


def _load_words(word_file="words.txt"):
    banned = set()
    for name in BAN_FILES:
        path = WORDS_DIR / name
        if path.exists():
            banned |= {line.strip() for line in path.read_text().splitlines() if line.strip()}

    words = []
    with open(WORDS_DIR / word_file, errors="replace") as f:
        for line in f:
            word = line.strip()
            if (
                MIN_LENGTH <= len(word) <= GRID_SIZE
                and word.isalpha()
                and word == word.lower()
                and word not in banned
            ):
                words.append(word)

    stems = _stems(word_file)
    return [w for w in words if not _is_inflected(w, stems)]


def _stems(word_file="words.txt"):
    """What counts as a word when deciding whether a trailing s is an
    inflection: the crossword dictionary, which unlike words.txt goes
    below four letters, plus the Target list itself."""
    stems = set()
    if STEM_DICTIONARY.exists():
        with open(STEM_DICTIONARY, errors="replace") as f:
            stems |= {w for line in f if (w := line.strip().lower()).isalpha()}
    with open(WORDS_DIR / word_file, errors="replace") as f:
        stems |= {w for line in f if (w := line.strip()).isalpha()}
    return stems


def _is_inflected(word, stems):
    """True for plurals and third-person verbs, which the rules shipped
    with every puzzle say aren't in the answer list.

    A trailing s only counts when the stem is itself a word -- forks ->
    fork drops out, class -> clas does not -- and -ies is checked against
    its -y form so dries -> dry is caught too.
    """
    if not word.endswith("s"):
        return False
    if word[:-1] in stems:
        return True
    return word.endswith("ies") and word[:-3] + "y" in stems


def solve(letters, words=None):
    """Every word in the dictionary that the nine `letters` can spell,
    given that the first letter must appear in each one."""
    letters = letters.lower()
    centre = letters[0]
    available = sorted(letters)
    if words is None:
        words = _load_words()

    found = []
    for word in words:
        # Enforced here as well as in _load_words, so solve() is correct
        # whatever list it's handed.
        if not (MIN_LENGTH <= len(word) <= GRID_SIZE) or centre not in word:
            continue
        pool = available.copy()
        for char in word:
            if char in pool:
                pool.remove(char)
            else:
                break
        else:
            found.append(word)
    return found


def make_target(letters=None, word_file="words.txt"):
    """Build a puzzle. Without `letters`, picks a nine-letter word whose
    letter multiset is unique in the dictionary -- that uniqueness is what
    guarantees exactly one nine-letter answer -- and shuffles it.

    Returns the grid letters (centre first), the nine-letter word, and the
    full answer list.
    """
    words = _load_words(word_file)

    if letters and len(letters) == GRID_SIZE:
        centre, rest = letters[0].lower(), list(letters[1:].lower())
        random.shuffle(rest)
        grid = centre + "".join(rest)
    else:
        nines = [w for w in words if len(w) == GRID_SIZE]
        # Anagram sets of size one: a second word with the same letters
        # would give the puzzle a second nine-letter answer.
        counts = {}
        for word in nines:
            counts.setdefault("".join(sorted(word)), []).append(word)
        unique = [group[0] for group in counts.values() if len(group) == 1]
        if not unique:
            raise ValueError("No nine-letter word with a unique anagram set.")
        shuffled = list(random.choice(unique))
        random.shuffle(shuffled)
        grid = "".join(shuffled)

    answers = solve(grid, words)
    nine = next((w for w in answers if len(w) == GRID_SIZE), "")
    return {"letters": grid, "nine_letter_word": nine, "words": answers}
