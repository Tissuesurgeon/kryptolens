from __future__ import annotations

from django.conf import settings

from apps.cmc.adapter import CMCAdapter, CMCError
from apps.cmc.normalize import normalize_listings
from apps.intelligence.tools import DEFAULT_TOOL_PERMISSIONS, dispatch_cmc
from apps.intelligence.workflow_executor import trigger_fired
from apps.lenses.models import Lens, Routine


def routine_live_status(lens: Lens, routine: Routine | None, adapter: CMCAdapter | None = None) -> dict:
    version = lens.current_version()
    workflow = version.as_workflow() if version else None
    trigger = workflow.trigger if workflow else None
    job = version.as_job() if version else None
    payload = {
        "when": (job.trigger_summary if job else "") or (trigger.asset if trigger else "—"),
        "do": (job.workflow_summary if job else "") or (job.purpose if job else lens.purpose),
        "steps": workflow.explained_steps() if workflow else [],
        "asset": trigger.asset if trigger else None,
        "threshold": trigger.value if trigger else None,
        "operator": trigger.operator if trigger else None,
        "price": None,
        "change": None,
        "distance": None,
        "fired": False,
        "error": "",
    }
    if not trigger or trigger.type != "asset_condition":
        return payload
    client = adapter or CMCAdapter(api_key=settings.CMC_API_KEY)
    permissions = version.tool_permissions() if version else DEFAULT_TOOL_PERMISSIONS
    try:
        call = dispatch_cmc(client, "get_quotes", permissions, symbols=[trigger.asset or "BTC"])
    except CMCError as exc:
        payload["error"] = str(exc)
        return payload
    observations = normalize_listings(call.payload)
    symbol = (trigger.asset or "BTC").upper()
    observation = next((item for item in observations if item.symbol.upper() == symbol), None)
    if observation is None:
        payload["error"] = "No live quote for the trigger asset."
        return payload
    payload["price"] = round(observation.price, 2) if observation.price is not None else None
    payload["change"] = round(observation.price_change_24h, 2) if observation.price_change_24h is not None else None
    fired, _ = trigger_fired(trigger, [observation])
    payload["fired"] = fired
    if observation.price_change_24h is not None and trigger.value is not None:
        payload["distance"] = round(observation.price_change_24h - trigger.value, 2)
    return payload
