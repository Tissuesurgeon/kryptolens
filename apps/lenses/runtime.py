from __future__ import annotations

import logging

from django.conf import settings
from django.utils import timezone

from apps.cmc.adapter import CMCAdapter, CMCError
from apps.events.models import Event
from apps.intelligence.engine import fallback_explanation
from apps.intelligence.explain import explain_event
from apps.intelligence.observations import Candidate
from apps.intelligence.tools import ToolPermissionError
from apps.intelligence.workflow import WorkflowDefinition
from apps.intelligence.workflow_executor import (
    WorkflowExecutionError,
    execute_steps,
    fetch_trigger_asset,
    trigger_fired,
)
from apps.lenses.conversation import add_item, record_error, record_result
from apps.lenses.models import Lens, LensRun, Result
from apps.lenses.observation_store import persist_observations
from apps.monitoring.services import MonitoringService, event_fingerprint
from apps.notifications.telegram import notify_event, notify_result

logger = logging.getLogger("kryptolens.runtime")


class LensRuntime:
    """Single runtime for Check now, Beat, and conversation commands."""

    def __init__(self, adapter: CMCAdapter | None = None, as_of=None):
        if adapter is not None:
            self.adapter = adapter
        else:
            self.adapter = CMCAdapter(api_key=settings.CMC_API_KEY, as_of=as_of)

    def run_now(
        self,
        lens_id: int,
        trigger: str = "manual",
        run: LensRun | None = None,
        *,
        record_conversation: bool = True,
    ) -> LensRun:
        return self._execute(
            lens_id, trigger=trigger, run=run, honor_trigger=False, record_conversation=record_conversation
        )

    def trigger_routine(
        self,
        lens_id: int,
        trigger: str = "scheduled",
        run: LensRun | None = None,
        *,
        record_conversation: bool = True,
    ) -> LensRun:
        return self._execute(
            lens_id, trigger=trigger, run=run, honor_trigger=True, record_conversation=record_conversation
        )

    def execute_workflow(
        self,
        lens_id: int,
        trigger: str = "manual",
        run: LensRun | None = None,
        *,
        record_conversation: bool = True,
    ) -> LensRun:
        return self._execute(
            lens_id, trigger=trigger, run=run, honor_trigger=False, record_conversation=record_conversation
        )

    def handle_instruction(self, lens: Lens, text: str):
        from apps.lenses.services import apply_intent_edit

        return apply_intent_edit(lens, text)

    def _execute(
        self,
        lens_id: int,
        trigger: str,
        run: LensRun | None,
        honor_trigger: bool,
        record_conversation: bool = True,
    ) -> LensRun:
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
        else:
            run.trigger = trigger
            run.status = "running"
            run.lens_version = version
            run.save(update_fields=["trigger", "status", "lens_version"])
        if getattr(self.adapter, "as_of", None) and not run.as_of:
            run.as_of = self.adapter.as_of
            run.trigger = run.trigger or "historical"
            run.save(update_fields=["as_of", "trigger"])

        if not version:
            return self._fail(lens, run, "Lens has no version")

        ask_override = (run.summary_json or {}).get("mode") == "ask" and run.workflow_json
        if ask_override:
            workflow = WorkflowDefinition.model_validate(run.workflow_json)
        else:
            workflow = version.as_workflow()
            run.workflow_json = workflow.model_dump(mode="json")
            run.save(update_fields=["workflow_json"])

        if not workflow.steps:
            monitor = MonitoringService(adapter=self.adapter).run_lens(lens.id, trigger=trigger, run=run)
            self._wrap_monitor_result(lens, version, monitor, record_conversation=record_conversation)
            return monitor

        try:
            run.set_stage("loading_policy")
            permissions = version.tool_permissions()
            trigger_obs = None
            fired = True
            if honor_trigger and workflow.trigger and workflow.trigger.type == "asset_condition":
                run.set_stage("evaluating")
                symbol = workflow.trigger.asset or "BTC"
                trigger_obs = fetch_trigger_asset(self.adapter, permissions, run, symbol)
                fired, trigger_obs = trigger_fired(workflow.trigger, [trigger_obs] if trigger_obs else [])
                if not fired:
                    actual = trigger_obs.price_change_24h if trigger_obs else None
                    change_text = f"{actual}%" if actual is not None else "unavailable"
                    result = Result.objects.create(
                        lens=lens,
                        lens_version=version,
                        lens_run=run,
                        kind="no_result",
                        title="Trigger condition not met",
                        payload_json={
                            "message": f"Trigger condition not met. Current {symbol} change: {change_text}.",
                            "trigger": workflow.trigger.model_dump(mode="json"),
                            "actual": actual,
                            "assets": 0,
                        },
                    )
                    self._finish_run(lens, run, tools=["get_quotes"], results=1, assets=1 if trigger_obs else 0)
                    if record_conversation:
                        record_result(lens, result, run)
                    return run

            executed = execute_steps(
                self.adapter,
                workflow,
                permissions,
                run,
                exclude_stablecoins=bool(version.as_policy().universe.exclude_stablecoins),
                previous_ranks={int(key): int(value) for key, value in (lens.rank_snapshot or {}).items()},
            )
            observations = executed["observations"]
            if trigger_obs is None and workflow.trigger and workflow.trigger.asset:
                trigger_obs = next(
                    (item for item in observations if item.symbol.upper() == workflow.trigger.asset.upper()),
                    None,
                )
            payload = executed["payload"]
            extras = executed.get("extras") or {}
            limitations = list(payload.get("limitations") or [])
            for key, value in extras.items():
                if key.endswith("_unavailable") and value:
                    limitations.append(str(value))
            if limitations:
                payload["limitations"] = limitations
            payload["extras"] = _json_extras(extras)
            payload["trigger"] = {
                "asset": workflow.trigger.asset if workflow.trigger else None,
                "actual": trigger_obs.price_change_24h if trigger_obs else None,
                "threshold": workflow.trigger.value if workflow.trigger else None,
                "fired": fired,
            }
            last_call = run.cmc_calls.order_by("-id").first() if hasattr(run, "cmc_calls") else None
            persist_observations(run, observations, endpoint=(last_call.endpoint if last_call else ""))
            result = Result.objects.create(
                lens=lens,
                lens_version=version,
                lens_run=run,
                kind=executed["kind"],
                title=executed["title"],
                payload_json=payload,
            )
            event = None
            if honor_trigger and fired and workflow.trigger and workflow.trigger.type == "asset_condition":
                event = self._promote_trigger_event(lens, version, run, trigger_obs, result)
            self._finish_run(
                lens,
                run,
                tools=executed["tools_used"],
                results=1,
                assets=len(observations),
                events=1 if event else 0,
            )
            if record_conversation:
                record_result(lens, result, run)
            if executed["kind"] in {"ranked_table", "comparison", "market_summary", "news_brief"}:
                notify_result(result)
            return run
        except ToolPermissionError as exc:
            return self._fail(lens, run, str(exc), version, record_conversation=record_conversation)
        except CMCError as exc:
            return self._fail(lens, run, str(exc), version, record_conversation=record_conversation)
        except (WorkflowExecutionError, Exception) as exc:
            logger.exception("runtime_failed lens=%s", lens.id)
            return self._fail(lens, run, str(exc), version, record_conversation=record_conversation)

    def _finish_run(self, lens: Lens, run: LensRun, *, tools, results, assets, events=0) -> None:
        run.tools_used_json = tools
        run.results_count = results
        run.assets_checked = assets
        run.events_promoted = events
        run.events_detected = events
        run.summary_json = {
            "assets_checked": assets,
            "results": results,
            "events": events,
            "tools": tools,
            "result_kind": (run.results.order_by("-id").first().kind if hasattr(run, "results") else None),
        }
        run.status = "ok"
        run.stage = "complete"
        run.completed_at = timezone.now()
        run.save()
        lens.last_run_at = run.completed_at
        lens.last_assets_checked = assets
        lens.save(update_fields=["last_run_at", "last_assets_checked", "updated_at"])

    def _fail(self, lens: Lens, run: LensRun, message: str, version=None, record_conversation: bool = True) -> LensRun:
        run.status = "error"
        run.stage = "error"
        run.error = message
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "stage", "error", "completed_at"])
        if version:
            Result.objects.create(
                lens=lens,
                lens_version=version,
                lens_run=run,
                kind="error",
                title="Needs attention",
                payload_json={"message": message},
            )
        if record_conversation:
            record_error(lens, message, run=run, version=version)
        return run

    def _wrap_monitor_result(self, lens: Lens, version, run: LensRun, record_conversation: bool = True) -> None:
        if run.status == "error":
            Result.objects.create(
                lens=lens,
                lens_version=version,
                lens_run=run,
                kind="error",
                title="Needs attention",
                payload_json={"message": run.error},
            )
            if record_conversation:
                record_error(lens, run.error, run=run, version=version)
            return
        events = list(run.events.all()) if hasattr(run, "events") else []
        if not events:
            events = list(Event.objects.filter(lens_run=run))
        if events:
            result = Result.objects.create(
                lens=lens,
                lens_version=version,
                lens_run=run,
                kind="event",
                title="New intelligence",
                payload_json={"event_ids": [item.id for item in events], "count": len(events)},
            )
        else:
            result = Result.objects.create(
                lens=lens,
                lens_version=version,
                lens_run=run,
                kind="no_result",
                title="Nothing needed your attention.",
                payload_json={
                    "assets": run.assets_checked,
                    "near_matches": run.near_matches_json,
                    "message": "Nothing met the conditions.",
                },
            )
        run.results_count = 1
        run.save(update_fields=["results_count"])
        if record_conversation:
            record_result(lens, result, run)
            for item in events:
                add_item(
                    lens,
                    "event_result",
                    {"symbol": item.symbol, "explanation": item.explanation},
                    version=version,
                    run=run,
                    event=item,
                    result=result,
                )

    def _promote_trigger_event(self, lens, version, run, observation, result) -> Event | None:
        if observation is None:
            return None
        now = timezone.now()
        fingerprint = event_fingerprint(lens.id, observation.asset_id, "trigger_fired", now)
        existing = Event.objects.filter(fingerprint=fingerprint).first()
        if existing:
            return existing
        candidate = Candidate(
            observation=observation,
            logic_passed=True,
            should_promote=True,
            score=3,
            reasons=["Trigger fired"],
            severity="medium",
        )
        try:
            explanation = explain_event(candidate, version.as_policy())
        except Exception:
            explanation = fallback_explanation(candidate, version.as_policy())
        event = Event.objects.create(
            lens=lens,
            lens_version=version,
            lens_run=run,
            asset_id=observation.asset_id,
            symbol=observation.symbol,
            name=observation.name,
            event_type="trigger_fired",
            fingerprint=fingerprint,
            observations_json={"asset": observation.model_dump(mode="json"), "result_id": result.id},
            score=3,
            score_reasons_json=["Trigger fired"],
            severity="medium",
            explanation=explanation or f"{observation.symbol} crossed the Lens trigger.",
        )
        notify_event(event)
        add_item(
            lens,
            "event_result",
            {"symbol": event.symbol, "explanation": event.explanation},
            version=version,
            run=run,
            event=event,
            result=result,
        )
        return event


def _json_extras(extras: dict) -> dict:
    out = {}
    for key, value in extras.items():
        if key.endswith("_call"):
            continue
        if hasattr(value, "__iter__") and not isinstance(value, (str, dict, bytes)):
            rows = []
            for item in value:
                if hasattr(item, "model_dump"):
                    rows.append(item.model_dump(mode="json"))
                elif isinstance(item, dict):
                    rows.append(item)
            out[key] = rows
        elif isinstance(value, (str, int, float, bool)) or value is None:
            out[key] = value
        elif isinstance(value, dict):
            out[key] = value
    return out
