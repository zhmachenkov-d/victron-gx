"""Tests for Victron GX select platform."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock

from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
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
from victron_mqtt._victron_enums import GenericOnOff

from custom_components.victon_gx_hub.const import DOMAIN
from custom_components.victon_gx_hub.select import VictronSelect, async_setup_entry

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

type NewMetricCallback = Callable[
    [FakeDevice, object, DeviceInfo, str],
    None,
]

OPTION_OFF = "off"
OPTION_ON = "on"
LABEL_OFF = "Disabled"
LABEL_ON = "Enabled"
UNKNOWN_OPTION = "unknown"


@dataclass
class FakeDevice:
    """Lightweight Victron device stand-in for tests."""

    unique_id: str = "device_1"
    name: str = "Test Device"


@dataclass(frozen=True)
class FakeMetricSpec:
    """Configuration for a writable select metric test double."""

    value: Any = GenericOnOff.ON
    unique_id: str = "metric_1"
    options: list[str] | None = None


class FakeWritableMetric(VictronVenusWritableMetric):
    """Writable Victron metric stand-in for select tests."""

    def __init__(self, spec: FakeMetricSpec | None = None) -> None:
        spec = spec or FakeMetricSpec()
        self._descriptor = SimpleNamespace(
            unit_of_measurement=None,
            metric_type=MetricType.ENUM,
            precision=None,
            main_topic=False,
            message_type=MetricKind.SELECT,
        )
        self._unique_id = spec.unique_id
        self._short_id = "select_mode"
        self._name = "Select Mode"
        self._generic_short_id = "select_mode"
        self._key_values: dict[str, str] = {}
        self._on_update = None
        self._value = spec.value
        self._enum_values = spec.options
        self._write_topic = "W/test/select"
        self.set = Mock()

    @property
    def enum_values(self) -> list[str] | None:
        """Return available options."""
        return self._enum_values

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
        """Invoke the registered select callback."""
        callback = self.registered_callbacks.get(MetricKind.SELECT)
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
    entity: VictronSelect,
    config_entry: MockConfigEntry,
) -> VictronSelect:
    """Add a select entity through a platform like Home Assistant does."""
    platform = EntityPlatform(
        hass=hass,
        logger=logging.getLogger(__name__),
        domain=SELECT_DOMAIN,
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


async def test_async_setup_entry_registers_select_callback(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Register a select callback on the config entry hub."""
    hub = mock_config_entry.runtime_data
    assert isinstance(hub, FakeHub)
    added_entities: list[VictronSelect] = []

    def async_add_entities(
        entities: list[VictronSelect],
        update_before_add: bool = False,
    ) -> None:
        added_entities.extend(entities)

    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    assert MetricKind.SELECT in hub.registered_callbacks

    hub.trigger_new_metric(
        FakeDevice(),
        FakeWritableMetric(FakeMetricSpec(options=_enum_options())),
        _make_device_info(),
        "installation_1",
    )

    assert len(added_entities) == 1
    assert added_entities[0].unique_id == "installation_1_metric_1"


async def test_async_setup_entry_skips_invalid_select_metrics(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Ignore non-writable select metrics and selects without options."""
    hub = mock_config_entry.runtime_data
    assert isinstance(hub, FakeHub)
    added_entities: list[VictronSelect] = []

    await async_setup_entry(hass, mock_config_entry, added_entities.extend)

    hub.trigger_new_metric(
        FakeDevice(), object(), _make_device_info(), "installation_1"
    )
    hub.trigger_new_metric(
        FakeDevice(),
        FakeWritableMetric(FakeMetricSpec(options=None)),
        _make_device_info(),
        "installation_1",
    )

    assert added_entities == []


async def test_async_setup_entry_skips_duplicate_select_metrics(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Avoid adding multiple entities for the same discovered select metric."""
    hub = mock_config_entry.runtime_data
    assert isinstance(hub, FakeHub)
    added_entities: list[VictronSelect] = []

    await async_setup_entry(hass, mock_config_entry, added_entities.extend)

    metric = FakeWritableMetric(FakeMetricSpec(options=_enum_options()))
    hub.trigger_new_metric(FakeDevice(), metric, _make_device_info(), "installation_1")
    hub.trigger_new_metric(FakeDevice(), metric, _make_device_info(), "installation_1")

    assert len(added_entities) == 1


def test_select_initializes_from_enum_option() -> None:
    """Initialize options and current option from a normal enum select."""
    entity = VictronSelect(
        FakeDevice(),
        FakeWritableMetric(FakeMetricSpec(options=_enum_options())),
        _make_device_info(),
        "installation_1",
    )

    assert entity.options == _enum_options()
    assert entity.current_option == OPTION_ON


def test_select_initializes_dynamic_dropdown_label_from_enum_code() -> None:
    """Map dynamic dropdown enum codes to custom label options."""
    entity = VictronSelect(
        FakeDevice(),
        FakeWritableMetric(FakeMetricSpec(options=_label_options())),
        _make_device_info(),
        "installation_1",
    )

    assert entity.options == _label_options()
    assert entity.current_option == LABEL_ON


async def test_async_select_option_writes_in_executor(hass: HomeAssistant) -> None:
    """Selecting an option writes the value through Home Assistant's executor."""
    metric = FakeWritableMetric(FakeMetricSpec(options=_enum_options()))
    entity = VictronSelect(
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

    await entity.async_select_option(OPTION_OFF)

    assert executor_calls == [(metric.set, (OPTION_OFF,))]
    metric.set.assert_called_once_with(OPTION_OFF)


async def test_async_select_option_rejects_unknown_option(
    hass: HomeAssistant,
) -> None:
    """Do not publish options that are not available for the select entity."""
    metric = FakeWritableMetric(FakeMetricSpec(options=_enum_options()))
    entity = VictronSelect(
        FakeDevice(),
        metric,
        _make_device_info(),
        "installation_1",
    )
    entity.hass = hass

    with pytest.raises(ValueError, match=UNKNOWN_OPTION):
        await entity.async_select_option(UNKNOWN_OPTION)

    metric.set.assert_not_called()


async def test_select_state_updates_on_metric_change(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Publish select state to Home Assistant on metric updates."""
    metric = FakeWritableMetric(
        FakeMetricSpec(value=GenericOnOff.OFF, options=_enum_options())
    )
    entity = VictronSelect(
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


async def test_select_state_unknown_for_value_outside_options(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Leave select state unknown when a metric value is not an option."""
    entity = VictronSelect(
        FakeDevice(),
        FakeWritableMetric(
            FakeMetricSpec(value=UNKNOWN_OPTION, options=_enum_options())
        ),
        _make_device_info(),
        "installation_1",
    )
    await _add_entity_to_hass(hass, entity, mock_config_entry)

    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert state.state == STATE_UNKNOWN
