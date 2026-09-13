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
    data = payload.get("data")
    if isinstance(data, list):
        sample = data[:2]
    elif isinstance(data, dict):
        sample = {key: data[key] for i, key in enumerate(data) if i < 2}
    else:
        sample = data
    status = payload.get("status") or {}
    safe_status = {
        "timestamp": status.get("timestamp"),
        "error_code": status.get("error_code"),
        "credit_count": status.get("credit_count"),
        "total_count": status.get("total_count"),
    }
    return json.dumps({"status": safe_status, "data_sample": sample}, default=str)[:limit]
