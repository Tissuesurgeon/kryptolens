"""Telegram inbound. Zero compile/policy logic — calls the same domain services as the web."""

from __future__ import annotations

from django.conf import settings

from apps.lenses.agent_service import AgentService
from apps.lenses.conversation_service import ConversationService
from apps.lenses.models import Lens
from apps.lenses.routine_service import RoutineService
from apps.lenses.run_service import RunService
from apps.lenses.status import lens_state
from apps.notifications.telegram import send_message
from apps.users.models import UserPreference


def handle_telegram_update(update: dict, *, sender=None, public_base: str = "") -> dict:
    sender = sender or send_message
    base = (public_base or settings.PUBLIC_BASE_URL).rstrip("/")
    message = update.get("message") or {}
    callback = update.get("callback_query") or {}
    if callback:
        message = callback.get("message") or message
        text = str(callback.get("data") or "")
    else:
        text = (message.get("text") or "").strip()
    chat = (message.get("chat") or {}) if message else {}
    chat_id = str(chat.get("id") or "")
    if not chat_id:
        return {"ok": False, "error": "missing chat"}
    preference = UserPreference.objects.filter(telegram_chat_id=chat_id, telegram_enabled=True).first()
    if not preference:
        reply = "Connect this chat in KryptoLens Settings, then send a job here."
        _safe_send(sender, chat_id, reply)
        return {"ok": False, "error": "unknown chat", "replies": [reply]}
    user = preference.user
    replies = _dispatch(user, preference, text, base)
    for item in replies:
        _safe_send(sender, chat_id, item)
    return {"ok": True, "replies": replies}


def _dispatch(user, preference, text: str, base: str) -> list[str]:
    lowered = text.lower().strip()
    if lowered in {"/start", "/help"}:
        return [_start_copy(user, base)]
    if lowered == "/agents":
        return [_agents_copy(user)]
    if lowered.startswith("/create "):
        name = text.split(" ", 1)[1].strip()
        if not name:
            return ["Send /create followed by a name."]
        lens = AgentService.create(user, name, "")
        return [f"Created {lens.name}. Message a job, or open {base}/agents/{lens.id}"]
    if lowered.startswith("agent:"):
        lens_id = lowered.split(":", 1)[1]
        lens = Lens.objects.filter(pk=lens_id, user=user).first()
        if not lens:
            return ["I couldn't find that Lens."]
        AgentService.select(user, lens)
        return [f"Talking to {lens.name}. Send a job in language."]
    lens = preference.active_lens if preference.active_lens_id else None
    if lens and lens.user_id != user.id:
        lens = None
    if lens is None:
        lens = Lens.objects.filter(user=user).order_by("-updated_at").first()
        if lens:
            AgentService.select(user, lens)
    if lowered == "/routines":
        if not lens:
            return ["Create a Lens first with /create Name"]
        routines = RoutineService.list_for_lens(lens)
        if not routines:
            return [f"{lens.name} has no routines yet."]
        lines = [f"{lens.name} routines:"]
        for item in routines:
            state = "paused" if item.paused else "active"
            lines.append(f"• {item.name or lens.name} ({item.kind}, {state})")
        return ["\n".join(lines)]
    if lowered == "/jobs":
        if not lens:
            return ["Create a Lens first with /create Name"]
        runs = RunService.list_for_lens(lens, limit=8)
        if not runs:
            return [f"{lens.name} has no jobs yet."]
        lines = [f"{lens.name} jobs:"]
        for run in runs:
            lines.append(f"• #{run.id} {run.status} {run.stage} — {base}/jobs/{run.id}")
        return ["\n".join(lines)]
    if lowered == "/status":
        if not lens:
            return ["Create a Lens first with /create Name"]
        state = lens_state(lens)
        return [f"{lens.name} is {state['label']}. {state['action']}"]
    if lowered in {"/delete", "delete agent"}:
        if not lens:
            return ["Pick a Lens first."]
        name = AgentService.delete(lens)
        return [f"Deleted {name}."]
    if lowered in {"create routine", "/confirm"}:
        if not lens:
            return ["Pick a Lens first."]
        result = ConversationService.handle(lens, "", action="create_routine", source="telegram")
        return [result.flash or "Routine created."]
    if not lens:
        return ["Create a Lens first: /create Market Scout"]
    result = ConversationService.handle(lens, text, source="telegram")
    return [_result_copy(lens, result, base)]


def _start_copy(user, base: str) -> str:
    lenses = AgentService.list_for_user(user)
    lines = ["KryptoLens. Message a job in language."]
    if not lenses:
        lines.append("No Lenses yet. Send /create Market Scout")
        return "\n".join(lines)
    lines.append("Your Lenses:")
    for item in lenses:
        lines.append(f"• {item.name} — {item.agent_state.get('label')}")
    lines.append(f"Open the desk: {base}/agents")
    return "\n".join(lines)


def _agents_copy(user) -> str:
    lenses = AgentService.list_for_user(user)
    if not lenses:
        return "No Lenses yet. Send /create Market Scout"
    return "\n".join(f"• {item.name} — {item.agent_state.get('label')}" for item in lenses)


def _result_copy(lens, result, base: str) -> str:
    if result.kind == "run" and result.run:
        return (
            f"{lens.name} is working (job #{result.run.id}). Run queued.\n"
            f"View Full Report: {base}/jobs/{result.run.id}"
        )
    if result.kind in {"attached", "routine_created", "applied"}:
        return result.flash or f"{lens.name} has the job. Routine activated. Open {base}/agents/{lens.id}"
    if result.kind == "proposed":
        return f"{lens.name} has the job. Routine activated. Open {base}/agents/{lens.id}"
    if result.flash:
        return result.flash
    return f"{lens.name} updated the conversation. {base}/agents/{lens.id}"


def _safe_send(sender, chat_id: str, text: str) -> None:
    try:
        sender(chat_id, text)
    except Exception:
        return
