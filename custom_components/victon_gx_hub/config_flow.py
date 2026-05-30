"""Config flow for Victron GX."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
import voluptuous as vol

from .const import DOMAIN


class VictronGxConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Victron GX."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="Victron GX", data={})

        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))
