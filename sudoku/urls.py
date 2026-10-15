from django.urls import path

from . import views

app_name = 'sudoku'


# The view names are the ones the original site used, so the ported views
# reverse exactly as they did there. Only the paths differ: here the app
# is mounted under /sudoku/, so the "sudoku/" prefix each pattern carried
# on the news site would double up. 'list', the archive, is the one
# addition.
urlpatterns = [
    path('', views.SudokuLatest.as_view(), name='latest'),
    # The old address for the newest sudoku, which the news site links to.
    path('latest/', views.SudokuLatest.as_view()),
    path('archive/', views.SudokuList.as_view(), name='list'),
    path('nav/<pk>', views.nav, name='nav'),
    path('<pk>/', views.SudokuDetailView.as_view(), name='detail'),
]
