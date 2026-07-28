"""Config flow for Victron GX."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from homeassistant.components.file_upload import process_uploaded_file
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import (
    CONF_HOST,
    CONF_MODEL,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.helpers import selector
from homeassistant.helpers.redact import async_redact_data
from victron_mqtt import (
    UPDATE_FREQUENCY_AUTO,
    UPDATE_FREQUENCY_AUTO_POWER_NONE,
    AuthenticationError,
    CannotConnectError,
    Hub as VictronVenusHub,
)
import voluptuous as vol

from .const import (
    CONF_CA_CERT,
    CONF_INSTALLATION_ID,
    CONF_SERIAL,
    CONF_UPDATE_INTERVAL,
    CONF_UPDATE_INTERVAL_SECONDS,
    DOMAIN,
)
from .hub import resolve_update_frequency
from .ssl_util import build_ssl_context

if TYPE_CHECKING:
    from collections.abc import Mapping

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.service_info.ssdp import SsdpServiceInfo

DEFAULT_HOST = "venus.local"
DEFAULT_PORT = 1883

_LOGGER = logging.getLogger(__name__)

TO_REDACT = {CONF_USERNAME, CONF_PASSWORD, CONF_CA_CERT}

ENTRY_TITLE_FORMAT = "Victron OS {installation_id} ({host}:{port})"

UPDATE_INTERVAL_PROFILES = frozenset(
    {UPDATE_FREQUENCY_AUTO, UPDATE_FREQUENCY_AUTO_POWER_NONE}
)

UPDATE_INTERVAL_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            UPDATE_FREQUENCY_AUTO,
            UPDATE_FREQUENCY_AUTO_POWER_NONE,
        ],
        custom_value=True,
        mode=selector.SelectSelectorMode.DROPDOWN,
        translation_key="update_interval",
    )
)

CA_CERT_SELECTOR = selector.FileSelector(
    selector.FileSelectorConfig(accept=".pem,.crt,.cer")
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_HOST): selector.TextSelector(),
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_USERNAME): selector.TextSelector(),
        vol.Optional(CONF_PASSWORD): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
        vol.Required(CONF_SSL, default=False): selector.BooleanSelector(),
        vol.Optional(CONF_VERIFY_SSL, default=False): selector.BooleanSelector(),
        vol.Optional(CONF_CA_CERT): CA_CERT_SELECTOR,
        vol.Optional(CONF_UPDATE_INTERVAL): UPDATE_INTERVAL_SELECTOR,
    }
)

STEP_SSDP_AUTH_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_USERNAME, default=""): selector.TextSelector(),
        vol.Optional(CONF_PASSWORD, default=""): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
        vol.Optional(CONF_SSL, default=False): selector.BooleanSelector(),
        vol.Optional(CONF_VERIFY_SSL, default=False): selector.BooleanSelector(),
        vol.Optional(CONF_CA_CERT): CA_CERT_SELECTOR,
        vol.Optional(CONF_UPDATE_INTERVAL): UPDATE_INTERVAL_SELECTOR,
    }
)

STEP_REAUTH_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_USERNAME, default=""): selector.TextSelector(),
        vol.Optional(CONF_PASSWORD, default=""): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
        vol.Optional(CONF_SSL): selector.BooleanSelector(),
        vol.Optional(CONF_VERIFY_SSL): selector.BooleanSelector(),
        vol.Optional(CONF_CA_CERT): CA_CERT_SELECTOR,
    }
)


async def validate_input(data: dict[str, Any]) -> str:
    """Validate the user input allows us to connect.

    Data has the keys from SSDP values as well as user input.

    Returns the installation id upon success.
    """
    _LOGGER.debug("Validating input: %s", async_redact_data(data, TO_REDACT))
    hub: VictronVenusHub | None = None
    use_ssl = data.get(CONF_SSL, False)
    try:
        hub = VictronVenusHub(
            host=data[CONF_HOST],
            port=int(data[CONF_PORT]),
            username=data.get(CONF_USERNAME) or None,
            password=data.get(CONF_PASSWORD) or None,
            use_ssl=use_ssl,
            ssl_context=build_ssl_context(data),
            installation_id=data.get(CONF_INSTALLATION_ID) or None,
            model_name=data.get(CONF_MODEL) or None,
            serial=data.get(CONF_SERIAL) or None,
            update_frequency_seconds=resolve_update_frequency(data),
        )

        await hub.connect()
        if hub.installation_id is None:
            raise CannotConnectError

        return hub.installation_id
    finally:
        if hub is not None:
            try:
                await hub.disconnect()
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Ignoring disconnect error during config validation")


def _apply_credential_updates(
    existing_data: dict[str, Any],
    user_input: dict[str, Any],
) -> dict[str, Any]:
    """Merge credential fields, preserving stored password when left blank."""
    # Keep CA handling out of the merge; caller finalizes TLS separately.
    merged_input = {
        key: value for key, value in user_input.items() if key != CONF_CA_CERT
    }
    data = {**existing_data, **merged_input}
    if CONF_USERNAME in user_input:
        data[CONF_USERNAME] = user_input[CONF_USERNAME] or None
    if CONF_PASSWORD in user_input:
        if user_input[CONF_PASSWORD]:
            data[CONF_PASSWORD] = user_input[CONF_PASSWORD]
        else:
            data[CONF_PASSWORD] = existing_data.get(CONF_PASSWORD)
    return data


def _normalize_update_interval(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize update interval and migrate the legacy seconds key."""
    normalized = dict(data)

    if (
        CONF_UPDATE_INTERVAL_SECONDS in normalized
        and CONF_UPDATE_INTERVAL not in normalized
    ):
        normalized[CONF_UPDATE_INTERVAL] = normalized.pop(CONF_UPDATE_INTERVAL_SECONDS)
    else:
        normalized.pop(CONF_UPDATE_INTERVAL_SECONDS, None)

    if CONF_UPDATE_INTERVAL not in normalized:
        return normalized

    value = normalized[CONF_UPDATE_INTERVAL]
    if value in (None, ""):
        normalized.pop(CONF_UPDATE_INTERVAL, None)
    elif value in UPDATE_INTERVAL_PROFILES:
        normalized[CONF_UPDATE_INTERVAL] = value
    else:
        normalized[CONF_UPDATE_INTERVAL] = int(value)
    return normalized


