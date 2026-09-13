from django.conf import settings
from django.db import models

from apps.intelligence.policy import IntelligencePolicy


class Lens(models.Model):
    STATUS = (("draft", "Draft"), ("active", "Active"), ("paused", "Paused"))

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lenses")
    name = models.CharField(max_length=160)
    natural_language_request = models.TextField()
    status = models.CharField(max_length=16, choices=STATUS, default="draft")
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_assets_checked = models.PositiveIntegerField(default=0)
    rank_snapshot = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.name

    def current_version(self):
        return self.versions.order_by("-version").first()

    def current_policy(self) -> IntelligencePolicy | None:
        version = self.current_version()
        if not version:
            return None
        return version.as_policy()


class LensVersion(models.Model):
    lens = models.ForeignKey(Lens, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField()
    policy_json = models.JSONField()
    source_intent = models.TextField()
    compile_report_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("lens", "version")
        ordering = ["-version"]

    def as_policy(self) -> IntelligencePolicy:
        return IntelligencePolicy.model_validate(self.policy_json)

    def __str__(self) -> str:
        return f"{self.lens.name} v{self.version}"


class LensRun(models.Model):
    STATUS = (("running", "Running"), ("ok", "OK"), ("error", "Error"))
    STAGES = (
        ("queued", "Queued"),
        ("loading_policy", "Loading policy"),
        ("fetching_cmc", "Fetching CMC"),
        ("evaluating", "Evaluating"),
        ("scoring", "Scoring"),
        ("complete", "Complete"),
        ("error", "Error"),
    )

    lens = models.ForeignKey(Lens, on_delete=models.CASCADE, related_name="runs")
    lens_version = models.ForeignKey(LensVersion, on_delete=models.SET_NULL, null=True)
    trigger = models.CharField(max_length=16, default="scheduled")
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS, default="running")
    stage = models.CharField(max_length=24, choices=STAGES, default="queued")
    assets_checked = models.PositiveIntegerField(default=0)
    candidates_evaluated = models.PositiveIntegerField(default=0)
    events_detected = models.PositiveIntegerField(default=0)
    events_promoted = models.PositiveIntegerField(default=0)
    events_suppressed = models.PositiveIntegerField(default=0)
    summary_json = models.JSONField(default=dict, blank=True)
    near_matches_json = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True)

    def set_stage(self, stage: str) -> None:
        self.stage = stage
        if stage == "error":
            self.status = "error"
        elif stage == "complete":
            self.status = "ok"
        else:
            self.status = "running"
        self.save(update_fields=["stage", "status"])

    class Meta:
        ordering = ["-started_at"]
