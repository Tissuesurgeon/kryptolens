"""Thin adapter over outbound Telegram. Inbound handle_update is added in the webhook increment."""

from __future__ import annotations

from apps.notifications.telegram import (
    TelegramError,
    format_event_message,
    notify_artifact,
    notify_event,
    notify_result,
    send_message,
)


class TelegramService:
    error = TelegramError

    send_message = staticmethod(send_message)
    notify_event = staticmethod(notify_event)
    notify_artifact = staticmethod(notify_artifact)
    notify_result = staticmethod(notify_result)
    format_event_message = staticmethod(format_event_message)

    @staticmethod
    def handle_update(update: dict, *, sender=None, public_base: str = "") -> dict:
        from apps.notifications.inbound import handle_telegram_update

        return handle_telegram_update(update, sender=sender, public_base=public_base)
