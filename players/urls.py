from django.urls import path

from . import views

urlpatterns = [
    path("profile/", views.player_profile, name="player_profile"),
]
