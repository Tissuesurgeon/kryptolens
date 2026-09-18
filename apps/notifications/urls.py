from django.urls import path

from . import views

urlpatterns = [
    path("settings", views.settings_page, name="settings"),
    path("telegram/webhook/<str:secret>", views.telegram_webhook, name="telegram_webhook"),
]
