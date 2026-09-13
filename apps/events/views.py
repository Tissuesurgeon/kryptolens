from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render

from .models import Event


@login_required
def receipt(request, event_id: int):
    event = (
        Event.objects.select_related("lens", "lens_version", "lens_run", "cmc_call_log")
        .filter(pk=event_id, lens__user=request.user)
        .first()
    )
    if not event:
        raise Http404()
    policy = event.lens_version.as_policy()
    observation = event.observations_json or {}
    context = observation.get("context") or {}
    return render(
        request,
        "events/receipt.html",
        {
            "event": event,
            "policy": policy,
            "understanding": policy.understanding(),
            "observation": observation.get("asset") or observation,
            "market_context": context,
            "show_evidence": True,
        },
    )
