"""Tests for Victron GX integration setup."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock

from homeassistant.const import CONF_HOST, EVENT_HOMEASSISTANT_STOP
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.victon_gx_hub import (
    PLATFORMS,
    async_remove_config_entry_device,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.victon_gx_hub.const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


class FakeHub:
    """Fake integration hub for entry lifecycle tests."""

    start_side_effect: Exception | None = None

    def __init__(self, hass: HomeAssistant, entry: MockConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.start = AsyncMock(side_effect=self.start_side_effect)
        self.stop = AsyncMock()
        self.unregister_all_new_metric_callbacks = Mock()
        self.is_device_connected_return_value = False
        self.is_device_connected_calls: list[set[tuple[str, str]]] = []

    def is_device_connected(self, identifiers: set[tuple[str, str]]) -> bool:
        """Return whether the device is known by the hub."""
        self.is_device_connected_calls.append(identifiers)
        return self.is_device_connected_return_value


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Create a config entry for integration setup tests."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.1"},
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def fake_hub_factory(monkeypatch: pytest.MonkeyPatch) -> list[FakeHub]:
    """Patch the integration Hub class and collect created fake hubs."""
    created_hubs: list[FakeHub] = []
    FakeHub.start_side_effect = None

    def _make_hub(hass: HomeAssistant, entry: MockConfigEntry) -> FakeHub:
        hub = FakeHub(hass, entry)
        created_hubs.append(hub)
        return hub

    monkeypatch.setattr("custom_components.victon_gx_hub.Hub", _make_hub)
    monkeypatch.setattr(FakeHub, "start_side_effect", None)
    return created_hubs


async def test_async_setup_entry_starts_hub_after_forwarding_platforms(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    fake_hub_factory: list[FakeHub],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Set up platforms, start the hub, and register stop cleanup."""
    forward_setups = AsyncMock()
    monkeypatch.setattr(
        hass.config_entries, "async_forward_entry_setups", forward_setups
    )

    assert await async_setup_entry(hass, config_entry) is True

    hub = fake_hub_factory[0]
    assert config_entry.runtime_data is hub
    forward_setups.assert_awaited_once_with(config_entry, PLATFORMS)
    hub.start.assert_awaited_once()

    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()

    hub.stop.assert_awaited_once()


async def test_async_setup_entry_unloads_platforms_when_hub_start_fails(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    fake_hub_factory: list[FakeHub],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Undo platform setup and callbacks when the hub cannot start."""
    forward_setups = AsyncMock()
    unload_platforms = AsyncMock(return_value=True)
    monkeypatch.setattr(
        hass.config_entries, "async_forward_entry_setups", forward_setups
    )
    monkeypatch.setattr(hass.config_entries, "async_unload_platforms", unload_platforms)

    FakeHub.start_side_effect = RuntimeError("cannot start")

    with pytest.raises(RuntimeError, match="cannot start"):
        await async_setup_entry(hass, config_entry)

    hub = fake_hub_factory[0]
    forward_setups.assert_awaited_once_with(config_entry, PLATFORMS)
    unload_platforms.assert_awaited_once_with(config_entry, PLATFORMS)
    hub.unregister_all_new_metric_callbacks.assert_called_once()


@pytest.mark.parametrize("unload_ok", [True, False])
async def test_async_unload_entry_stops_hub_only_after_successful_platform_unload(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    monkeypatch: pytest.MonkeyPatch,
    unload_ok: bool,
) -> None:
    """Unload platforms and stop the hub only when platform unload succeeds."""
    hub = FakeHub(hass, config_entry)
    config_entry.runtime_data = hub
    unload_platforms = AsyncMock(return_value=unload_ok)
    monkeypatch.setattr(hass.config_entries, "async_unload_platforms", unload_platforms)

    assert await async_unload_entry(hass, config_entry) is unload_ok

    unload_platforms.assert_awaited_once_with(config_entry, PLATFORMS)
    if unload_ok:
        hub.stop.assert_awaited_once()
        hub.unregister_all_new_metric_callbacks.assert_called_once()
    else:
        hub.stop.assert_not_awaited()
        hub.unregister_all_new_metric_callbacks.assert_not_called()


@pytest.mark.parametrize(
    ("device_connected", "expected_can_remove"),
    [
        (True, False),
        (False, True),
    ],
)
async def test_async_remove_config_entry_device_delegates_to_hub_connection_state(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device_connected: bool,
    expected_can_remove: bool,
) -> None:
    """Allow device removal only when the hub no longer knows the device."""
    hub = FakeHub(hass, config_entry)
    hub.is_device_connected_return_value = device_connected
    config_entry.runtime_data = hub
    identifiers = {(DOMAIN, "installation_1_device_1")}

    class FakeDeviceEntry:
        """Minimal device entry for remove-device tests."""

        def __init__(self) -> None:
            self.identifiers = identifiers

    assert (
        await async_remove_config_entry_device(hass, config_entry, FakeDeviceEntry())
        is expected_can_remove
    )
    assert hub.is_device_connected_calls == [identifiers]
