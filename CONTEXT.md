# Victron GX Hub

Home Assistant integration for Victron GX installations connected over MQTT.

## Language

**Installation**:
A physical Victron GX setup identified by its installation ID and connected to one Home Assistant instance.
_Avoid_: Account, site

**Update interval**:
The cadence for hub metric updates for an Installation. Either a number of seconds, or an auto profile (`auto` / `auto_power_none`). When unset, the hub uses `auto`.
_Avoid_: Poll interval, update frequency, scan interval

**Integration**:
The Home Assistant package for Victron GX Installations (`victron_gx_hub`).
_Avoid_: component (when meaning the whole package)

**Custom repository**:
A GitHub repo users add manually in HACS (not in the default store).
_Avoid_: default repository
