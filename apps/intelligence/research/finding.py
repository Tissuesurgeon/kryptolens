"""A finding is a calculated conclusion, traceable to evidence and verification."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Finding(BaseModel):
    claim: str = ""
    kind: str = ""
    title: str = ""
    verification: str = ""
    evidence: list[str] = Field(default_factory=list)
    observation_ids: list[int] = Field(default_factory=list)
    result_id: int | None = None
    quantitative: bool = False
    supported: bool = False

    def grounded(self) -> bool:
        if self.verification in {"unsupported", "inconclusive", "needs_more_evidence"}:
            return False
        if self.quantitative and not self.evidence and not self.observation_ids:
            return False
        return bool(self.claim or self.title)


def finding_from_result(result, verification: dict | None = None, evidence_items=None) -> Finding:
    payload = (getattr(result, "payload_json", None) or {}) if result else {}
    claims = [str(item) for item in (payload.get("claims") or []) if item]
    evidence_claims = []
    observation_ids: list[int] = []
    for item in evidence_items or []:
        claim = getattr(item, "claim", "") or ""
        if claim:
            evidence_claims.append(claim)
        obs = getattr(item, "observation_id", None)
        if obs:
            observation_ids.append(int(obs))
    status = (verification or {}).get("status") or ""
    kind = getattr(result, "kind", "") or ""
    title = getattr(result, "title", "") or ""
    quantitative = kind in {"comparison", "ranked_table", "market_summary", "quote"} or bool(payload.get("metrics"))
    claim = claims[0] if claims else title
    supported = status in {"supported", "passed", "verified", ""} and status != "unsupported"
    if status in {"unsupported", "inconclusive", "needs_more_evidence"}:
        supported = False
    return Finding(
        claim=claim,
        kind=kind,
        title=title,
        verification=status,
        evidence=evidence_claims or claims[:4],
        observation_ids=observation_ids,
        result_id=getattr(result, "id", None),
        quantitative=quantitative,
        supported=supported,
    )
