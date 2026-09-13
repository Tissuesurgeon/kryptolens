from django.db import models


class Event(models.Model):
    lens = models.ForeignKey("lenses.Lens", on_delete=models.CASCADE, related_name="events")
    lens_version = models.ForeignKey("lenses.LensVersion", on_delete=models.PROTECT, related_name="events")
    lens_run = models.ForeignKey("lenses.LensRun", on_delete=models.SET_NULL, null=True, blank=True, related_name="events")
    cmc_call_log = models.ForeignKey(
        "cmc.CmcCallLog",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    asset_id = models.PositiveIntegerField()
    symbol = models.CharField(max_length=32)
    name = models.CharField(max_length=120, blank=True)
    event_type = models.CharField(max_length=40, default="policy_match")
    fingerprint = models.CharField(max_length=64, db_index=True)
    observations_json = models.JSONField(default=dict)
    score = models.PositiveIntegerField(default=0)
    score_reasons_json = models.JSONField(default=list)
    severity = models.CharField(max_length=16, default="low")
    explanation = models.TextField(blank=True)
    detected_at = models.DateTimeField(auto_now_add=True)
    notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-detected_at"]

    def __str__(self) -> str:
        return f"{self.symbol} / {self.lens.name}"

    def observation(self) -> dict:
        return self.observations_json or {}
