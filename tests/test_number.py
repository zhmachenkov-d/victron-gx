"""Tests for Victron GX number platform."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock

from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN, NumberDeviceClass
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, STATE_UNKNOWN
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import EntityPlatform
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from victron_mqtt import (
    MetricKind,
    MetricType,
    WritableMetric as VictronVenusWritableMetric,
)

from custom_components.victon_gx_hub.const import DOMAIN
from custom_components.victon_gx_hub.number import (
    METRIC_TYPE_TO_DEVICE_CLASS,
    VictronNumber,
    async_setup_entry,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

type NewMetricCallback = Callable[
    [FakeDevice, object, DeviceInfo, str],
    None,
]

INITIAL_VALUE = 12
UPDATED_VALUE = 24
SET_VALUE = 42.0
MIN_VALUE = 0
MAX_VALUE = 100
STEP_VALUE = 5
CURRENT_UNIT = "A"
CUSTOM_UNIT = "widgets"


@dataclass
class FakeDevice:
    """Lightweight Victron device stand-in for tests."""

    unique_id: str = "device_1"
    name: str = "Test Device"


@dataclass(frozen=True)
class FakeMetricSpec:
    """Configuration for a writable number metric test double."""

    value: Any = INITIAL_VALUE
    unique_id: str = "metric_1"
    metric_type: MetricType = MetricType.CURRENT
    unit_of_measurement: str | None = CURRENT_UNIT
    min_value: int | float | None = MIN_VALUE
    max_value: int | float | None = MAX_VALUE
    step: int | float | None = STEP_VALUE


class FakeWritableMetric(VictronVenusWritableMetric):
    """Writable Victron metric stand-in for number tests."""

    def __init__(self, spec: FakeMetricSpec | None = None) -> None:
        spec = spec or FakeMetricSpec()
        self._descriptor = SimpleNamespace(
            unit_of_measurement=spec.unit_of_measurement,
            metric_type=spec.metric_type,
            precision=None,
            main_topic=False,
            message_type=MetricKind.NUMBER,
        )
        self._unique_id = spec.unique_id
        self._generic_short_id = "charge_current_limit"
        self._key_values: dict[str, str] = {}
        self._on_update = None
        self._value = spec.value
        self._min_value = spec.min_value
        self._max_value = spec.max_value
        self._step_value = spec.step
        self._unit_of_measurement = spec.unit_of_measurement
        self.set = Mock()

    def emit_update(self, value: Any) -> None:
        """Simulate a Victron metric value update."""
        self._value = value
        if self._on_update is not None:
            self._on_update(self, value)


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
        metric: object,
        device_info: DeviceInfo,
        installation_id: str,
    ) -> None:
        """Invoke the registered number callback."""
        callback = self.registered_callbacks.get(MetricKind.NUMBER)
        if callback is not None:
            callback(device, metric, device_info, installation_id)


def _make_device_info() -> DeviceInfo:
    return DeviceInfo(identifiers={(DOMAIN, "installation_1_device_1")})


async def _add_entity_to_hass(
    hass: HomeAssistant,
    entity: VictronNumber,
    config_entry: MockConfigEntry,
) -> VictronNumber:
    """Add a number entity through a platform like Home Assistant does."""
    platform = EntityPlatform(
        hass=hass,
        logger=logging.getLogger(__name__),
        domain=NUMBER_DOMAIN,
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


async def test_async_setup_entry_registers_number_callback(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Register a number callback on the config entry hub."""
    hub = mock_config_entry.runtime_data
    assert isinstance(hub, FakeHub)
    added_entities: list[VictronNumber] = []

    def async_add_entities(
        entities: list[VictronNumber],
        update_before_add: bool = False,
    ) -> None:
        added_entities.extend(entities)

    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    assert MetricKind.NUMBER in hub.registered_callbacks

    hub.trigger_new_metric(
        FakeDevice(),
        FakeWritableMetric(),
        _make_device_info(),
        "installation_1",
    )

    assert len(added_entities) == 1
    assert added_entities[0].unique_id == "installation_1_metric_1"


