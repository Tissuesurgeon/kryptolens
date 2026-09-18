from __future__ import annotations

import json

from .adapter import CMCCall
from .models import CmcCallLog


def persist_call(call: CMCCall, lens_run=None) -> CmcCallLog:
    return CmcCallLog.objects.create(
        lens_run=lens_run,
        endpoint=call.endpoint,
        params_redacted=dict(call.params),
        status_code=call.status_code,
        credit_count=call.credit_count,
        response_excerpt=_excerpt(call.payload),
        fields_used=list(call.fields_used),
        elapsed_ms=call.elapsed_ms,
        error=call.error[:240] if call.error else "",
    )


def _excerpt(payload: dict, limit: int = 1800) -> str:
    status = payload.get("status") or {}
    safe_status = {
        "timestamp": status.get("timestamp"),
        "error_code": status.get("error_code"),
        "credit_count": status.get("credit_count"),
        "total_count": status.get("total_count"),
    }
    quotes = _quote_sample(payload.get("data"))
    headlines = _headline_sample(payload.get("data"))
    if quotes:
        body = {"status": safe_status, "quotes": quotes}
    elif headlines:
        body = {"status": safe_status, "headlines": headlines}
    else:
        body = {"status": safe_status, "data_sample": _compact_sample(payload.get("data"))}
    return json.dumps(body, default=str)[:limit]


def _headline_sample(data) -> list[dict]:
    rows = []
    if isinstance(data, list):
        values = data
    elif isinstance(data, dict):
        values = data.get("list") or data.get("items") or list(data.values())
    else:
        return []
    for item in values[:3]:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        assets = [
            str(asset.get("symbol") or "").upper()
            for asset in (item.get("assets") or [])
            if isinstance(asset, dict) and asset.get("symbol")
        ]
        rows.append({"title": item.get("title"), "source": item.get("source_name"), "assets": assets})
    return rows


def _quote_sample(data) -> list[dict]:
    from apps.cmc.normalize import quote_usd

    rows = []
    for item in _asset_dicts(data)[:3]:
        usd = quote_usd(item)
        price = usd.get("price")
        change = usd.get("percent_change_24h")
        if price is None and change is None:
            continue
        rows.append(
            {
                "symbol": item.get("symbol"),
                "name": item.get("name"),
                "price": price,
                "percent_change_24h": change,
            }
        )
    return rows


def _compact_sample(data):
    items = _asset_dicts(data)[:2]
    if not items:
        return data
    keep = ("id", "name", "symbol", "cmc_rank", "quote")
    return [{key: item[key] for key in keep if key in item} for item in items]


def _asset_dicts(data) -> list[dict]:
    items: list[dict] = []
    if isinstance(data, list):
        values = data
    elif isinstance(data, dict):
        values = list(data.values())
    else:
        return []
    for value in values:
        if isinstance(value, list):
            items.extend(entry for entry in value if isinstance(entry, dict))
        elif isinstance(value, dict):
            items.append(value)
    return items
