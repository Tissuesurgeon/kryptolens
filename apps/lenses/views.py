from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.lenses.agent_service import AgentService
from apps.lenses.conversation_service import ConversationService
from apps.lenses.models import Lens, Routine
from apps.lenses.routine_service import RoutineService
from apps.lenses.run_service import RunService
from apps.monitoring.tasks import run_lens as run_lens_task  # tests patch .delay


def _owned(request, lens_id: int) -> Lens:
    lens = Lens.objects.filter(pk=lens_id, user=request.user).first()
    if not lens:
        raise Http404()
    return lens


def _owned_routine(request, lens: Lens, routine_id: int) -> Routine:
    routine = lens.routines.filter(pk=routine_id).first()
    if not routine:
        raise Http404()
    return routine


def _flash(request, result) -> None:
    if not result.flash:
        return
    getattr(messages, result.flash_level, messages.info)(request, result.flash)


def _run_response(request, lens, run):
    if request.headers.get("HX-Request"):
        return render(
            request,
            "workspace/partials/run_status.html",
            {"lens": lens, "run": run, "working_cards": RunService.working_cards(run)},
        )
    if request.accepts("application/json") and not request.accepts("text/html"):
        return JsonResponse({"run_id": run.id, "stage": run.stage})
    return redirect(f"{reverse('lens_detail', args=[lens.id])}?run={run.id}")


@login_required
def lens_list(request):
    return redirect("agent_home")


@login_required
def lens_create(request):
    if request.method == "POST":
        text = (request.POST.get("intent") or "").strip()
        if not text:
            messages.error(request, "Describe the job you want this agent to handle.")
            return redirect("lens_create")
        lens, version, policy = AgentService.create_from_intent(request.user, text)
        messages.success(request, f"Created {policy.name} as Lens v{version.version}.")
        return redirect("lens_detail", lens_id=lens.id)
    lens = AgentService.create_draft(request.user)
    return redirect("lens_detail", lens_id=lens.id)


@login_required
def lens_detail(request, lens_id: int):
    lens = _owned(request, lens_id)
    AgentService.select(request.user, lens)
    preview = None
    diffs = []
    draft = ""
    if request.method == "POST":
        result = ConversationService.handle(
            lens,
            request.POST.get("intent") or "",
            action=request.POST.get("action") or "",
        )
        _flash(request, result)
        if result.kind == "run":
            return _run_response(request, lens, result.run)
        if result.kind == "preview":
            preview, diffs, draft = result.preview, result.diffs, result.draft
        else:
            return redirect("lens_detail", lens_id=lens.id)
    context = ConversationService.context(lens, request)
    context.update({"preview": preview, "diffs": diffs, "draft": draft})
    return render(request, "workspace/lens.html", context)


@login_required
@require_POST
def lens_activate(request, lens_id: int):
    lens = _owned(request, lens_id)
    status = AgentService.activate(lens)
    if status == "no_job":
        messages.error(request, "Give this agent a job before activating.")
    elif status == "news":
        messages.info(request, "News monitoring isn't available yet.")
    else:
        messages.success(
            request,
            "I'm on it. I'll keep this job running and bring results back here.",
        )
    return redirect("lens_detail", lens_id=lens.id)


@login_required
@require_POST
def lens_pause(request, lens_id: int):
    lens = _owned(request, lens_id)
    AgentService.pause(lens)
    messages.info(request, f"{lens.name} is paused.")
    return redirect("lens_detail", lens_id=lens.id)


@login_required
@require_POST
def lens_run_now(request, lens_id: int):
    lens = _owned(request, lens_id)
    run = RunService.queue_now(lens, trigger="manual")
    if not run:
        messages.error(request, "This agent has no job yet.")
        return redirect("lens_detail", lens_id=lens.id)
    return _run_response(request, lens, run)


@login_required
def lens_run_status(request, lens_id: int, run_id: int):
    lens = Lens.objects.filter(pk=lens_id).first()
    if not lens:
        return HttpResponse("")
    if lens.user_id != request.user.id:
        raise Http404()
    run = lens.runs.filter(pk=run_id).first()
    if not run:
        return HttpResponse("")
    run = RunService.kick_if_stranded(run)
    RunService.record_activity(lens, run)
    return render(
        request,
        "workspace/partials/run_status.html",
        {"lens": lens, "run": run, "working_cards": RunService.working_cards(run)},
    )


@login_required
def lens_edit_intent(request, lens_id: int):
    lens = _owned(request, lens_id)
    preview = None
    diffs = []
    draft = request.GET.get("intent") or "Make this stricter."
    if request.method == "POST":
        text = (request.POST.get("intent") or "").strip()
        action = request.POST.get("action")
        result = ConversationService.apply(lens, text) if action == "apply" else ConversationService.compile_preview(lens, text)
        _flash(request, result)
        if result.kind == "applied":
            return redirect("lens_detail", lens_id=lens.id)
        if result.kind == "error":
            return redirect("lens_detail", lens_id=lens.id)
        preview, diffs, draft = result.preview, result.diffs, result.draft
    context = ConversationService.context(lens)
    context.update({"preview": preview, "diffs": diffs, "draft": draft})
    return render(request, "workspace/edit.html", context)


