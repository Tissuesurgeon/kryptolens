from celery import shared_task
from django.utils import timezone

from apps.lenses.models import Lens


def _due_for_schedule(routine) -> bool:
    from apps.lenses.routine_service import RoutineService

    return RoutineService.due_for_schedule(routine)


def _should_run(lens: Lens) -> bool:
    from apps.lenses.routine_service import RoutineService

    return RoutineService.should_run(lens)


@shared_task
def run_active_lenses():
    from apps.lenses.routine_service import RoutineService

    for routine in RoutineService.due_routines():
        run_lens.delay(routine.lens_id, "scheduled")
    return "LensRuntime"


@shared_task
def run_lens(lens_id: int, trigger: str = "scheduled", run_id: int | None = None, as_of: str | None = None):
    from apps.intelligence.agent_runtime import AgentRuntime
    from apps.lenses.models import LensRun

    existing = LensRun.objects.filter(pk=run_id).first() if run_id else None
    runtime = AgentRuntime(as_of=as_of)
    if as_of or trigger in {"manual", "historical", "chat"}:
        return runtime.run_now(lens_id, trigger=trigger, run=existing).id
    return runtime.trigger_routine(lens_id, trigger=trigger, run=existing).id
