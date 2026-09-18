from django.urls import path

from . import views

urlpatterns = [
    path("lenses", views.lens_list, name="lens_list"),
    path("lenses/create", views.lens_create, name="lens_create"),
    path("lenses/<int:lens_id>", views.lens_detail, name="lens_detail"),
    path("lenses/<int:lens_id>/activate", views.lens_activate, name="lens_activate"),
    path("lenses/<int:lens_id>/pause", views.lens_pause, name="lens_pause"),
    path("lenses/<int:lens_id>/run-now", views.lens_run_now, name="lens_run_now"),
    path("lenses/<int:lens_id>/runs/<int:run_id>", views.lens_run_status, name="lens_run_status"),
    path("lenses/<int:lens_id>/edit-intent", views.lens_edit_intent, name="lens_edit_intent"),
    path("agents", views.agent_home, name="agent_home"),
    path("agents/new", views.agent_create, name="agent_create"),
    path("agents/<int:lens_id>", views.lens_detail, name="agent_chat"),
    path("agents/<int:lens_id>/delete", views.agent_delete, name="agent_delete"),
    path("agents/<int:lens_id>/profile", views.agent_profile, name="agent_profile"),
    path("agents/<int:lens_id>/routines", views.agent_routines, name="agent_routines"),
    path("agents/<int:lens_id>/routines/<int:routine_id>", views.agent_routine_detail, name="agent_routine_detail"),
    path(
        "agents/<int:lens_id>/routines/<int:routine_id>/pause",
        views.agent_routine_pause,
        name="agent_routine_pause",
    ),
    path(
        "agents/<int:lens_id>/routines/<int:routine_id>/run-now",
        views.agent_routine_run,
        name="agent_routine_run",
    ),
    path(
        "agents/<int:lens_id>/routines/<int:routine_id>/historical",
        views.agent_routine_historical,
        name="agent_routine_historical",
    ),
    path("agents/<int:lens_id>/jobs", views.agent_jobs, name="agent_jobs"),
    path("jobs", views.job_list, name="job_list"),
    path("jobs/<int:run_id>", views.job_detail, name="job_detail"),
    path("market/strip", views.market_strip, name="market_strip"),
]
