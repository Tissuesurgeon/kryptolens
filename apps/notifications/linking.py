"""One-time codes that bind a Telegram chat to a KryptoLens account."""

from __future__ import annotations

import secrets

from django.db import IntegrityError

from apps.users.models import UserPreference

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def ensure_link_code(preference: UserPreference) -> str:
    if preference.telegram_link_code:
        return preference.telegram_link_code
    for _ in range(6):
        code = "".join(secrets.choice(_ALPHABET) for _ in range(8))
        preference.telegram_link_code = code
        try:
            preference.save(update_fields=["telegram_link_code"])
            return code
        except IntegrityError:
            preference.telegram_link_code = None
    raise RuntimeError("could not issue a Telegram link code")


def claim_link(code: str, chat_id: str) -> UserPreference | None:
    code = (code or "").strip().upper()
    chat_id = str(chat_id or "").strip()
    if not code or not chat_id:
        return None
    preference = UserPreference.objects.filter(telegram_link_code=code).first()
    if preference is None:
        return None
    UserPreference.objects.filter(telegram_chat_id=chat_id).exclude(pk=preference.pk).update(
        telegram_chat_id="",
        telegram_enabled=False,
    )
    preference.telegram_chat_id = chat_id
    preference.telegram_enabled = True
    preference.telegram_link_code = None
    preference.save(update_fields=["telegram_chat_id", "telegram_enabled", "telegram_link_code"])
    return preference


def link_code_from_text(text: str) -> str:
    parts = (text or "").strip().split()
    if len(parts) < 2:
        return ""
    command = parts[0].split("@", 1)[0].lower()
    if command not in {"/start", "/link"}:
        return ""
    return parts[1].strip()
