from __future__ import annotations

import hashlib
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.cmc.adapter import CMCAdapter, CMCError
from apps.cmc.logging import persist_call
from apps.cmc.normalize import (
    is_stablecoin,
    normalize_fear_greed,
    normalize_global_metrics,
    normalize_listings,
)
from apps.events.models import Event
from apps.intelligence.engine import evaluate_policy, fallback_explanation
from apps.intelligence.explain import explain_event
from apps.intelligence.observations import Candidate
from apps.intelligence.planner import plan_query
from apps.lenses.models import Lens, LensRun
from apps.notifications.telegram import notify_event

logger = logging.getLogger("kryptolens.monitor")


def next_check_at(last_run_at):
    if not last_run_at:
        return None
    return last_run_at + timedelta(minutes=settings.MONITOR_INTERVAL_MINUTES)


class MonitoringService:
    """Single monitoring path for Celery Beat and Run now."""

    def __init__(self, adapter: CMCAdapter | None = None):
        self.adapter = adapter or CMCAdapter(api_key=settings.CMC_API_KEY)

    def run_lens(self, lens_id: int, trigger: str = "scheduled", run: LensRun | None = None) -> LensRun:
        lens = Lens.objects.select_related("user").get(pk=lens_id)
        if run is None:
            run = LensRun.objects.create(
                lens=lens,
                trigger=trigger,
                status="running",
                stage="queued",
            )
        else:
            run.trigger = trigger
            run.status = "running"
            run.save(update_fields=["trigger", "status"])

        run.set_stage("loading_policy")
        version = lens.current_version()
        if not version:
            run.error = "Lens has no policy version"
            run.completed_at = timezone.now()
            run.set_stage("error")
            run.save(update_fields=["error", "completed_at", "stage", "status"])
            return run
        policy = version.as_policy()
        plan = plan_query(policy)
        run.lens_version = version
        run.save(update_fields=["lens_version"])

        primary_log = None
        try:
            run.set_stage("fetching_cmc")
            if policy.universe.type == "symbols":
                call = self.adapter.get_quotes(policy.universe.symbols)
            else:
                call = self.adapter.get_listings(limit=policy.universe.limit)
            primary_log = persist_call(call, run)
            previous = {int(key): int(value) for key, value in (lens.rank_snapshot or {}).items()}
            observations = normalize_listings(call.payload, previous)
            if policy.universe.exclude_stablecoins:
                observations = [item for item in observations if not is_stablecoin(item)]

            context = None
            if "fear_greed" in plan.include_context:
                fear = self.adapter.get_fear_greed()
                persist_call(fear, run)
                context = normalize_fear_greed(fear.payload)
            if "global_metrics" in plan.include_context:
                global_call = self.adapter.get_global_metrics()
                persist_call(global_call, run)
                context = normalize_global_metrics(global_call.payload, context)

            run.set_stage("evaluating")
            promoted = 0
            suppressed = 0
            detected = 0
            near_matches: list[dict] = []
            for observation in observations:
                candidate = evaluate_policy(observation, policy, context)
                run.candidates_evaluated += 1
                payload = near_match_payload(candidate)
                if payload and len(near_matches) < 20:
                    near_matches.append(payload)
                if candidate.should_promote and "store_event" in policy.actions:
                    event, created = self._promote(lens, version, run, candidate, primary_log)
                    if created:
                        promoted += 1
                        detected += 1
                        if candidate.should_notify:
                            notify_event(event)
                    else:
                        suppressed += 1
                elif candidate.logic_passed:
                    suppressed += 1
                elif candidate.suppress_reason:
                    suppressed += 1

            run.set_stage("scoring")
            snapshot = {
                str(item.asset_id): item.market_cap_rank
                for item in observations
                if item.market_cap_rank is not None
            }
            lens.rank_snapshot = snapshot
            lens.last_run_at = timezone.now()
            lens.last_assets_checked = len(observations)
            lens.save(update_fields=["rank_snapshot", "last_run_at", "last_assets_checked", "updated_at"])
            run.assets_checked = len(observations)
            run.events_detected = detected
            run.events_promoted = promoted
            run.events_suppressed = suppressed
            run.near_matches_json = near_matches
            run.summary_json = {
                "assets_checked": len(observations),
                "candidates": run.candidates_evaluated,
                "events": detected,
                "near_matches": len(near_matches),
            }
            run.status = "ok"
            run.stage = "complete"
            run.completed_at = timezone.now()
            run.save()
        except CMCError as exc:
            run.status = "error"
            run.stage = "error"
            run.error = str(exc)
            run.completed_at = timezone.now()
            run.save(update_fields=["status", "stage", "error", "completed_at"])
            logger.warning("monitor_failed lens=%s error=%s", lens.id, exc)
        except Exception as exc:
            run.status = "error"
            run.stage = "error"
            run.error = str(exc)
            run.completed_at = timezone.now()
            run.save(update_fields=["status", "stage", "error", "completed_at"])
            logger.exception("monitor_crashed lens=%s", lens.id)
        return run

    def _promote(
        self,
        lens: Lens,
        version,
        run: LensRun,
        candidate: Candidate,
        cmc_log,
    ) -> tuple[Event, bool]:
        now = timezone.now()
        fingerprint = event_fingerprint(lens.id, candidate.observation.asset_id, "policy_match", now)
        existing = Event.objects.filter(fingerprint=fingerprint).first()
        if existing:
            return existing, False
        try:
            explanation = explain_event(candidate, version.as_policy())
        except Exception:
            explanation = fallback_explanation(candidate, version.as_policy())
        if not explanation:
            explanation = fallback_explanation(candidate, version.as_policy())
        event = Event.objects.create(
            lens=lens,
            lens_version=version,
            lens_run=run,
            cmc_call_log=cmc_log,
            asset_id=candidate.observation.asset_id,
            symbol=candidate.observation.symbol,
            name=candidate.observation.name,
            event_type="policy_match",
            fingerprint=fingerprint,
            observations_json={
                "asset": candidate.observation.model_dump(mode="json"),
                "context": candidate.context.model_dump(mode="json") if candidate.context else {},
                "conditions": candidate.condition_results,
            },
            score=candidate.score,
            score_reasons_json=candidate.reasons,
            severity=candidate.severity,
            explanation=explanation,
        )
        return event, True


def near_match_payload(candidate: Candidate) -> dict | None:
    if candidate.logic_passed or not candidate.conditions_met:
        return None
    actuals = {}
    conditions = []
    for item in candidate.condition_results:
        if item.get("skipped"):
            continue
        actuals[item["metric"]] = item["actual"]
        conditions.append(
            {
                "metric": item["metric"],
                "operator": item["operator"],
                "threshold": item["expected"],
                "passed": item["met"],
            }
        )
    if not conditions:
        return None
    observation = candidate.observation
    return {
        "symbol": observation.symbol,
        "name": observation.name,
        "actuals": actuals,
        "conditions": conditions,
    }


def event_fingerprint(lens_id: int, asset_id: int, event_type: str, when) -> str:
    minutes = max(1, settings.EVENT_COOLDOWN_MINUTES)
    bucket = when.replace(second=0, microsecond=0)
    floored = (bucket.minute // minutes) * minutes if minutes < 60 else 0
    if minutes >= 60:
        hour_bucket = (bucket.hour // (minutes // 60)) * (minutes // 60)
        bucket = bucket.replace(hour=hour_bucket, minute=0)
    else:
        bucket = bucket.replace(minute=floored)
    raw = f"{lens_id}:{asset_id}:{event_type}:{bucket.isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()
