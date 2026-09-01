from django.urls import path

from . import views

app_name = "target"


# The view names are the ones the original site used, so the ported views
# and models reverse exactly as they did there. Only the paths differ:
# here the whole app is mounted under /target/, so the "target/" prefix
# each pattern carried on the news site would double up.
urlpatterns = [
    path('', views.TargetList.as_view(), name='list'),
    path('latest/', views.TargetLatest.as_view(), name='latest'),
    path('create/', views.TargetCreate.as_view(), name='create'),
    path('create/<str:letters>',
         views.TargetCreate.as_view(), name='create_letters'),
    path('update/<int:pk>', views.TargetUpdate.as_view(), name='update'),
    path('delete/<int:pk>', views.TargetDelete.as_view(), name='delete'),
    path('<int:pk>', views.TargetDetail.as_view(), name='detail'),
    path('<int:pk>/hint/', views.hint, name='hint'),
]
