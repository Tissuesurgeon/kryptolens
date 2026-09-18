from __future__ import annotations

import logging

from django.conf import settings

from apps.cmc.adapter import CMCAdapter
from apps.intelligence.agent import AgentPlan, ChiefAgent, build_agent_plan, job_category, validate_agent_plan
from apps.intelligence.capabilities import merge_capability_payload, run_capabilities
from apps.intelligence.clarified_task import ClarifiedTask
from apps.intelligence.job import JobDefinition
from apps.intelligence.observations import MarketContext, MarketObservation
from apps.intelligence.response import compose_reply
from apps.intelligence.verification import claim_supported, verify_result
from apps.intelligence.workflow import WorkflowDefinition
from apps.lenses.conversation import add_item, record_result
from apps.lenses.models import (
    AgentTask,
    ApprovalRequest,
    Artifact,
    Evidence,
    Job,
    Lens,
    LensRun,
    Observation,
    Result,
    VerificationRecord,
)
from apps.lenses.runtime import LensRuntime
from apps.notifications.telegram import notify_artifact

logger = logging.getLogger("kryptolens.agent_runtime")

ENDPOINT_TOOLS = (
    ("listings/latest", "get_market_listings"),
    ("listings/new", "get_new_listings"),
    ("quotes/historical", "get_quotes_historical"),
    ("ohlcv/historical", "get_ohlcv_historical"),
    ("quotes/latest", "get_quotes"),
    ("content/latest", "get_content"),
    ("global-metrics", "get_global_metrics"),
    ("fear-and-greed", "get_fear_and_greed"),
    ("trending/latest", "get_trending"),
    ("gainers-losers", "get_gainers_losers"),
    ("categories", "get_categories"),
    ("price-performance", "get_price_performance"),
    ("altcoin-season", "get_altcoin_season"),
    ("index/quotes", "get_cmc_index"),
)


