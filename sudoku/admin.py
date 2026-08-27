from django.contrib import admin

from .models import Sudoku


@admin.register(Sudoku)
class SudokuAdmin(admin.ModelAdmin):
    list_display = ["pk", "number", "difficulty", "published", "is_published"]
    list_filter = ["difficulty"]
    ordering = ["-published"]
