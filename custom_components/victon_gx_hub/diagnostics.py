"""Diagnostics support for victron_gx."""

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import DIAGNOSTICS_REDACT
from .hub import VictronGxConfigEntry


async def async_get_config_entry_diagnostics(
    _hass: HomeAssistant, entry: VictronGxConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    merged_config = {**entry.data, **entry.options}
    diagnostics: dict[str, Any] = {
        "entry_data": async_redact_data(merged_config, DIAGNOSTICS_REDACT),
    }
    hub = entry.runtime_data
    if hub is not None:
        diagnostics["devices"] = hub.get_diagnostics_data()
    return diagnostics
