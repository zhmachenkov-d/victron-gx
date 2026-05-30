"""The Victron GX integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

type VictronGxConfigEntry = ConfigEntry[None]


async def async_setup_entry(hass: HomeAssistant, entry: VictronGxConfigEntry) -> bool:
    """Set up Victron GX from a config entry."""
    entry.runtime_data = None
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VictronGxConfigEntry) -> bool:
    """Unload a config entry."""
    return True
