from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import PlayerProfileForm
from .models import Player


@login_required
def player_profile(request):
    try:
        player = request.user.player
    except Player.DoesNotExist:
        player = Player(user=request.user)

    if request.method == "POST":
        form = PlayerProfileForm(request.POST, instance=player)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile saved.")
            return redirect("home")
    else:
        form = PlayerProfileForm(instance=player)

    return render(request, "players/profile.html", {"form": form})
