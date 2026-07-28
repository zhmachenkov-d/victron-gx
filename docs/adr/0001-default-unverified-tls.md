# ADR 0001: Default unverified TLS for Victron GX MQTT

## Status

Accepted

## Context

Victron GX devices commonly expose MQTT over TLS using self-signed certificates.
The `victron-mqtt` library does not verify certificates unless the caller supplies
an explicit `ssl_context`. Home Assistant core's `victron_gx` integration
likewise enables SSL without verification.

Users who terminate MQTT on a properly signed broker (or who want to pin a
custom CA) need an opt-in path to enable verification.

## Decision

When SSL is enabled for this integration:

1. Always pass an explicit `ssl_context` to `victron-mqtt`.
2. Default `verify_ssl` to off, using an unverified TLS client context so typical
   GX self-signed brokers keep working.
3. When `verify_ssl` is on, use `ssl.create_default_context()`. If the user
   uploaded a CA PEM, load it via `cadata`; otherwise trust the system CA store.

## Consequences

- Existing and typical GX setups continue to connect over SSL without extra
  certificate configuration.
- Verified TLS is available but must be opted into; misconfigured verify
  settings will surface as connection failures during config validation.
- CA PEM material is stored in config entry data and redacted from logs and
  diagnostics.
