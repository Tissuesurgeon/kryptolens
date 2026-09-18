import pytest
from django.conf import settings


@pytest.fixture(autouse=True)
def _fast_settings(settings, monkeypatch):
    settings.CMC_API_KEY = "test-key"
    settings.TELEGRAM_BOT_TOKEN = ""
    settings.EVENT_COOLDOWN_MINUTES = 60
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.SCORE_HIGH_MIN = 4
    settings.SCORE_MEDIUM_MIN = 2
    monkeypatch.setenv("CURSOR_API_KEY", "")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
