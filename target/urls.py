from django.urls import path

from . import views

urlpatterns = [
    path("", views.TargetSelectView.as_view(), name="target_select"),
    path("latest/", views.target_latest, name="target_latest"),
    path("<int:pk>/solve/", views.target_solve, name="target_solve"),
    path("<int:pk>/hint/", views.target_hint, name="target_hint"),
]
