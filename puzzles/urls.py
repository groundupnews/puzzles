"""
URL configuration for puzzles project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from django.views.generic.base import RedirectView, TemplateView

from puzzles.views import logout_everywhere

urlpatterns = [
    path('admin/', admin.site.urls),
    # The old password-based login/signup pages are retired in favour of
    # login-by-code; redirect anyone who still has these URLs bookmarked.
    path('accounts/login/', RedirectView.as_view(pattern_name='account_request_login_code', query_string=True)),
    path('accounts/signup/', RedirectView.as_view(pattern_name='account_request_login_code', query_string=True)),
    path('accounts/', include('allauth.urls')),
    path('accounts/sessions/', include('allauth.usersessions.urls')),
    path('accounts/logout-everywhere/', logout_everywhere, name='logout_everywhere'),
    path('crossword/', include('crossword.urls')),
    path('', TemplateView.as_view(template_name="home.html"), name="home",), ]