async def _async_read_uploaded_ca(hass: HomeAssistant, file_id: str) -> str:
    """Read an uploaded CA certificate file as a PEM string."""

    def _read() -> str:
        with process_uploaded_file(hass, file_id) as file_path:
            return file_path.read_text(encoding="utf-8")

    return await hass.async_add_executor_job(_read)


async def _async_finalize_config_data(
    hass: HomeAssistant,
    data: dict[str, Any],
    *,
    ca_upload_id: str | None = None,
    existing_data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize interval/TLS fields for storage in a config entry."""
    prepared = _normalize_update_interval(data)
    existing = existing_data or {}

    use_ssl = prepared.get(CONF_SSL, False)
    if not use_ssl:
        prepared.pop(CONF_VERIFY_SSL, None)
        prepared.pop(CONF_CA_CERT, None)
        return prepared

    verify_ssl = bool(prepared.get(CONF_VERIFY_SSL, False))
    prepared[CONF_VERIFY_SSL] = verify_ssl
    if not verify_ssl:
        prepared.pop(CONF_CA_CERT, None)
        return prepared

    if ca_upload_id:
        prepared[CONF_CA_CERT] = await _async_read_uploaded_ca(hass, ca_upload_id)
    elif existing.get(CONF_CA_CERT):
        prepared[CONF_CA_CERT] = existing[CONF_CA_CERT]
    else:
        prepared.pop(CONF_CA_CERT, None)
    return prepared


def _suggested_update_interval(entry_data: Mapping[str, Any]) -> Any:
    """Return the stored update interval, including legacy key migration."""
    if CONF_UPDATE_INTERVAL in entry_data:
        return entry_data[CONF_UPDATE_INTERVAL]
    return entry_data.get(CONF_UPDATE_INTERVAL_SECONDS)


class VictronGxConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Victron GX."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self.hostname: str | None = None
        self.serial: str | None = None
        self.installation_id: str | None = None
        self.friendly_name: str | None = None
        self.model_name: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            ca_upload_id = user_input.pop(CONF_CA_CERT, None)
            _LOGGER.debug(
                "User input received: %s",
                async_redact_data(user_input, TO_REDACT),
            )
            data = await _async_finalize_config_data(
                self.hass,
                {
                    **user_input,
                    CONF_SERIAL: self.serial,
                    CONF_MODEL: self.model_name,
                },
                ca_upload_id=ca_upload_id,
            )

            try:
                installation_id = await validate_input(data)
                _LOGGER.debug(
                    "Successfully connected to Victron device: %s", installation_id
                )
            except AuthenticationError:
                _LOGGER.debug(
                    "Authentication failed during initial setup", exc_info=True
                )
                errors["base"] = "invalid_auth"
            except CannotConnectError:
                _LOGGER.debug("Cannot connect to Victron device", exc_info=True)
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error connecting to Victron device")
                errors["base"] = "unknown"
            else:
                data[CONF_INSTALLATION_ID] = installation_id
                unique_id = installation_id
                await self.async_set_unique_id(unique_id)

                self._abort_if_unique_id_configured()
                title = ENTRY_TITLE_FORMAT.format(
                    installation_id=installation_id,
                    host=data[CONF_HOST],
                    port=data[CONF_PORT],
                )
                return self.async_create_entry(title=title, data=data)

        _LOGGER.debug("Showing form with errors: %s", errors)
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_ssdp(
        self, discovery_info: SsdpServiceInfo
    ) -> ConfigFlowResult:
        """Handle SSDP discovery."""
        hostname = urlparse(discovery_info.ssdp_location).hostname
        if not hostname:
            return self.async_abort(reason="cannot_connect")

        upnp = discovery_info.upnp
        installation_id = upnp.get("X_VrmPortalId")
        if not installation_id:
            return self.async_abort(reason="cannot_connect")

        self.hostname = hostname
        self.serial = upnp.get("serialNumber")
        self.installation_id = installation_id
        self.model_name = upnp.get("modelName")
        self.friendly_name = upnp.get("friendlyName")

        await self.async_set_unique_id(self.installation_id)
        self._abort_if_unique_id_configured()

        self.context["title_placeholders"] = {
            "name": self.friendly_name or self.hostname
        }

        # Verify connectivity before showing the confirmation dialog
        try:
            ssdp_conf = {
                CONF_HOST: self.hostname,
                CONF_PORT: DEFAULT_PORT,
                CONF_SERIAL: self.serial,
                CONF_INSTALLATION_ID: self.installation_id,
                CONF_MODEL: self.model_name,
            }
            await validate_input(ssdp_conf)
        except AuthenticationError:
            return await self.async_step_ssdp_auth()
        except CannotConnectError:
            return self.async_abort(reason="cannot_connect")
        except Exception:
            _LOGGER.exception(
                "Unexpected error validating SSDP discovery for Victron GX"
            )
            return self.async_abort(reason="unknown")

        return await self.async_step_ssdp_confirm()

    async def async_step_ssdp_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm SSDP discovered device."""
        assert self.hostname is not None
        assert self.installation_id is not None

        if user_input is not None:
            return self.async_create_entry(
                title=ENTRY_TITLE_FORMAT.format(
                    installation_id=self.installation_id,
                    host=self.hostname,
                    port=DEFAULT_PORT,
                ),
                data={
                    CONF_HOST: self.hostname,
                    CONF_PORT: DEFAULT_PORT,
                    CONF_SERIAL: self.serial,
                    CONF_INSTALLATION_ID: self.installation_id,
                    CONF_MODEL: self.model_name,
                },
            )

        self._set_confirm_only()
        return self.async_show_form(
            step_id="ssdp_confirm",
            description_placeholders={"name": self.friendly_name or self.hostname},
        )

    async def async_step_ssdp_auth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle SSDP auth when credentials are required."""
        assert self.hostname is not None
        assert self.installation_id is not None

        errors: dict[str, str] = {}

        if user_input is not None:
            ca_upload_id = user_input.pop(CONF_CA_CERT, None)
            _LOGGER.debug(
                "SSDP auth user input received: %s",
                async_redact_data(user_input, TO_REDACT),
            )
            data = await _async_finalize_config_data(
                self.hass,
                {
                    CONF_HOST: self.hostname,
                    CONF_PORT: DEFAULT_PORT,
                    CONF_SERIAL: self.serial,
                    CONF_INSTALLATION_ID: self.installation_id,
                    CONF_MODEL: self.model_name,
                    CONF_USERNAME: user_input.get(CONF_USERNAME) or None,
                    CONF_PASSWORD: user_input.get(CONF_PASSWORD) or None,
                    CONF_SSL: user_input.get(CONF_SSL, False),
                    CONF_VERIFY_SSL: user_input.get(CONF_VERIFY_SSL, False),
                    CONF_UPDATE_INTERVAL: user_input.get(CONF_UPDATE_INTERVAL),
                },
                ca_upload_id=ca_upload_id,
            )

            try:
                await validate_input(data)
                _LOGGER.debug("SSDP authentication successful")
            except AuthenticationError:
                _LOGGER.debug("Authentication failed during SSDP setup", exc_info=True)
                errors["base"] = "invalid_auth"
            except CannotConnectError:
                _LOGGER.debug("Cannot connect during SSDP setup", exc_info=True)
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during SSDP setup")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=ENTRY_TITLE_FORMAT.format(
                        installation_id=self.installation_id,
                        host=self.hostname,
                        port=DEFAULT_PORT,
                    ),
                    data=data,
                )

        return self.async_show_form(
            step_id="ssdp_auth",
            data_schema=self.add_suggested_values_to_schema(
                STEP_SSDP_AUTH_DATA_SCHEMA, user_input
            ),
            errors=errors,
            description_placeholders={CONF_HOST: self.hostname},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of a Victron GX device."""
        errors: dict[str, str] = {}
        reconfigure_entry = self._get_reconfigure_entry()

        if user_input is not None:
            ca_upload_id = user_input.get(CONF_CA_CERT)
            data = _apply_credential_updates(dict(reconfigure_entry.data), user_input)
            data = await _async_finalize_config_data(
                self.hass,
                data,
                ca_upload_id=ca_upload_id,
                existing_data=reconfigure_entry.data,
            )
            try:
                installation_id = await validate_input(data)
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during reconfiguration")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(installation_id)
                self._abort_if_unique_id_mismatch(reason="different_device")
                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    title=ENTRY_TITLE_FORMAT.format(
                        installation_id=installation_id,
                        host=user_input[CONF_HOST],
                        port=user_input[CONF_PORT],
                    ),
                    data=data,
                )

        suggested_values = {
            CONF_HOST: reconfigure_entry.data[CONF_HOST],
            CONF_PORT: reconfigure_entry.data[CONF_PORT],
            CONF_USERNAME: reconfigure_entry.data.get(CONF_USERNAME),
            CONF_SSL: reconfigure_entry.data.get(CONF_SSL, False),
            CONF_VERIFY_SSL: reconfigure_entry.data.get(CONF_VERIFY_SSL, False),
            CONF_UPDATE_INTERVAL: _suggested_update_interval(reconfigure_entry.data),
        }
        if user_input is not None:
            suggested_values.update(
                {key: value for key, value in user_input.items() if key != CONF_CA_CERT}
            )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, suggested_values
            ),
            errors=errors,
        )

    async def async_step_reauth(self, _: Mapping[str, Any]) -> ConfigFlowResult:
        """Handle reauthentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reauthentication confirmation."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            ca_upload_id = user_input.get(CONF_CA_CERT)
            updates: dict[str, Any] = {
                CONF_USERNAME: user_input.get(CONF_USERNAME) or None,
                CONF_SSL: user_input.get(
                    CONF_SSL, reauth_entry.data.get(CONF_SSL, False)
                ),
                CONF_VERIFY_SSL: user_input.get(
                    CONF_VERIFY_SSL, reauth_entry.data.get(CONF_VERIFY_SSL, False)
                ),
            }
            if user_input.get(CONF_PASSWORD):
                updates[CONF_PASSWORD] = user_input[CONF_PASSWORD]

            validation_data = await _async_finalize_config_data(
                self.hass,
                {**reauth_entry.data, **updates},
                ca_upload_id=ca_upload_id,
                existing_data=reauth_entry.data,
            )

            try:
                await validate_input(validation_data)
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during reauthentication")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data=validation_data,
                )

        suggested_values = {
            CONF_USERNAME: reauth_entry.data.get(CONF_USERNAME, None),
            CONF_SSL: reauth_entry.data.get(CONF_SSL, False),
            CONF_VERIFY_SSL: reauth_entry.data.get(CONF_VERIFY_SSL, False),
        }
        if user_input is not None:
            suggested_values.update(
                {key: value for key, value in user_input.items() if key != CONF_CA_CERT}
            )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                STEP_REAUTH_DATA_SCHEMA, suggested_values
            ),
            description_placeholders={CONF_HOST: reauth_entry.data[CONF_HOST]},
            errors=errors,
        )
