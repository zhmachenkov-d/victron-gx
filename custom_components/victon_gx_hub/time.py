"""Support for Victron GX times."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .hub import VictronGxConfigEntry

PARALLEL_UPDATES = 0  # There is no I/O in the entity itself.


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: VictronGxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Victron GX times from a config entry."""
