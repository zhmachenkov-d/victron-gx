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
