from django.db import models
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
    date_added = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["quiz", "question"], name="unique_quiz_question"
            ),
            models.UniqueConstraint(fields=["quiz", "order"], name="unique_quiz_order"),
        ]


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
