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
from allauth.account.views import request_login_code
from django.contrib import admin
from django.urls import include, path
from django.views.generic.base import RedirectView, TemplateView

from puzzles.views import logout_everywhere

urlpatterns = [
    path('admin/', admin.site.urls),
    # Serve login-by-code at /accounts/login/ instead of allauth's default
    # /accounts/login/code/. Registered twice: before the allauth include so
    # it wins routing, and again after it, under allauth's own name, so
    # reverse() (form actions, nav links, allauth's own internal redirects)
    # also resolves to this URL. The old password-based signup page is
    # retired; redirect anyone who still has that URL bookmarked.
    path('accounts/login/', request_login_code),
    path('accounts/signup/', RedirectView.as_view(pattern_name='account_request_login_code', query_string=True)),
    path('accounts/', include('allauth.urls')),
    path('accounts/login/', request_login_code, name='account_request_login_code'),
    path('accounts/settings/', include('allauth.usersessions.urls')),
    path('accounts/logout-everywhere/', logout_everywhere, name='logout_everywhere'),
    path('crossword/', include('crossword.urls')),
    path('players/', include('players.urls')),
    path('', TemplateView.as_view(template_name="home.html"), name="home",), ]
