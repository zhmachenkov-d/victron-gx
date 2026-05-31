"""Tests for Victron GX device tracker platform."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from homeassistant.components.device_tracker import DOMAIN as DEVICE_TRACKER_DOMAIN
from homeassistant.components.device_tracker.config_entry import SourceType
from homeassistant.const import ATTR_LATITUDE, ATTR_LONGITUDE, STATE_NOT_HOME
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import EntityPlatform
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from victron_mqtt import GpsLocation, MetricKind, MetricType

from custom_components.victon_gx_hub.const import DOMAIN
from custom_components.victon_gx_hub.device_tracker import (
    ATTR_ALTITUDE,
    ATTR_COURSE,
    ATTR_SPEED,
    ATTR_SPEED_UNIT,
    SPEED_UNIT_METERS_PER_SECOND,
    VictronDeviceTracker,
    async_setup_entry,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

type NewMetricCallback = Callable[
    [FakeDevice, FakeMetric, DeviceInfo, str],
    None,
]

LATITUDE = 52.1
LONGITUDE = 5.2
ALTITUDE = 12.3
COURSE = 90.0
SPEED = 4.5


@dataclass
class FakeDevice:
    """Lightweight Victron device stand-in for tests."""

    unique_id: str = "device_1"
    name: str = "Test Device"


@dataclass
class FakeMetric:
    """Lightweight Victron metric stand-in for tests."""

    value: Any = None
    unique_id: str = "metric_1"
    generic_short_id: str = "gps_location"
    key_values: dict[str, str] = field(default_factory=dict)
    on_update: Callable[[FakeMetric, Any], None] | None = None

    def __post_init__(self) -> None:
        self._descriptor = SimpleNamespace(
            unit_of_measurement=None,
            metric_type=MetricType.LOCATION,
            precision=None,
            main_topic=False,
            message_type=MetricKind.DEVICE_TRACKER,
        )

    @property
    def precision(self) -> int | None:
        """Return the metric precision."""
        return self._descriptor.precision

    @property
    def unit_of_measurement(self) -> str | None:
        """Return the metric unit."""
        return self._descriptor.unit_of_measurement

    @property
    def metric_type(self) -> MetricType:
        """Return the metric type."""
        return self._descriptor.metric_type

    @property
    def main_topic(self) -> bool:
        """Return whether this is the device main topic."""
        return self._descriptor.main_topic

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
        """Invoke the registered device tracker callback."""
        callback = self.registered_callbacks.get(MetricKind.DEVICE_TRACKER)
        if callback is not None:
            callback(device, metric, device_info, installation_id)


def _make_location(
    latitude: float = LATITUDE,
    longitude: float = LONGITUDE,
    altitude: float | None = ALTITUDE,
    course: float | None = COURSE,
    speed: float | None = SPEED,
) -> GpsLocation:
    return GpsLocation(
        latitude=latitude,
        longitude=longitude,
        altitude=altitude,
        course=course,
        speed=speed,
    )


def _make_device_info() -> DeviceInfo:
    return DeviceInfo(identifiers={(DOMAIN, "installation_1_device_1")})


async def _add_entity_to_hass(
    hass: HomeAssistant,
    entity: VictronDeviceTracker,
    config_entry: MockConfigEntry,
) -> VictronDeviceTracker:
    """Add a device tracker entity through a platform like Home Assistant does."""
    platform = EntityPlatform(
        hass=hass,
        logger=logging.getLogger(__name__),
        domain=DEVICE_TRACKER_DOMAIN,
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


async def test_async_setup_entry_registers_device_tracker_callback(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Register a device tracker callback on the config entry hub."""
    hub = mock_config_entry.runtime_data
    assert isinstance(hub, FakeHub)
    added_entities: list[VictronDeviceTracker] = []

    def async_add_entities(
        entities: list[VictronDeviceTracker],
        update_before_add: bool = False,
    ) -> None:
        added_entities.extend(entities)

    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    assert MetricKind.DEVICE_TRACKER in hub.registered_callbacks

    hub.trigger_new_metric(
        FakeDevice(),
        FakeMetric(value=_make_location()),
        _make_device_info(),
        "installation_1",
    )

    assert len(added_entities) == 1
    assert added_entities[0].unique_id == "installation_1_metric_1"


async def test_async_setup_entry_skips_duplicate_device_tracker_metrics(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Avoid adding multiple entities for the same discovered tracker metric."""
    hub = mock_config_entry.runtime_data
    assert isinstance(hub, FakeHub)
    added_entities: list[VictronDeviceTracker] = []

    await async_setup_entry(hass, mock_config_entry, added_entities.extend)

    metric = FakeMetric(value=_make_location())
    hub.trigger_new_metric(FakeDevice(), metric, _make_device_info(), "installation_1")
    hub.trigger_new_metric(FakeDevice(), metric, _make_device_info(), "installation_1")

    assert len(added_entities) == 1


def test_device_tracker_initializes_from_location_value() -> None:
    """Initialize public tracker properties from a GpsLocation value."""
    entity = VictronDeviceTracker(
        FakeDevice(),
        FakeMetric(value=_make_location()),
        _make_device_info(),
        "installation_1",
    )

    assert entity.latitude == LATITUDE
    assert entity.longitude == LONGITUDE
    assert entity.source_type == SourceType.GPS
    assert entity.extra_state_attributes == {
        ATTR_ALTITUDE: ALTITUDE,
        ATTR_COURSE: COURSE,
        ATTR_SPEED: SPEED,
        ATTR_SPEED_UNIT: SPEED_UNIT_METERS_PER_SECOND,
    }


def test_device_tracker_clears_location_and_omits_empty_extra_attributes() -> None:
    """Clear coordinates and omit optional attributes when no GPS fix is available."""
    entity = VictronDeviceTracker(
        FakeDevice(),
        FakeMetric(value=None),
        _make_device_info(),
        "installation_1",
    )

    assert entity.latitude is None
    assert entity.longitude is None
    assert entity.extra_state_attributes == {}


async def test_device_tracker_state_updates_on_metric_change(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Publish tracker state and attributes to Home Assistant on metric updates."""
    metric = FakeMetric(value=_make_location())
    entity = VictronDeviceTracker(
        FakeDevice(),
        metric,
        _make_device_info(),
        "installation_1",
    )
    await _add_entity_to_hass(hass, entity, mock_config_entry)

    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert state.state == STATE_NOT_HOME
    assert state.attributes[ATTR_LATITUDE] == LATITUDE
    assert state.attributes[ATTR_LONGITUDE] == LONGITUDE
    assert state.attributes[ATTR_ALTITUDE] == ALTITUDE
    assert state.attributes[ATTR_SPEED_UNIT] == SPEED_UNIT_METERS_PER_SECOND

    metric.emit_update(None)
    await hass.async_block_till_done()

    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert state.state == "unknown"
    assert ATTR_LATITUDE not in state.attributes
    assert ATTR_ALTITUDE not in state.attributes
    assert ATTR_SPEED_UNIT not in state.attributes