class AgentRuntime:
    """PLAN → ACT → OBSERVE → VERIFY → REPAIR? → COMPLETE. Wraps LensRuntime."""

    def __init__(self, adapter: CMCAdapter | None = None, as_of=None):
        if adapter is not None:
            self.adapter = adapter
        else:
            self.adapter = CMCAdapter(api_key=settings.CMC_API_KEY, as_of=as_of)
        self.lens_runtime = LensRuntime(adapter=self.adapter)
        self.chief = ChiefAgent()

    def run_now(self, lens_id: int, trigger: str = "manual", run: LensRun | None = None) -> LensRun:
        return self._loop(lens_id, trigger=trigger, run=run, honor_trigger=False)

    def trigger_routine(self, lens_id: int, trigger: str = "scheduled", run: LensRun | None = None) -> LensRun:
        return self._loop(lens_id, trigger=trigger, run=run, honor_trigger=True)

    def _loop(self, lens_id: int, trigger: str, run: LensRun | None, honor_trigger: bool) -> LensRun:
        lens = Lens.objects.select_related("user").get(pk=lens_id)
        version = lens.current_version()
        if run is None:
            run = LensRun.objects.create(
                lens=lens,
                lens_version=version,
                trigger=trigger,
                status="running",
                stage="queued",
            )
        if getattr(self.adapter, "as_of", None) and not run.as_of:
            run.as_of = self.adapter.as_of
            run.trigger = run.trigger or "historical"
            run.save(update_fields=["as_of", "trigger"])
        if not version:
            return self.lens_runtime._fail(lens, run, "Lens has no version")

        job = _ensure_job(lens, version)
        plan = _plan_for_run(self.chief, version, run)
        job.current_run = run
        job.status = "active" if lens.status == "active" else job.status
        job.save(update_fields=["current_run", "status", "updated_at"])

        run.set_stage("investigating")
        plan_artifact = _persist_plan(lens, version, run, plan)
        chief_task, market_task = _seed_tasks(lens, run, plan, plan_artifact)
        if not lens.conversation_items.filter(item_type="plan", lens_version=version).exists():
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
                run=run,
                artifact=plan_artifact,
            )
        retries = plan.repair_policy.max_retries
        attempt = 0
        result = None
        verification = {"status": "unsupported", "checks": [], "passed": False}

        while True:
            if attempt:
                run.set_stage("repairing")
                market_task.status = "acting"
                market_task.next_gate = "observe"
                market_task.save(update_fields=["status", "next_gate", "updated_at"])
            else:
                market_task.status = "acting"
                market_task.save(update_fields=["status", "updated_at"])

            if honor_trigger:
                run = self.lens_runtime.trigger_routine(
                    lens.id, trigger=trigger, run=run, record_conversation=False
                )
            else:
                run = self.lens_runtime.run_now(lens.id, trigger=trigger, run=run, record_conversation=False)

            result = run.results.order_by("-id").first()
            if result:
                if result.kind != "no_result":
                    _apply_capabilities(lens, version, run, result, plan)
            market_task.status = "observing"
            market_task.save(update_fields=["status", "updated_at"])

            if result is None:
                verification = {"status": "needs_more_evidence", "checks": [], "passed": False}
            else:
                market_task.status = "verifying"
                market_task.save(update_fields=["status", "updated_at"])
                verification = verify_result(result, version.as_workflow(), plan)

            if _needs_repair(result, verification) and attempt < retries:
                attempt += 1
                continue
            break

        run = LensRun.objects.get(pk=run.id)
        evidence_items = _persist_evidence(lens, version, run, result, plan, verification)
        verification_record, verification_artifact = _persist_verification(
            lens, version, run, result, verification
        )
        receipt = _persist_receipt(lens, version, run, result, job, plan, verification, evidence_items)

        if result:
            job.last_result = result
            job.save(update_fields=["last_result", "updated_at"])
            lens.context_json = {
                **(lens.context_json or {}),
                "last_findings": {
                    "result_id": result.id,
                    "kind": result.kind,
                    "title": result.title,
                    "verification": verification["status"],
                },
            }
            lens.save(update_fields=["context_json", "updated_at"])

        if verification["status"] == "needs_more_evidence":
            market_task.status = "needs_more_evidence"
            if run.status != "error":
                run.status = "ok"
                run.stage = "complete"
                run.save(update_fields=["status", "stage"])
        elif run.status == "error":
            market_task.status = "needs_more_evidence"
        else:
            market_task.status = "complete"
        market_task.output_artifacts = [item.id for item in evidence_items if item.artifact_id]
        market_task.next_gate = "complete"
        market_task.save(update_fields=["status", "output_artifacts", "next_gate", "updated_at"])
        chief_task.status = "complete" if market_task.status == "complete" else market_task.status
        chief_task.output_artifacts = [plan_artifact.id, receipt.id]
        chief_task.next_gate = "complete"
        chief_task.save(update_fields=["status", "output_artifacts", "next_gate", "updated_at"])

        _record_os_conversation(lens, version, run, result, evidence_items, verification_artifact, receipt, verification)
        notify_artifact(receipt)
        if result and result.kind == "market_summary":
            report = Artifact.objects.create(
                lens=lens,
                lens_version=version,
                lens_run=run,
                result=result,
                kind="report",
                title=result.title or "Market brief",
                payload_json=result.payload_json,
            )
            notify_artifact(report)
        return run


def _plan_for_run(chief: ChiefAgent, version, run) -> AgentPlan:
    summary = run.summary_json or {}
    if summary.get("mode") == "ask" and (run.workflow_json or summary.get("job")):
        job = JobDefinition.model_validate(summary["job"]) if summary.get("job") else JobDefinition(
            purpose=run.objective or "Ask",
            execution_model="task",
            mode="ask",
        )
        workflow = WorkflowDefinition.model_validate(run.workflow_json or {})
        plan = build_agent_plan(job, workflow, job.purpose)
        plan.capabilities = list(summary.get("capabilities") or plan.capabilities)
        plan.persistent = False
        validate_agent_plan(plan, version.tool_permissions())
        return plan
    return chief.plan_from_version(version)


