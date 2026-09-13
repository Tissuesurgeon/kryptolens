from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User, UserPreference


@admin.register(User)
class KryptoUserAdmin(UserAdmin):
    list_display = ("email", "username", "is_staff")


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "telegram_enabled", "telegram_chat_id")
