from datetime import time as day_time
from datetime import timedelta

from django.utils import timezone

from apps.intelligence.agent import ChiefAgent, job_category
from apps.intelligence.job import JobDefinition
from apps.intelligence.job_compiler import compile_job_report
from apps.intelligence.policy import IntelligencePolicy, policy_diff
from apps.lenses.conversation import add_item, record_creation
from apps.lenses.models import ApprovalRequest, Artifact, Job, Lens, LensVersion, Routine


def _report_payload(report: dict) -> dict:
    return {
        "you_asked": report.get("you_asked") or [],
        "assumptions": report.get("assumptions") or [],
        "clarification": report.get("clarification"),
        "confidence": report.get("confidence"),
        "capabilities": report.get("capabilities") or [],
        "clarified_task": report.get("clarified_task") or {},
    }


def create_draft_lens(user, name: str | None = None, purpose: str = "") -> Lens:
    chosen = (name or "").strip() or "New Lens"
    purpose = (purpose or "").strip()
    if chosen == "New Lens":
        for lens in Lens.objects.filter(user=user, status="draft"):
            if not lens.current_version() and not (lens.natural_language_request or "").strip():
                if purpose and not lens.purpose:
                    lens.purpose = purpose
                    lens.save(update_fields=["purpose", "updated_at"])
                return lens
    return Lens.objects.create(
        user=user,
        name=chosen,
        purpose=purpose,
        natural_language_request="",
        status="draft",
    )


def create_agent(user, name: str, purpose: str = "") -> Lens:
    return create_draft_lens(user, name=name, purpose=purpose)


def _description_is_job(text: str) -> bool:
    lowered = text.lower()
    markers = (
        "when ",
        "watch ",
        "analyze ",
        "rank ",
        "every ",
        "drop",
        "alert",
        "brief",
        "compare ",
        "investigate",
        "monitor ",
    )
    return any(marker in lowered for marker in markers)


def attach_job_to_lens(
    lens: Lens,
    text: str,
    provider=None,
    *,
    persist_routine: bool = True,
) -> tuple[Lens, LensVersion, IntelligencePolicy]:
    if lens.current_version():
        version, _ = apply_intent_edit(lens, text, provider=provider)
        return lens, version, lens.current_policy()
    report = compile_job_report(text, provider=provider)
    return attach_compiled_job(lens, text, report, persist_routine=persist_routine)


def attach_compiled_job(
    lens: Lens,
    text: str,
    report: dict,
    *,
    persist_routine: bool = True,
) -> tuple[Lens, LensVersion, IntelligencePolicy]:
    if lens.current_version():
        version, _ = apply_compiled_edit(lens, text, report)
        return lens, version, lens.current_policy()
    policy = report["policy"]
    job = report["job"]
    workflow = report["workflow"]
    version = LensVersion.objects.create(
        lens=lens,
        version=1,
        policy_json=policy.model_dump(mode="json"),
        source_intent=text,
        compile_report_json=_report_payload(report),
        job_definition_json=job.model_dump(mode="json") if job else {},
        workflow_json=workflow.model_dump(mode="json") if workflow else {},
        tool_permissions_json=report.get("tool_permissions") or {},
    )
    if not lens.name or lens.name == "New Lens":
        lens.name = policy.name
    if not lens.purpose:
        lens.purpose = job.purpose if job else policy.summary
    lens.natural_language_request = text
    lens.save(update_fields=["name", "purpose", "natural_language_request", "updated_at"])
    routine = None
    if persist_routine and job and job.is_persistent() and job.routine_kind:
        routine = Routine.objects.create(
            lens=lens,
            lens_version=version,
            name=(job.summary or policy.name or "")[:160],
            description=job.purpose or "",
            **_routine_fields(job.routine_kind),
        )
    record_creation(lens, version, job, workflow, routine)
    upsert_job(lens, version, job, routine)
    _record_plan(lens, version, job, workflow)
    ApprovalRequest.objects.create(
        lens=lens,
        user=lens.user,
        action="create_job",
        sensitivity="READ",
        status="not_required",
    )
    if persist_routine and job and job.is_persistent() and not job.news_unavailable:
        start_watching(lens)
    return lens, version, policy


def create_lens_from_intent(user, text: str, provider=None) -> tuple[Lens, LensVersion, IntelligencePolicy]:
    lens = create_draft_lens(user)
    return attach_job_to_lens(lens, text, provider=provider)


def apply_intent_edit(
    lens: Lens, text: str, provider=None, *, record_diff: bool = True
) -> tuple[LensVersion, list[dict]]:
    current = lens.current_policy()
    current_version = lens.current_version()
    current_job = current_version.as_job() if current_version else None
    current_workflow = current_version.as_workflow() if current_version else None
    report = compile_job_report(
        text,
        provider=provider,
        current_policy=current,
        current_job=current_job,
        current_workflow=current_workflow,
    )
    return apply_compiled_edit(lens, text, report, record_diff=record_diff)