def _apply_capabilities(lens, version, run, result, plan: AgentPlan) -> None:
    names = list(plan.capabilities or (version.compile_report_json or {}).get("capabilities") or [])
    if not names:
        return
    task_data = (version.compile_report_json or {}).get("clarified_task") or {}
    if (run.summary_json or {}).get("mode") == "ask":
        task_data = (run.summary_json or {}).get("clarified_task") or task_data
    try:
        task = ClarifiedTask.model_validate(task_data) if task_data else ClarifiedTask(capabilities=names)
    except Exception:
        task = ClarifiedTask(capabilities=names)
    observations = _observations_from_run(run, result)
    context = _context_from_result(result)
    extras = dict((result.payload_json or {}).get("extras") or {})
    extras = _hydrate_extras(extras)
    results = run_capabilities(names, observations, context, task, extras)
    payload = merge_capability_payload(dict(result.payload_json or {}), results)
    result.payload_json = payload
    result.save(update_fields=["payload_json"])


def _observations_from_run(run, result) -> list[MarketObservation]:
    stored = list(Observation.objects.filter(lens_run=run))
    if stored:
        items = []
        for row in stored:
            fields = row.fields_json or {}
            items.append(
                MarketObservation(
                    asset_id=row.asset_id,
                    symbol=row.symbol,
                    name=fields.get("name") or "",
                    price=fields.get("price"),
                    price_change_24h=fields.get("percent_change_24h"),
                    volume_24h=fields.get("volume_24h"),
                    volume_change_24h=fields.get("volume_change_24h"),
                    market_cap=fields.get("market_cap"),
                    market_cap_rank=fields.get("cmc_rank"),
                    observed_at=row.observed_at,
                )
            )
        return items
    rows = (result.payload_json or {}).get("rows") or []
    items = []
    for row in rows:
        items.append(
            MarketObservation(
                asset_id=int(row.get("asset_id") or 0),
                symbol=str(row.get("symbol") or ""),
                name=str(row.get("name") or ""),
                price=row.get("price"),
                price_change_24h=row.get("price_change_24h"),
                volume_24h=row.get("volume_24h"),
                market_cap=row.get("market_cap"),
                market_cap_rank=row.get("cmc_rank"),
            )
        )
    return items


def _hydrate_extras(extras: dict) -> dict:
    hydrated = dict(extras)
    for key in ("historical", "ohlcv", "trending", "gainers", "new_listings"):
        rows = extras.get(key) or []
        items = []
        for row in rows:
            if isinstance(row, MarketObservation):
                items.append(row)
            elif isinstance(row, dict):
                try:
                    items.append(MarketObservation.model_validate(row))
                except Exception:
                    continue
        if items:
            hydrated[key] = items
    return hydrated


def _context_from_result(result) -> MarketContext | None:
    payload = result.payload_json or {}
    raw = payload.get("context") or {}
    if not raw:
        return None
    try:
        return MarketContext.model_validate(raw)
    except Exception:
        return None


def _ensure_job(lens: Lens, version) -> Job:
    definition = version.as_job()
    objective = definition.purpose if definition else lens.purpose or lens.natural_language_request
    defaults = {
        "lens_version": version,
        "routine": lens.current_routine(),
        "objective": objective,
        "category": job_category(definition),
        "status": "active" if lens.status == "active" else "draft",
    }
    job = lens.live_job()
    if job:
        for key, value in defaults.items():
            setattr(job, key, value)
        job.save()
        return job
    return Job.objects.create(lens=lens, **defaults)


def _persist_plan(lens, version, run, plan: AgentPlan) -> Artifact:
    return Artifact.objects.create(
        lens=lens,
        lens_version=version,
        lens_run=run,
        kind="plan",
        title="Plan",
        payload_json=plan.model_dump(mode="json"),
    )


def _seed_tasks(lens, run, plan: AgentPlan, plan_artifact: Artifact) -> tuple[AgentTask, AgentTask]:
    specialist = plan.specialist if plan.specialist != "unavailable" else "unavailable"
    chief = AgentTask.objects.create(
        lens=lens,
        lens_run=run,
        assigned_agent="chief",
        objective=plan.objective,
        status="acting",
        input_artifacts=[plan_artifact.id],
        next_gate="act",
    )
    market = AgentTask.objects.create(
        lens=lens,
        lens_run=run,
        parent_task=chief,
        assigned_agent=specialist if specialist in {"market", "research", "unavailable"} else "market",
        objective=plan.objective,
        status="planned",
        input_artifacts=[plan_artifact.id],
        next_gate="act",
    )
    return chief, market


