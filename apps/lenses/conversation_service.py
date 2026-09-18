"""Chat router shared by web (and later Telegram). Does not talk to CMC directly."""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.intelligence.clarified_task import ClarifiedTask
from apps.intelligence.compiler import infer_you_asked
from apps.intelligence.conversation_agent import ConversationAgent
from apps.intelligence.job_compiler import compile_job_report
from apps.intelligence.policy import policy_diff
from apps.intelligence.task_compiler import compile_from_task
from apps.lenses.agent_service import AgentService
from apps.lenses.conversation import add_item, ensure_conversation, is_visible_thread_item
from apps.lenses.models import Lens
from apps.lenses.routine_service import RoutineService
from apps.lenses.run_service import RunService
from apps.lenses.services import apply_compiled_edit, apply_intent_edit, attach_compiled_job, start_watching
from apps.lenses.status import last_cmc_action, lens_state, routine_kind_label, work_track

CHECK_NOW_PHRASES = frozenset({"check now", "check this now", "check this", "run now", "run that again", "run again"})
PAUSE_PHRASES = frozenset({"pause", "pause this", "pause this lens", "pause this agent"})
RESUME_PHRASES = frozenset(
    {"resume", "resume this", "resume this lens", "resume this agent", "unpause", "activate", "activate this"}
)
FOUND_PHRASES = frozenset({"what have you found", "what have you found?", "what did you find", "show results"})
EVIDENCE_PHRASES = frozenset({"show evidence", "show the evidence"})
WHY_PHRASES = frozenset(
    {
        "why did you conclude this",
        "why did you conclude this?",
        "why do you believe this",
        "why do you believe this?",
        "why did you flag this",
        "why did you flag this?",
    }
)
DOING_PHRASES = frozenset(
    {
        "what is this lens doing",
        "what is this lens doing?",
        "what is this lens doing now",
        "what is this agent doing",
        "what is this agent doing?",
        "what is this agent doing now",
    }
)


@dataclass
class ChatResult:
    kind: str
    flash: str = ""
    flash_level: str = "info"
    command: str | None = None
    run: object | None = None
    preview: object | None = None
    diffs: list = field(default_factory=list)
    draft: str = ""


