from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.lenses.models import Lens, LensRun

ACTIVE_STAGES = ("queued", "loading_policy", "fetching_cmc", "evaluating", "scoring")


def _active_run(queryset):
    cutoff = timezone.now() - timedelta(minutes=2)
    return queryset.filter(stage__in=ACTIVE_STAGES, started_at__gte=cutoff).exists()


def workspace_state_for(user) -> dict:
    lenses = Lens.objects.filter(user=user)
    active = lenses.filter(status="active")
    running = _active_run(LensRun.objects.filter(lens__user=user))
    last = LensRun.objects.filter(lens__user=user).order_by("-started_at").first()
    if running:
        return {"label": "Checking", "kind": "checking"}
    if last and last.status == "error":
        return {"label": "Degraded", "kind": "degraded"}
    if not active.exists():
        return {"label": "Paused" if lenses.exists() else "Idle", "kind": "paused"}
    if last and last.status == "ok":
        finished = last.completed_at or last.started_at
        window = timedelta(minutes=getattr(settings, "MONITOR_INTERVAL_MINUTES", 15))
        if finished and timezone.now() - finished <= window:
            return {"label": "Scan complete", "kind": "complete"}
    return {"label": "Watching", "kind": "watching"}


def lens_state(lens: Lens) -> dict:
    running = _active_run(lens.runs.all())
    last = lens.runs.order_by("-started_at").first()
    if running:
        return {"label": "Checking", "kind": "checking"}
    if lens.status != "active":
        return {"label": "Paused" if lens.status == "paused" else "Draft", "kind": "paused"}
    if last and last.status == "error":
        return {"label": "Degraded", "kind": "degraded"}
    if last and last.status == "ok":
        return {"label": "Scan complete", "kind": "complete"}
    return {"label": "Watching", "kind": "watching"}