def _needs_repair(result, verification: dict) -> bool:
    if verification.get("status") == "needs_more_evidence":
        return True
    if result is None:
        return True
    if result.kind == "ranked_table" and not (result.payload_json or {}).get("rows"):
        return True
    message = ((result.payload_json or {}).get("message") or result.title or "").lower()
    if result.kind == "error" and any(token in message for token in ("empty", "missing", "unavailable")):
        return True
    return False


def _tool_for_endpoint(endpoint: str) -> str:
    for fragment, tool in ENDPOINT_TOOLS:
        if fragment in (endpoint or ""):
            return tool
    return "get_market_listings"


def _result_symbols(result) -> list[str]:
    if not result:
        return []
    rows = (result.payload_json or {}).get("rows") or []
    seen: list[str] = []
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        if symbol and symbol not in seen:
            seen.append(symbol)
    trigger = str(((result.payload_json or {}).get("trigger") or {}).get("asset") or "").upper()
    if trigger and trigger not in seen:
        seen.insert(0, trigger)
    return seen


def _observation_ids(result) -> list[str]:
    if not result:
        return []
    stored = list(Observation.objects.filter(lens_run_id=result.lens_run_id).values_list("id", flat=True))
    if stored:
        return [str(item) for item in stored]
    rows = (result.payload_json or {}).get("rows") or []
    ids = []
    for row in rows:
        asset_id = row.get("asset_id")
        symbol = row.get("symbol")
        if asset_id is not None:
            ids.append(f"obs:{result.lens_run_id}:{asset_id}")
        elif symbol:
            ids.append(f"obs:{result.lens_run_id}:{symbol}")
    trigger = (result.payload_json or {}).get("trigger") or {}
    if trigger.get("asset"):
        ids.insert(0, f"obs:{result.lens_run_id}:{trigger['asset']}")
    return ids


def _persist_evidence(lens, version, run, result, plan: AgentPlan, verification: dict) -> list[Evidence]:
    pack = Artifact.objects.create(
        lens=lens,
        lens_version=version,
        lens_run=run,
        result=result,
        kind="evidence_pack",
        title="Evidence",
        payload_json={"observation_ids": _observation_ids(result), "tools": plan.tools},
    )
    created: list[Evidence] = []
    logs = list(run.cmc_calls.all()) if run else []
    tools_called = [_tool_for_endpoint(log.endpoint) for log in logs]
    observation_ids = _observation_ids(result)
    claims = list((result.payload_json or {}).get("claims") or [])
    if not claims:
        claims = _fallback_claims(result, run)
    if not claims:
        status = "needs_more_evidence" if verification.get("status") == "needs_more_evidence" else "inconclusive"
        created.append(
            Evidence.objects.create(
                lens=lens,
                lens_run=run,
                artifact=pack,
                source="cmc",
                tool=tools_called[0] if tools_called else "",
                observation_ids=observation_ids,
                claim=result.title if result else "No CMC call was recorded",
                status=status,
            )
        )
        return created
    for index, claim in enumerate(claims):
        status = claim_supported(claim, result, observation_ids) if result else "inconclusive"
        if verification.get("status") == "needs_more_evidence" and status == "supported":
            status = "needs_more_evidence"
        tool = tools_called[index] if index < len(tools_called) else (tools_called[0] if tools_called else _tool_for_claim(claim, plan))
        created.append(
            Evidence.objects.create(
                lens=lens,
                lens_run=run,
                artifact=pack,
                source="cmc",
                tool=tool,
                observation_ids=observation_ids[:8],
                claim=claim,
                status=status,
            )
        )
    return created


