from django.urls import path

from . import views

app_name = 'sudoku'


# The view names are the ones the original site used, so the ported views
# reverse exactly as they did there. Only the paths differ: here the app
# is mounted under /sudoku/, so the "sudoku/" prefix each pattern carried
# on the news site would double up. 'list' is the one addition.
urlpatterns = [
    path('', views.SudokuList.as_view(), name='list'),
    path('latest/', views.SudokuLatest.as_view(), name='latest'),
    path('nav/<pk>', views.nav, name='nav'),
    path('<pk>/', views.SudokuDetailView.as_view(), name='detail'),
]
