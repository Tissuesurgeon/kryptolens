from django.utils import timezone

from apps.lenses.models import Lens
from apps.lenses.status import workspace_state_for
from apps.monitoring.services import next_check_at


def agent_status(request):
    if not request.user.is_authenticated:
        return {}
    lenses = Lens.objects.filter(user=request.user).order_by("-updated_at")
    active = [item for item in lenses if item.status == "active"]
    assets = 0
    last_run = None
    for lens in active:
        assets += lens.last_assets_checked or 0
        if lens.last_run_at and (last_run is None or lens.last_run_at > last_run):
            last_run = lens.last_run_at
    last_active = next((item for item in active if item.last_run_at), None)
    state = workspace_state_for(request.user)
    return {
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
        },
    }
