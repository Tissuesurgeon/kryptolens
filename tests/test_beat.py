import inspect

import pytest

from apps.lenses.services import create_lens_from_intent
from apps.monitoring import tasks
from apps.users.models import User


def test_beat_task_source_uses_agent_runtime():
    source = inspect.getsource(tasks.run_lens)
    assert "AgentRuntime" in source
    assert "trigger_routine" in source
    assert "run_now" in source
    assert "invent" not in source.lower()
    beat = inspect.getsource(tasks.run_active_lenses)
    assert "run_lens.delay" in beat
    assert "AgentRuntime" not in beat


@pytest.mark.django_db
def test_scheduled_beat_calls_trigger_routine(monkeypatch):
    user = User.objects.create_user(username="beat", email="beat@kryptolens.app", password="x")
    lens, _, _ = create_lens_from_intent(user, "When BTC drops 2%, analyze the top 100.")
    lens.status = "active"
    lens.save(update_fields=["status"])
    calls = []

    class FakeRuntime:
        def __init__(self, *args, **kwargs):
            pass

        def trigger_routine(self, lens_id, trigger="scheduled", run=None):
            calls.append(("routine", lens_id, trigger))

            class Result:
                id = 7

            return Result()

        def run_now(self, lens_id, trigger="manual", run=None):
            raise AssertionError("Beat must not call run_now")

    monkeypatch.setattr("apps.intelligence.agent_runtime.AgentRuntime", FakeRuntime)
    assert tasks.run_lens(lens.id, "scheduled") == 7
    assert calls == [("routine", lens.id, "scheduled")]


@pytest.mark.django_db
def test_run_active_lenses_queues_due_teammates(monkeypatch):
    user = User.objects.create_user(username="queue", email="queue@kryptolens.app", password="x")
    lens, _, _ = create_lens_from_intent(user, "When BTC drops 2%, analyze the top 100.")
    lens.status = "active"
    lens.save(update_fields=["status"])
    queued = []
    monkeypatch.setattr("apps.monitoring.tasks.run_lens.delay", lambda *args, **kwargs: queued.append(args))
    assert tasks.run_active_lenses() == "LensRuntime"
    assert queued == [(lens.id, "scheduled")]
    assert tasks._should_run(lens)


@pytest.mark.django_db
def test_routine_run_now_calls_trigger_routine(monkeypatch):
    user = User.objects.create_user(username="honor", email="honor@kryptolens.app", password="x")
    lens, _, _ = create_lens_from_intent(user, "When BTC drops 2%, analyze the top 100.")
    calls = []

    class FakeRuntime:
        def __init__(self, *args, **kwargs):
            pass

        def trigger_routine(self, lens_id, trigger="scheduled", run=None):
            calls.append(("routine", lens_id, trigger))

            class Result:
                id = 9

            return Result()

        def run_now(self, lens_id, trigger="manual", run=None):
            raise AssertionError("Routine Run now must honor the trigger")

    monkeypatch.setattr("apps.intelligence.agent_runtime.AgentRuntime", FakeRuntime)
    assert tasks.run_lens(lens.id, "routine") == 9
    assert calls == [("routine", lens.id, "routine")]
