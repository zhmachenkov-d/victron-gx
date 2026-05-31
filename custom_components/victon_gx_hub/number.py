"""Support for Victron GX number entities."""

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.number import NumberDeviceClass, NumberEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from victron_mqtt import (
    Device as VictronVenusDevice,
    Metric as VictronVenusMetric,
    MetricKind,
    MetricType,
    WritableMetric as VictronVenusWritableMetric,
)

from .entity import VictronBaseEntity
from .hub import VictronGxConfigEntry

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

METRIC_TYPE_TO_DEVICE_CLASS: dict[MetricType, NumberDeviceClass] = {
    MetricType.POWER: NumberDeviceClass.POWER,
    MetricType.APPARENT_POWER: NumberDeviceClass.APPARENT_POWER,
    MetricType.ENERGY: NumberDeviceClass.ENERGY,
    MetricType.VOLTAGE: NumberDeviceClass.VOLTAGE,
    MetricType.CURRENT: NumberDeviceClass.CURRENT,
    MetricType.FREQUENCY: NumberDeviceClass.FREQUENCY,
    MetricType.ELECTRIC_STORAGE_PERCENTAGE: NumberDeviceClass.BATTERY,
    MetricType.TEMPERATURE: NumberDeviceClass.TEMPERATURE,
    MetricType.SPEED: NumberDeviceClass.SPEED,
    MetricType.LIQUID_VOLUME: NumberDeviceClass.VOLUME_STORAGE,
    MetricType.DURATION: NumberDeviceClass.DURATION,
}


async def async_setup_entry(
    _hass: HomeAssistant,
    config_entry: VictronGxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Victron GX number entities from a config entry."""
    hub = config_entry.runtime_data
    seen_unique_ids: set[str] = set()

    def on_new_metric(
        device: VictronVenusDevice,
        metric: VictronVenusMetric,
        device_info: DeviceInfo,
        installation_id: str,
    ) -> None:
        """Handle new number metric discovery."""
        if not isinstance(metric, VictronVenusWritableMetric):
            _LOGGER.warning("Skipping non-writable number metric: %s", metric)
            return
        unique_id = f"{installation_id}_{metric.unique_id}"
        if unique_id in seen_unique_ids:
            _LOGGER.debug("Skipping duplicate number metric: %s", unique_id)
            return
        seen_unique_ids.add(unique_id)

        async_add_entities(
            [VictronNumber(device, metric, device_info, installation_id)]
        )

    hub.register_new_metric_callback(MetricKind.NUMBER, on_new_metric)


class VictronNumber(VictronBaseEntity, NumberEntity):
    """Implementation of a Victron GX number entity."""

    def __init__(
        self,
        device: VictronVenusDevice,
        metric: VictronVenusWritableMetric,
        device_info: DeviceInfo,
        installation_id: str,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(device, metric, device_info, installation_id)
        self._attr_device_class = METRIC_TYPE_TO_DEVICE_CLASS.get(metric.metric_type)
        if metric.unit_of_measurement is not None:
            self._attr_native_unit_of_measurement = metric.unit_of_measurement
        self._attr_native_value = self._convert_native_value(metric.value)
        if metric.min_value is not None:
            self._attr_native_min_value = metric.min_value
        if metric.max_value is not None:
            self._attr_native_max_value = metric.max_value
        if metric.step is not None:
            self._attr_native_step = metric.step

    @callback
    def _on_update_cb(self, value: Any) -> None:
        self._attr_native_value = self._convert_native_value(value)
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Set a new value."""
        if TYPE_CHECKING:
            assert isinstance(self._metric, VictronVenusWritableMetric)
        await self.hass.async_add_executor_job(self._metric.set, value)

    @staticmethod
    def _convert_native_value(value: Any) -> float | None:
        """Convert a Victron numeric value to a Home Assistant number value."""
        if value is None:
            return None
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
        _LOGGER.warning("Ignoring non-numeric number value: %s", value)
        return None