class ConversationService:
    @staticmethod
    def normalize(text: str) -> str:
        return " ".join(text.lower().strip().rstrip(".!").split())

    @staticmethod
    def command(text: str, action: str = "") -> str | None:
        if action == "apply":
            return None
        phrase = ConversationService.normalize(text)
        if phrase in CHECK_NOW_PHRASES:
            return "check"
        if phrase in PAUSE_PHRASES:
            return "pause"
        if phrase in RESUME_PHRASES:
            return "resume"
        if phrase in FOUND_PHRASES:
            return "found"
        if phrase in EVIDENCE_PHRASES:
            return "evidence"
        if phrase in WHY_PHRASES:
            return "why"
        if phrase in DOING_PHRASES:
            return "doing"
        return None

    @staticmethod
    def handle(lens: Lens, text: str, action: str = "", source: str = "web") -> ChatResult:
        _ = source
        text = (text or "").strip()
        if action in {"create_routine", "confirm"}:
            if not lens.current_version():
                return ChatResult(kind="error", flash="Give this agent a job.", flash_level="error")
            if lens.status == "active" and lens.current_routine():
                return ChatResult(kind="routine_created", flash="Already watching.")
            RoutineService.confirm(lens, text)
            job = lens.current_version().as_job() if lens.current_version() else None
            return ConversationService._begin_work(lens, persistent=bool(job and job.is_persistent()))
        if action == "cancel_proposal":
            add_item(lens, "assistant_message", {"text": "Okay — I won't create that routine."})
            return ChatResult(kind="cancelled")
        command = ConversationService.command(text, action=action)
        if command == "check":
            run = RunService.queue_now(lens, trigger="manual")
            if not run:
                return ChatResult(kind="error", flash="This agent has no job yet.", flash_level="error")
            return ChatResult(kind="run", command="check", run=run)
        if command == "pause":
            AgentService.pause(lens)
            return ChatResult(kind="paused", command="pause", flash=f"{lens.name} is paused.")
        if command == "resume":
            status = AgentService.activate(lens)
            if status == "no_job":
                return ChatResult(kind="error", flash="Give this agent a job before activating.", flash_level="error")
            if status == "news":
                return ChatResult(kind="news", flash="News monitoring isn't available yet.")
            return ChatResult(
                kind="resumed",
                command="resume",
                flash="I'm on it. I'll keep this job running and bring results back here.",
                flash_level="success",
            )
        if command == "found":
            return ChatResult(kind="found", command="found", flash="Latest results are on this conversation.")
        if command == "evidence":
            add_item(lens, "user_message", {"text": text})
            add_item(lens, "assistant_message", ConversationService.evidence_reply(lens))
            return ChatResult(kind="replied", command="evidence")
        if command == "why":
            add_item(lens, "user_message", {"text": text})
            add_item(lens, "assistant_message", ConversationService.why_reply(lens))
            return ChatResult(kind="replied", command="why")
        if command == "doing":
            add_item(lens, "user_message", {"text": text})
            add_item(lens, "assistant_message", ConversationService.doing_reply(lens))
            return ChatResult(kind="replied", command="doing")
        return ConversationService._turn(lens, text, action=action)

    @staticmethod
    def _turn(lens: Lens, text: str, action: str = "") -> ChatResult:
        if not text.strip():
            return ChatResult(kind="error", flash="Give this agent a job.", flash_level="error")
        version = lens.current_version()
        current_job = version.as_job() if version else None
        try:
            current_workflow = version.as_workflow() if version else None
        except Exception:
            current_workflow = None
        current_policy = lens.current_policy()
        pending = (lens.context_json or {}).get("pending_task")
        turn = ConversationAgent.understand(
            text,
            history=ConversationService._history(lens),
            current_job=current_job,
            pending=pending,
        )
        if turn.status == "needs_input" and turn.task:
            add_item(lens, "user_message", {"text": text})
            add_item(lens, "assistant_message", {"text": turn.question, "clarifying": True})
            ConversationService._store_pending(lens, turn.task)
            return ChatResult(kind="needs_input")
        ConversationService._clear_pending(lens)
        task = turn.task
        if not task:
            return ChatResult(kind="error", flash="Give this agent a job.", flash_level="error")
        report = compile_from_task(
            task,
            current_policy=current_policy,
            current_job=current_job,
            current_workflow=current_workflow,
        )
        if action == "preview":
            preview = report["policy"]
            diffs = policy_diff(current_policy, preview) if current_policy else []
            add_item(lens, "user_message", {"text": text})
            return ChatResult(kind="preview", preview=preview, diffs=diffs, draft=text)
        job = report.get("job")
        if job and job.news_unavailable:
            return ConversationService._reply_news(lens, text)
        if task.mode == "ask" and current_job and current_job.is_persistent():
            add_item(lens, "user_message", {"text": text})
            return ConversationService._begin_ask(lens, report)
        if not version:
            attach_compiled_job(lens, text, report, persist_routine=task.mode == "work")
            return ConversationService._begin_work(lens, persistent=task.mode == "work")
        if task.mode == "work":
            version, diffs = apply_compiled_edit(lens, text, report)
            next_job = version.as_job()
            if next_job and not next_job.news_unavailable:
                start_watching(lens)
            return ConversationService._begin_work(lens, persistent=True, diffs=diffs)
        new_workflow = report.get("workflow")
        if ConversationService._same_one_shot(current_job, current_workflow, job, new_workflow):
            add_item(lens, "user_message", {"text": text})
        else:
            apply_compiled_edit(lens, text, report, record_diff=False)
        return ConversationService._begin_ask(lens, report)

    @staticmethod
    def _begin_ask(lens: Lens, report: dict) -> ChatResult:
        job = report.get("job")
        run = RunService.queue_now(
            lens,
            trigger="chat",
            summary={
                "mode": "ask",
                "job": job.model_dump(mode="json") if job else {},
                "capabilities": report.get("capabilities") or [],
            },
            workflow=report.get("workflow"),
            objective=job.purpose if job else "",
        )
        if not run:
            return ChatResult(kind="attached")
        return ChatResult(kind="run", run=run)

    @staticmethod
    def _store_pending(lens: Lens, task: ClarifiedTask) -> None:
        context = dict(lens.context_json or {})
        context["pending_task"] = {
            "task": task.model_dump(mode="json"),
            "pending_field": task.pending_field,
        }
        lens.context_json = context
        lens.save(update_fields=["context_json", "updated_at"])

    @staticmethod
    def _clear_pending(lens: Lens) -> None:
        context = dict(lens.context_json or {})
        if "pending_task" not in context:
            return
        context.pop("pending_task", None)
        lens.context_json = context
        lens.save(update_fields=["context_json", "updated_at"])

    @staticmethod
    def _history(lens: Lens) -> list[dict]:
        items = []
        for item in lens.conversation_items.order_by("-created_at")[:12]:
            items.append({"type": item.item_type, "payload": item.payload_json})
        items.reverse()
        return items

    @staticmethod
    def _reply_news(lens: Lens, text: str) -> ChatResult:
        add_item(lens, "user_message", {"text": text})
        add_item(lens, "assistant_message", {"text": "News monitoring isn't available yet."})
        return ChatResult(kind="news", command="news", flash="News monitoring isn't available yet.")

    @staticmethod
    def _same_one_shot(current_job, current_workflow, job, new_workflow) -> bool:
        if not job or job.is_persistent():
            return False
        if not current_job or current_job.is_persistent():
            return False
        old_steps = current_workflow.explained_steps() if current_workflow else []
        new_steps = new_workflow.explained_steps() if new_workflow else []
        return old_steps == new_steps

    @staticmethod
    def _begin_work(lens: Lens, *, persistent: bool = False, diffs=None) -> ChatResult:
        version = lens.current_version()
        job = version.as_job() if version else None
        if job and job.news_unavailable:
            return ChatResult(kind="news", flash="News monitoring isn't available yet.")
        run = RunService.queue_now(lens, trigger="chat")
        diffs = diffs or []
        flash = "I'll keep watch." if persistent else ""
        level = "success" if persistent else "info"
        if not run:
            kind = "applied" if diffs else "attached"
            return ChatResult(kind=kind, diffs=diffs, flash=flash, flash_level=level)
        return ChatResult(kind="run", run=run, diffs=diffs, flash=flash, flash_level=level)

    @staticmethod
    def compile_preview(lens: Lens, text: str) -> ChatResult:
        current = lens.current_policy()
        if not current:
            return ChatResult(kind="error", flash="This agent has no job definition yet.", flash_level="error")
        version = lens.current_version()
        report = compile_job_report(
            text,
            current_policy=current,
            current_job=version.as_job() if version else None,
            current_workflow=version.as_workflow() if version else None,
        )
        return ChatResult(kind="preview", preview=report["policy"], diffs=policy_diff(current, report["policy"]), draft=text)

    @staticmethod
    def apply(lens: Lens, text: str) -> ChatResult:
        current = lens.current_policy()
        if not current:
            return ChatResult(kind="error", flash="This agent has no job definition yet.", flash_level="error")
        version, diffs = apply_intent_edit(lens, text)
        return ChatResult(
            kind="applied",
            diffs=diffs,
            flash=f"Applied as Lens v{version.version}.",
            flash_level="success",
        )

    @staticmethod
    def evidence_reply(lens: Lens) -> dict:
        items = list(lens.evidence.order_by("-created_at")[:8])
        if not items:
            return {"text": "No evidence has been collected yet. Run Check now to gather CoinMarketCap observations."}
        lines = [f"{item.claim or item.tool} ({item.status})" for item in items]
        return {"text": "Evidence collected:\n" + "\n".join(lines)}

    @staticmethod
    def why_reply(lens: Lens) -> dict:
        record = lens.verifications.order_by("-created_at").first()
        if not record:
            return {"text": "I have not verified a result yet. Run Check now first."}
        checks = record.checks_json or []
        lines = []
        for check in checks:
            mark = "✓" if check.get("passed") else "○"
            lines.append(f"{mark} {check.get('label') or check.get('id')}")
        evidence = lens.evidence.order_by("-created_at").first()
        claim = f" Claim: {evidence.claim}." if evidence and evidence.claim else ""
        return {"text": f"Verification is {record.overall_status}.{claim}\n" + "\n".join(lines)}

    @staticmethod
    def doing_reply(lens: Lens) -> dict:
        job = lens.live_job()
        version = lens.current_version()
        definition = version.as_job() if version else None
        state = lens_state(lens)
        bits = [
            f"{lens.name} is {state['label']}.",
            f"Job: {job.objective if job else lens.purpose or lens.natural_language_request}.",
        ]
        if job:
            bits.append(f"Category: {job.category}.")
        routine = lens.current_routine()
        if routine:
            bits.append(f"Routine: {routine.kind}.")
        if definition and definition.trigger_summary:
            bits.append(f"Trigger: {definition.trigger_summary}.")
        return {"text": " ".join(bits)}

    @staticmethod
    def context(lens: Lens, request=None) -> dict:
        AgentService.drop_canned_openers(lens)
        ensure_conversation(lens)
        version = lens.current_version()
        policy = None
        job = None
        workflow = None
        try:
            policy = version.as_policy() if version else None
        except Exception:
            policy = None
        if version:
            job = version.as_job()
            try:
                workflow = version.as_workflow()
            except Exception:
                workflow = None
        report = (version.compile_report_json if version else {}) or {}
        if policy and not report.get("you_asked"):
            report = {
                "you_asked": infer_you_asked(lens.natural_language_request, policy),
                "assumptions": list(policy.assumptions),
                "clarification": None,
                "confidence": report.get("confidence"),
            }
        latest_run = None
        if request is not None:
            run_id = request.GET.get("run")
            if run_id:
                latest_run = lens.runs.filter(pk=run_id).first()
        latest_run = latest_run or lens.runs.order_by("-started_at").first()
        latest_run = RunService.kick_if_stranded(latest_run)
        latest_result = lens.results.order_by("-created_at").first()
        items = [
            item
            for item in lens.conversation_items.select_related("result", "event", "lens_run", "lens_version", "artifact")
            if is_visible_thread_item(item)
        ]
        assignment = lens.live_job()
        return {
            "lens": lens,
            "version": version,
            "policy": policy,
            "job": job,
            "assignment": assignment,
            "workflow": workflow,
            "workflow_steps": workflow.explained_steps() if workflow else [],
            "routine": lens.current_routine(),
            "policy_json": policy.model_dump_json(indent=2) if policy else "",
            "understanding": policy.understanding() if policy else None,
            "compile_report": report,
            "events": lens.events.select_related("lens_version")[:20],
            "runs": lens.runs.all()[:8],
            "latest_run": latest_run,
            "latest_result": latest_result,
            "conversation_items": items,
            "lens_state": lens_state(lens),
            "tool_permissions": version.tool_permissions() if version else {},
            "next_run_at": assignment.next_run_at if assignment else None,
            "routine_kind_label": routine_kind_label(lens.current_routine().kind if lens.current_routine() else None),
            "last_cmc_action": last_cmc_action(latest_run),
            "work_track": work_track(latest_run),
            "work_open": False,
            "working_cards": RunService.working_cards(latest_run) if latest_run else [],
            "composer_placeholder": f"Ask {lens.name}…",
            "agent_nav": "chat",
        }
