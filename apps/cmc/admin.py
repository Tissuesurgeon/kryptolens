from django.contrib import admin

from .models import CmcCallLog


@admin.register(CmcCallLog)
class CmcCallLogAdmin(admin.ModelAdmin):
    list_display = ("endpoint", "status_code", "credit_count", "created_at")
