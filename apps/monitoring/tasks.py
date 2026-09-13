from celery import shared_task

from apps.lenses.models import Lens

from .services import MonitoringService


@shared_task
def run_active_lenses():
    service = MonitoringService()
    for lens_id in Lens.objects.filter(status="active").values_list("id", flat=True):
        run_lens.delay(lens_id, "scheduled")
    return service.__class__.__name__


@shared_task
def run_lens(lens_id: int, trigger: str = "scheduled", run_id: int | None = None):
    from apps.lenses.models import LensRun

    existing = LensRun.objects.filter(pk=run_id).first() if run_id else None
    return MonitoringService().run_lens(lens_id, trigger=trigger, run=existing).id