def apply_compiled_edit(
    lens: Lens, text: str, report: dict, *, record_diff: bool = True, announce_job: bool = True
) -> tuple[LensVersion, list[dict]]:
    current = lens.current_policy()
    current_version = lens.current_version()
    current_workflow = current_version.as_workflow() if current_version else None
    policy = report["policy"]
    job = report["job"]
    workflow = report["workflow"]
    next_version = (current_version.version if current_version else 0) + 1
    version = LensVersion.objects.create(
        lens=lens,
        version=next_version,
        policy_json=policy.model_dump(mode="json"),
        source_intent=text,
        compile_report_json=_report_payload(report),
        job_definition_json=job.model_dump(mode="json") if job else {},
        workflow_json=workflow.model_dump(mode="json") if workflow else {},
        tool_permissions_json=report.get("tool_permissions") or {},
    )
    if not lens.name or lens.name == "New Lens":
        lens.name = policy.name
    if not lens.purpose:
        lens.purpose = job.purpose if job else policy.summary
    lens.natural_language_request = text
    lens.save(update_fields=["name", "purpose", "natural_language_request", "updated_at"])
    diffs = policy_diff(current, policy) if current else []
    if current_workflow:
        old_steps = current_workflow.explained_steps()
        new_steps = workflow.explained_steps()
        if old_steps != new_steps:
            diffs.append({"metric": "workflow", "from": old_steps, "to": new_steps})
    add_item(
        lens,
        "user_message",
        {"text": text},
        version=version,
    )
    if record_diff:
        add_item(
            lens,
            "policy_diff",
            {"diffs": diffs, "version": version.version},
            version=version,
        )
    if announce_job:
        add_item(
            lens,
            "job_created",
            {
                "you_asked": job.you_asked if job else [],
                "assumptions": report.get("assumptions") or [],
                "purpose": lens.purpose,
                "clarification": report.get("clarification"),
            },
            version=version,
        )
    _sync_routine(lens, job)
    upsert_job(lens, version, job, lens.current_routine())
    _record_plan(lens, version, job, workflow)
    return version, diffs


def upsert_job(lens: Lens, version: LensVersion, definition: JobDefinition | None, routine: Routine | None = None) -> Job:
    objective = definition.purpose if definition else lens.purpose or lens.natural_language_request
    defaults = {
        "lens_version": version,
        "routine": routine or lens.current_routine(),
        "objective": objective,
        "category": job_category(definition),
        "status": "active" if lens.status == "active" else "draft",
    }
    routine = defaults["routine"]
    if routine and routine.kind in {"interval", "event_triggered", "scheduled"}:
        defaults["next_run_at"] = timezone.now() + timedelta(minutes=routine.interval_minutes or 15)
    job = lens.live_job()
    if job:
        for key, value in defaults.items():
            setattr(job, key, value)
        job.save()
        return job
    return Job.objects.create(lens=lens, **defaults)


def _record_plan(lens: Lens, version: LensVersion, job: JobDefinition | None, workflow) -> Artifact:
    plan = ChiefAgent().plan_from_version(version)
    artifact = Artifact.objects.create(
        lens=lens,
        lens_version=version,
        kind="plan",
        title="Plan",
        payload_json=plan.model_dump(mode="json"),
    )
    add_item(
        lens,
        "plan",
        {
            "objective": plan.objective,
            "job_type": plan.job_type,
            "steps": plan.steps,
            "tools": plan.tools,
            "specialist": plan.specialist,
        },
        version=version,
        artifact=artifact,
    )
    return artifact


def start_watching(lens: Lens) -> None:
    """Routine starts the job without another prompt."""
    if not lens.current_version():
        return
    job = lens.current_version().as_job()
    if job and job.news_unavailable:
        return
    ensure_routine(lens)
    lens.status = "active"
    lens.save(update_fields=["status", "updated_at"])
    live = lens.live_job()
    if live:
        live.status = "active"
        live.routine = lens.current_routine()
        live.save(update_fields=["status", "routine", "updated_at"])
    add_item(lens, "status_update", {"text": "Watching", "status": "active"})


def ensure_routine(lens: Lens) -> Routine | None:
    job = lens.current_version().as_job() if lens.current_version() else None
    existing = lens.current_routine()
    if existing:
        return existing
    if job and job.is_persistent() and job.routine_kind:
        return Routine.objects.create(
            lens=lens,
            lens_version=lens.current_version(),
            name=(job.summary or "")[:160],
            **_routine_fields(job.routine_kind),
        )
    if job and job.execution_model == "task":
        return None
    return Routine.objects.create(lens=lens, **_routine_fields("event_triggered"))


def _sync_routine(lens: Lens, job) -> None:
    if not job:
        return
    existing = lens.current_routine()
    if job.is_persistent() and job.routine_kind:
        fields = _routine_fields(job.routine_kind)
        if existing:
            existing.kind = fields["kind"]
            existing.interval_minutes = fields["interval_minutes"]
            existing.schedule_time = fields.get("schedule_time")
            if not existing.name:
                existing.name = (job.summary or "")[:160]
            existing.save(update_fields=["kind", "interval_minutes", "schedule_time", "name"])
        else:
            Routine.objects.create(lens=lens, name=(job.summary or "")[:160], **fields)
    elif job.execution_model == "task" and existing and existing.kind != "manual":
        existing.kind = "manual"
        existing.schedule_time = None
        existing.save(update_fields=["kind", "schedule_time"])


def _routine_fields(kind: str) -> dict:
    fields = {"kind": kind, "interval_minutes": 15, "schedule_time": None}
    if kind == "scheduled":
        fields["schedule_time"] = day_time(8, 0)
    return fields
