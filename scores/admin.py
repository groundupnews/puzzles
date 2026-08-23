from django.contrib import admin

from .models import Competition, Score


@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = ("name", "date_added", "date_modified")
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(Score)
class ScoreAdmin(admin.ModelAdmin):
    list_display = (
        "competition",
        "puzzle_pk",
        "player",
        "adjusted_score",
    )
    list_filter = (
        "competition",
        "puzzle_pk",
        "player",
    )
    search_fields = (
        "competition",
        "puzzle_pk",
        "player",
    )
