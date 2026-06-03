"""Tests for the Victron GX hub wrapper."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

from homeassistant.const import (
    CONF_HOST,
    CONF_MODEL,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SSL,
    CONF_USERNAME,
)
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from victron_mqtt import (
    AuthenticationError,
    CannotConnectError,
    GenericOnOff,
    MetricKind,
    MetricType,
    OperationMode,
)

from custom_components.victron_gx_hub import hub as hub_module
from custom_components.victron_gx_hub.const import (
    CONF_INSTALLATION_ID,
    CONF_SERIAL,
    CONF_UPDATE_INTERVAL_SECONDS,
    DOMAIN,
)
from custom_components.victron_gx_hub.hub import Hub

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

HOST = "192.168.1.1"
INSTALLATION_ID = "portal-1"
DEVICE_ID = "device_1"
PARENT_DEVICE_ID = "parent_1"
SERIAL = "serial-1"
MODEL = "Cerbo GX"
USERNAME = "user"
PASSWORD = "secret"


class FakeVictronVenusHub:
    """Fake victron-mqtt hub used by hub wrapper tests."""

    connect_side_effect: Exception | None = None
    disconnect_side_effect: Exception | None = None
    instances: list[FakeVictronVenusHub] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.installation_id = kwargs.get("installation_id", INSTALLATION_ID)
        self.connect = AsyncMock(side_effect=self.connect_side_effect)
        self.disconnect = AsyncMock(side_effect=self.disconnect_side_effect)
        self.devices: dict[str, FakeDevice] = {}
        self.on_new_metric = None
        self.instances.append(self)


@dataclass
class FakeDeviceType:
    """Minimal Victron device type."""

    string: str = "GX Device"


@dataclass
class FakeDevice:
    """Minimal Victron device."""

    unique_id: str = DEVICE_ID
    name: str = "Test Device"
    model: str = MODEL
    serial_number: str = SERIAL
    manufacturer: str | None = None
    firmware_version: str = "1.0.0"
    device_type: FakeDeviceType = field(default_factory=FakeDeviceType)
    parent_device: FakeDevice | None = None
    metrics: list[FakeMetric] | None = None

    def __post_init__(self) -> None:
        if self.metrics is None:
            self.metrics = []


@dataclass
class FakeMetric:
    """Minimal Victron metric."""

    short_id: str = "state"
    name: str = "State"
    value: Any = GenericOnOff.ON
    unit_of_measurement: str | None = None
    metric_kind: MetricKind = MetricKind.SENSOR
    metric_type: MetricType = MetricType.ENUM


@pytest.fixture
def fake_victron_hub(monkeypatch: pytest.MonkeyPatch) -> type[FakeVictronVenusHub]:
    """Patch the victron-mqtt hub wrapped by the integration hub."""
    FakeVictronVenusHub.connect_side_effect = None
    FakeVictronVenusHub.disconnect_side_effect = None
    FakeVictronVenusHub.instances = []
    monkeypatch.setattr(hub_module, "VictronVenusHub", FakeVictronVenusHub)
    return FakeVictronVenusHub


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Create a config entry for hub tests."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: HOST,
            CONF_PORT: 8883,
            CONF_USERNAME: USERNAME,
            CONF_PASSWORD: PASSWORD,
            CONF_SSL: True,
            CONF_INSTALLATION_ID: INSTALLATION_ID,
            CONF_MODEL: MODEL,
            CONF_SERIAL: SERIAL,
        },
        options={CONF_UPDATE_INTERVAL_SECONDS: 30},
    )
    entry.add_to_hass(hass)
    return entry


def test_hub_initializes_victron_client(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    fake_victron_hub: type[FakeVictronVenusHub],
) -> None:
    """Initialize the wrapped victron-mqtt hub from config entry data/options."""
    hub = Hub(hass, config_entry)

    victron_hub = fake_victron_hub.instances[0]
    assert hub.hass is hass
    assert hub.host == HOST
    assert victron_hub.on_new_metric is not None
    assert victron_hub.kwargs == {
        "host": HOST,
        "port": 8883,
        "username": USERNAME,
        "password": PASSWORD,
        "use_ssl": True,
        "installation_id": INSTALLATION_ID,
        "model_name": MODEL,
        "serial": SERIAL,
        "operation_mode": OperationMode.FULL,
        "update_frequency_seconds": 30,
    }


async def test_start_connects_wrapped_hub(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    fake_victron_hub: type[FakeVictronVenusHub],
) -> None:
    """Start connects the wrapped hub."""
    hub = Hub(hass, config_entry)

    await hub.start()

    fake_victron_hub.instances[0].connect.assert_awaited_once()


@pytest.mark.parametrize(
    ("side_effect", "expected_exception"),
    [
        (AuthenticationError, ConfigEntryAuthFailed),
        (CannotConnectError, ConfigEntryNotReady),
    ],
)
async def test_start_translates_connection_errors(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    fake_victron_hub: type[FakeVictronVenusHub],
    side_effect: type[Exception],
    expected_exception: type[Exception],
) -> None:
    """Translate victron-mqtt startup failures into Home Assistant exceptions."""
    fake_victron_hub.connect_side_effect = side_effect
    hub = Hub(hass, config_entry)

    with pytest.raises(expected_exception):
        await hub.start()


async def test_stop_disconnects_and_ignores_disconnect_errors(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    fake_victron_hub: type[FakeVictronVenusHub],
) -> None:
    """Stop disconnects the wrapped hub and ignores shutdown errors."""
    fake_victron_hub.disconnect_side_effect = RuntimeError("disconnect failed")
    hub = Hub(hass, config_entry)

    await hub.stop()

    fake_victron_hub.instances[0].disconnect.assert_awaited_once()


def test_new_metric_callback_receives_mapped_device_info(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    fake_victron_hub: type[FakeVictronVenusHub],
) -> None:
    """Dispatch new metrics to registered callbacks."""
    hub = Hub(hass, config_entry)
    parent = FakeDevice(unique_id=PARENT_DEVICE_ID)
    device = FakeDevice(parent_device=parent)
    metric = FakeMetric(metric_kind=MetricKind.SENSOR)
    callback_calls: list[tuple[FakeDevice, FakeMetric, Any, str]] = []

    def on_new_metric(
        callback_device: FakeDevice,
        callback_metric: FakeMetric,
        device_info: Any,
        installation_id: str,
    ) -> None:
        callback_calls.append(
            (callback_device, callback_metric, device_info, installation_id)
        )

    hub.register_new_metric_callback(MetricKind.SENSOR, on_new_metric)
    fake_victron_hub.instances[0].on_new_metric(
        fake_victron_hub.instances[0], device, metric
    )

    device_info = callback_calls[0][2]
    assert callback_calls == [
        (
            device,
            metric,
            device_info,
            INSTALLATION_ID,
        )
    ]
    assert device_info["identifiers"] == {(DOMAIN, f"{INSTALLATION_ID}_{DEVICE_ID}")}
    assert device_info["manufacturer"] == "Victron Energy"
    assert device_info["name"] == device.name
    assert device_info["model"] == MODEL
    assert device_info["serial_number"] == SERIAL
    assert device_info["via_device"] == (
        DOMAIN,
        f"{INSTALLATION_ID}_{PARENT_DEVICE_ID}",
    )

    hub.unregister_all_new_metric_callbacks()
    fake_victron_hub.instances[0].on_new_metric(
        fake_victron_hub.instances[0], device, metric
    )
    assert len(callback_calls) == 1


def test_is_device_connected_checks_known_victron_devices(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    fake_victron_hub: type[FakeVictronVenusHub],
) -> None:
    """Report whether a Home Assistant device is still known by Victron."""
    hub = Hub(hass, config_entry)
    fake_victron_hub.instances[0].devices = {DEVICE_ID: FakeDevice()}

    assert hub.is_device_connected({(DOMAIN, f"{INSTALLATION_ID}_{DEVICE_ID}")}) is True
    assert hub.is_device_connected({(DOMAIN, f"{INSTALLATION_ID}_missing")}) is False
    assert (
        hub.is_device_connected({("other", f"{INSTALLATION_ID}_{DEVICE_ID}")}) is False
    )


def test_get_diagnostics_data_redacts_locations_and_maps_enums(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    fake_victron_hub: type[FakeVictronVenusHub],
) -> None:
    """Return diagnostics data with sensitive locations redacted."""
    hub = Hub(hass, config_entry)
    fake_victron_hub.instances[0].devices = {
        DEVICE_ID: FakeDevice(
            metrics=[
                FakeMetric(short_id="state", value=GenericOnOff.ON),
                FakeMetric(
                    short_id="location",
                    name="Location",
                    value={"lat": 1, "lon": 2},
                    metric_type=MetricType.LOCATION,
                ),
                FakeMetric(
                    short_id="voltage",
                    name="Voltage",
                    value=12.5,
                    unit_of_measurement="V",
                    metric_type=MetricType.VOLTAGE,
                ),
            ]
        )
    }

    assert hub.get_diagnostics_data() == {
        DEVICE_ID: {
            "name": "Test Device",
            "model": MODEL,
            "manufacturer": None,
            "firmware_version": "1.0.0",
            "device_type": "GX Device",
            "metrics": {
                "state": {
                    "name": "State",
                    "value": "on",
                    "unit": None,
                    "kind": "SENSOR",
                    "type": "ENUM",
                },
                "location": {
                    "name": "Location",
                    "value": "**REDACTED**",
                    "unit": None,
                    "kind": "SENSOR",
                    "type": "LOCATION",
                },
                "voltage": {
                    "name": "Voltage",
                    "value": 12.5,
                    "unit": "V",
                    "kind": "SENSOR",
                    "type": "VOLTAGE",
                },
            },
        }
    }
