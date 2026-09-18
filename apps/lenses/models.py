from django.conf import settings
from django.db import models

from apps.intelligence.job import JobDefinition
from apps.intelligence.policy import IntelligencePolicy
from apps.intelligence.tools import DEFAULT_TOOL_PERMISSIONS
from apps.intelligence.workflow import WorkflowDefinition


class Lens(models.Model):
    """A Lens is a persistent crypto agent with a job, workflow, routines, tools, conversation, and results."""

    STATUS = (("draft", "Draft"), ("active", "Active"), ("paused", "Paused"))

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lenses")
    name = models.CharField(max_length=160)
    purpose = models.TextField(blank=True)
    natural_language_request = models.TextField()
    status = models.CharField(max_length=16, choices=STATUS, default="draft")
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_assets_checked = models.PositiveIntegerField(default=0)
    rank_snapshot = models.JSONField(default=dict, blank=True)
    context_json = models.JSONField(default=dict, blank=True)
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

    def current_routine(self):
        return self.routines.order_by("-id").first()

    def live_job(self):
        try:
            return self.assignment
        except Job.DoesNotExist:
            return None


class LensVersion(models.Model):
    lens = models.ForeignKey(Lens, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField()
    source_intent = models.TextField()
    job_definition_json = models.JSONField(default=dict, blank=True)
    policy_json = models.JSONField()
    workflow_json = models.JSONField(default=dict, blank=True)
    tool_permissions_json = models.JSONField(default=dict, blank=True)
    compile_report_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("lens", "version")
        ordering = ["-version"]

    def as_policy(self) -> IntelligencePolicy:
        return IntelligencePolicy.model_validate(self.policy_json)

    def as_job(self) -> JobDefinition | None:
        if not self.job_definition_json:
            return None
        return JobDefinition.model_validate(self.job_definition_json)

    def as_workflow(self) -> WorkflowDefinition:
        if not self.workflow_json:
            return WorkflowDefinition()
        return WorkflowDefinition.model_validate(self.workflow_json)

    def tool_permissions(self) -> dict:
        perms = dict(DEFAULT_TOOL_PERMISSIONS)
        perms.update(self.tool_permissions_json or {})
        return perms

    def __str__(self) -> str:
        return f"{self.lens.name} v{self.version}"


class LensRun(models.Model):
    STATUS = (("running", "Running"), ("ok", "OK"), ("error", "Error"))
    STAGES = (
        ("queued", "Queued"),
        ("loading_policy", "Loading policy"),
        ("planning", "Planning"),
        ("trigger_check", "Trigger check"),
        ("fetching_cmc", "Fetching CMC"),
        ("evaluating", "Evaluating"),
        ("analyzing", "Analyzing"),
        ("scoring", "Scoring"),
        ("investigating", "Investigating"),
        ("generating_report", "Generating report"),
        ("verifying", "Verifying"),
        ("repairing", "Repairing"),
        ("notifying", "Notifying"),
        ("complete", "Complete"),
        ("error", "Error"),
    )

    lens = models.ForeignKey(Lens, on_delete=models.CASCADE, related_name="runs")
    lens_version = models.ForeignKey(LensVersion, on_delete=models.SET_NULL, null=True)
    routine = models.ForeignKey("Routine", on_delete=models.SET_NULL, null=True, blank=True, related_name="runs")
    objective = models.TextField(blank=True)
    trigger = models.CharField(max_length=16, default="scheduled")
    as_of = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS, default="running")
    stage = models.CharField(max_length=24, choices=STAGES, default="queued")
    assets_checked = models.PositiveIntegerField(default=0)
    candidates_evaluated = models.PositiveIntegerField(default=0)
    events_detected = models.PositiveIntegerField(default=0)
    events_promoted = models.PositiveIntegerField(default=0)
    events_suppressed = models.PositiveIntegerField(default=0)
    results_count = models.PositiveIntegerField(default=0)
    workflow_json = models.JSONField(default=dict, blank=True)
    tools_used_json = models.JSONField(default=list, blank=True)
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


