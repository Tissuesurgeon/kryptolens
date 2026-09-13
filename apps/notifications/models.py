from django.db import models


class Notification(models.Model):
    STATUS = (("queued", "Queued"), ("sent", "Sent"), ("failed", "Failed"))

    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="notifications")
    channel = models.CharField(max_length=24, default="telegram")
    status = models.CharField(max_length=16, choices=STATUS, default="queued")
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
