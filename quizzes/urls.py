from django.urls import path

from . import views

urlpatterns = [
    path("new/", views.quiz_add, name="quiz_add"),
    path("", views.QuizSelectView.as_view(), name="quiz_select"),
    path("<int:pk>/solve/", views.quiz_solve, name="quiz_solve"),
    path("<int:pk>/check/", views.quiz_check, name="quiz_check"),
    path("<int:pk>/edit/", views.quiz_edit, name="quiz_edit"),
    path("<int:pk>/save/", views.quiz_save, name="quiz_save"),
    path("<int:pk>/delete/", views.quiz_delete, name="quiz_delete"),
]
