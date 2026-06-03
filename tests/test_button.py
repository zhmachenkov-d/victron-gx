"""Tests for Victron GX button platform."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock

from homeassistant.helpers.device_registry import DeviceInfo
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from victron_mqtt import (
    GenericOnOff,
    MetricKind,
    MetricType,
    WritableMetric as VictronVenusWritableMetric,
)

from custom_components.victron_gx_hub.button import VictronButton, async_setup_entry
from custom_components.victron_gx_hub.const import DOMAIN

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
    """Writable Victron metric stand-in for button tests."""

    def __init__(self, unique_id: str = "metric_1") -> None:
        self._descriptor = SimpleNamespace(
            unit_of_measurement=None,
            metric_type=MetricType.RESTART,
            precision=None,
            main_topic=False,
            message_type=MetricKind.BUTTON,
        )
        self._unique_id = unique_id
        self._generic_short_id = "platform_device_reboot"
        self._key_values: dict[str, str] = {}
        self._on_update = None
        self.set = Mock()


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
        """Invoke the registered button callback."""
        callback = self.registered_callbacks.get(MetricKind.BUTTON)
        if callback is not None:
            callback(device, metric, device_info, installation_id)


def _make_device_info() -> DeviceInfo:
    return DeviceInfo(identifiers={(DOMAIN, "installation_1_device_1")})


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


async def test_async_setup_entry_registers_button_callback(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Register a button callback on the config entry hub."""
    hub = mock_config_entry.runtime_data
    assert isinstance(hub, FakeHub)

    added_entities: list[VictronButton] = []

    def async_add_entities(
        entities: list[VictronButton],
        update_before_add: bool = False,
    ) -> None:
        added_entities.extend(entities)

    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    assert MetricKind.BUTTON in hub.registered_callbacks

    hub.trigger_new_metric(
        FakeDevice(),
        FakeWritableMetric(),
        _make_device_info(),
        "installation_1",
    )

    assert len(added_entities) == 1
    assert added_entities[0].unique_id == "installation_1_metric_1"


async def test_async_setup_entry_skips_non_writable_button_metrics(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Ignore button metrics that cannot be written."""
    hub = mock_config_entry.runtime_data
    assert isinstance(hub, FakeHub)
    added_entities: list[VictronButton] = []

    await async_setup_entry(hass, mock_config_entry, added_entities.extend)

    hub.trigger_new_metric(
        FakeDevice(),
        object(),
        _make_device_info(),
        "installation_1",
    )

    assert added_entities == []


async def test_async_setup_entry_skips_duplicate_button_metrics(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Avoid adding multiple entities for the same discovered button metric."""
    hub = mock_config_entry.runtime_data
    assert isinstance(hub, FakeHub)
    added_entities: list[VictronButton] = []

    await async_setup_entry(hass, mock_config_entry, added_entities.extend)

    metric = FakeWritableMetric()
    hub.trigger_new_metric(FakeDevice(), metric, _make_device_info(), "installation_1")
    hub.trigger_new_metric(FakeDevice(), metric, _make_device_info(), "installation_1")

    assert len(added_entities) == 1


async def test_async_press_writes_on_value_in_executor(hass: HomeAssistant) -> None:
    """Pressing a button writes GenericOnOff.ON through Home Assistant's executor."""
    metric = FakeWritableMetric()
    entity = VictronButton(
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

    await entity.async_press()

    assert executor_calls == [(metric.set, (GenericOnOff.ON,))]
    metric.set.assert_called_once_with(GenericOnOff.ON)
