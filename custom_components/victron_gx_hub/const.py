"""Constants for the Victron GX integration."""

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME

DOMAIN = "victron_gx_hub"

CONF_INSTALLATION_ID = "installation_id"
CONF_SERIAL = "serial"
CONF_UPDATE_INTERVAL = "update_interval"
# Legacy key migrated to CONF_UPDATE_INTERVAL.
CONF_UPDATE_INTERVAL_SECONDS = "update_interval_seconds"
CONF_CA_CERT = "ca_cert"

# Maps to hub update_frequency_seconds=None (update on every value change).
UPDATE_FREQUENCY_REALTIME = "realtime"

DIAGNOSTICS_REDACT = frozenset(
    {
        CONF_USERNAME,
        CONF_PASSWORD,
        CONF_HOST,
        CONF_SERIAL,
        CONF_INSTALLATION_ID,
        CONF_CA_CERT,
    }
)

# Binary sensor enum ids must be "on" for on and "off" for off.
BINARY_SENSOR_ON_ID = "on"
BINARY_SENSOR_OFF_ID = "off"
