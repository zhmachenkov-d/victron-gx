"""Tests for Victron GX config flow."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_SSDP, SOURCE_USER
from homeassistant.const import (
    CONF_HOST,
    CONF_MODEL,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SSL,
    CONF_USERNAME,
)
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from victron_mqtt import AuthenticationError, CannotConnectError

from custom_components.victon_gx_hub import config_flow
from custom_components.victon_gx_hub.config_flow import (
    DEFAULT_PORT,
    ENTRY_TITLE_FORMAT,
    _apply_credential_updates,
    _normalize_update_interval,
    validate_input,
)
from custom_components.victon_gx_hub.const import (
    CONF_INSTALLATION_ID,
    CONF_SERIAL,
    CONF_UPDATE_INTERVAL_SECONDS,
    DOMAIN,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

HOST = "192.168.1.1"
INSTALLATION_ID = "portal-1"
MODEL = "Cerbo GX"
SERIAL = "serial-1"
USERNAME = "user"
PASSWORD = "secret"
UPDATED_PASSWORD = "new-secret"
USER_UPDATE_INTERVAL = 20


class FakeVictronVenusHub:
    """Fake victron-mqtt hub for config validation tests."""

    connect_side_effect: Exception | None = None
    disconnect_side_effect: Exception | None = None
    installation_id_value: str | None = INSTALLATION_ID
    instances: list[FakeVictronVenusHub] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.installation_id = self.installation_id_value
        self.connect = AsyncMock(side_effect=self.connect_side_effect)
        self.disconnect = AsyncMock(side_effect=self.disconnect_side_effect)
        self.instances.append(self)


@pytest.fixture
def fake_victron_hub(monkeypatch: pytest.MonkeyPatch) -> type[FakeVictronVenusHub]:
    """Patch the victron-mqtt hub used by config validation."""
    FakeVictronVenusHub.connect_side_effect = None
    FakeVictronVenusHub.disconnect_side_effect = None
    FakeVictronVenusHub.installation_id_value = INSTALLATION_ID
    FakeVictronVenusHub.instances = []
    monkeypatch.setattr(config_flow, "VictronVenusHub", FakeVictronVenusHub)
    monkeypatch.setattr(
        "custom_components.victon_gx_hub.async_setup_entry",
        AsyncMock(return_value=True),
    )
    return FakeVictronVenusHub


def _user_input(**overrides: Any) -> dict[str, Any]:
    data = {
        CONF_HOST: HOST,
        CONF_PORT: DEFAULT_PORT,
        CONF_USERNAME: USERNAME,
        CONF_PASSWORD: PASSWORD,
        CONF_SSL: False,
    }
    data.update(overrides)
    return data


def _ssdp_info(**upnp_overrides: str) -> SimpleNamespace:
    upnp = {
        "X_VrmPortalId": INSTALLATION_ID,
        "serialNumber": SERIAL,
        "modelName": MODEL,
        "friendlyName": "Victron GX",
    }
    upnp.update(upnp_overrides)
    return SimpleNamespace(ssdp_location=f"http://{HOST}:80/root.xml", upnp=upnp)


def test_normalize_update_interval() -> None:
    """Normalize optional update interval fields."""
    assert _normalize_update_interval({CONF_HOST: HOST}) == {CONF_HOST: HOST}
    assert _normalize_update_interval({CONF_UPDATE_INTERVAL_SECONDS: ""}) == {}
    assert _normalize_update_interval({CONF_UPDATE_INTERVAL_SECONDS: "30"}) == {
        CONF_UPDATE_INTERVAL_SECONDS: 30
    }


def test_apply_credential_updates_preserves_blank_password() -> None:
    """Merge credential updates while preserving stored password when blank."""
    existing = {
        CONF_HOST: HOST,
        CONF_PORT: DEFAULT_PORT,
        CONF_USERNAME: USERNAME,
        CONF_PASSWORD: PASSWORD,
        CONF_UPDATE_INTERVAL_SECONDS: 10,
    }
    updates = {
        CONF_USERNAME: "",
        CONF_PASSWORD: "",
        CONF_UPDATE_INTERVAL_SECONDS: "",
    }

    assert _apply_credential_updates(existing, updates) == {
        CONF_HOST: HOST,
        CONF_PORT: DEFAULT_PORT,
        CONF_USERNAME: None,
        CONF_PASSWORD: PASSWORD,
    }


async def test_validate_input_connects_and_disconnects(
    fake_victron_hub: type[FakeVictronVenusHub],
) -> None:
    """Connect to Victron MQTT and return the discovered installation id."""
    data = _user_input(
        **{
            CONF_INSTALLATION_ID: INSTALLATION_ID,
            CONF_MODEL: MODEL,
            CONF_SERIAL: SERIAL,
            CONF_UPDATE_INTERVAL_SECONDS: 15,
        }
    )

    assert await validate_input(data) == INSTALLATION_ID

    hub = fake_victron_hub.instances[0]
    assert hub.kwargs == {
        "host": HOST,
        "port": DEFAULT_PORT,
        "username": USERNAME,
        "password": PASSWORD,
        "use_ssl": False,
        "installation_id": INSTALLATION_ID,
        "model_name": MODEL,
        "serial": SERIAL,
        "update_frequency_seconds": 15,
    }
    hub.connect.assert_awaited_once()
    hub.disconnect.assert_awaited_once()


async def test_validate_input_disconnects_when_connect_fails(
    fake_victron_hub: type[FakeVictronVenusHub],
) -> None:
    """Disconnect during validation cleanup even when connect raises."""
    fake_victron_hub.connect_side_effect = AuthenticationError

    with pytest.raises(AuthenticationError):
        await validate_input(_user_input())

    fake_victron_hub.instances[0].disconnect.assert_awaited_once()


async def test_validate_input_requires_installation_id(
    fake_victron_hub: type[FakeVictronVenusHub],
) -> None:
    """Treat missing installation id as a connection failure."""
    fake_victron_hub.installation_id_value = None

    with pytest.raises(CannotConnectError):
        await validate_input(_user_input())


async def test_validate_input_ignores_disconnect_error(
    fake_victron_hub: type[FakeVictronVenusHub],
) -> None:
    """Ignore disconnect errors during validation cleanup."""
    fake_victron_hub.disconnect_side_effect = RuntimeError("disconnect failed")

    assert await validate_input(_user_input()) == INSTALLATION_ID


async def test_user_flow_creates_entry(
    hass: HomeAssistant,
    fake_victron_hub: type[FakeVictronVenusHub],
) -> None:
    """Create a config entry from manual setup."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
        data=_user_input(**{CONF_UPDATE_INTERVAL_SECONDS: str(USER_UPDATE_INTERVAL)}),
    )

    assert result["type"] == "create_entry"
    assert result["title"] == ENTRY_TITLE_FORMAT.format(
        installation_id=INSTALLATION_ID,
        host=HOST,
        port=DEFAULT_PORT,
    )
    assert result["data"][CONF_INSTALLATION_ID] == INSTALLATION_ID
    assert result["data"][CONF_UPDATE_INTERVAL_SECONDS] == USER_UPDATE_INTERVAL
    assert fake_victron_hub.instances[0].connect.await_count == 1


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        (AuthenticationError, "invalid_auth"),
        (CannotConnectError, "cannot_connect"),
        (RuntimeError("boom"), "unknown"),
    ],
)
async def test_user_flow_shows_errors(
    hass: HomeAssistant,
    fake_victron_hub: type[FakeVictronVenusHub],
    side_effect: Exception | type[Exception],
    error: str,
) -> None:
    """Show the user form again when validation fails."""
    fake_victron_hub.connect_side_effect = side_effect

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
        data=_user_input(),
    )

    assert result["type"] == "form"
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": error}


