from __future__ import annotations

import logging

import httpx
from django.conf import settings
from django.utils import timezone

from apps.events.models import Event
from apps.users.models import UserPreference

from .models import Notification

logger = logging.getLogger("kryptolens.telegram")


class TelegramError(Exception):
    pass


def send_message(chat_id: str, text: str, token: str | None = None) -> None:
    token = token or settings.TELEGRAM_BOT_TOKEN
    if not token:
        raise TelegramError("TELEGRAM_BOT_TOKEN is not configured")
    if not chat_id:
        raise TelegramError("Telegram chat id is missing")
    try:
        response = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        raise TelegramError(f"Telegram request failed: {exc}") from exc
    payload = {}
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if response.status_code >= 400 or not payload.get("ok"):
        raise TelegramError(payload.get("description") or f"Telegram HTTP {response.status_code}")


def notify_event(event: Event) -> Notification | None:
    preference = UserPreference.objects.filter(user=event.lens.user).first()
    if not preference or not preference.telegram_enabled or not preference.telegram_chat_id:
        return None
    record = Notification.objects.create(event=event, channel="telegram", status="queued")
    text = format_event_message(event)
    try:
        send_message(preference.telegram_chat_id, text)
    except TelegramError as exc:
        record.status = "failed"
        record.error = str(exc)
        record.save(update_fields=["status", "error"])
        logger.warning("telegram_failed event=%s error=%s", event.id, exc)
        return record
    record.status = "sent"
    record.sent_at = timezone.now()
    record.save(update_fields=["status", "sent_at"])
    event.notified_at = record.sent_at
    event.save(update_fields=["notified_at"])
    return record


def format_event_message(event: Event) -> str:
    reasons = ", ".join(event.score_reasons_json or [])
    return (
        f"KryptoLens · {event.lens.name}\n"
        f"{event.symbol} scored {event.score} ({event.severity})\n"
        f"{event.explanation or reasons}\n"
        f"Generated under Lens v{event.lens_version.version}"
    )
