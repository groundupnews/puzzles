from django.urls import path

from . import views

urlpatterns = [
    path("", views.SudokuSelectView.as_view(), name="sudoku_select"),
    path("latest/", views.sudoku_latest, name="sudoku_latest"),
    path("<int:pk>/solve/", views.sudoku_solve, name="sudoku_solve"),
]
