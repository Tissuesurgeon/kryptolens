from apps.intelligence.compiler import compile_intent_report
from apps.intelligence.policy import IntelligencePolicy, policy_diff

from .models import Lens, LensVersion


def _report_payload(report: dict) -> dict:
    return {
        "you_asked": report.get("you_asked") or [],
        "assumptions": report.get("assumptions") or [],
        "clarification": report.get("clarification"),
        "confidence": report.get("confidence"),
    }


def create_lens_from_intent(user, text: str, provider=None) -> tuple[Lens, LensVersion, IntelligencePolicy]:
    report = compile_intent_report(text, provider=provider)
    policy = report["policy"]
    lens = Lens.objects.create(
        user=user,
        name=policy.name,
        natural_language_request=text,
        status="draft",
    )
    version = LensVersion.objects.create(
        lens=lens,
        version=1,
        policy_json=policy.model_dump(mode="json"),
        source_intent=text,
        compile_report_json=_report_payload(report),
    )
    return lens, version, policy


def apply_intent_edit(lens: Lens, text: str, provider=None) -> tuple[LensVersion, list[dict]]:
    current = lens.current_policy()
    report = compile_intent_report(text, provider=provider, current_policy=current)
    policy = report["policy"]
    next_version = (lens.current_version().version if lens.current_version() else 0) + 1
    version = LensVersion.objects.create(
        lens=lens,
        version=next_version,
        policy_json=policy.model_dump(mode="json"),
        source_intent=text,
        compile_report_json=_report_payload(report),
    )
    lens.name = policy.name
    lens.natural_language_request = text
    lens.save(update_fields=["name", "natural_language_request", "updated_at"])
    return version, policy_diff(current, policy) if current else []
