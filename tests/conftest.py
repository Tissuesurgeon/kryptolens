import pytest
from django.conf import settings


@pytest.fixture(autouse=True)
def _fast_settings(settings):
    settings.CMC_API_KEY = "test-key"
    settings.TELEGRAM_BOT_TOKEN = ""
    settings.EVENT_COOLDOWN_MINUTES = 60
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.SCORE_HIGH_MIN = 4
    settings.SCORE_MEDIUM_MIN = 2
