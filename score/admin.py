from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from score.models import Player


class PlayerAdmin(admin.StackedInline):
    model = Player
    can_delete = False


class UserAdmin(BaseUserAdmin):
    inlines = [PlayerAdmin]


# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
