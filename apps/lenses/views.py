from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.intelligence.compiler import compile_intent_report
from apps.intelligence.policy import policy_diff
from apps.lenses.templates_catalog import LENS_TEMPLATES
from apps.lenses.status import lens_state
from apps.monitoring.tasks import run_lens as run_lens_task

from .models import Lens, LensRun
from .services import apply_intent_edit, create_lens_from_intent


def _owned(request, lens_id: int) -> Lens:
    lens = Lens.objects.filter(pk=lens_id, user=request.user).first()
    if not lens:
        raise Http404()
    return lens


def _conversation_context(lens: Lens, request=None) -> dict:
    version = lens.current_version()
    policy = version.as_policy() if version else None
    report = (version.compile_report_json if version else {}) or {}
    if policy and not report.get("you_asked"):
        from apps.intelligence.compiler import infer_you_asked

        report = {
            "you_asked": infer_you_asked(lens.natural_language_request, policy),
            "assumptions": list(policy.assumptions),
            "clarification": None,
            "confidence": report.get("confidence"),
        }
    latest_run = None
    if request is not None:
        run_id = request.GET.get("run")
        if run_id:
            latest_run = lens.runs.filter(pk=run_id).first()
    latest_run = latest_run or lens.runs.order_by("-started_at").first()
    return {
        "lens": lens,
        "version": version,
        "policy": policy,
        "policy_json": policy.model_dump_json(indent=2) if policy else "",
        "understanding": policy.understanding() if policy else None,
        "compile_report": report,
        "events": lens.events.select_related("lens_version")[:20],
        "runs": lens.runs.all()[:8],
        "latest_run": latest_run,
        "lens_state": lens_state(lens),
    }


@login_required
def lens_list(request):
    return redirect("home")


@login_required
def lens_create(request):
    preset = request.GET.get("template", "")
    intent = next((item["intent"] for item in LENS_TEMPLATES if item["slug"] == preset), "")
    if request.method == "POST":
        text = (request.POST.get("intent") or "").strip()
        if not text:
            messages.error(request, "Describe what you want KryptoLens to watch.")
            return redirect("lens_create")
        lens, version, policy = create_lens_from_intent(request.user, text)
        messages.success(request, f"Compiled {policy.name} as Lens v{version.version}.")
        return redirect("lens_detail", lens_id=lens.id)
    return render(
        request,
        "workspace/create.html",
        {"templates": LENS_TEMPLATES, "intent": intent},
    )


@login_required
def lens_detail(request, lens_id: int):
    lens = _owned(request, lens_id)
    preview = None
    diffs = []
    draft = ""
    if request.method == "POST":
        text = (request.POST.get("intent") or "").strip()
        action = request.POST.get("action") or "preview"
        current = lens.current_policy()
        if not current:
            messages.error(request, "No current policy to edit.")
            return redirect("lens_detail", lens_id=lens.id)
        if action == "apply":
            version, diffs = apply_intent_edit(lens, text)
            messages.success(request, f"Applied as Lens v{version.version}.")
            return redirect("lens_detail", lens_id=lens.id)
        report = compile_intent_report(text, current_policy=current)
        preview = report["policy"]
        diffs = policy_diff(current, preview)
        draft = text
    context = _conversation_context(lens, request)
    context.update({"preview": preview, "diffs": diffs, "draft": draft})
    return render(request, "workspace/lens.html", context)


@login_required
@require_POST
def lens_activate(request, lens_id: int):
    lens = _owned(request, lens_id)
    if not lens.current_version():
        messages.error(request, "Compile an intent before activating.")
        return redirect("lens_detail", lens_id=lens.id)
    lens.status = "active"
    lens.save(update_fields=["status", "updated_at"])
    messages.success(request, f"{lens.name} is now monitoring every 15 minutes.")
    return redirect("lens_detail", lens_id=lens.id)


@login_required
@require_POST
def lens_pause(request, lens_id: int):
    lens = _owned(request, lens_id)
    lens.status = "paused"
    lens.save(update_fields=["status", "updated_at"])
    messages.info(request, f"{lens.name} is paused.")
    return redirect("lens_detail", lens_id=lens.id)


@login_required
@require_POST
def lens_run_now(request, lens_id: int):
    lens = _owned(request, lens_id)
    version = lens.current_version()
    if not version:
        messages.error(request, "This lens has no policy yet.")
        return redirect("lens_detail", lens_id=lens.id)
    run = LensRun.objects.create(
        lens=lens,
        lens_version=version,
        trigger="manual",
        status="running",
        stage="queued",
    )
    try:
        run_lens_task.delay(lens.id, "manual", run.id)
    except Exception as exc:
        run.error = f"Could not queue run: {exc}"
        run.stage = "error"
        run.status = "error"
        run.save(update_fields=["error", "stage", "status"])
    if request.headers.get("HX-Request"):
        return render(request, "workspace/partials/run_status.html", {"lens": lens, "run": run})
    if request.accepts("application/json") and not request.accepts("text/html"):
        return JsonResponse({"run_id": run.id, "stage": run.stage})
    return redirect(f"{reverse('lens_detail', args=[lens.id])}?run={run.id}")


@login_required
def lens_run_status(request, lens_id: int, run_id: int):
    lens = _owned(request, lens_id)
    run = lens.runs.filter(pk=run_id).first()
    if not run:
        raise Http404()
    return render(request, "workspace/partials/run_status.html", {"lens": lens, "run": run})


@login_required
def lens_edit_intent(request, lens_id: int):
    lens = _owned(request, lens_id)
    current = lens.current_policy()
    preview = None
    diffs = []
    draft = request.GET.get("intent") or "Make this stricter."
    if request.method == "POST":
        text = (request.POST.get("intent") or "").strip()
        action = request.POST.get("action")
        if not current:
            messages.error(request, "No current policy to edit.")
            return redirect("lens_detail", lens_id=lens.id)
        if action == "apply":
            version, diffs = apply_intent_edit(lens, text)
            messages.success(request, f"Applied as Lens v{version.version}.")
            return redirect("lens_detail", lens_id=lens.id)
        report = compile_intent_report(text, current_policy=current)
        preview = report["policy"]
        diffs = policy_diff(current, preview)
        draft = text
    context = _conversation_context(lens)
    context.update({"preview": preview, "diffs": diffs, "draft": draft})
    return render(request, "workspace/edit.html", context)
