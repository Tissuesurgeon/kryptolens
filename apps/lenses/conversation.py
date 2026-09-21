from __future__ import annotations

from apps.lenses.models import ConversationItem, Lens, LensVersion, Result

THREAD_HIDDEN_TYPES = frozenset(
    {
        "plan",
        "execution_receipt",
        "cmc_activity",
    }
)


def is_visible_thread_item(item) -> bool:
    if item.item_type in THREAD_HIDDEN_TYPES:
        return False
    if item.item_type == "status_update":
        payload = item.payload_json or {}
        if payload.get("status") == "working" or (payload.get("text") or "").strip() == "Working":
            return False
    if item.item_type == "lens_created":
        return False
    result = getattr(item, "result", None)
    kind = getattr(result, "kind", None)
    rows = ((result.payload_json or {}).get("rows") if result else None) or []
    run = getattr(item, "lens_run", None)
    ask_run = bool(run and (getattr(run, "summary_json", None) or {}).get("mode") == "ask")
    direction = ((result.payload_json or {}).get("direction") if result else "") or ""
    if item.item_type in {"evidence", "verification"} and (
        kind == "comparison" or ask_run or direction in {"gainers", "losers"}
    ):
        return False
    if item.item_type == "scan_result" and kind == "comparison" and len(rows) <= 1:
        return False
    return True


def add_item(
    lens: Lens,
    item_type: str,
    payload: dict | None = None,
    *,
    version: LensVersion | None = None,
    run=None,
    result: Result | None = None,
    event=None,
    artifact=None,
) -> ConversationItem:
    return ConversationItem.objects.create(
        lens=lens,
        lens_version=version or lens.current_version(),
        lens_run=run,
        result=result,
        event=event,
        artifact=artifact,
        item_type=item_type,
        payload_json=payload or {},
    )


def watching_payload(job, workflow, routine) -> dict:
    trigger = workflow.trigger if workflow else None
    if job and job.trigger_summary:
        when = job.trigger_summary
    elif trigger and getattr(trigger, "asset", None):
        when = f"{trigger.asset} {trigger.operator} {trigger.value}"
    else:
        when = "when the condition occurs"
    return {
        "kind": routine.kind if routine else "",
        "interval_minutes": routine.interval_minutes if routine else None,
        "name": (routine.name if routine else "") or (job.summary if job else ""),
        "when": when,
        "do": workflow.explained_steps() if workflow else [],
        "data": "CoinMarketCap only",
        "failure": "Report failure if current CoinMarketCap data is unavailable.",
        "watching": True,
        "text": "Routine activated.",
    }


def record_creation(lens: Lens, version: LensVersion, job, workflow, routine=None) -> None:
    add_item(
        lens,
        "user_message",
        {"text": version.source_intent},
        version=version,
    )
    if job and not job.is_persistent():
        return
    add_item(
        lens,
        "job_created",
        {
            "you_asked": (job.you_asked if job else []) or (version.compile_report_json or {}).get("you_asked") or [],
            "assumptions": (version.compile_report_json or {}).get("assumptions") or [],
            "purpose": lens.purpose,
            "clarification": (version.compile_report_json or {}).get("clarification"),
            "news_unavailable": bool(job and job.news_unavailable),
        },
        version=version,
    )
    if workflow and (workflow.steps or workflow.trigger):
        add_item(
            lens,
            "workflow_created",
            {
                "trigger": workflow.trigger.model_dump() if workflow.trigger else None,
                "steps": workflow.explained_steps(),
            },
            version=version,
        )
    if routine:
        add_item(
            lens,
            "routine_created",
            watching_payload(job, workflow, routine),
            version=version,
        )


def ensure_conversation(lens: Lens) -> None:
    if lens.conversation_items.exists():
        return
    version = lens.current_version()
    if not version:
        return
    job = version.as_job()
    try:
        workflow = version.as_workflow()
    except Exception:
        workflow = None
    record_creation(lens, version, job, workflow, lens.current_routine())
    for event in lens.events.order_by("detected_at")[:20]:
        add_item(
            lens,
            "event_result",
            {"symbol": event.symbol, "explanation": event.explanation},
            version=event.lens_version,
            event=event,
        )


def record_result(lens: Lens, result: Result, run=None) -> ConversationItem:
    return add_item(
        lens,
        "scan_result",
        {"kind": result.kind, "title": result.title},
        version=result.lens_version,
        run=run,
        result=result,
    )


def record_cmc_activity(lens: Lens, run) -> list[ConversationItem]:
    """CMC calls stay on CmcCallLog / job receipts, not in the user thread."""
    return []


def _cmc_label(endpoint: str) -> str:
    text = endpoint or ""
    if "listings" in text:
        return "CMC · Top assets"
    if "quotes" in text:
        return "CMC · Market quotes"
    if "global-metrics" in text:
        return "CMC · Global metrics"
    if "fear" in text:
        return "CMC · Fear & Greed"
    return "CMC"


def working_label(call) -> str:
    endpoint = call.endpoint or ""
    params = call.params_redacted or {}
    symbols = str(params.get("symbol") or "").upper()
    if "quotes" in endpoint:
        if symbols:
            first = symbols.split(",")[0]
            return f"Fetching {first} quote…"
        return "Fetching market quotes…"
    if "listings" in endpoint:
        return "Fetching top listings…"
    if "global" in endpoint:
        return "Fetching global metrics…"
    if "fear" in endpoint:
        return "Fetching Fear & Greed…"
    return f"Calling {endpoint}…"


def record_error(lens: Lens, message: str, run=None, version=None) -> ConversationItem:
    return add_item(
        lens,
        "execution_error",
        {"message": message},
        version=version or lens.current_version(),
        run=run,
    )
