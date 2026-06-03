#!/usr/bin/env bash

set -e

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$ROOT"

CONFIG_DIR="${ROOT}/config"
HASS="${ROOT}/.venv/bin/hass"

if [[ ! -x "${HASS}" ]]; then
    echo "Home Assistant is not installed. Run scripts/setup-dev.sh first." >&2
    exit 1
fi

# Create config dir if not present
if [[ ! -d "${CONFIG_DIR}" ]]; then
    mkdir -p "${CONFIG_DIR}"
    if "${HASS}" --config "${CONFIG_DIR}" --script ensure_config; then
        :
    else
        status=$?
        exit "${status}"
    fi
fi

mkdir -p "${CONFIG_DIR}/custom_components"
INTEGRATION_LINK="${CONFIG_DIR}/custom_components/victron_gx_hub"
if [[ ! -e "${INTEGRATION_LINK}" ]]; then
    ln -sfn "${ROOT}/custom_components/victron_gx_hub" "${INTEGRATION_LINK}"
fi

# Start Home Assistant
if "${HASS}" --config "${CONFIG_DIR}" --debug; then
    :
else
    status=$?
    exit "${status}"
fi
