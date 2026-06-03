"""Tests for Victron GX sensor platform."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN, SensorDeviceClass
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, STATE_UNKNOWN
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import EntityPlatform
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from victron_mqtt import MetricKind, MetricNature, MetricType
from victron_mqtt._victron_enums import GenericOnOff

from custom_components.victron_gx_hub.const import DOMAIN
from custom_components.victron_gx_hub.sensor import (
    METRIC_TYPE_TO_DEVICE_CLASS,
    VictronSensor,
    async_setup_entry,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

type NewMetricCallback = Callable[
    [FakeDevice, FakeMetric, DeviceInfo, str],
    None,
]

INITIAL_VALUE = 12
UPDATED_VALUE = 24
CURRENT_UNIT = "A"
OPTION_OFF = "off"
OPTION_ON = "on"
LABEL_OFF = "Disabled"
LABEL_ON = "Enabled"
UNKNOWN_OPTION = "unknown"
GENERIC_STATE = "charging"


@dataclass
class FakeDevice:
    """Lightweight Victron device stand-in for tests."""

    unique_id: str = "device_1"
    name: str = "Test Device"


@dataclass
class FakeMetric:
    """Lightweight Victron metric stand-in for tests."""

    metric_kind: MetricKind = MetricKind.SENSOR
    metric_type: MetricType = MetricType.CURRENT
    metric_nature: MetricNature = MetricNature.MEASUREMENT
    value: Any = INITIAL_VALUE
    unique_id: str = "metric_1"
    generic_short_id: str = "dc_current"
    main_topic: bool = False
    precision: int | None = None
    unit_of_measurement: str | None = CURRENT_UNIT
    enum_values: list[str] | None = None
    key_values: dict[str, str] = field(default_factory=dict)
    on_update: Callable[[FakeMetric, Any], None] | None = None
    name: str = "DC Current"

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
        """Invoke the registered sensor callback."""
        callback = self.registered_callbacks.get(MetricKind.SENSOR)
        if callback is not None:
            callback(device, metric, device_info, installation_id)


def _enum_options() -> list[str]:
    return [OPTION_OFF, OPTION_ON]


def _label_options() -> list[str]:
    return [LABEL_OFF, LABEL_ON]


def _make_device_info() -> DeviceInfo:
    return DeviceInfo(identifiers={(DOMAIN, "installation_1_device_1")})


async def _add_entity_to_hass(
    hass: HomeAssistant,
    entity: VictronSensor,
    config_entry: MockConfigEntry,
) -> VictronSensor:
    """Add a sensor entity through a platform like Home Assistant does."""
    platform = EntityPlatform(
        hass=hass,
        logger=logging.getLogger(__name__),
        domain=SENSOR_DOMAIN,
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


async def test_async_setup_entry_registers_sensor_callback(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Register a sensor callback on the config entry hub."""
    hub = mock_config_entry.runtime_data
    assert isinstance(hub, FakeHub)
    added_entities: list[VictronSensor] = []

    def async_add_entities(
        entities: list[VictronSensor],
        update_before_add: bool = False,
    ) -> None:
        added_entities.extend(entities)

    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    assert MetricKind.SENSOR in hub.registered_callbacks

    hub.trigger_new_metric(
        FakeDevice(),
        FakeMetric(),
        _make_device_info(),
        "installation_1",
    )

    assert len(added_entities) == 1
    assert added_entities[0].unique_id == "installation_1_metric_1"


