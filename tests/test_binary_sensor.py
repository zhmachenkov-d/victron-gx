"""Tests for Victron GX binary sensor platform."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import EntityPlatform
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from victron_mqtt import MetricKind, MetricType
from victron_mqtt._victron_enums import ACSystemMode, GenericOnOff

from custom_components.victon_gx_hub.binary_sensor import (
    METRIC_TYPE_TO_DEVICE_CLASS,
    VictronBinarySensor,
    async_setup_entry,
)
from custom_components.victon_gx_hub.const import (
    BINARY_SENSOR_OFF_ID,
    BINARY_SENSOR_ON_ID,
    DOMAIN,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

type NewMetricCallback = Callable[
    [FakeDevice, FakeMetric, DeviceInfo, str],
    None,
]


@dataclass
class FakeDevice:
    """Lightweight Victron device stand-in for tests."""

    unique_id: str = "device_1"
    name: str = "Test Device"


@dataclass
class FakeMetric:
    """Lightweight Victron metric stand-in for tests."""

    metric_kind: MetricKind = MetricKind.BINARY_SENSOR
    metric_type: MetricType = MetricType.POWER
    value: Any = None
    unique_id: str = "metric_1"
    generic_short_id: str = "switch_status"
    main_topic: bool = False
    precision: int | None = None
    unit_of_measurement: str | None = None
    key_values: dict[str, str] = field(default_factory=dict)
    on_update: Callable[[FakeMetric, Any], None] | None = None
    name: str = "Switch Status"

    def emit_update(self, value: Any) -> None:
        """Simulate a Victron metric value update."""
        self.value = value
        if self.on_update is not None:
            self.on_update(self, value)


class FakeHub:
    """Lightweight hub stand-in for platform setup tests."""

    def __init__(self) -> None:
        self.registered_callbacks: dict[MetricKind, NewMetricCallback] = {}

    def register_new_metric_callback(
        self, kind: MetricKind, callback: NewMetricCallback
    ) -> None:
        """Register a callback for a metric kind."""
        self.registered_callbacks[kind] = callback

    def trigger_new_metric(
        self,
        device: FakeDevice,
        metric: FakeMetric,
        device_info: DeviceInfo,
        installation_id: str,
    ) -> None:
        """Invoke the registered callback for a metric kind."""
        callback = self.registered_callbacks.get(metric.metric_kind)
        if callback is not None:
            callback(device, metric, device_info, installation_id)


def _make_device_info() -> DeviceInfo:
    return DeviceInfo(identifiers={(DOMAIN, "installation_1_device_1")})


async def _add_entity_to_hass(
    hass: HomeAssistant,
    entity: VictronBinarySensor,
    config_entry: MockConfigEntry,
) -> VictronBinarySensor:
    """Add a binary sensor entity through a platform like Home Assistant does."""
    platform = EntityPlatform(
        hass=hass,
        logger=logging.getLogger(__name__),
        domain="binary_sensor",
        platform_name=DOMAIN,
        platform=None,
        scan_interval=timedelta(seconds=30),
        entity_namespace=None,
    )
    platform.config_entry = config_entry
    await platform.async_add_entities([entity], update_before_add=True)
    await hass.async_block_till_done()
    return entity


@pytest.fixture
def mock_config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Create a config entry with a fake hub for platform tests."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "192.168.1.1"},
    )
    config_entry.runtime_data = FakeHub()
    config_entry.add_to_hass(hass)
    return config_entry


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (GenericOnOff.ON, True),
        (GenericOnOff.OFF, False),
        (None, None),
        ("not-an-enum", None),
        (ACSystemMode.PASSTHROUGH, None),
    ],
)
def test_convert_metric_value_to_is_on(value: Any, expected: bool | None) -> None:
    """Convert Victron on/off enum values to binary sensor booleans."""
    assert VictronBinarySensor.convert_metric_value_to_is_on(value) is expected


def test_binary_sensor_on_off_ids_match_generic_on_off() -> None:
    """Binary sensor constants align with GenericOnOff enum ids."""
    assert GenericOnOff.ON.id == BINARY_SENSOR_ON_ID
    assert GenericOnOff.OFF.id == BINARY_SENSOR_OFF_ID


@pytest.mark.parametrize(
    ("metric_type", "expected_device_class"),
    [
        (MetricType.POWER, BinarySensorDeviceClass.POWER),
        (MetricType.PROBLEM, BinarySensorDeviceClass.PROBLEM),
        (MetricType.CONNECTIVITY, BinarySensorDeviceClass.CONNECTIVITY),
    ],
)
def test_metric_type_to_device_class(
    metric_type: MetricType,
    expected_device_class: BinarySensorDeviceClass,
) -> None:
    """Map Victron metric types to binary sensor device classes."""
    assert METRIC_TYPE_TO_DEVICE_CLASS[metric_type] == expected_device_class

    metric = FakeMetric(metric_type=metric_type, value=GenericOnOff.ON)
    entity = VictronBinarySensor(
        FakeDevice(),
        metric,
        _make_device_info(),
        "installation_1",
    )

    assert entity.device_class == expected_device_class


def test_entity_initial_state_from_metric_value() -> None:
    """Initialize entity state from the metric's current value."""
    metric = FakeMetric(value=GenericOnOff.ON)
    entity = VictronBinarySensor(
        FakeDevice(),
        metric,
        _make_device_info(),
        "installation_1",
    )

    assert entity.is_on is True
    assert entity.unique_id == "installation_1_metric_1"


async def test_async_setup_entry_registers_binary_sensor_callback(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Register a binary sensor callback on the config entry hub."""
    hub = mock_config_entry.runtime_data
    assert isinstance(hub, FakeHub)

    added_entities: list[VictronBinarySensor] = []

    def async_add_entities(
        entities: list[VictronBinarySensor],
        update_before_add: bool = False,
    ) -> None:
        added_entities.extend(entities)

    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    assert MetricKind.BINARY_SENSOR in hub.registered_callbacks

    metric = FakeMetric(
        metric_type=MetricType.CONNECTIVITY,
        value=GenericOnOff.ON,
    )
    hub.trigger_new_metric(
        FakeDevice(),
        metric,
        _make_device_info(),
        "installation_1",
    )

    assert len(added_entities) == 1
    assert added_entities[0].is_on is True
    assert added_entities[0].device_class == BinarySensorDeviceClass.CONNECTIVITY


async def test_entity_state_updates_on_metric_change(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Publish binary sensor state to Home Assistant on metric updates."""
    metric = FakeMetric(value=GenericOnOff.ON)
    entity = VictronBinarySensor(
        FakeDevice(),
        metric,
        _make_device_info(),
        "installation_1",
    )
    await _add_entity_to_hass(hass, entity, mock_config_entry)

    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert state.state == STATE_ON

    metric.emit_update(GenericOnOff.OFF)
    await hass.async_block_till_done()

    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert state.state == STATE_OFF


async def test_entity_state_unknown_for_unmapped_enum(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Leave binary sensor state unknown when enum id is not on/off."""
    metric = FakeMetric(value=ACSystemMode.PASSTHROUGH)
    entity = VictronBinarySensor(
        FakeDevice(),
        metric,
        _make_device_info(),
        "installation_1",
    )
    await _add_entity_to_hass(hass, entity, mock_config_entry)

    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert state.state == STATE_UNKNOWN
