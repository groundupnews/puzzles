from django.db import models
from django.contrib.auth.models import User


class Player(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    display_name = models.CharField(max_length=100)