def _fallback_claims(result, run) -> list[str]:
    claims = []
    if result and result.title:
        claims.append(result.title)
    logs = list(run.cmc_calls.all()) if run else []
    for log in logs:
        tool = _tool_for_endpoint(log.endpoint)
        if tool == "get_quotes":
            claims.append("Quote observed")
        elif tool == "get_market_listings":
            claims.append("CMC listings observed")
        else:
            claims.append(f"{tool} observed")
    return claims


def _tool_for_claim(claim: str, plan: AgentPlan) -> str:
    lowered = claim.lower()
    if "headline" in lowered:
        return "get_content"
    if "listing" in lowered:
        return "get_market_listings"
    if plan.tools:
        return plan.tools[0]
    return "get_quotes"


def _persist_verification(lens, version, run, result, verification: dict) -> tuple[VerificationRecord, Artifact]:
    artifact = Artifact.objects.create(
        lens=lens,
        lens_version=version,
        lens_run=run,
        result=result,
        kind="verification",
        title="Verification",
        payload_json=verification,
    )
    record = VerificationRecord.objects.create(
        lens=lens,
        lens_run=run,
        artifact=artifact,
        overall_status=verification.get("status") or "inconclusive",
        checks_json=verification.get("checks") or [],
    )
    return record, artifact


def _persist_receipt(lens, version, run, result, job: Job, plan: AgentPlan, verification: dict, evidence: list[Evidence]) -> Artifact:
    trigger = (result.payload_json or {}).get("trigger") if result else {}
    assets = (result.payload_json or {}).get("assets") if result else 0
    rows = (result.payload_json or {}).get("rows") if result else []
    payload = {
        "job": job.objective,
        "what_triggered_it": _trigger_line(trigger),
        "what_i_did": plan.steps,
        "evidence": [item.claim for item in evidence if item.claim],
        "verification": verification.get("status"),
        "checks": verification.get("checks") or [],
        "result": result.title if result else "No result",
        "assets": assets or (len(rows) if rows else 0),
    }
    return Artifact.objects.create(
        lens=lens,
        lens_version=version,
        lens_run=run,
        result=result,
        kind="execution_receipt",
        title="Execution receipt",
        payload_json=payload,
    )


def _trigger_line(trigger: dict) -> str:
    if not trigger:
        return "Manual check"
    asset = trigger.get("asset") or "asset"
    actual = trigger.get("actual")
    if actual is None:
        return f"{asset} trigger observed"
    return f"{asset} moved {actual}%"


def _record_os_conversation(lens, version, run, result, evidence, verification_artifact, receipt, verification=None) -> None:
    if result:
        spoken = compose_reply(
            result,
            verification=verification or verification_artifact.payload_json,
            evidence=evidence,
            task=(run.summary_json or {}).get("clarified_task") if run else None,
        )
        if spoken and not lens.conversation_items.filter(lens_run=run, item_type="assistant_message").exists():
            add_item(
                lens,
                "assistant_message",
                {"text": spoken},
                version=version,
                run=run,
                result=result,
            )
        if not lens.conversation_items.filter(result=result, item_type="scan_result").exists():
            record_result(lens, result, run)
    ask = (run.summary_json or {}).get("mode") == "ask"
    direction = ((result.payload_json or {}).get("direction") if result else "") or ""
    if ask or direction in {"gainers", "losers"}:
        add_item(
            lens,
            "execution_receipt",
            receipt.payload_json,
            version=version,
            run=run,
            result=result,
            artifact=receipt,
        )
        return
    add_item(
        lens,
        "evidence",
        {
            "compact": True,
            "claims": [{"claim": item.claim, "status": item.status} for item in evidence if item.claim],
        },
        version=version,
        run=run,
        result=result,
    )
    add_item(
        lens,
        "verification",
        {
            "compact": True,
            "status": (verification or verification_artifact.payload_json or {}).get("status"),
            "checks": (verification or verification_artifact.payload_json or {}).get("checks") or [],
        },
        version=version,
        run=run,
        result=result,
        artifact=verification_artifact,
    )
    add_item(
        lens,
        "execution_receipt",
        receipt.payload_json,
        version=version,
        run=run,
        result=result,
        artifact=receipt,
    )
