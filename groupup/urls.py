from django.urls import path

from . import views

app_name = "groupup"

urlpatterns = [
    path("", views.GroupUpListView.as_view(), name="list"),
    path("new/", views.groupup_add, name="add"),
    path("<int:pk>/", views.groupup_solve, name="solve"),
    path("<int:pk>/check/", views.groupup_check, name="check"),
    path("<int:pk>/edit/", views.groupup_edit, name="edit"),
    path("<int:pk>/delete/", views.groupup_delete, name="delete"),
]
