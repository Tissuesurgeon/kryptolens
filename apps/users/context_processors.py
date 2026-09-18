from django.conf import settings
from django.db.models import Exists, OuterRef
from django.utils import timezone

from apps.lenses.conversation import is_visible_thread_item
from apps.lenses.models import ApprovalRequest, Lens
from apps.lenses.status import lens_state, workspace_state_for
from apps.monitoring.services import next_check_at


def _roster_preview(lens: Lens) -> str:
    item = next(
        (row for row in lens.conversation_items.order_by("-created_at") if is_visible_thread_item(row)),
        None,
    )
    if not item:
        if not lens.current_version():
            return "Give this agent a job."
        return (lens.purpose or lens.natural_language_request or lens.name)[:72]
    payload = item.payload_json or {}
    text = payload.get("text") or payload.get("purpose") or payload.get("objective") or ""
    if item.item_type == "job_created":
        asked = payload.get("you_asked") or []
        if asked:
            text = asked[0]
    elif item.item_type == "routine_created":
        text = "Routine created"
    elif item.item_type == "status_update":
        text = payload.get("text") or text
    return (text or lens.purpose or lens.name)[:72]


def agent_status(request):
    context = {"STATIC_VERSION": getattr(settings, "STATIC_VERSION", "1")}
    if not request.user.is_authenticated:
        return context
    pending = ApprovalRequest.objects.filter(lens_id=OuterRef("pk"), status="pending")
    lenses = list(
        Lens.objects.filter(user=request.user)
        .annotate(has_pending_approval=Exists(pending))
        .order_by("-updated_at")
    )
    for item in lenses:
        item.agent_state = lens_state(item)
        last = item.conversation_items.order_by("-created_at").first()
        item.last_preview = _roster_preview(item)
        item.last_at = last.created_at if last else item.updated_at
        item.routine_count = item.routines.count()
    active = [item for item in lenses if item.status == "active"]
    assets = 0
    last_run = None
    for lens in active:
        assets += lens.last_assets_checked or 0
        if lens.last_run_at and (last_run is None or lens.last_run_at > last_run):
            last_run = lens.last_run_at
    last_active = next((item for item in active if item.last_run_at), None)
    state = workspace_state_for(request.user)
    context.update(
        {
            "workspace_lenses": lenses,
            "workspace_state": state,
            "agent_status": {
                "watching": bool(active),
                "assets": assets,
                "last_checked": last_run,
                "next_check": next_check_at(last_active.last_run_at) if last_active and last_active.last_run_at else None,
                "now": timezone.now(),
                "label": state["label"],
                "kind": state["kind"],
                "action": state["action"],
            },
        }
    )
    return context