class Routine(models.Model):
    """When a Lens should work. Workflow defines what it does."""

    KINDS = (
        ("manual", "Manual"),
        ("interval", "Interval"),
        ("scheduled", "Scheduled"),
        ("event_triggered", "Event triggered"),
    )

    lens = models.ForeignKey(Lens, on_delete=models.CASCADE, related_name="routines")
    lens_version = models.ForeignKey(
        "LensVersion", on_delete=models.SET_NULL, null=True, blank=True, related_name="routines"
    )
    name = models.CharField(max_length=160, blank=True)
    description = models.TextField(blank=True)
    kind = models.CharField(max_length=24, choices=KINDS, default="event_triggered")
    interval_minutes = models.PositiveIntegerField(default=15)
    schedule_time = models.TimeField(null=True, blank=True)
    paused = models.BooleanField(default=False)
    enabled = models.BooleanField(default=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.lens.name} {self.kind}"


class Result(models.Model):
    """Primary output of a Lens run. Events are only one kind of result."""

    KINDS = (
        ("ranked_table", "Ranked table"),
        ("market_summary", "Market summary"),
        ("comparison", "Comparison"),
        ("news_brief", "News brief"),
        ("event", "Event"),
        ("no_result", "No result"),
        ("error", "Error"),
    )

    lens = models.ForeignKey(Lens, on_delete=models.CASCADE, related_name="results")
    lens_version = models.ForeignKey(LensVersion, on_delete=models.PROTECT, related_name="results")
    lens_run = models.ForeignKey(LensRun, on_delete=models.SET_NULL, null=True, blank=True, related_name="results")
    kind = models.CharField(max_length=24, choices=KINDS)
    title = models.CharField(max_length=200, blank=True)
    payload_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.kind} / {self.lens.name}"


class ConversationItem(models.Model):
    TYPES = (
        ("user_message", "User"),
        ("assistant_message", "Assistant"),
        ("lens_created", "Lens created"),
        ("job_created", "Job"),
        ("workflow_created", "Workflow"),
        ("routine_created", "Routine"),
        ("status_update", "Status"),
        ("scan_result", "Scan result"),
        ("event_result", "Event"),
        ("policy_diff", "Policy diff"),
        ("execution_error", "Error"),
        ("plan", "Plan"),
        ("evidence", "Evidence"),
        ("verification", "Verification"),
        ("execution_receipt", "Execution receipt"),
        ("cmc_activity", "CMC activity"),
        ("routine_proposal", "Routine proposal"),
        ("execution_trace", "Execution trace"),
    )

    lens = models.ForeignKey(Lens, on_delete=models.CASCADE, related_name="conversation_items")
    lens_version = models.ForeignKey(LensVersion, on_delete=models.SET_NULL, null=True, blank=True)
    lens_run = models.ForeignKey(LensRun, on_delete=models.SET_NULL, null=True, blank=True)
    result = models.ForeignKey(Result, on_delete=models.SET_NULL, null=True, blank=True)
    event = models.ForeignKey("events.Event", on_delete=models.SET_NULL, null=True, blank=True)
    artifact = models.ForeignKey(
        "Artifact",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conversation_items",
    )
    item_type = models.CharField(max_length=32, choices=TYPES)
    payload_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class Job(models.Model):
    """Live assignment for a Lens. JobDefinition JSON on LensVersion remains the versioned snapshot."""

    CATEGORIES = (("monitor", "Monitor"), ("investigate", "Investigate"), ("research", "Research"))
    STATUSES = (
        ("draft", "Draft"),
        ("active", "Active"),
        ("paused", "Paused"),
        ("completed", "Completed"),
        ("needs_attention", "Needs attention"),
    )

    lens = models.OneToOneField(Lens, on_delete=models.CASCADE, related_name="assignment")
    lens_version = models.ForeignKey(LensVersion, on_delete=models.SET_NULL, null=True, blank=True)
    routine = models.ForeignKey(Routine, on_delete=models.SET_NULL, null=True, blank=True)
    current_run = models.ForeignKey(
        LensRun, on_delete=models.SET_NULL, null=True, blank=True, related_name="current_jobs"
    )
    last_result = models.ForeignKey(
        Result, on_delete=models.SET_NULL, null=True, blank=True, related_name="jobs"
    )
    objective = models.TextField()
    category = models.CharField(max_length=16, choices=CATEGORIES, default="monitor")
    status = models.CharField(max_length=24, choices=STATUSES, default="draft")
    next_run_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.category} / {self.lens.name}"


class Observation(models.Model):
    """Persisted CMC observation for a run. Evidence references Observation.id, not raw API dicts."""

    lens_run = models.ForeignKey(LensRun, on_delete=models.CASCADE, related_name="observations")
    asset_id = models.IntegerField(default=0)
    symbol = models.CharField(max_length=24, blank=True)
    observed_at = models.DateTimeField()
    fields_json = models.JSONField(default=dict, blank=True)
    source_endpoint = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.symbol or self.asset_id} @ {self.observed_at}"


