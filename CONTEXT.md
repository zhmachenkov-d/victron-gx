# Victron GX Hub

Home Assistant integration for Victron GX installations connected over MQTT.

## Language

**Installation**:
A physical Victron GX setup identified by its installation ID and connected to one Home Assistant instance.
_Avoid_: Account, site

**Update interval**:
The cadence for hub metric updates for an Installation. Either a number of seconds, or an auto profile (`auto` / `auto_power_none`). When unset, the hub uses `auto`.
_Avoid_: Poll interval, update frequency, scan interval
