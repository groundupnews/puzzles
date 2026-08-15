from allauth.usersessions.models import UserSession
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.sessions.models import Session
from django.shortcuts import redirect, render


@login_required
def logout_everywhere(request):
    if request.method != "POST":
        return render(request, "account/logout_everywhere.html")
    user_sessions = UserSession.objects.filter(user_id=request.user.pk)
    Session.objects.filter(
        session_key__in=user_sessions.values_list("session_key", flat=True)
    ).delete()
    user_sessions.delete()
    auth_logout(request)
    return redirect("home")
