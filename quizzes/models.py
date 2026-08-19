from django.db import models
from crossword.models import default_copyright


class Quiz(models.Model):
    name = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    authors = models.CharField(max_length=200, blank=True)
    editors = models.CharField(max_length=200, blank=True)
    copyright = models.CharField(max_length=200, default=default_copyright)
    date_added = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)
    published = models.DateTimeField(null=True, blank=True)

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
        ]
