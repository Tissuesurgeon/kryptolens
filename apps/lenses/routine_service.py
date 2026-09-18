"""Routine = WHEN a Lens/Agent should work. DO lives on LensVersion.workflow."""

from __future__ import annotations

from django.utils import timezone

from apps.cmc.adapter import parse_as_of
from apps.intelligence.job_compiler import compile_job_report
from apps.lenses.conversation import add_item
from apps.lenses.live import routine_live_status
from apps.lenses.models import Lens, Routine
from apps.lenses.run_service import RunService
from apps.lenses.services import start_watching


class RoutineService:
    @staticmethod
    def due_for_schedule(routine: Routine) -> bool:
        if routine.kind != "scheduled" or not routine.schedule_time:
            return True
        from apps.monitoring import tasks as monitoring_tasks

        now = monitoring_tasks.timezone.localtime()
        scheduled = now.replace(
            hour=routine.schedule_time.hour,
            minute=routine.schedule_time.minute,
            second=0,
            microsecond=0,
        )
        delta = abs((now - scheduled).total_seconds())
        return delta <= 15 * 60

    @staticmethod
    def should_run_routine(routine: Routine) -> bool:
        if not routine.enabled or routine.paused:
            return False
        lens = routine.lens
        if lens.status != "active":
            return False
        version = routine.lens_version or lens.current_version()
        job = version.as_job() if version else None
        if job and job.execution_model == "task" and not job.is_persistent():
            return False
        if routine.kind == "manual":
            return False
        if routine.kind == "scheduled" and not RoutineService.due_for_schedule(routine):
            return False
        return True

    @staticmethod
    def should_run(lens: Lens) -> bool:
        routines = list(lens.routines.all())
        if not routines:
            return False
        return any(RoutineService.should_run_routine(item) for item in routines)

    @staticmethod
    def due_lenses():
        return [lens for lens in Lens.objects.filter(status="active") if RoutineService.should_run(lens)]

    @staticmethod
    def due_routines() -> list[Routine]:
        items = []
        for routine in Routine.objects.filter(enabled=True, paused=False, lens__status="active").select_related("lens"):
            if RoutineService.should_run_routine(routine):
                items.append(routine)
        return items

    @staticmethod
    def list_for_lens(lens: Lens) -> list[Routine]:
        return list(lens.routines.order_by("-id"))

    @staticmethod
    def live_status(lens: Lens, routine: Routine, adapter=None) -> dict:
        return routine_live_status(lens, routine, adapter=adapter)

    @staticmethod
    def recent_runs(lens: Lens, routine: Routine | None = None, limit: int = 12):
        runs = lens.runs.all()
        if routine:
            runs = runs.filter(routine=routine)
        return runs.order_by("-started_at")[:limit]

    @staticmethod
    def toggle_pause(routine: Routine) -> Routine:
        routine.paused = not routine.paused
        routine.save(update_fields=["paused", "updated_at"])
        return routine

    @staticmethod
    def proposal_payload(lens: Lens, text: str) -> dict:
        version = lens.current_version()
        report = compile_job_report(
            text,
            current_policy=lens.current_policy(),
            current_job=version.as_job() if version else None,
            current_workflow=version.as_workflow() if version else None,
        )
        job = report.get("job")
        workflow = report.get("workflow")
        trigger = workflow.trigger if workflow else None
        when = (job.trigger_summary if job else "") or (
            f"{trigger.asset} {trigger.operator} {trigger.value}" if trigger and trigger.asset else "when the condition occurs"
        )
        steps = workflow.explained_steps() if workflow else []
        return {
            "name": (job.summary if job else "") or lens.name,
            "when": when,
            "do": steps,
            "data": "CoinMarketCap only",
            "output": (job.workflow_summary if job else "") or "ranked report / summary",
            "failure": "Report failure if current CoinMarketCap data is unavailable.",
            "run": "Automatically when the trigger occurs.",
            "intent": text,
        }

    @staticmethod
    def propose(lens: Lens, text: str):
        payload = RoutineService.proposal_payload(lens, text)
        add_item(lens, "user_message", {"text": text})
        add_item(lens, "routine_proposal", payload)
        return payload

    @staticmethod
    def confirm(lens: Lens, text: str = "") -> Routine:
        from apps.lenses.conversation import watching_payload
        from apps.lenses.services import _routine_fields, apply_intent_edit, attach_job_to_lens

        existing = lens.current_routine()
        if lens.status == "active" and existing and lens.current_version():
            return existing
        text = (text or "").strip()
        version = lens.current_version()
        if text and not version:
            attach_job_to_lens(lens, text, persist_routine=True)
            version = lens.current_version()
            existing = lens.current_routine()
            if existing:
                return existing
        elif text and version and (version.source_intent or "").strip() != text:
            version, _ = apply_intent_edit(lens, text)
        job = version.as_job() if version else None
        kind = job.routine_kind if job and job.routine_kind else "event_triggered"
        routine = lens.routines.filter(lens_version=version).first() or lens.current_routine()
        if routine:
            routine.lens_version = version
            routine.name = routine.name or ((job.summary if job else "") or lens.name)
            routine.description = text or routine.description or (job.purpose if job else "")
            routine.save(update_fields=["lens_version", "name", "description", "updated_at"])
        else:
            routine = Routine.objects.create(
                lens=lens,
                lens_version=version,
                name=(job.summary if job else "") or lens.name,
                description=text or (job.purpose if job else ""),
                **_routine_fields(kind if isinstance(kind, str) else "event_triggered"),
            )
        workflow = version.as_workflow() if version else None
        add_item(
            lens,
            "routine_created",
            watching_payload(job, workflow, routine),
            version=version,
        )
        start_watching(lens)
        return routine

    @staticmethod
    def queue_run_now(lens: Lens, routine: Routine):
        """Honor the trigger against live CMC. Do not pretend it fired."""
        version = routine.lens_version or lens.current_version()
        objective = ""
        if version and version.as_job():
            objective = version.as_job().purpose or ""
        return RunService.queue_now(
            lens,
            trigger="routine",
            routine=routine,
            objective=objective,
        )

    @staticmethod
    def queue_historical(lens: Lens, routine: Routine, as_of_raw: str):
        _ = routine
        version = lens.current_version()
        moment = parse_as_of(as_of_raw)
        if not version or moment is None:
            return None
        return RunService.queue_now(
            lens,
            trigger="historical",
            as_of=moment,
            as_of_arg=moment.date().isoformat(),
            summary={"label": f"Historical test • {moment.date().isoformat()} • Using CMC historical data"},
        )

    @staticmethod
    def mark_ran(routine: Routine | None) -> None:
        if not routine:
            return
        routine.last_run_at = timezone.now()
        routine.save(update_fields=["last_run_at", "updated_at"])
