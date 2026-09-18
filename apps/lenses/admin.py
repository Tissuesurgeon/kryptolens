from django.contrib import admin

from .models import (
    AgentTask,
    ApprovalRequest,
    Artifact,
    ConversationItem,
    Evidence,
    Job,
    Lens,
    LensRun,
    LensVersion,
    Result,
    Routine,
    VerificationRecord,
)


@admin.register(Lens)
class LensAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "status", "last_run_at")


@admin.register(LensVersion)
class LensVersionAdmin(admin.ModelAdmin):
    list_display = ("lens", "version", "created_at")


@admin.register(LensRun)
class LensRunAdmin(admin.ModelAdmin):
    list_display = ("lens", "trigger", "status", "stage", "events_promoted", "results_count", "started_at")


@admin.register(Routine)
class RoutineAdmin(admin.ModelAdmin):
    list_display = ("lens", "kind", "paused", "interval_minutes")


@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
    list_display = ("lens", "kind", "title", "created_at")


@admin.register(ConversationItem)
class ConversationItemAdmin(admin.ModelAdmin):
    list_display = ("lens", "item_type", "created_at")


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("lens", "category", "status", "updated_at")


@admin.register(Artifact)
class ArtifactAdmin(admin.ModelAdmin):
    list_display = ("lens", "kind", "title", "created_at")


@admin.register(AgentTask)
class AgentTaskAdmin(admin.ModelAdmin):
    list_display = ("lens", "assigned_agent", "status", "updated_at")


@admin.register(Evidence)
class EvidenceAdmin(admin.ModelAdmin):
    list_display = ("lens", "tool", "status", "created_at")


@admin.register(VerificationRecord)
class VerificationRecordAdmin(admin.ModelAdmin):
    list_display = ("lens", "overall_status", "created_at")


@admin.register(ApprovalRequest)
class ApprovalRequestAdmin(admin.ModelAdmin):
    list_display = ("lens", "action", "sensitivity", "status")
