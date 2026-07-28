"""SSL context helpers for Victron GX MQTT connections."""

from __future__ import annotations

import ssl
from typing import TYPE_CHECKING, Any

from homeassistant.const import CONF_SSL, CONF_VERIFY_SSL

from .const import CONF_CA_CERT

if TYPE_CHECKING:
    from collections.abc import Mapping


def build_ssl_context(config: Mapping[str, Any]) -> ssl.SSLContext | None:
    """Build an SSL context from entry config, or None when SSL is disabled.

    When SSL is enabled:
    - verify_ssl off (default): return an unverified client context
    - verify_ssl on with ca_cert: trust the uploaded PEM CA
    - verify_ssl on without ca_cert: use system CA store
    """
    if not config.get(CONF_SSL, False):
        return None

    if not config.get(CONF_VERIFY_SSL, False):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    ca_cert = config.get(CONF_CA_CERT)
    if ca_cert:
        return ssl.create_default_context(cadata=ca_cert)
    return ssl.create_default_context()
