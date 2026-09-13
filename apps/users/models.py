from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    email = models.EmailField(unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]


class UserPreference(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="preference")
    telegram_chat_id = models.CharField(max_length=64, blank=True)
    telegram_enabled = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"prefs:{self.user.email}"