async def test_async_setup_entry_skips_duplicate_sensor_metrics(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Avoid adding multiple entities for the same discovered sensor metric."""
    hub = mock_config_entry.runtime_data
    assert isinstance(hub, FakeHub)
    added_entities: list[VictronSensor] = []

    await async_setup_entry(hass, mock_config_entry, added_entities.extend)

    metric = FakeMetric()
    hub.trigger_new_metric(FakeDevice(), metric, _make_device_info(), "installation_1")
    hub.trigger_new_metric(FakeDevice(), metric, _make_device_info(), "installation_1")

    assert len(added_entities) == 1


@pytest.mark.parametrize(
    ("metric_type", "expected_device_class"),
    [
        (MetricType.POWER, SensorDeviceClass.POWER),
        (MetricType.CURRENT, SensorDeviceClass.CURRENT),
        (MetricType.ENUM, SensorDeviceClass.ENUM),
    ],
)
def test_metric_type_to_device_class(
    metric_type: MetricType,
    expected_device_class: SensorDeviceClass,
) -> None:
    """Map Victron metric types to sensor device classes."""
    assert METRIC_TYPE_TO_DEVICE_CLASS[metric_type] == expected_device_class

    entity = VictronSensor(
        FakeDevice(),
        FakeMetric(metric_type=metric_type),
        _make_device_info(),
        "installation_1",
    )

    assert entity.device_class == expected_device_class


def test_sensor_initializes_numeric_properties() -> None:
    """Initialize numeric value, unit, and state class from the metric."""
    entity = VictronSensor(
        FakeDevice(),
        FakeMetric(),
        _make_device_info(),
        "installation_1",
    )

    assert entity.native_value == float(INITIAL_VALUE)
    assert entity.native_unit_of_measurement == CURRENT_UNIT
    assert entity.state_class == "measurement"


def test_sensor_initializes_enum_without_state_class() -> None:
    """Initialize enum options without a measurement state class."""
    entity = VictronSensor(
        FakeDevice(),
        FakeMetric(
            metric_type=MetricType.ENUM,
            value=GenericOnOff.ON,
            enum_values=_enum_options(),
            unit_of_measurement=None,
        ),
        _make_device_info(),
        "installation_1",
    )

    assert entity.options == _enum_options()
    assert entity.native_value == OPTION_ON
    assert entity.state_class is None


def test_sensor_initializes_enum_label_from_enum_code() -> None:
    """Map dynamic dropdown enum codes to custom label options."""
    entity = VictronSensor(
        FakeDevice(),
        FakeMetric(
            metric_type=MetricType.ENUM,
            value=GenericOnOff.ON,
            enum_values=_label_options(),
            unit_of_measurement=None,
        ),
        _make_device_info(),
        "installation_1",
    )

    assert entity.options == _label_options()
    assert entity.native_value == LABEL_ON


def test_sensor_generic_value_without_device_class() -> None:
    """Pass through generic sensor values when there is no device class."""
    entity = VictronSensor(
        FakeDevice(),
        FakeMetric(
            metric_type=MetricType.NONE,
            value=GENERIC_STATE,
            unit_of_measurement=None,
        ),
        _make_device_info(),
        "installation_1",
    )

    assert entity.device_class is None
    assert entity.native_value == GENERIC_STATE


async def test_sensor_state_updates_on_metric_change(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Publish sensor state to Home Assistant on metric updates."""
    metric = FakeMetric()
    entity = VictronSensor(
        FakeDevice(),
        metric,
        _make_device_info(),
        "installation_1",
    )
    await _add_entity_to_hass(hass, entity, mock_config_entry)

    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert state.state == str(float(INITIAL_VALUE))
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == CURRENT_UNIT

    metric.emit_update(UPDATED_VALUE)
    await hass.async_block_till_done()

    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert state.state == str(float(UPDATED_VALUE))


async def test_sensor_state_unknown_for_non_numeric_metric_value(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Leave sensor state unknown when the metric value is not numeric."""
    entity = VictronSensor(
        FakeDevice(),
        FakeMetric(value="not-a-number"),
        _make_device_info(),
        "installation_1",
    )
    await _add_entity_to_hass(hass, entity, mock_config_entry)

    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert state.state == STATE_UNKNOWN


async def test_sensor_state_unknown_for_enum_outside_options(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Leave enum sensor state unknown when a metric value is not an option."""
    entity = VictronSensor(
        FakeDevice(),
        FakeMetric(
            metric_type=MetricType.ENUM,
            value=UNKNOWN_OPTION,
            enum_values=_enum_options(),
            unit_of_measurement=None,
        ),
        _make_device_info(),
        "installation_1",
    )
    await _add_entity_to_hass(hass, entity, mock_config_entry)

    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert state.state == STATE_UNKNOWN


async def test_sensor_enum_state_updates_on_metric_change(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Publish enum sensor state to Home Assistant on metric updates."""
    metric = FakeMetric(
        metric_type=MetricType.ENUM,
        value=GenericOnOff.OFF,
        enum_values=_enum_options(),
        unit_of_measurement=None,
    )
    entity = VictronSensor(
        FakeDevice(),
        metric,
        _make_device_info(),
        "installation_1",
    )
    await _add_entity_to_hass(hass, entity, mock_config_entry)

    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert state.state == OPTION_OFF

    metric.emit_update(GenericOnOff.ON)
    await hass.async_block_till_done()

    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert state.state == OPTION_ON
