# Victron GX Hub

Home Assistant custom integration for Victron GX devices running Venus OS.

The integration connects to the GX device over local MQTT using
[`victron-mqtt`](https://pypi.org/project/victron-mqtt/) and creates Home
Assistant entities as Victron metrics are discovered.

## Features

- Local push integration over MQTT (`iot_class: local_push`)
- UI-based config flow
- SSDP discovery for GX devices with MQTT on LAN enabled
- Reauthentication and reconfiguration flows
- Device registry support, including parent/child device relationships
- Diagnostics with sensitive location data redacted
- Entity support for:
  - Binary sensors
  - Buttons
  - Device trackers
  - Numbers
  - Selects
  - Sensors
  - Switches
  - Time entities

## Requirements

- Home Assistant `2026.5.0` or newer for this development branch
- A Victron GX device with MQTT on LAN enabled
- Network access from Home Assistant to the GX device MQTT broker

The integration package installs `victron-mqtt==2026.7.6` through
`custom_components/victron_gx_hub/manifest.json`.

## Installation

### HACS (recommended)

1. Install [HACS](https://hacs.xyz/) if you do not already have it.
2. In HACS, add a custom repository:
   - Repository: `denys/victron-gx`
   - Category: Integration
3. Search for **Victron GX Hub** and download/install it.
4. Restart Home Assistant.

Or use this My Home Assistant link to add the custom repository:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=denys&repository=victron-gx&category=integration)

### Manual

Copy `custom_components/victron_gx_hub` into your Home Assistant
`custom_components` directory, then restart Home Assistant.

### Add the integration

After install and restart, add the integration from:

```text
Settings -> Devices & services -> Add integration -> Victron GX Hub
```

If SSDP discovery succeeds, Home Assistant can show the device automatically.

## Configuration

Manual setup asks for:

- Host, for example `venus.local` or the GX device IP address
- MQTT port, default `1883`
- Optional username and password
- SSL on/off
- Optional update interval in seconds

Discovered devices may also ask for credentials if the first connection attempt
requires authentication.

## Custom topic definitions

The integration ships an empty overlay file at
`custom_components/victron_gx_hub/victron_mqtt.json`. Edit that file to add or
change MQTT topic definitions without waiting for a `victron-mqtt` library
release.

Overlay entries use the same JSON shape as upstream's published dump. Each
entry is matched by `short_id`:

- Matching `short_id` replaces the library built-in in place
- Unknown `short_id` values are appended
- Topics not listed in the overlay are left untouched, including the
  `MetricKind.ATTRIBUTE` topics that populate device model, serial, firmware,
  and manufacturer

Copy topic or enum entries from the upstream
[`victron_mqtt.json`](https://github.com/tomer-w/victron_mqtt/blob/main/victron_mqtt.json)
dump, or generate one against the pinned library version:

```bash
python -m victron_mqtt.utils.dump_victron_mqtt out.json
```

Reload the config entry after editing the overlay so the new definitions are
applied before the hub connects.

## Development Setup

Run the bootstrap script from the repository root. It creates `.venv`, installs
dependencies, and registers git hooks:

```bash
scripts/setup-dev.sh
```

Activate the virtual environment for interactive work:

```bash
source .venv/bin/activate
```

Opening this repository in a dev container runs `scripts/setup-dev.sh`
automatically via `postCreateCommand`.

To pass environment variables into the Dev Container, copy `.env.example` to
`.env`, add `KEY=value` lines, then rebuild the container. Values from `.env`
are applied at container create time, so rebuild again after changing them.

## Quality Checks

Git commits run [pre-commit](https://pre-commit.com/) hooks for Ruff,
formatting, spelling, and tests. Run them manually with:

```bash
.venv/bin/pre-commit run --all-files
```

Run the test suite directly with:

```bash
.venv/bin/pytest tests/
```

Run tests with coverage:

```bash
.venv/bin/python -m pytest \
  --cov=custom_components/victron_gx_hub \
  --cov-report=term \
  tests/
```
