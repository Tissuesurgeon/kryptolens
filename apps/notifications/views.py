from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from apps.users.models import UserPreference

from .telegram import TelegramError, send_message


@login_required
def settings_page(request):
    preference, _ = UserPreference.objects.get_or_create(user=request.user)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "disconnect":
            preference.telegram_chat_id = ""
            preference.telegram_enabled = False
            preference.save(update_fields=["telegram_chat_id", "telegram_enabled"])
            messages.info(request, "Telegram disconnected.")
            return redirect("settings")
        preference.telegram_chat_id = (request.POST.get("telegram_chat_id") or "").strip()
        if action == "connect":
            preference.telegram_enabled = bool(preference.telegram_chat_id)
        elif action == "save":
            preference.telegram_enabled = request.POST.get("telegram_enabled") == "on"
        preference.save()
        if action == "test":
            try:
                send_message(
                    preference.telegram_chat_id,
                    "KryptoLens test: Telegram is connected. You will receive Event Receipts here.",
                )
                messages.success(request, "Test message sent.")
            except TelegramError as exc:
                messages.error(request, str(exc))
        elif action == "connect":
            if preference.telegram_chat_id:
                messages.success(request, "Telegram connected. Receipts will be delivered to this chat.")
            else:
                messages.error(request, "Enter a Telegram chat ID to connect.")
        else:
            messages.success(request, "Telegram settings saved.")
        return redirect("settings")
    connected = bool(preference.telegram_chat_id and preference.telegram_enabled)
    return render(
        request,
        "settings.html",
        {"preference": preference, "telegram_connected": connected},
    )
