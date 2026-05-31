"""Tests for Victron GX switch platform."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock

from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import EntityPlatform
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from victron_mqtt import (
    MetricKind,
    MetricType,
    WritableMetric as VictronVenusWritableMetric,
)
from victron_mqtt._victron_enums import ACSystemMode, GenericOnOff

from custom_components.victon_gx_hub.const import (
    BINARY_SENSOR_OFF_ID,
    BINARY_SENSOR_ON_ID,
    DOMAIN,
)
from custom_components.victon_gx_hub.switch import VictronSwitch, async_setup_entry

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

type NewMetricCallback = Callable[
    [FakeDevice, object, DeviceInfo, str],
    None,
]


@dataclass
class FakeDevice:
    """Lightweight Victron device stand-in for tests."""

    unique_id: str = "device_1"
    name: str = "Test Device"


class FakeWritableMetric(VictronVenusWritableMetric):
    """Writable Victron metric stand-in for switch tests."""

    def __init__(
        self,
        value: Any = GenericOnOff.ON,
        unique_id: str = "metric_1",
    ) -> None:
        self._descriptor = SimpleNamespace(
            unit_of_measurement=None,
            metric_type=MetricType.ENUM,
            precision=None,
            main_topic=False,
            message_type=MetricKind.SWITCH,
        )
        self._unique_id = unique_id
        self._short_id = "switch_state"
        self._name = "Switch State"
        self._generic_short_id = "switch_state"
        self._key_values: dict[str, str] = {}
        self._on_update = None
        self._value = value
        self._write_topic = "W/test/switch"
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
        """Invoke the registered switch callback."""
        callback = self.registered_callbacks.get(MetricKind.SWITCH)
        if callback is not None:
            callback(device, metric, device_info, installation_id)


def _make_device_info() -> DeviceInfo:
    return DeviceInfo(identifiers={(DOMAIN, "installation_1_device_1")})


async def _add_entity_to_hass(
    hass: HomeAssistant,
    entity: VictronSwitch,
    config_entry: MockConfigEntry,
) -> VictronSwitch:
    """Add a switch entity through a platform like Home Assistant does."""
    platform = EntityPlatform(
        hass=hass,
        logger=logging.getLogger(__name__),
        domain=SWITCH_DOMAIN,
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


async def test_async_setup_entry_registers_switch_callback(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Register a switch callback on the config entry hub."""
    hub = mock_config_entry.runtime_data
    assert isinstance(hub, FakeHub)
    added_entities: list[VictronSwitch] = []

    def async_add_entities(
        entities: list[VictronSwitch],
        update_before_add: bool = False,
    ) -> None:
        added_entities.extend(entities)

    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    assert MetricKind.SWITCH in hub.registered_callbacks

    hub.trigger_new_metric(
        FakeDevice(),
        FakeWritableMetric(),
        _make_device_info(),
        "installation_1",
    )

    assert len(added_entities) == 1
    assert added_entities[0].unique_id == "installation_1_metric_1"


async def test_async_setup_entry_skips_non_writable_switch_metrics(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Ignore switch metrics that cannot be written."""
    hub = mock_config_entry.runtime_data
    assert isinstance(hub, FakeHub)
    added_entities: list[VictronSwitch] = []

    await async_setup_entry(hass, mock_config_entry, added_entities.extend)

    hub.trigger_new_metric(
        FakeDevice(),
        object(),
        _make_device_info(),
        "installation_1",
    )

    assert added_entities == []


async def test_async_setup_entry_skips_duplicate_switch_metrics(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Avoid adding multiple entities for the same discovered switch metric."""
    hub = mock_config_entry.runtime_data
    assert isinstance(hub, FakeHub)
    added_entities: list[VictronSwitch] = []

    await async_setup_entry(hass, mock_config_entry, added_entities.extend)

    metric = FakeWritableMetric()
    hub.trigger_new_metric(FakeDevice(), metric, _make_device_info(), "installation_1")
    hub.trigger_new_metric(FakeDevice(), metric, _make_device_info(), "installation_1")

    assert len(added_entities) == 1


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (GenericOnOff.ON, True),
        (GenericOnOff.OFF, False),
        (None, None),
        (ACSystemMode.PASSTHROUGH, None),
    ],
)
def test_switch_initializes_from_metric_value(
    value: Any, expected: bool | None
) -> None:
    """Initialize switch state from the metric's current value."""
    entity = VictronSwitch(
        FakeDevice(),
        FakeWritableMetric(value=value),
        _make_device_info(),
        "installation_1",
    )

    assert entity.is_on is expected


async def test_async_turn_on_writes_in_executor(hass: HomeAssistant) -> None:
    """Turning on writes the on id through Home Assistant's executor."""
    metric = FakeWritableMetric(value=GenericOnOff.OFF)
    entity = VictronSwitch(
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

    await entity.async_turn_on()

    assert executor_calls == [(metric.set, (BINARY_SENSOR_ON_ID,))]
    metric.set.assert_called_once_with(BINARY_SENSOR_ON_ID)


async def test_async_turn_off_writes_in_executor(hass: HomeAssistant) -> None:
    """Turning off writes the off id through Home Assistant's executor."""
    metric = FakeWritableMetric()
    entity = VictronSwitch(
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

    await entity.async_turn_off()

    assert executor_calls == [(metric.set, (BINARY_SENSOR_OFF_ID,))]
    metric.set.assert_called_once_with(BINARY_SENSOR_OFF_ID)


async def test_switch_state_updates_on_metric_change(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Publish switch state to Home Assistant on metric updates."""
    metric = FakeWritableMetric(value=GenericOnOff.ON)
    entity = VictronSwitch(
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


async def test_switch_state_unknown_for_unmapped_enum(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Leave switch state unknown when enum id is not on/off."""
    entity = VictronSwitch(
        FakeDevice(),
        FakeWritableMetric(value=ACSystemMode.PASSTHROUGH),
        _make_device_info(),
        "installation_1",
    )
    await _add_entity_to_hass(hass, entity, mock_config_entry)

    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert state.state == STATE_UNKNOWN
