from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.events.models import Event
from apps.intelligence.compiler import compile_intent_report
from apps.lenses.models import Lens
from apps.lenses.services import create_lens_from_intent
from apps.lenses.templates_catalog import LENS_TEMPLATES
from apps.users.services import ensure_workspace_user


def landing(request):
    if request.user.is_authenticated:
        return redirect("home")
    preview = request.session.get("pending_compile")
    if request.method == "POST":
        text = (request.POST.get("intent") or "").strip()
        if text:
            report = compile_intent_report(text)
            preview = {
                "intent": text,
                "name": report["policy"].name,
                "you_asked": report["you_asked"],
                "assumptions": report["assumptions"],
                "clarification": report["clarification"],
                "confidence": report["confidence"],
            }
            request.session["pending_intent"] = text
            request.session["pending_compile"] = preview
    return render(
        request,
        "landing.html",
        {"preview": preview, "templates": LENS_TEMPLATES},
    )


def start(request):
    user = ensure_workspace_user()
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    pending = request.session.pop("pending_intent", None)
    request.session.pop("pending_compile", None)
    if pending:
        lens, _, _ = create_lens_from_intent(user, pending)
        return redirect("lens_detail", lens_id=lens.id)
    return redirect("home")


@require_POST
def sign_out(request):
    logout(request)
    return redirect("landing")


@login_required
def home(request):
    if request.method == "POST":
        text = (request.POST.get("intent") or "").strip()
        if text:
            lens, _, _ = create_lens_from_intent(request.user, text)
            return redirect("lens_detail", lens_id=lens.id)
    lenses = Lens.objects.filter(user=request.user).order_by("-updated_at")
    events = Event.objects.filter(lens__user=request.user).select_related("lens", "lens_version")[:12]
    suppressed = sum(run.events_suppressed for run in _recent_runs(request.user))
    return render(
        request,
        "workspace/home.html",
        {
            "lenses": lenses,
            "active_lenses": [item for item in lenses if item.status == "active"],
            "events": events,
            "templates": LENS_TEMPLATES,
            "filtered_count": suppressed,
        },
    )


def _recent_runs(user):
    from apps.lenses.models import LensRun

    return LensRun.objects.filter(lens__user=user).order_by("-started_at")[:20]
