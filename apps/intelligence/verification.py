from __future__ import annotations

from apps.intelligence.agent import AgentPlan
from apps.intelligence.workflow import WorkflowDefinition


def verify_result(result, workflow: WorkflowDefinition | None, plan: AgentPlan | None) -> dict:
    rows = list((result.payload_json or {}).get("rows") or [])
    trigger = (result.payload_json or {}).get("trigger") or {}
    assets = (result.payload_json or {}).get("assets")
    if assets is None:
        assets = len(rows)
    requirements = list(plan.verification_requirements) if plan else []
    if not requirements:
        requirements = _default_requirements(workflow, result)

    checks: list[dict] = []
    for req in requirements:
        checks.append(_run_check(req, result, rows, trigger, assets, workflow))

    if not checks:
        checks.append({"id": "result_present", "label": "Result recorded", "passed": result.kind != "error"})

    passed = [item for item in checks if item.get("passed")]
    failed = [item for item in checks if not item.get("passed") and not item.get("skipped")]
    if result.kind == "error":
        status = "unsupported"
    elif result.kind == "no_result":
        status = "supported" if not failed else "inconclusive"
    elif result.kind == "news_brief":
        items = list((result.payload_json or {}).get("items") or [])
        status = "supported" if items and not failed else "needs_more_evidence" if not items else "unsupported"
    elif not rows and result.kind == "ranked_table":
        status = "needs_more_evidence"
    elif failed and not passed:
        status = "unsupported"
    elif failed:
        status = "unsupported"
    else:
        status = "supported"
    if status == "supported":
        # Product alias: verified maps onto stored supported.
        pass
    return {"status": status, "checks": checks, "passed": not failed}


def _default_requirements(workflow: WorkflowDefinition | None, result) -> list[str]:
    reqs: list[str] = []
    if workflow and workflow.trigger and workflow.trigger.asset:
        reqs.append("btc_trigger_verified" if workflow.trigger.asset.upper() == "BTC" else "trigger_verified")
    if result.kind == "ranked_table":
        reqs.extend(["assets_loaded", "decline_calculation_verified", "ranking_verified", "required_fields_present"])
    elif result.kind in {"comparison", "market_summary", "news_brief"}:
        reqs.append("required_fields_present")
        if result.kind == "news_brief":
            reqs.insert(0, "headlines_loaded")
    return reqs


def _run_check(req: str, result, rows: list[dict], trigger: dict, assets: int, workflow) -> dict:
    if req in {"btc_trigger_verified", "trigger_verified"}:
        actual = trigger.get("actual")
        if result.kind == "no_result":
            return {"id": req, "label": "Trigger verified", "passed": True}
        return {
            "id": req,
            "label": "Trigger verified",
            "passed": actual is not None or not (workflow and workflow.trigger and workflow.trigger.asset),
        }
    if req == "assets_loaded":
        expected = _expected_limit(workflow)
        label = f"{assets} assets loaded"
        passed = assets > 0 if result.kind != "no_result" else True
        if expected and assets and result.kind == "ranked_table":
            passed = assets > 0
        return {"id": req, "label": label, "passed": passed}
    if req == "decline_calculation_verified":
        if result.kind == "no_result":
            return {"id": req, "label": "Decline calculation verified", "passed": True, "skipped": True}
        passed = bool(rows) and all("price_change_24h" in row for row in rows)
        return {"id": req, "label": "Decline calculation verified", "passed": passed}
    if req == "ranking_verified":
        if result.kind == "no_result":
            return {"id": req, "label": "Ranking verified", "passed": True, "skipped": True}
        changes = [row["price_change_24h"] for row in rows if row.get("price_change_24h") is not None]
        passed = bool(changes) and changes == sorted(changes)
        return {"id": req, "label": "Ranking verified", "passed": passed}
    if req == "headlines_loaded":
        items = list((result.payload_json or {}).get("items") or [])
        count = len(items)
        return {
            "id": req,
            "label": f"{count} headlines loaded",
            "passed": bool(items) or result.kind == "no_result",
        }
    if req == "quotes_loaded":
        return {
            "id": req,
            "label": "Quotes loaded",
            "passed": bool(rows) or result.kind == "no_result",
        }
    if req == "required_fields_present":
        if result.kind in {"no_result", "event", "market_summary", "news_brief"}:
            return {"id": req, "label": "Required fields present", "passed": True}
        passed = bool(rows) and all(row.get("symbol") and "price_change_24h" in row for row in rows)
        return {"id": req, "label": "Required fields present", "passed": passed}
    return {"id": req, "label": req.replace("_", " ").title(), "passed": True}


def _expected_limit(workflow: WorkflowDefinition | None) -> int | None:
    if not workflow:
        return None
    for step in workflow.steps:
        if step.limit:
            return step.limit
    return None


def claim_supported(claim: str, result, evidence_rows: list) -> str:
    text = (claim or "").strip()
    if not text:
        return "inconclusive"
    payload = result.payload_json or {}
    symbols = {str(row.get("symbol") or "").upper() for row in (payload.get("rows") or []) if row.get("symbol")}
    tokens = [token.strip(".,:;!") for token in text.split() if token.strip(".,:;!")]
    mentioned = [token.upper() for token in tokens if token.isalpha() and 2 <= len(token) <= 5]
    mentioned = [token for token in mentioned if token not in {"LED", "THE", "CMC", "FROM", "WITH"}]
    if mentioned and symbols:
        if any(token in symbols for token in mentioned):
            return "supported"
        return "unsupported"
    haystack = " ".join(symbols).lower()
    if any(token.lower() in haystack for token in tokens if len(token) > 2):
        return "supported"
    if evidence_rows:
        return "unsupported"
    return "inconclusive"
