from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.lenses.agent_service import AgentService
from apps.users.forms import LoginForm, SignupForm
from apps.users.models import UserPreference
from apps.users.services import consume_pending_intent


def landing(request):
    if request.user.is_authenticated:
        return redirect("home")
    if request.method == "POST":
        text = (request.POST.get("intent") or "").strip()
        if text:
            request.session["pending_intent"] = text
            return redirect("signup")
    return render(
        request,
        "landing.html",
        {"preview": None},
    )


def signup(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        UserPreference.objects.get_or_create(user=user)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        lens = consume_pending_intent(request)
        if lens:
            return redirect("lens_detail", lens_id=lens.id)
        return redirect("home")
    return render(request, "auth/signup.html", {"form": form})


def log_in(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = LoginForm(request.POST or None, request=request)
    if request.method == "POST" and form.is_valid():
        login(request, form.user, backend="django.contrib.auth.backends.ModelBackend")
        lens = consume_pending_intent(request)
        if lens:
            return redirect("lens_detail", lens_id=lens.id)
        nxt = request.GET.get("next") or request.POST.get("next")
        if nxt:
            return redirect(nxt)
        return redirect("home")
    return render(request, "auth/login.html", {"form": form, "next": request.GET.get("next", "")})


@require_POST
def sign_out(request):
    logout(request)
    return redirect("landing")


@login_required
def home(request):
    if request.method == "POST":
        text = (request.POST.get("intent") or "").strip()
        if text:
            lens, _, _ = AgentService.create_from_intent(request.user, text)
            return redirect("lens_detail", lens_id=lens.id)
        return redirect("agent_create")
    from apps.lenses.views import agent_home

    return agent_home(request)
