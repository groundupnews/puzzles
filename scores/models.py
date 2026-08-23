from django.db import models
from players.models import Player


class Competition(models.Model):
    name = models.CharField(max_length=100, unique=True)
    date_added = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [
            "name",
        ]

    def __str__(self):
        return self.name


class Score(models.Model):
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE)
    puzzle_pk = models.PositiveIntegerField()
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    raw_score = models.FloatField(default=0.0)
    time = models.FloatField(default=0.0)
    adjusted_score = models.FloatField(default=0.0)
    additional = models.TextField(blank=True)
    date_added = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["competition", "puzzle_pk", "player"],
                name="unique_competition_puzzle_pk_player",
            ),
        ]
        ordering = [
            "competition",
            "puzzle_pk",
            "-adjusted_score",
        ]

    def __str__(self):
        return " ".join([self.competition, self.puzzle_pk, self.player])