async def test_async_setup_entry_skips_non_writable_number_metrics(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Ignore number metrics that cannot be written."""
    hub = mock_config_entry.runtime_data
    assert isinstance(hub, FakeHub)
    added_entities: list[VictronNumber] = []

    await async_setup_entry(hass, mock_config_entry, added_entities.extend)

    hub.trigger_new_metric(
        FakeDevice(),
        object(),
        _make_device_info(),
        "installation_1",
    )

    assert added_entities == []


async def test_async_setup_entry_skips_duplicate_number_metrics(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Avoid adding multiple entities for the same discovered number metric."""
    hub = mock_config_entry.runtime_data
    assert isinstance(hub, FakeHub)
    added_entities: list[VictronNumber] = []

    await async_setup_entry(hass, mock_config_entry, added_entities.extend)

    metric = FakeWritableMetric()
    hub.trigger_new_metric(FakeDevice(), metric, _make_device_info(), "installation_1")
    hub.trigger_new_metric(FakeDevice(), metric, _make_device_info(), "installation_1")

    assert len(added_entities) == 1


@pytest.mark.parametrize(
    ("metric_type", "expected_device_class"),
    [
        (MetricType.POWER, NumberDeviceClass.POWER),
        (MetricType.CURRENT, NumberDeviceClass.CURRENT),
        (MetricType.ELECTRIC_STORAGE_PERCENTAGE, NumberDeviceClass.BATTERY),
    ],
)
def test_metric_type_to_device_class(
    metric_type: MetricType,
    expected_device_class: NumberDeviceClass,
) -> None:
    """Map Victron metric types to number device classes."""
    assert METRIC_TYPE_TO_DEVICE_CLASS[metric_type] == expected_device_class

    entity = VictronNumber(
        FakeDevice(),
        FakeWritableMetric(FakeMetricSpec(metric_type=metric_type)),
        _make_device_info(),
        "installation_1",
    )

    assert entity.device_class == expected_device_class


def test_number_initializes_public_properties() -> None:
    """Initialize number value, unit, min, max, and step from the metric."""
    entity = VictronNumber(
        FakeDevice(),
        FakeWritableMetric(),
        _make_device_info(),
        "installation_1",
    )

    assert entity.native_value == float(INITIAL_VALUE)
    assert entity.native_unit_of_measurement == CURRENT_UNIT
    assert entity.native_min_value == MIN_VALUE
    assert entity.native_max_value == MAX_VALUE
    assert entity.native_step == STEP_VALUE


def test_number_keeps_unit_without_device_class() -> None:
    """Preserve metric units even when there is no HA number device class."""
    entity = VictronNumber(
        FakeDevice(),
        FakeWritableMetric(
            FakeMetricSpec(
                metric_type=MetricType.PERCENTAGE,
                unit_of_measurement=CUSTOM_UNIT,
            )
        ),
        _make_device_info(),
        "installation_1",
    )

    assert entity.device_class is None
    assert entity.native_unit_of_measurement == CUSTOM_UNIT


async def test_async_set_native_value_writes_in_executor(
    hass: HomeAssistant,
) -> None:
    """Setting a number writes the value through Home Assistant's executor."""
    metric = FakeWritableMetric()
    entity = VictronNumber(
        FakeDevice(),
        metric,
        _make_device_info(),
        "installation_1",
    )
    entity.hass = hass
    executor_calls: list[tuple[Callable[..., Any], tuple[Any, ...]]] = []

    async def async_add_executor_job(target: Callable[..., Any], *args: Any) -> None:
        executor_calls.append((target, args))
        target(*args)

    hass.async_add_executor_job = async_add_executor_job

    await entity.async_set_native_value(SET_VALUE)

    assert executor_calls == [(metric.set, (SET_VALUE,))]
    metric.set.assert_called_once_with(SET_VALUE)


async def test_number_state_updates_on_metric_change(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Publish number state to Home Assistant on metric updates."""
    metric = FakeWritableMetric()
    entity = VictronNumber(
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


async def test_number_state_unknown_for_non_numeric_metric_value(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Leave number state unknown when the metric value is not numeric."""
    entity = VictronNumber(
        FakeDevice(),
        FakeWritableMetric(FakeMetricSpec(value="not-a-number")),
        _make_device_info(),
        "installation_1",
    )
    await _add_entity_to_hass(hass, entity, mock_config_entry)

    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert state.state == STATE_UNKNOWN
