#!/usr/bin/env bash

set -e

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$ROOT"

CONFIG_DIR="${ROOT}/config"
HASS="${ROOT}/.venv/bin/hass"
DEBUG_RUN_ID="${DEBUG_RUN_ID:-initial}"

# region agent log
debug_log() {
    local hypothesis_id="$1"
    local message="$2"
    local data_json="$3"
    python3 - "$hypothesis_id" "$message" "$data_json" "$DEBUG_RUN_ID" <<'PY'
import json
import sys
import time

hypothesis_id, message, data_json, run_id = sys.argv[1:]
payload = {
    "sessionId": "ed6a48",
    "runId": run_id,
    "hypothesisId": hypothesis_id,
    "location": "scripts/run.sh",
    "message": message,
    "data": json.loads(data_json),
    "timestamp": int(time.time() * 1000),
}
with open("/workspaces/victron-gx/.cursor/debug-ed6a48.log", "a", encoding="utf-8") as log_file:
    log_file.write(json.dumps(payload, separators=(",", ":")) + "\n")
PY
}
# endregion

# region agent log
debug_log "H1,H2,H5" "run script environment" "{\"root\":\"${ROOT}\",\"pwd\":\"${PWD}\",\"hass_bin\":\"${HASS}\",\"venv_exists\":$(if [[ -d "${ROOT}/.venv" ]]; then echo true; else echo false; fi),\"venv_hass_executable\":$(if [[ -x "${HASS}" ]]; then echo true; else echo false; fi),\"path_hass\":\"$(command -v hass || true)\"}"
# endregion

if [[ ! -x "${HASS}" ]]; then
    # region agent log
    debug_log "H1,H2" "hass executable missing" "{\"hass_bin\":\"${HASS}\",\"root\":\"${ROOT}\"}"
    # endregion
    echo "Home Assistant is not installed. Run scripts/setup-dev.sh first." >&2
    exit 1
fi

# Create config dir if not present
if [[ ! -d "${CONFIG_DIR}" ]]; then
    # region agent log
    debug_log "H3" "config directory missing; running ensure_config" "{\"config_dir\":\"${CONFIG_DIR}\"}"
    # endregion
    mkdir -p "${CONFIG_DIR}"
    if "${HASS}" --config "${CONFIG_DIR}" --script ensure_config; then
        :
    else
        status=$?
        # region agent log
        debug_log "H1,H2,H3" "ensure_config failed" "{\"exit_code\":${status},\"config_dir\":\"${CONFIG_DIR}\",\"hass_bin\":\"${HASS}\"}"
        # endregion
        exit "${status}"
    fi
else
    # region agent log
    debug_log "H3,H5" "config directory already exists; skipping ensure_config" "{\"config_dir\":\"${CONFIG_DIR}\",\"configuration_yaml_exists\":$(if [[ -f "${CONFIG_DIR}/configuration.yaml" ]]; then echo true; else echo false; fi)}"
    # endregion
fi

mkdir -p "${CONFIG_DIR}/custom_components"
INTEGRATION_LINK="${CONFIG_DIR}/custom_components/victon_gx_hub"
if [[ ! -e "${INTEGRATION_LINK}" ]]; then
    ln -sfn "${ROOT}/custom_components/victon_gx_hub" "${INTEGRATION_LINK}"
fi

# region agent log
debug_log "H4,H5" "before starting Home Assistant" "{\"hass_bin\":\"${HASS}\",\"repo_custom_component_exists\":$(if [[ -d "${ROOT}/custom_components/victon_gx_hub" ]]; then echo true; else echo false; fi),\"config_custom_component_exists\":$(if [[ -e "${INTEGRATION_LINK}" ]]; then echo true; else echo false; fi),\"configuration_yaml_exists\":$(if [[ -f "${CONFIG_DIR}/configuration.yaml" ]]; then echo true; else echo false; fi)}"
# endregion

# Start Home Assistant
if "${HASS}" --config "${CONFIG_DIR}" --debug; then
    :
else
    status=$?
    # region agent log
    debug_log "H1,H2,H4,H5" "Home Assistant failed" "{\"exit_code\":${status},\"hass_bin\":\"${HASS}\",\"config_custom_component_exists\":$(if [[ -e "${INTEGRATION_LINK}" ]]; then echo true; else echo false; fi)}"
    # endregion
    exit "${status}"
fi
