from django.db import models


class CmcCallLog(models.Model):
    lens_run = models.ForeignKey(
        "lenses.LensRun",
        on_delete=models.CASCADE,
        related_name="cmc_calls",
        null=True,
        blank=True,
    )
    endpoint = models.CharField(max_length=160)
    params_redacted = models.JSONField(default=dict)
    status_code = models.PositiveIntegerField(default=0)
    credit_count = models.PositiveIntegerField(null=True, blank=True)
    response_excerpt = models.TextField(blank=True)
    fields_used = models.JSONField(default=list)
    elapsed_ms = models.PositiveIntegerField(default=0)
    error = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.endpoint} {self.status_code}"
