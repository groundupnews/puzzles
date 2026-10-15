from django.urls import path

from . import views

app_name = "streetwise"

urlpatterns = [
    path("", views.StreetwiseListView.as_view(), name="list"),
    path("latest/", views.latest, name="latest"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/guess/", views.guess, name="guess"),
]
