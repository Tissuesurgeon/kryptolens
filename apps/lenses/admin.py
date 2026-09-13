from django.contrib import admin

from .models import Lens, LensRun, LensVersion


@admin.register(Lens)
class LensAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "status", "last_run_at")


@admin.register(LensVersion)
class LensVersionAdmin(admin.ModelAdmin):
    list_display = ("lens", "version", "created_at")


@admin.register(LensRun)
class LensRunAdmin(admin.ModelAdmin):
    list_display = ("lens", "trigger", "status", "stage", "events_promoted", "started_at")
