from __future__ import annotations

from apps.intelligence.calculations import period_adjective, period_label
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
        window = period_label(str(payload.get("window") or "")) or "the requested period"
        if payload.get("window") and any(row.get("window_change") is not None for row in rows):
            return " ".join(_spoken_window_row(row, window) for row in rows)
        if payload.get("window"):
            names = " and ".join(row.get("name") or row.get("symbol") or "the asset" for row in rows)
            live = " ".join(_spoken_row(row) for row in rows)
            return (
                f"A {period_adjective(str(payload.get('window') or ''))} history was not returned for {names}, "
                f"so these 24-hour quotes are not that comparison. {live}"
            )
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
            text = f"{assets} assets analyzed; the mean 24h change is unchanged."
        else:
            text = f"{assets} assets analyzed; the mean 24h change is {direction} {abs(mean):.2f}%."
        context = payload.get("context") or {}
        label = context.get("fear_greed_label")
        value = context.get("fear_greed_value")
        if label:
            reading = f"Fear & Greed is {label}"
            if value is not None:
                reading += f" ({value})"
            text = text.rstrip(".") + ". " + reading + "."
        return text
    if kind == "news_brief":
        analysis = (payload.get("analysis") or "").strip()
        if analysis:
            return analysis
        headlines = payload.get("headlines")
        count = len(headlines) if isinstance(headlines, list) else headlines or len(payload.get("items") or [])
        if count:
            return f"{count} CoinMarketCap headlines, related to live quotes."
        return "CoinMarketCap returned no News/Headlines for this request."
    if kind == "no_result":
        return (
            payload.get("message")
            or "No matching result was found based on the available CoinMarketCap data."
        )
    return None


def _spoken_window_row(row: dict, window: str) -> str:
    name = row.get("name") or row.get("symbol") or "This asset"
    change = row.get("window_change")
    start = _format_usd(row.get("window_start"))
    end = _format_usd(row.get("window_end"))
    if change is None or start == "—" or end == "—":
        return _spoken_row(row)
    if change > 0:
        move = f"up {abs(change):.2f}%"
    elif change < 0:
        move = f"down {abs(change):.2f}%"
    else:
        move = "unchanged"
    latest = _format_usd(row.get("price"))
    sentence = f"{name} moved from {start} to {end}, {move} over {window}."
    if latest != "—":
        sentence += f" The latest price is {latest}."
    return sentence


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
