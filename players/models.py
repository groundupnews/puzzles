import re

from django.core.exceptions import ValidationError
from django.db import models
from django.contrib.auth.models import User

DEFAULT_DISPLAY_NAME_RE = re.compile(r"^player_(\d+)$")


class Player(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    # blank=True so a blank display_name survives model validation on its
    # way to save(), which fills in the "player_<pk>" default. Forms that
    # expose this field to users (it's meant to be required there) must
    # set required=True explicitly, since Django derives ModelForm field
    # requiredness from blank.
    display_name = models.CharField(max_length=100, unique=True, blank=True)
    
    def clean(self):
        # Reserve the "player_<pk>" namespace for its rightful owner, so
        # nobody can squat on the default name a future user will be
        # assigned (e.g. claiming "player_42" before user 42 signs up).
        match = DEFAULT_DISPLAY_NAME_RE.match(self.display_name)
        if match and int(match.group(1)) != self.user_id:
            raise ValidationError(
                {"display_name": "You can only use a \"player_<number>\" name that matches your own account number."}
            )

    def save(self, *args, **kwargs):
        if not self.display_name:
            self.display_name = f"player_{self.user_id}"
        super().save(*args, **kwargs)

    def __str__(self):
        if self.display_name:
            return self.display_name
        if self.user.first_name and self.user.last_name:
            return " ".join([self.user.first_name, self.user.last_name])
        if self.user.first_name:
            return self.user.first_name
        return self.user.email