async def test_ssdp_flow_creates_entry_after_confirmation(
    hass: HomeAssistant,
    fake_victron_hub: type[FakeVictronVenusHub],
) -> None:
    """Confirm an SSDP-discovered device and create an entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_SSDP},
        data=_ssdp_info(),
    )

    assert result["type"] == "form"
    assert result["step_id"] == "ssdp_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={}
    )

    assert result["type"] == "create_entry"
    assert result["data"][CONF_HOST] == HOST
    assert result["data"][CONF_INSTALLATION_ID] == INSTALLATION_ID
    assert result["data"][CONF_MODEL] == MODEL
    assert result["data"][CONF_SERIAL] == SERIAL


async def test_ssdp_flow_requests_auth_when_needed(
    hass: HomeAssistant,
    fake_victron_hub: type[FakeVictronVenusHub],
) -> None:
    """Route SSDP discovery to the auth form when credentials are required."""
    fake_victron_hub.connect_side_effect = AuthenticationError

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_SSDP},
        data=_ssdp_info(),
    )

    assert result["type"] == "form"
    assert result["step_id"] == "ssdp_auth"
    assert result["errors"] == {}


async def test_ssdp_auth_creates_entry(
    hass: HomeAssistant,
    fake_victron_hub: type[FakeVictronVenusHub],
) -> None:
    """Submit credentials for an SSDP-discovered device."""
    fake_victron_hub.connect_side_effect = AuthenticationError
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_SSDP},
        data=_ssdp_info(),
    )
    fake_victron_hub.connect_side_effect = None

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_USERNAME: USERNAME,
            CONF_PASSWORD: PASSWORD,
            CONF_SSL: True,
            CONF_UPDATE_INTERVAL_SECONDS: "45",
        },
    )

    assert result["type"] == "create_entry"
    assert result["data"][CONF_USERNAME] == USERNAME
    assert result["data"][CONF_PASSWORD] == PASSWORD
    assert result["data"][CONF_SSL] is True


@pytest.mark.parametrize(
    ("location", "upnp", "reason"),
    [
        ("not-a-url", {"X_VrmPortalId": INSTALLATION_ID}, "cannot_connect"),
        (f"http://{HOST}/root.xml", {}, "cannot_connect"),
    ],
)
async def test_ssdp_flow_aborts_for_incomplete_discovery(
    hass: HomeAssistant,
    location: str,
    upnp: dict[str, str],
    reason: str,
) -> None:
    """Abort SSDP flow when required discovery data is missing."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_SSDP},
        data=SimpleNamespace(ssdp_location=location, upnp=upnp),
    )

    assert result["type"] == "abort"
    assert result["reason"] == reason


async def test_reauth_updates_credentials(
    hass: HomeAssistant,
    fake_victron_hub: type[FakeVictronVenusHub],
) -> None:
    """Update credentials during reauthentication."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=_user_input(**{CONF_INSTALLATION_ID: INSTALLATION_ID}),
        unique_id=INSTALLATION_ID,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )
    assert result["type"] == "form"
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_USERNAME: USERNAME,
            CONF_PASSWORD: UPDATED_PASSWORD,
            CONF_SSL: True,
        },
    )

    assert result["type"] == "abort"
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == UPDATED_PASSWORD
    assert entry.data[CONF_SSL] is True
