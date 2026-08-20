"""JSON quiz import: build a Quiz (and its Questions/Answers) from an
uploaded JSON document. Mirrors crossword's xd.py/xml_format.py split
between pure parsing/building logic and the view that calls it.

Expected shape:

    {
      "name": "...", "authors": "...", "editors": "...",
      "copyright": "...", "description": "...", "published": "...",
      "questions": [
        ["Capital of France?", [["Paris", true], ["Lyon", false]]],
        ...
      ]
    }

Every top-level field is optional (missing/null becomes blank). Unlike
crossword_import, a malformed file isn't rejected outright: import is
best-effort -- an unusable or duplicate question/answer is dropped and
the drop recorded, rather than failing the whole file, since one bad
entry shouldn't cost the setter everything else in it.
"""
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from .models import Answer, Question, Quiz


def import_quiz_from_json(data):
    """Create a Quiz from parsed JSON `data`. Returns (quiz, warnings) --
    `warnings` is a list of human-readable strings describing anything
    dropped or suspicious, for the caller to surface to the setter."""
    warnings = []

    quiz = Quiz(
        name=data.get("name") or "",
        authors=data.get("authors") or "",
        editors=data.get("editors") or "",
        copyright=data.get("copyright") or "",
        description=data.get("description") or "",
    )
    published_str = data.get("published") or ""
    if published_str:
        try:
            dt = datetime.fromisoformat(published_str)
            quiz.published = dt if timezone.is_aware(dt) else timezone.make_aware(dt)
        except ValueError:
            warnings.append(f"Could not parse published date {published_str!r}; left blank.")

    raw_questions = data.get("questions")
    if not isinstance(raw_questions, list):
        if raw_questions is not None:
            warnings.append("'questions' is missing or not a list; no questions imported.")
        raw_questions = []

    with transaction.atomic():
        quiz.save()

        order = 0
        seen_question_texts = set()
        for i, entry in enumerate(raw_questions, start=1):
            if not (isinstance(entry, (list, tuple)) and len(entry) == 2):
                warnings.append(f"Question {i}: malformed entry, skipped.")
                continue
            text, raw_answers = entry
            text = (text or "").strip()
            if not text:
                warnings.append(f"Question {i}: blank text, skipped.")
                continue
            if text in seen_question_texts:
                warnings.append(f"Question {i} ({text!r}): duplicate question text, skipped.")
                continue
            if not isinstance(raw_answers, list):
                warnings.append(f"Question {i} ({text!r}): answers missing or malformed; saved with no answers.")
                raw_answers = []

            question = Question.objects.create(quiz=quiz, question=text, order=order)
            order += 1
            seen_question_texts.add(text)

            a_order = 0
            has_correct = False
            seen_answer_texts = set()
            for j, a_entry in enumerate(raw_answers, start=1):
                if not (isinstance(a_entry, (list, tuple)) and len(a_entry) == 2):
                    warnings.append(f"Question {i} ({text!r}), answer {j}: malformed entry, skipped.")
                    continue
                a_text, correct = a_entry
                a_text = (a_text or "").strip()
                if not a_text:
                    warnings.append(f"Question {i} ({text!r}), answer {j}: blank text, skipped.")
                    continue
                if a_text in seen_answer_texts:
                    warnings.append(f"Question {i} ({text!r}): duplicate answer {a_text!r}, skipped.")
                    continue

                correct = bool(correct)
                if correct and has_correct:
                    warnings.append(
                        f"Question {i} ({text!r}): more than one answer marked correct; "
                        f"kept the first, {a_text!r} saved as incorrect."
                    )
                    correct = False
                has_correct = has_correct or correct

                Answer.objects.create(question=question, answer=a_text, correct=correct, order=a_order)
                a_order += 1
                seen_answer_texts.add(a_text)

            if not has_correct:
                warnings.append(f"Question {i} ({text!r}): no correct answer marked.")

    return quiz, warnings
