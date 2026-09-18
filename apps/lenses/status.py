from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.utils.timesince import timeuntil

from apps.lenses.models import ApprovalRequest, Lens, LensRun

ACTIVE_STAGES = (
    "queued",
    "loading_policy",
    "fetching_cmc",
    "evaluating",
    "analyzing",
    "scoring",
    "investigating",
    "verifying",
    "repairing",
)

STAGE_ACTIONS = {
    "queued": "queued",
    "loading_policy": "loading policy",
    "fetching_cmc": "fetching CMC",
    "evaluating": "evaluating",
    "analyzing": "analyzing",
    "scoring": "scoring",
    "investigating": "investigating",
    "verifying": "verifying",
    "repairing": "repairing",
}

ROUTINE_KIND_LABELS = {
    "event_triggered": "event-triggered",
    "interval": "interval",
    "scheduled": "scheduled",
    "manual": "manual",
}

CMC_TOOL_LABELS = {
    "get_market_listings": "top-100 listings",
    "get_quotes": "quotes",
    "get_global_metrics": "global metrics",
    "get_fear_and_greed": "Fear & Greed",
}


def _active_run(queryset):
    cutoff = timezone.now() - timedelta(minutes=2)
    return queryset.filter(stage__in=ACTIVE_STAGES, started_at__gte=cutoff).exists()


def _events_from_run(run: LensRun | None) -> int:
    if not run:
        return 0
    summary = run.summary_json or {}
    if summary.get("events") is not None:
        return int(summary["events"])
    return int(run.events_promoted or 0)


def _results_from_run(run: LensRun | None) -> int:
    if not run:
        return 0
    summary = run.summary_json or {}
    if summary.get("results") is not None:
        return int(summary["results"])
    return int(getattr(run, "results_count", 0) or 0)


def _new_intelligence(run: LensRun | None) -> bool:
    if not run or run.status != "ok":
        return False
    if _events_from_run(run) > 0:
        return True
    kind = (run.summary_json or {}).get("result_kind")
    if kind in {"ranked_table", "comparison", "market_summary", "event"}:
        return True
    return _results_from_run(run) > 0 and (run.summary_json or {}).get("events", 0) > 0


def _state(label: str, kind: str, action: str) -> dict:
    return {"label": label, "kind": kind, "action": action}


def _has_pending_approval(*, lens: Lens | None = None, user=None) -> bool:
    if lens is not None:
        flagged = getattr(lens, "has_pending_approval", None)
        if flagged is not None:
            return bool(flagged)
        return lens.approvals.filter(status="pending").exists()
    qs = ApprovalRequest.objects.filter(status="pending")
    if user is not None:
        qs = qs.filter(user=user)
    return qs.exists()


def _next_check_at(lens: Lens):
    job = None
    try:
        job = lens.assignment
    except Exception:
        job = None
    if job and job.next_run_at:
        return job.next_run_at
    if lens.last_run_at:
        from apps.monitoring.services import next_check_at

        return next_check_at(lens.last_run_at)
    return None


def _watching_action(lens: Lens) -> str:
    nxt = _next_check_at(lens)
    if nxt and nxt > timezone.now():
        return f"Next check {timeuntil(nxt)}"
    if lens.status == "active":
        return "Next check on the 15-minute beat"
    return "Activate to keep watch"


def _running_state(run: LensRun | None) -> dict:
    stage = run.stage if run else ""
    if stage == "investigating":
        return _state("Investigating", "checking", "investigating")
    if stage == "verifying":
        return _state("Verifying", "checking", "verifying")
    return _state("Working", "checking", STAGE_ACTIONS.get(stage, "working"))


def workspace_state_for(user) -> dict:
    lenses = Lens.objects.filter(user=user)
    active = lenses.filter(status="active")
    if _has_pending_approval(user=user):
        return _state("Waiting for approval", "waiting", "Waiting for you")
    running = _active_run(LensRun.objects.filter(lens__user=user))
    last = LensRun.objects.filter(lens__user=user).order_by("-started_at").first()
    if running:
        last_active = LensRun.objects.filter(lens__user=user, stage__in=ACTIVE_STAGES).order_by("-started_at").first()
        return _running_state(last_active)
    if last and last.status == "error":
        return _state("Error", "degraded", last.error or "Needs attention")
    if not active.exists():
        if lenses.filter(status="paused").exists():
            return _state("Paused", "paused", "Paused")
        return _state("Idle", "paused", "Give a Lens a job")
    if _new_intelligence(last):
        finished = last.completed_at or last.started_at
        window = timedelta(minutes=getattr(settings, "MONITOR_INTERVAL_MINUTES", 15))
        if finished and timezone.now() - finished <= window:
            return _state("Completed", "complete", "Completed")
    return _state("Watching", "watching", "Next check on the 15-minute beat")


def lens_state(lens: Lens) -> dict:
    if _has_pending_approval(lens=lens):
        return _state("Waiting for approval", "waiting", "Waiting for you")
    running = _active_run(lens.runs.all())
    last = lens.runs.order_by("-started_at").first()
    if running:
        return _running_state(last)
    if lens.status == "paused":
        return _state("Paused", "paused", "Paused")
    if lens.status != "active":
        if lens.current_version():
            return _state("Ready", "paused", "Activate to keep watch")
        return _state("Idle", "paused", "Give this Lens a job")
    if last and last.status == "error":
        return _state("Error", "degraded", last.error or "Needs attention")
    if _new_intelligence(last):
        kind = ((last.summary_json or {}).get("result_kind") if last else "") or ""
        action = kind.replace("_", " ") if kind else "Completed"
        return _state("Completed", "complete", action)
    return _state("Watching", "watching", _watching_action(lens))


def routine_kind_label(kind: str | None) -> str:
    if not kind:
        return "manual"
    return ROUTINE_KIND_LABELS.get(kind, kind.replace("_", "-"))


def last_cmc_action(run: LensRun | None) -> str:
    if not run:
        return ""
    tools = list(run.tools_used_json or []) or list((run.summary_json or {}).get("tools") or [])
    if tools:
        last = tools[-1]
        if isinstance(last, dict):
            last = last.get("tool") or last.get("name") or ""
        last = str(last)
        return CMC_TOOL_LABELS.get(last, last.replace("_", " "))
    call = run.cmc_calls.order_by("-created_at").first()
    if not call:
        return ""
    endpoint = call.endpoint or ""
    if "listings" in endpoint:
        return "top-100 listings"
    if "quotes" in endpoint:
        return "quotes"
    if "fear" in endpoint:
        return "Fear & Greed"
    if "global" in endpoint:
        return "global metrics"
    return endpoint


def work_track(run: LensRun | None) -> list[dict]:
    stage = getattr(run, "stage", None) or ""
    plan, observe, verify = "open", "open", "open"
    if stage in {"queued", "loading_policy"}:
        plan = "current"
    elif stage in {"fetching_cmc", "evaluating", "analyzing", "scoring", "investigating"}:
        plan, observe = "filled", "current"
    elif stage in {"verifying", "repairing"}:
        plan, observe, verify = "filled", "filled", "current"
    elif stage == "complete":
        plan = observe = verify = "filled"
    elif stage == "error":
        plan = "filled"
    return [
        {"id": "plan", "label": "Plan", "fill": plan},
        {"id": "observe", "label": "Observe", "fill": observe},
        {"id": "verify", "label": "Verify", "fill": verify},
    ]
