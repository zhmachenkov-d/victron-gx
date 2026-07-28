"""Tests for Victron GX SSL context helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import ssl

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from homeassistant.const import CONF_SSL, CONF_VERIFY_SSL

from custom_components.victron_gx_hub.const import CONF_CA_CERT
from custom_components.victron_gx_hub.ssl_util import build_ssl_context


def _self_signed_ca_pem() -> str:
    """Return a short-lived self-signed CA certificate PEM."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-ca")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def test_build_ssl_context_returns_none_without_ssl() -> None:
    """Return None when SSL is disabled."""
    assert build_ssl_context({}) is None
    assert build_ssl_context({CONF_SSL: False}) is None


def test_build_ssl_context_defaults_to_unverified() -> None:
    """Build an unverified context when SSL is on and verify is off."""
    context = build_ssl_context({CONF_SSL: True})
    assert context is not None
    assert context.verify_mode == ssl.CERT_NONE
    assert context.check_hostname is False


def test_build_ssl_context_uses_system_cas_when_verifying() -> None:
    """Build a default verified context without a custom CA."""
    context = build_ssl_context({CONF_SSL: True, CONF_VERIFY_SSL: True})
    assert context is not None
    assert context.verify_mode == ssl.CERT_REQUIRED


def test_build_ssl_context_loads_uploaded_ca() -> None:
    """Load an uploaded CA PEM when verifying with ca_cert set."""
    context = build_ssl_context(
        {
            CONF_SSL: True,
            CONF_VERIFY_SSL: True,
            CONF_CA_CERT: _self_signed_ca_pem(),
        }
    )
    assert context is not None
    assert context.verify_mode == ssl.CERT_REQUIRED
