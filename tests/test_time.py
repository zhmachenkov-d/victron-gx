"""Tests for Victron GX time platform."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import time as dt_time, timedelta
import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock

from homeassistant.components.time import DOMAIN as TIME_DOMAIN
from homeassistant.const import STATE_UNKNOWN
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
from custom_components.victon_gx_hub.time import (
    MINUTES_PER_DAY,
    VictronTime,
    async_setup_entry,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

type NewMetricCallback = Callable[
    [FakeDevice, object, DeviceInfo, str],
    None,
]

INITIAL_MINUTES = 510
UPDATED_MINUTES = 615
SET_MINUTES = 1380
OUT_OF_RANGE_MINUTES = MINUTES_PER_DAY
TIME_STATE = "08:30:00"
UPDATED_TIME_STATE = "10:15:00"
SET_TIME = dt_time(hour=23)


@dataclass
class FakeDevice:
    """Lightweight Victron device stand-in for tests."""

    unique_id: str = "device_1"
    name: str = "Test Device"


class FakeWritableMetric(VictronVenusWritableMetric):
    """Writable Victron metric stand-in for time tests."""

    def __init__(
        self,
        value: Any = INITIAL_MINUTES,
        unique_id: str = "metric_1",
    ) -> None:
        self._descriptor = SimpleNamespace(
            unit_of_measurement="min",
            metric_type=MetricType.TIME,
            precision=None,
            main_topic=False,
            message_type=MetricKind.TIME,
        )
        self._unique_id = unique_id
        self._short_id = "schedule_start"
        self._name = "Schedule Start"
        self._generic_short_id = "schedule_start"
        self._key_values: dict[str, str] = {}
        self._on_update = None
        self._value = value
        self._write_topic = "W/test/time"
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
        """Invoke the registered time callback."""
        callback = self.registered_callbacks.get(MetricKind.TIME)
        if callback is not None:
            callback(device, metric, device_info, installation_id)


def _make_device_info() -> DeviceInfo:
    return DeviceInfo(identifiers={(DOMAIN, "installation_1_device_1")})


async def _add_entity_to_hass(
    hass: HomeAssistant,
    entity: VictronTime,
    config_entry: MockConfigEntry,
) -> VictronTime:
    """Add a time entity through a platform like Home Assistant does."""
    platform = EntityPlatform(
        hass=hass,
        logger=logging.getLogger(__name__),
        domain=TIME_DOMAIN,
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


async def test_async_setup_entry_registers_time_callback(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Register a time callback on the config entry hub."""
    hub = mock_config_entry.runtime_data
    assert isinstance(hub, FakeHub)
    added_entities: list[VictronTime] = []

    def async_add_entities(
        entities: list[VictronTime],
        update_before_add: bool = False,
    ) -> None:
        added_entities.extend(entities)

    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    assert MetricKind.TIME in hub.registered_callbacks

    hub.trigger_new_metric(
        FakeDevice(),
        FakeWritableMetric(),
        _make_device_info(),
        "installation_1",
    )

    assert len(added_entities) == 1
    assert added_entities[0].unique_id == "installation_1_metric_1"


async def test_async_setup_entry_skips_non_writable_time_metrics(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Ignore time metrics that cannot be written."""
    hub = mock_config_entry.runtime_data
    assert isinstance(hub, FakeHub)
    added_entities: list[VictronTime] = []

    await async_setup_entry(hass, mock_config_entry, added_entities.extend)

    hub.trigger_new_metric(
        FakeDevice(),
        object(),
        _make_device_info(),
        "installation_1",
    )

    assert added_entities == []


async def test_async_setup_entry_skips_duplicate_time_metrics(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Avoid adding multiple entities for the same discovered time metric."""
    hub = mock_config_entry.runtime_data
    assert isinstance(hub, FakeHub)
    added_entities: list[VictronTime] = []

    await async_setup_entry(hass, mock_config_entry, added_entities.extend)

    metric = FakeWritableMetric()
    hub.trigger_new_metric(FakeDevice(), metric, _make_device_info(), "installation_1")
    hub.trigger_new_metric(FakeDevice(), metric, _make_device_info(), "installation_1")

    assert len(added_entities) == 1


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (INITIAL_MINUTES, dt_time(hour=8, minute=30)),
        (float(INITIAL_MINUTES), dt_time(hour=8, minute=30)),
        (None, None),
        ("not-a-time", None),
        (True, None),
        (OUT_OF_RANGE_MINUTES, None),
    ],
)
def test_victron_time_to_time(value: Any, expected: dt_time | None) -> None:
    """Convert Victron minutes since midnight to Home Assistant time values."""
    assert VictronTime.victron_time_to_time(value) == expected


def test_time_to_victron_time() -> None:
    """Convert Home Assistant time values to Victron minutes since midnight."""
    assert VictronTime.time_to_victron_time(SET_TIME) == SET_MINUTES


def test_time_initializes_native_value() -> None:
    """Initialize native value from the metric's current value."""
    entity = VictronTime(
        FakeDevice(),
        FakeWritableMetric(),
        _make_device_info(),
        "installation_1",
    )

    assert entity.native_value == dt_time(hour=8, minute=30)


async def test_async_set_value_writes_in_executor(hass: HomeAssistant) -> None:
    """Setting a time writes minutes through Home Assistant's executor."""
    metric = FakeWritableMetric()
    entity = VictronTime(
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

    await entity.async_set_value(SET_TIME)

    assert executor_calls == [(metric.set, (SET_MINUTES,))]
    metric.set.assert_called_once_with(SET_MINUTES)


async def test_time_state_updates_on_metric_change(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Publish time state to Home Assistant on metric updates."""
    metric = FakeWritableMetric()
    entity = VictronTime(
        FakeDevice(),
        metric,
        _make_device_info(),
        "installation_1",
    )
    await _add_entity_to_hass(hass, entity, mock_config_entry)

    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert state.state == TIME_STATE

    metric.emit_update(UPDATED_MINUTES)
    await hass.async_block_till_done()

    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert state.state == UPDATED_TIME_STATE


async def test_time_state_unknown_for_invalid_metric_value(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Leave time state unknown when the metric value is invalid."""
    entity = VictronTime(
        FakeDevice(),
        FakeWritableMetric(value=OUT_OF_RANGE_MINUTES),
        _make_device_info(),
        "installation_1",
    )
    await _add_entity_to_hass(hass, entity, mock_config_entry)

    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert state.state == STATE_UNKNOWN
