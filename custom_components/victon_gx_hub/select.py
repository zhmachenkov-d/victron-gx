"""Support for Victron GX select entities."""

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from victron_mqtt import (
    Device as VictronVenusDevice,
    Metric as VictronVenusMetric,
    MetricKind,
    VictronEnum,
    WritableMetric as VictronVenusWritableMetric,
)

from .entity import VictronBaseEntity
from .hub import VictronGxConfigEntry

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0  # There is no I/O in the entity itself.


async def async_setup_entry(
    _hass: HomeAssistant,
    config_entry: VictronGxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Victron GX select entities from a config entry."""
    hub = config_entry.runtime_data
    seen_unique_ids: set[str] = set()

    def on_new_metric(
        device: VictronVenusDevice,
        metric: VictronVenusMetric,
        device_info: DeviceInfo,
        installation_id: str,
    ) -> None:
        """Handle new select metric discovery."""
        if not isinstance(metric, VictronVenusWritableMetric):
            _LOGGER.warning("Skipping non-writable select metric: %s", metric)
            return
        if not metric.enum_values:
            _LOGGER.warning("Skipping select metric without options: %s", metric)
            return
        unique_id = f"{installation_id}_{metric.unique_id}"
        if unique_id in seen_unique_ids:
            _LOGGER.debug("Skipping duplicate select metric: %s", unique_id)
            return
        seen_unique_ids.add(unique_id)

        async_add_entities(
            [VictronSelect(device, metric, device_info, installation_id)]
        )

    hub.register_new_metric_callback(MetricKind.SELECT, on_new_metric)


class VictronSelect(VictronBaseEntity, SelectEntity):
    """Implementation of a Victron GX select entity."""

    def __init__(
        self,
        device: VictronVenusDevice,
        metric: VictronVenusWritableMetric,
        device_info: DeviceInfo,
        installation_id: str,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(device, metric, device_info, installation_id)
        self._attr_options = metric.enum_values or []
        self._attr_current_option = self._normalize_value(metric.value)

    @callback
    def _on_update_cb(self, value: Any) -> None:
        self._attr_current_option = self._normalize_value(value)
        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if TYPE_CHECKING:
            assert isinstance(self._metric, VictronVenusWritableMetric)
        if option not in self.options:
            raise ValueError(option)
        _LOGGER.debug("Setting select %s to %s", self.unique_id, option)
        await self.hass.async_add_executor_job(self._metric.set, option)

    def _normalize_value(self, value: Any) -> str | None:
        """Normalize Victron enum values to their enum code."""
        if value is None:
            return None
        if isinstance(value, VictronEnum):
            if value.id in self.options:
                return value.id
            if 0 <= value.code < len(self.options):
                return self.options[value.code]
            _LOGGER.warning(
                "Select value %s is not in options: %s", value, self.options
            )
            return None
        if isinstance(value, str) and value in self.options:
            return value
        _LOGGER.warning("Ignoring select value not in options: %s", value)
        return None
