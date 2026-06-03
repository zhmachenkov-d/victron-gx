"""Support for Victron GX button entities."""

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from victron_mqtt import (
    Device as VictronVenusDevice,
    GenericOnOff,
    Metric as VictronVenusMetric,
    MetricKind,
    WritableMetric as VictronVenusWritableMetric,
)

from .entity import VictronBaseEntity
from .hub import VictronGxConfigEntry

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    _hass: HomeAssistant,
    config_entry: VictronGxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Victron GX button entities from a config entry."""
    hub = config_entry.runtime_data
    seen_unique_ids: set[str] = set()

    def on_new_metric(
        device: VictronVenusDevice,
        metric: VictronVenusMetric,
        device_info: DeviceInfo,
        installation_id: str,
    ) -> None:
        """Handle new button metric discovery."""
        if not isinstance(metric, VictronVenusWritableMetric):
            _LOGGER.warning("Skipping non-writable button metric: %s", metric)
            return
        unique_id = f"{installation_id}_{metric.unique_id}"
        if unique_id in seen_unique_ids:
            _LOGGER.debug("Skipping duplicate button metric: %s", unique_id)
            return
        seen_unique_ids.add(unique_id)

        async_add_entities(
            [VictronButton(device, metric, device_info, installation_id)]
        )

    hub.register_new_metric_callback(MetricKind.BUTTON, on_new_metric)


class VictronButton(VictronBaseEntity, ButtonEntity):
    """Implementation of a Victron GX button entity."""

    @callback
    def _on_update_cb(self, _value: Any) -> None:
        # Buttons are stateless in HA; incoming metric
        # updates are intentionally ignored.
        pass

    async def async_press(self) -> None:
        """Press the button."""
        if TYPE_CHECKING:
            assert isinstance(self._metric, VictronVenusWritableMetric)
        _LOGGER.debug("Pressing button: %s", self.unique_id)
        await self.hass.async_add_executor_job(self._metric.set, GenericOnOff.ON)