@login_required
def agent_home(request):
    lenses = AgentService.list_for_user(request.user)
    return render(
        request,
        "workspace/home.html",
        {
            "lenses": lenses,
            "first_run": not lenses,
            "agent_home": True,
        },
    )


@login_required
def agent_create(request):
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        purpose = (request.POST.get("purpose") or request.POST.get("description") or "").strip()
        if not name:
            messages.error(request, "Give this agent a name.")
            return render(request, "workspace/create_agent.html", {"name": name, "purpose": purpose})
        lens = AgentService.create(request.user, name, purpose)
        messages.success(request, f"Created {lens.name}.")
        return redirect("lens_detail", lens_id=lens.id)
    return render(request, "workspace/create_agent.html", {"name": "", "purpose": ""})


@login_required
@require_POST
def agent_delete(request, lens_id: int):
    lens = _owned(request, lens_id)
    name = AgentService.delete(lens)
    messages.info(request, f"Deleted {name}.")
    return redirect("agent_home")


@login_required
def agent_profile(request, lens_id: int):
    lens = _owned(request, lens_id)
    if request.method == "POST":
        AgentService.update_profile(
            lens,
            (request.POST.get("name") or "").strip(),
            (request.POST.get("purpose") or "").strip(),
        )
        messages.success(request, "Agent updated.")
        return redirect("agent_profile", lens_id=lens.id)
    context = ConversationService.context(lens, request)
    context.update(
        {
            "agent_nav": "profile",
            "routine_count": lens.routines.count(),
            "jobs_completed": lens.runs.filter(status="ok").count(),
        }
    )
    return render(request, "workspace/profile.html", context)


@login_required
def agent_routines(request, lens_id: int):
    lens = _owned(request, lens_id)
    context = ConversationService.context(lens, request)
    context.update({"agent_nav": "routines", "routines": RoutineService.list_for_lens(lens)})
    return render(request, "workspace/routines.html", context)


@login_required
def agent_routine_detail(request, lens_id: int, routine_id: int):
    lens = _owned(request, lens_id)
    routine = _owned_routine(request, lens, routine_id)
    context = ConversationService.context(lens, request)
    context.update(
        {
            "agent_nav": "routines",
            "detail_routine": routine,
            "live": RoutineService.live_status(lens, routine),
            "routine_runs": RoutineService.recent_runs(lens, routine),
        }
    )
    return render(request, "workspace/routine_detail.html", context)


@login_required
@require_POST
def agent_routine_pause(request, lens_id: int, routine_id: int):
    lens = _owned(request, lens_id)
    routine = RoutineService.toggle_pause(_owned_routine(request, lens, routine_id))
    messages.info(request, "Paused." if routine.paused else "Resumed.")
    return redirect("agent_routine_detail", lens_id=lens.id, routine_id=routine.id)


@login_required
@require_POST
def agent_routine_run(request, lens_id: int, routine_id: int):
    lens = _owned(request, lens_id)
    routine = _owned_routine(request, lens, routine_id)
    run = RoutineService.queue_run_now(lens, routine)
    if not run:
        messages.error(request, "This agent has no job yet.")
        return redirect("agent_routine_detail", lens_id=lens.id, routine_id=routine.id)
    return _run_response(request, lens, run)


@login_required
@require_POST
def agent_routine_historical(request, lens_id: int, routine_id: int):
    lens = _owned(request, lens_id)
    routine = _owned_routine(request, lens, routine_id)
    run = RoutineService.queue_historical(lens, routine, request.POST.get("as_of") or "")
    if not run:
        messages.error(request, "Pick a date for the historical test.")
        return redirect("agent_routine_detail", lens_id=lens.id, routine_id=routine.id)
    return _run_response(request, lens, run)


@login_required
def agent_jobs(request, lens_id: int):
    lens = _owned(request, lens_id)
    runs = RunService.list_for_lens(lens)
    context = ConversationService.context(lens, request)
    context.update(
        {
            "agent_nav": "jobs",
            "runs": runs,
            "running": [item for item in runs if item.status == "running"],
            "completed": [item for item in runs if item.status == "ok"],
            "failed": [item for item in runs if item.status == "error"],
        }
    )
    return render(request, "workspace/jobs.html", context)


@login_required
def job_list(request):
    grouped = RunService.grouped_for_user(request.user)
    grouped["first_run"] = False
    return render(request, "workspace/jobs.html", grouped)


@login_required
def job_detail(request, run_id: int):
    run = RunService.get_for_user(request.user, run_id)
    if not run:
        raise Http404()
    result = run.results.order_by("-id").first()
    return render(
        request,
        "workspace/job_detail.html",
        {
            "lens": run.lens,
            "run": run,
            "result": result,
            "cmc_calls": list(run.cmc_calls.order_by("created_at")),
            "trace": RunService.get_trace(run),
        },
    )


@login_required
def market_strip(request):
    from apps.cmc.strip import MarketStripService

    return render(request, "workspace/partials/market_strip.html", {"strip": MarketStripService.load()})
