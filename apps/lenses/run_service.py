"""Product Jobs list = LensRun. The OneToOne Job model is the standing assignment."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from apps.lenses.conversation import working_label
from apps.lenses.models import Lens, LensRun
from apps.monitoring.tasks import run_lens as run_lens_task

INLINE_TRIGGERS = frozenset({"chat", "manual"})


class RunService:
    @staticmethod
    def create_queued(
        lens: Lens,
        trigger: str,
        *,
        as_of=None,
        summary: dict | None = None,
        routine=None,
        objective: str = "",
        workflow=None,
    ) -> LensRun | None:
        version = lens.current_version()
        if not version:
            return None
        workflow_json = version.workflow_json or {}
        if workflow is not None:
            workflow_json = workflow.model_dump(mode="json") if hasattr(workflow, "model_dump") else workflow
        payload = {
            "lens": lens,
            "lens_version": version,
            "trigger": trigger,
            "status": "running",
            "stage": "queued",
            "workflow_json": workflow_json,
            "objective": objective or (version.as_job().purpose if version.as_job() else ""),
        }
        if routine is not None:
            payload["routine"] = routine
        if as_of is not None:
            payload["as_of"] = as_of
        if summary:
            payload["summary_json"] = summary
        return LensRun.objects.create(**payload)

    @staticmethod
    def enqueue(lens: Lens, run: LensRun, trigger: str = "manual", as_of: str | None = None) -> LensRun:
        try:
            if trigger == "chat":
                run_lens_task.apply(args=(lens.id, trigger, run.id, as_of))
            else:
                run_lens_task.delay(lens.id, trigger, run.id, as_of)
        except Exception as exc:
            run.error = f"Could not queue run: {exc}"
            run.stage = "error"
            run.status = "error"
            run.save(update_fields=["error", "stage", "status"])
        run.refresh_from_db()
        return run

    @staticmethod
    def kick_if_stranded(run: LensRun | None) -> LensRun | None:
        """If a chat/check sat queued with no worker, run it in this process."""
        if not run or run.stage != "queued":
            return run
        if (run.trigger or "") not in INLINE_TRIGGERS:
            return run
        started = run.started_at or timezone.now()
        if timezone.now() - started < timedelta(seconds=2):
            return run
        try:
            run_lens_task.apply(args=(run.lens_id, run.trigger or "chat", run.id, None))
        except Exception as exc:
            run.error = f"Could not start run: {exc}"
            run.stage = "error"
            run.status = "error"
            run.save(update_fields=["error", "stage", "status"])
        run.refresh_from_db()
        return run

    @staticmethod
    def queue_now(
        lens: Lens,
        trigger: str = "manual",
        *,
        as_of=None,
        as_of_arg: str | None = None,
        summary=None,
        routine=None,
        objective: str = "",
        workflow=None,
    ) -> LensRun | None:
        run = RunService.create_queued(
            lens, trigger, as_of=as_of, summary=summary, routine=routine, objective=objective, workflow=workflow
        )
        if not run:
            return None
        return RunService.enqueue(lens, run, trigger=trigger, as_of=as_of_arg)

    @staticmethod
    def working_cards(run: LensRun | None) -> list[dict]:
        if not run:
            return []
        cards = []
        for call in run.cmc_calls.order_by("created_at"):
            cards.append({"label": working_label(call), "endpoint": call.endpoint, "ms": call.elapsed_ms})
        if not cards:
            stage = run.stage or "queued"
            fallback = {
                "queued": "Queued…",
                "loading_policy": "Loading policy…",
                "fetching_cmc": "Fetching CMC…",
                "evaluating": "Checking trigger…",
                "analyzing": "Analyzing market data…",
                "investigating": "Investigating…",
                "verifying": "Verifying…",
            }
            cards.append({"label": fallback.get(stage, "Working…"), "endpoint": "", "ms": None})
        return cards

    @staticmethod
    def record_activity(lens: Lens, run: LensRun) -> None:
        return

    @staticmethod
    def list_for_user(user, limit: int = 80) -> list[LensRun]:
        return list(
            LensRun.objects.filter(lens__user=user)
            .select_related("lens", "lens_version")
            .order_by("-started_at")[:limit]
        )

    @staticmethod
    def grouped_for_user(user, limit: int = 80) -> dict:
        runs = RunService.list_for_user(user, limit=limit)
        return {
            "runs": runs,
            "running": [item for item in runs if item.status == "running"],
            "completed": [item for item in runs if item.status == "ok"],
            "failed": [item for item in runs if item.status == "error"],
        }

    @staticmethod
    def get_for_user(user, run_id: int) -> LensRun | None:
        return (
            LensRun.objects.filter(pk=run_id, lens__user=user)
            .select_related("lens", "lens_version", "routine")
            .prefetch_related("cmc_calls", "results", "artifacts")
            .first()
        )

    @staticmethod
    def list_for_lens(lens: Lens, limit: int = 80) -> list[LensRun]:
        return list(lens.runs.select_related("lens", "lens_version").order_by("-started_at")[:limit])

    @staticmethod
    def get_trace(run: LensRun) -> dict:
        order = [
            "queued",
            "planning",
            "loading_policy",
            "trigger_check",
            "fetching_cmc",
            "evaluating",
            "analyzing",
            "investigating",
            "generating_report",
            "verifying",
            "notifying",
            "complete",
            "error",
        ]
        persisted = run.stage or "queued"
        seen = []
        for stage in order:
            seen.append({"id": stage, "current": stage == persisted})
            if stage == persisted:
                break
        calls = [
            {
                "endpoint": call.endpoint,
                "status_code": call.status_code,
                "elapsed_ms": call.elapsed_ms,
                "params": call.params_redacted,
                "excerpt": call.response_excerpt,
            }
            for call in run.cmc_calls.order_by("created_at")
        ]
        verification = run.verifications.order_by("-created_at").first() if hasattr(run, "verifications") else None
        if verification is None:
            verification = run.lens.verifications.filter(lens_run=run).order_by("-created_at").first()
        result = run.results.order_by("-id").first()
        return {
            "stage": persisted,
            "stages": seen,
            "cmc_calls": calls,
            "verification": verification.overall_status if verification else "",
            "result": result,
        }
