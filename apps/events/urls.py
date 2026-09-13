from django.urls import path

from . import views

urlpatterns = [
    path("events/<int:event_id>", views.receipt, name="event_receipt"),
]
