from __future__ import annotations

from datetime import datetime, timezone

from apps.intelligence.observations import MarketObservation
from apps.lenses.models import Observation


def persist_observations(run, observations: list[MarketObservation], endpoint: str = "") -> list[Observation]:
    created: list[Observation] = []
    if not run:
        return created
    for item in observations:
        created.append(
            Observation.objects.create(
                lens_run=run,
                asset_id=item.asset_id or 0,
                symbol=item.symbol or "",
                observed_at=item.observed_at or datetime.now(timezone.utc),
                fields_json={
                    "price": item.price,
                    "percent_change_24h": item.price_change_24h,
                    "volume_24h": item.volume_24h,
                    "volume_change_24h": item.volume_change_24h,
                    "market_cap": item.market_cap,
                    "cmc_rank": item.market_cap_rank,
                    "name": item.name,
                },
                source_endpoint=endpoint,
            )
        )
    return created
