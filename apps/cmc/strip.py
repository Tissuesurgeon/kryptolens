from __future__ import annotations

from datetime import datetime

from django.conf import settings
from django.utils import timezone as django_timezone

from apps.cmc.adapter import CMCAdapter, CMCError
from apps.cmc.normalize import index_by_symbol, normalize_global_metrics, normalize_listings


class MarketStripService:
    @staticmethod
    def load(adapter: CMCAdapter | None = None) -> dict:
        return market_strip(adapter)


def _money(value: float | None) -> str:
    if value is None:
        return "—"
    abs_value = abs(value)
    if abs_value >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:.2f}T"
    if abs_value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if abs_value >= 1_000:
        return f"${value:,.0f}"
    return f"${value:,.2f}"


def _change(value: float | None) -> dict:
    if value is None:
        return {"text": "—", "kind": ""}
    kind = "up" if value > 0 else "down" if value < 0 else ""
    sign = "+" if value > 0 else ""
    return {"text": f"{sign}{value:.2f}%", "kind": kind}


def market_strip(adapter: CMCAdapter | None = None) -> dict:
    """Live BTC/ETH/SOL + global cap. Never invents numbers."""
    client = adapter or CMCAdapter(api_key=settings.CMC_API_KEY)
    fetched_at = django_timezone.now()
    try:
        quotes = client.get_quotes(["BTC", "ETH", "SOL"])
        global_call = client.get_global_metrics()
    except CMCError as exc:
        return {"ok": False, "error": str(exc), "assets": [], "total": None, "fetched_at": fetched_at}
    observations = index_by_symbol(normalize_listings(quotes.payload))
    context = normalize_global_metrics(global_call.payload)
    assets = []
    for symbol in ("BTC", "ETH", "SOL"):
        item = observations.get(symbol)
        assets.append(
            {
                "symbol": symbol,
                "price": _money(item.price if item else None),
                "change": _change(item.price_change_24h if item else None),
            }
        )
    timestamp = None
    status = (quotes.payload or {}).get("status") or {}
    raw_ts = status.get("timestamp")
    if raw_ts:
        try:
            timestamp = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
        except ValueError:
            timestamp = None
    return {
        "ok": True,
        "error": "",
        "assets": assets,
        "total": {
            "label": "TOTAL",
            "price": _money(context.total_market_cap),
            "change": _change(None),
        },
        "fetched_at": timestamp or fetched_at,
        "source": "CMC",
    }
