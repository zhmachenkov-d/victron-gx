"""Support for Victron GX sensors."""

from datetime import datetime
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from victron_mqtt import (
    Device as VictronVenusDevice,
    Metric as VictronVenusMetric,
    MetricKind,
    MetricNature,
    MetricType,
    VictronEnum,
)

from .entity import VictronBaseEntity
from .hub import VictronGxConfigEntry

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0  # There is no I/O in the entity itself.

METRIC_TYPE_TO_DEVICE_CLASS: dict[MetricType, SensorDeviceClass] = {
    MetricType.POWER: SensorDeviceClass.POWER,
    MetricType.APPARENT_POWER: SensorDeviceClass.APPARENT_POWER,
    MetricType.ENERGY: SensorDeviceClass.ENERGY,
    MetricType.VOLTAGE: SensorDeviceClass.VOLTAGE,
    MetricType.CURRENT: SensorDeviceClass.CURRENT,
    MetricType.FREQUENCY: SensorDeviceClass.FREQUENCY,
    MetricType.ELECTRIC_STORAGE_PERCENTAGE: SensorDeviceClass.BATTERY,
    MetricType.TEMPERATURE: SensorDeviceClass.TEMPERATURE,
    MetricType.HUMIDITY: SensorDeviceClass.HUMIDITY,
    MetricType.PRESSURE: SensorDeviceClass.PRESSURE,
    MetricType.DISTANCE: SensorDeviceClass.DISTANCE,
    MetricType.POWER_FACTOR: SensorDeviceClass.POWER_FACTOR,
    MetricType.COST: SensorDeviceClass.MONETARY,
    MetricType.SPEED: SensorDeviceClass.SPEED,
    MetricType.LIQUID_VOLUME: SensorDeviceClass.VOLUME_STORAGE,
    MetricType.DURATION: SensorDeviceClass.DURATION,
    MetricType.ENUM: SensorDeviceClass.ENUM,
    MetricType.IRRADIANCE: SensorDeviceClass.IRRADIANCE,
    MetricType.TIMESTAMP: SensorDeviceClass.TIMESTAMP,
}

METRIC_NATURE_TO_STATE_CLASS: dict[MetricNature, SensorStateClass] = {
    MetricNature.MEASUREMENT: SensorStateClass.MEASUREMENT,
    MetricNature.TOTAL: SensorStateClass.TOTAL,
    MetricNature.TOTAL_INCREASING: SensorStateClass.TOTAL_INCREASING,
}


async def async_setup_entry(
    _hass: HomeAssistant,
    config_entry: VictronGxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Victron GX sensors from a config entry."""
    hub = config_entry.runtime_data
    seen_unique_ids: set[str] = set()

    def on_new_metric(
        device: VictronVenusDevice,
        metric: VictronVenusMetric,
        device_info: DeviceInfo,
        installation_id: str,
    ) -> None:
        """Handle new sensor metric discovery."""
        unique_id = f"{installation_id}_{metric.unique_id}"
        if unique_id in seen_unique_ids:
            _LOGGER.debug("Skipping duplicate sensor metric: %s", unique_id)
            return
        seen_unique_ids.add(unique_id)

        async_add_entities(
            [VictronSensor(device, metric, device_info, installation_id)]
        )

    hub.register_new_metric_callback(MetricKind.SENSOR, on_new_metric)


class VictronSensor(VictronBaseEntity, SensorEntity):
    """Implementation of a Victron GX sensor."""

    def __init__(
        self,
        device: VictronVenusDevice,
        metric: VictronVenusMetric,
        device_info: DeviceInfo,
        installation_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(device, metric, device_info, installation_id)
        self._attr_device_class = METRIC_TYPE_TO_DEVICE_CLASS.get(metric.metric_type)
        # Enum and timestamp sensors must not have a state class
        if self._attr_device_class == SensorDeviceClass.ENUM:
            self._attr_options = metric.enum_values or []
        elif self._attr_device_class != SensorDeviceClass.TIMESTAMP:
            self._attr_state_class = METRIC_NATURE_TO_STATE_CLASS.get(
                metric.metric_nature
            )
        # Only set native_unit_of_measurement when a device_class is present.
        # Entities without a device_class get their display unit from
        # the translation files instead.
        if self._attr_device_class is not None:
            self._attr_native_unit_of_measurement = metric.unit_of_measurement
        self._attr_native_value = self._normalize_value(metric.value)

    @callback
    def _on_update_cb(self, value: Any) -> None:
        self._attr_native_value = self._normalize_value(value)
        self.async_write_ha_state()

    def _normalize_value(self, value: Any) -> Any:
        """Normalize Victron metric values for Home Assistant."""
        if value is None:
            return None
        if self._attr_device_class == SensorDeviceClass.ENUM:
            return self._normalize_enum_value(value)
        if self._attr_device_class == SensorDeviceClass.TIMESTAMP:
            return self._normalize_timestamp_value(value)
        if self._attr_device_class is not None:
            return self._normalize_numeric_value(value)
        if isinstance(value, VictronEnum):
            return value.id
        return value

    def _normalize_enum_value(self, value: Any) -> str | None:
        """Normalize Victron enum values to their enum code."""
        options = self.options or []
        if isinstance(value, VictronEnum):
            if value.id in options:
                return value.id
            if 0 <= value.code < len(options):
                return options[value.code]
            _LOGGER.warning("Sensor value %s is not in options: %s", value, options)
            return None
        if isinstance(value, str) and value in options:
            return value
        _LOGGER.warning("Ignoring sensor value not in options: %s", value)
        return None

    @staticmethod
    def _normalize_timestamp_value(value: Any) -> datetime | None:
        """Pass through datetime values for timestamp sensors."""
        if isinstance(value, datetime):
            return value
        _LOGGER.warning("Ignoring non-datetime timestamp sensor value: %s", value)
        return None

    @staticmethod
    def _normalize_numeric_value(value: Any) -> float | None:
        """Convert a Victron numeric value to a Home Assistant sensor value."""
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
        _LOGGER.warning("Ignoring non-numeric sensor value: %s", value)
        return None