class Artifact(models.Model):
    KINDS = (
        ("plan", "Plan"),
        ("result", "Result"),
        ("evidence_pack", "Evidence pack"),
        ("report", "Report"),
        ("verification", "Verification"),
        ("execution_receipt", "Execution receipt"),
    )

    lens = models.ForeignKey(Lens, on_delete=models.CASCADE, related_name="artifacts")
    lens_version = models.ForeignKey(LensVersion, on_delete=models.SET_NULL, null=True, blank=True)
    lens_run = models.ForeignKey(LensRun, on_delete=models.SET_NULL, null=True, blank=True, related_name="artifacts")
    result = models.ForeignKey(Result, on_delete=models.SET_NULL, null=True, blank=True, related_name="artifacts")
    kind = models.CharField(max_length=32, choices=KINDS)
    title = models.CharField(max_length=200, blank=True)
    payload_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.kind} / {self.lens.name}"


class AgentTask(models.Model):
    AGENTS = (
        ("chief", "Chief"),
        ("market", "Market"),
        ("research", "Research"),
        ("unavailable", "Unavailable"),
    )
    STATUSES = (
        ("planned", "Planned"),
        ("acting", "Acting"),
        ("observing", "Observing"),
        ("verifying", "Verifying"),
        ("complete", "Complete"),
        ("needs_more_evidence", "Needs more evidence"),
    )

    lens = models.ForeignKey(Lens, on_delete=models.CASCADE, related_name="agent_tasks")
    lens_run = models.ForeignKey(LensRun, on_delete=models.SET_NULL, null=True, blank=True, related_name="agent_tasks")
    parent_task = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="children")
    assigned_agent = models.CharField(max_length=24, choices=AGENTS, default="chief")
    objective = models.TextField()
    status = models.CharField(max_length=32, choices=STATUSES, default="planned")
    input_artifacts = models.JSONField(default=list, blank=True)
    output_artifacts = models.JSONField(default=list, blank=True)
    next_gate = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Evidence(models.Model):
    STATUSES = (
        ("supported", "Supported"),
        ("unsupported", "Unsupported"),
        ("inconclusive", "Inconclusive"),
        ("needs_more_evidence", "Needs more evidence"),
    )

    lens = models.ForeignKey(Lens, on_delete=models.CASCADE, related_name="evidence")
    lens_run = models.ForeignKey(LensRun, on_delete=models.SET_NULL, null=True, blank=True, related_name="evidence")
    artifact = models.ForeignKey(Artifact, on_delete=models.SET_NULL, null=True, blank=True, related_name="evidence")
    cmc_call_log = models.ForeignKey(
        "cmc.CmcCallLog",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evidence",
    )
    source = models.CharField(max_length=64, default="cmc")
    tool = models.CharField(max_length=64, blank=True)
    fields_used = models.JSONField(default=list, blank=True)
    observation_ids = models.JSONField(default=list, blank=True)
    claim = models.TextField(blank=True)
    status = models.CharField(max_length=32, choices=STATUSES, default="supported")
    sanitized_excerpt = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class VerificationRecord(models.Model):
    STATUSES = (
        ("supported", "Supported"),
        ("unsupported", "Unsupported"),
        ("inconclusive", "Inconclusive"),
        ("needs_more_evidence", "Needs more evidence"),
    )

    lens = models.ForeignKey(Lens, on_delete=models.CASCADE, related_name="verifications")
    lens_run = models.ForeignKey(LensRun, on_delete=models.SET_NULL, null=True, blank=True, related_name="verifications")
    artifact = models.ForeignKey(
        Artifact, on_delete=models.SET_NULL, null=True, blank=True, related_name="verification_records"
    )
    overall_status = models.CharField(max_length=32, choices=STATUSES, default="supported")
    checks_json = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class ApprovalRequest(models.Model):
    STATUSES = (
        ("not_required", "Not required"),
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("denied", "Denied"),
    )

    lens = models.ForeignKey(Lens, on_delete=models.CASCADE, related_name="approvals")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="approvals")
    action = models.CharField(max_length=64)
    sensitivity = models.CharField(max_length=32)
    status = models.CharField(max_length=24, choices=STATUSES, default="not_required")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
