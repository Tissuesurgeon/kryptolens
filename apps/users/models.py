from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    email = models.EmailField(unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]


class UserPreference(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="preference")
    telegram_chat_id = models.CharField(max_length=64, blank=True)
    telegram_link_code = models.CharField(max_length=16, blank=True, unique=True, null=True)
    telegram_enabled = models.BooleanField(default=False)
    telegram_notify_results = models.BooleanField(default=True)
    active_lens = models.ForeignKey(
        "lenses.Lens",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="active_for_preferences",
    )

    def __str__(self) -> str:
        return f"prefs:{self.user.email}"
