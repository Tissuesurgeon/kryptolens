"""Agent (product) = Lens (model). Do not rename the table."""

from __future__ import annotations

from django.db.models import Count, Q

from apps.lenses.conversation import add_item
from apps.lenses.models import Lens
from apps.lenses.services import create_agent, create_draft_lens, create_lens_from_intent, start_watching
from apps.lenses.status import lens_state
from apps.users.models import UserPreference


class AgentService:
    @staticmethod
    def list_for_user(user) -> list[Lens]:
        AgentService.drop_canned_openers_for_user(user)
        lenses = list(
            Lens.objects.filter(user=user)
            .annotate(
                routine_count=Count("routines"),
                active_routine_count=Count("routines", filter=Q(routines__paused=False, routines__enabled=True)),
                job_count=Count("runs"),
            )
            .order_by("-updated_at")
        )
        for item in lenses:
            item.agent_state = lens_state(item)
            last = item.conversation_items.order_by("-created_at").first()
            payload = (last.payload_json or {}) if last else {}
            item.last_activity = (
                payload.get("text")
                or payload.get("purpose")
                or payload.get("objective")
                or item.purpose
                or item.agent_state.get("label")
            )
            item.last_at = last.created_at if last else item.updated_at
        return lenses

    @staticmethod
    def drop_canned_openers(lens: Lens) -> int:
        from apps.lenses.models import ConversationItem

        removed = 0
        for item in ConversationItem.objects.filter(lens=lens, item_type="assistant_message"):
            text = (item.payload_json or {}).get("text") or ""
            if "What would you like me to watch?" in text:
                item.delete()
                removed += 1
        return removed

    @staticmethod
    def drop_canned_openers_for_user(user) -> int:
        from apps.lenses.models import ConversationItem

        removed = 0
        for item in ConversationItem.objects.filter(lens__user=user, item_type="assistant_message"):
            text = (item.payload_json or {}).get("text") or ""
            if "What would you like me to watch?" in text:
                item.delete()
                removed += 1
        return removed

    @staticmethod
    def create(user, name: str, purpose: str = "") -> Lens:
        lens = create_agent(user, name, purpose)
        AgentService.select(user, lens)
        return lens

    @staticmethod
    def select(user, lens: Lens) -> None:
        preference, _ = UserPreference.objects.get_or_create(user=user)
        preference.active_lens = lens
        preference.save(update_fields=["active_lens"])

    @staticmethod
    def create_from_intent(user, text: str, provider=None):
        return create_lens_from_intent(user, text, provider=provider)

    @staticmethod
    def create_draft(user, name: str | None = None, purpose: str = "") -> Lens:
        return create_draft_lens(user, name=name, purpose=purpose)

    @staticmethod
    def update_profile(lens: Lens, name: str, purpose: str) -> Lens:
        if name:
            lens.name = name
        lens.purpose = purpose
        lens.save(update_fields=["name", "purpose", "updated_at"])
        return lens

    @staticmethod
    def activate(lens: Lens) -> str:
        if not lens.current_version():
            return "no_job"
        job = lens.current_version().as_job()
        if job and job.news_unavailable:
            return "news"
        start_watching(lens)
        return "ok"

    @staticmethod
    def pause(lens: Lens) -> None:
        lens.status = "paused"
        lens.save(update_fields=["status", "updated_at"])
        job = lens.live_job()
        if job:
            job.status = "paused"
            job.save(update_fields=["status", "updated_at"])
        add_item(lens, "status_update", {"text": "Paused", "status": "paused"})

    @staticmethod
    def delete(lens: Lens) -> str:
        from django.db import transaction

        from apps.events.models import Event

        name = lens.name
        user = lens.user
        with transaction.atomic():
            lens.results.all().delete()
            Event.objects.filter(lens=lens).delete()
            lens.delete()
        remaining = Lens.objects.filter(user=user).order_by("-updated_at").first()
        preference = UserPreference.objects.filter(user=user).first()
        if remaining and preference and preference.active_lens_id is None:
            AgentService.select(user, remaining)
        return name
