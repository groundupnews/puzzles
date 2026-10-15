from django.urls import path

from . import views

app_name = "streetwise"

urlpatterns = [
    path("", views.latest, name="latest"),
    path("archive/", views.StreetwiseListView.as_view(), name="list"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/guess/", views.guess, name="guess"),
]
