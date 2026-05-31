"""Tests for Victron GX config entry diagnostics."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock

from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SSL,
    CONF_USERNAME,
)
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.victon_gx_hub.const import (
    CONF_INSTALLATION_ID,
    CONF_SERIAL,
    DOMAIN,
)
from custom_components.victon_gx_hub.diagnostics import (
    async_get_config_entry_diagnostics,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

REDACTED = "**REDACTED**"
MQTT_PORT = 1883


class FakeHub:
    """Fake hub returning deterministic diagnostics data."""

    def get_diagnostics_data(self) -> dict[str, object]:
        """Return sample device diagnostics."""
        return {
            "gps_0": {
                "name": "GPS",
                "metrics": {"gps_location": {"value": REDACTED}},
            }
        }


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Create a config entry for diagnostics tests."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "192.168.1.1",
            CONF_PORT: MQTT_PORT,
            CONF_USERNAME: "victron",
            CONF_PASSWORD: "secret",
            CONF_SSL: False,
            CONF_INSTALLATION_ID: "installation_123",
            CONF_SERIAL: "GX123456",
        },
    )
    entry.add_to_hass(hass)
    return entry


async def test_diagnostics_redacts_sensitive_entry_data(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Redact credentials, host, and installation identifiers from entry data."""
    config_entry.runtime_data = FakeHub()

    diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)

    entry_data = diagnostics["entry_data"]
    assert entry_data[CONF_HOST] == REDACTED
    assert entry_data[CONF_USERNAME] == REDACTED
    assert entry_data[CONF_PASSWORD] == REDACTED
    assert entry_data[CONF_INSTALLATION_ID] == REDACTED
    assert entry_data[CONF_SERIAL] == REDACTED
    assert entry_data[CONF_PORT] == MQTT_PORT
    assert entry_data[CONF_SSL] is False


async def test_diagnostics_includes_hub_device_data_when_available(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Include hub diagnostics when runtime data is available."""
    config_entry.runtime_data = FakeHub()

    diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)

    assert diagnostics["devices"] == {
        "gps_0": {
            "name": "GPS",
            "metrics": {"gps_location": {"value": REDACTED}},
        }
    }


async def test_diagnostics_omits_devices_when_hub_unavailable(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Return only entry data when the hub has not been initialized."""
    config_entry.runtime_data = None

    diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)

    assert "entry_data" in diagnostics
    assert "devices" not in diagnostics
    assert diagnostics["entry_data"][CONF_HOST] == REDACTED


async def test_diagnostics_merges_entry_options(hass: HomeAssistant) -> None:
    """Merge config entry options into exported diagnostics data."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.1", CONF_PORT: MQTT_PORT, CONF_SSL: False},
        options={CONF_SSL: True},
    )
    config_entry.add_to_hass(hass)
    config_entry.runtime_data = Mock()
    config_entry.runtime_data.get_diagnostics_data.return_value = {}

    diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)

    assert diagnostics["entry_data"][CONF_SSL] is True
