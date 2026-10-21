from django.db import models
from django.urls import reverse
from django.utils import timezone

from crossword.models import default_copyright


class QuizQuerySet(models.QuerySet):
    def published(self):
        """Quizzes with a publication datetime that has already passed.
        Used to filter what non-generator users are allowed to see
        (mirrors CrosswordQuerySet.published)."""
        return self.filter(published__isnull=False, published__lte=timezone.now())


class Quiz(models.Model):
    name = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    authors = models.CharField(max_length=200, blank=True)
    editors = models.CharField(max_length=200, blank=True)
    copyright = models.CharField(max_length=200, default=default_copyright)
    date_added = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)
    published = models.DateTimeField(null=True, blank=True)

    objects = QuizQuerySet.as_manager()

    class Meta:
        permissions = [("can_generate_quizzes", "Can generate quizzes")]

    def get_absolute_url(self):
        return reverse("quiz_solve", args=[self.pk])

    def is_published(self):
        """True once `published` is set and that moment has passed
        (mirrors Crossword.is_published)."""
        return self.published is not None and self.published <= timezone.now()

    def __str__(self):
        return self.name


class Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE)
    question = models.TextField()
    order = models.SmallIntegerField()
    # The news story the question is about, if any, to send the solver on
    # to. Its headline and picture are looked up when the setter adds the
    # link (see quiz_article), and kept, so showing it costs nothing.
    article_url = models.URLField(max_length=500, blank=True)
    article_title = models.CharField(max_length=300, blank=True)
    article_image = models.URLField(max_length=500, blank=True)
    date_added = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["quiz", "question"], name="unique_quiz_question"
            ),
            models.UniqueConstraint(fields=["quiz", "order"], name="unique_quiz_order"),
        ]

    def article(self):
        """The linked story as {"url", "title", "image"}, or None."""
        if not self.article_url:
            return None
        return {"url": self.article_url, "title": self.article_title, "image": self.article_image}


def _web_link(value):
    value = (value or "").strip() if isinstance(value, str) else ""
    return value if value.startswith(("https://", "http://")) else ""


def article_fields(article):
    """A Question's article fields, from {"url", "title", "image"} as the
    builder posts it and the JSON export writes it. Anything but a web
    link is dropped, as is a headline left behind by a removed link."""
    article = article if isinstance(article, dict) else {}
    url = _web_link(article.get("url"))
    title = article.get("title") if url and isinstance(article.get("title"), str) else ""
    return {
        "article_url": url,
        "article_title": title.strip()[:300],
        "article_image": _web_link(article.get("image")) if url else "",
    }


class Answer(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    answer = models.TextField()
    correct = models.BooleanField(default=False)
    order = models.SmallIntegerField()
    date_added = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["question", "answer"], name="unique_question_answer"
            ),
            models.UniqueConstraint(fields=["question", "order"], name="unique_question_order"),
            models.UniqueConstraint(
                fields=["question"],
                condition=models.Q(correct=True),
                name="one_correct_answer_per_question",
            ),
        ]
