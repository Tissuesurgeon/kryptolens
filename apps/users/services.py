from __future__ import annotations

import re

from apps.users.models import User, UserPreference


def username_from_email(email: str) -> str:
    local = (email or "").split("@", 1)[0]
    base = re.sub(r"[^a-zA-Z0-9]", "", local)[:24] or "user"
    username = base
    suffix = 1
    while User.objects.filter(username=username).exists():
        username = f"{base}{suffix}"
        suffix += 1
    return username


def consume_pending_intent(request):
    """Create a Lens from a landing-page instruction after authentication."""
    pending = (request.session.pop("pending_intent", None) or "").strip()
    request.session.pop("pending_compile", None)
    if not pending:
        return None
    from apps.lenses.agent_service import AgentService

    UserPreference.objects.get_or_create(user=request.user)
    lens, _, _ = AgentService.create_from_intent(request.user, pending)
    return lens
