from __future__ import annotations

from apps.intelligence.observations import MarketObservation


def comparison_title(observations: list[MarketObservation]) -> str:
    if len(observations) == 1:
        return observations[0].name or observations[0].symbol or "Quote"
    if observations:
        return " · ".join(item.symbol for item in observations if item.symbol) or "Comparison"
    return "Comparison"


def spoken_result(result) -> str | None:
    if not result:
        return None
    payload = result.payload_json or {}
    kind = result.kind
    if kind == "comparison":
        rows = list(payload.get("rows") or [])
        if not rows:
            return "CoinMarketCap returned quotes, but I couldn't read a price from them."
        return " ".join(_spoken_row(row) for row in rows)
    if kind == "ranked_table":
        rows = list(payload.get("rows") or [])
        if not rows:
            return "CoinMarketCap returned listings, but none matched this ranking."
        leaders = rows[:3]
        direction = payload.get("direction") or ""
        if direction == "gainers" or (result.title or "").lower().startswith("highest 24h"):
            preface = "Highest 24h gains:"
        elif direction == "losers" or "declin" in (result.title or "").lower():
            preface = "Biggest 24h declines:"
        else:
            preface = "Biggest 24h moves:"
        return preface + " " + " ".join(_spoken_row(row) for row in leaders)
    if kind == "market_summary":
        assets = payload.get("assets")
        mean = payload.get("mean_price_change_24h")
        if assets is None:
            return None
        if mean is None:
            return f"{assets} assets analyzed."
        direction = "up" if mean > 0 else "down" if mean < 0 else "unchanged"
        if mean == 0:
            return f"{assets} assets analyzed; the mean 24h change is unchanged."
        return f"{assets} assets analyzed; the mean 24h change is {direction} {abs(mean):.2f}%."
    if kind == "news_brief":
        analysis = (payload.get("analysis") or "").strip()
        if analysis:
            return analysis
        headlines = payload.get("headlines") or len(payload.get("items") or [])
        if headlines:
            return f"{headlines} CoinMarketCap headlines, related to live quotes."
        return "CoinMarketCap returned no News/Headlines for this request."
    if kind == "no_result":
        return (
            payload.get("message")
            or "No matching result was found based on the available CoinMarketCap data."
        )
    return None


def _spoken_row(row: dict) -> str:
    name = row.get("name") or row.get("symbol") or "This asset"
    price = _format_usd(row.get("price"))
    change = row.get("price_change_24h")
    if price == "—":
        if change is None:
            return f"{name} is on CoinMarketCap, but the quote did not include a price."
        return f"{name} is { _format_pct_clause(change) }."
    if change is None:
        return f"{name} is at {price}."
    return f"{name} is at {price}, {_format_pct_clause(change)}."


def _format_pct_clause(change: float) -> str:
    if change > 0:
        return f"up {abs(change):.2f}% over 24 hours"
    if change < 0:
        return f"down {abs(change):.2f}% over 24 hours"
    return "unchanged over 24 hours"


def _format_usd(price) -> str:
    try:
        value = float(price)
    except (TypeError, ValueError):
        return "—"
    if abs(value) >= 1:
        return f"${value:,.2f}"
    if abs(value) >= 0.01:
        return f"${value:,.4f}"
    return f"${value:.8f}".rstrip("0").rstrip(".")
