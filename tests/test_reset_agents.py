import pytest
from django.core.management import call_command

from apps.cmc.models import CmcCallLog
from apps.events.models import Event
from apps.lenses.models import Lens
from apps.lenses.services import create_lens_from_intent
from apps.users.models import User, UserPreference

GOLDEN = "When BTC drops by 2%, check the top 100 coins and rank their declines."


@pytest.mark.django_db
def test_reset_agents_keeps_users(capsys):
    user = User.objects.create_user(username="keep", email="keep@kryptolens.app", password="Workspace-secret-99")
    lens, version, _ = create_lens_from_intent(user, GOLDEN)
    UserPreference.objects.update_or_create(user=user, defaults={"active_lens": lens})
    CmcCallLog.objects.create(endpoint="/v3/cryptocurrency/listings/latest", status_code=200)
    Event.objects.create(
        lens=lens,
        lens_version=version,
        asset_id=1,
        symbol="BTC",
        event_type="trigger_fired",
        fingerprint="x",
    )
    assert Lens.objects.count() >= 1
    call_command("reset_agents")
    out = capsys.readouterr().out
    assert User.objects.filter(pk=user.pk).exists()
    assert Lens.objects.count() == 0
    assert Event.objects.count() == 0
    assert CmcCallLog.objects.count() == 0
    assert UserPreference.objects.get(user=user).active_lens_id is None
    assert "Kept 1 user" in out
    assert "Lenses remaining: 0" in out
