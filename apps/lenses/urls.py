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
]
