from django.conf import settings

from apps.users.models import User, UserPreference


def ensure_workspace_user() -> User:
    """Ensure the single workspace operator account exists."""
    user, _ = User.objects.get_or_create(
        email=settings.APP_EMAIL,
        defaults={"username": "operator", "is_staff": False},
    )
    if not user.check_password(settings.APP_PASSWORD):
        user.set_password(settings.APP_PASSWORD)
        user.save(update_fields=["password"])
    UserPreference.objects.get_or_create(user=user)
    return user
