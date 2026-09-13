#!/usr/bin/env python3
"""M0 technology proof: prompt → policy JSON → CMC → observation → evaluate."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from apps.cmc.adapter import CMCAdapter, CMCError
from apps.cmc.normalize import is_stablecoin, normalize_fear_greed, normalize_listings
from apps.intelligence.compiler import compile_intent_safe
from apps.intelligence.engine import evaluate_policy
from apps.intelligence.planner import plan_query


def main() -> int:
    prompt = " ".join(sys.argv[1:]) or (
        "Watch the top 100 assets by market cap for strong 24h price movement, "
        "elevated volume, and improving market-cap rank."
    )
    print("== M0 chain ==")
    print(f"prompt: {prompt}")

    policy = compile_intent_safe(prompt)
    print("\n[1] IntelligencePolicy")
    print(policy.model_dump_json(indent=2))

    plan = plan_query(policy)
    print("\n[2] QueryPlan")
    print(plan.model_dump_json(indent=2))

    adapter = CMCAdapter()
    observations = []
    context = None
    try:
        if policy.universe.type == "symbols":
            call = adapter.get_quotes(policy.universe.symbols)
        else:
            call = adapter.get_listings(limit=policy.universe.limit)
        observations = normalize_listings(call.payload)
        print(f"\n[3] CMC {call.endpoint} status={call.status_code} credits={call.credit_count}")
        print(f"    observations={len(observations)}")
        if "fear_greed" in plan.include_context:
            fg = adapter.get_fear_greed()
            context = normalize_fear_greed(fg.payload)
            print(f"    fear_greed={context.fear_greed_value} {context.fear_greed_label}")
    except CMCError as exc:
        print(f"\n[3] CMC hop failed: {exc}")
        print("    Live CoinMarketCap data is required. No fixture fallback.")
        return 1

    if policy.universe.exclude_stablecoins:
        observations = [item for item in observations if not is_stablecoin(item)]

    evaluated = 0
    promoted = 0
    print("\n[4] Evaluation")
    for observation in observations:
        candidate = evaluate_policy(observation, policy, context)
        evaluated += 1
        if candidate.should_promote:
            promoted += 1
            print(
                f"    PROMOTE {observation.symbol} score={candidate.score} "
                f"severity={candidate.severity} reasons={candidate.reasons}"
            )
    print(f"    evaluated={evaluated} promoted={promoted}")
    print("\nM0 chain complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
