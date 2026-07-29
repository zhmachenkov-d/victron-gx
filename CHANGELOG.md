# Changelog

All notable changes to this project will be documented in this file.

## [1.2.1] - 2026-07-29

### Bug Fixes
- map runtime timers to duration sensors (#12)

## [1.2.0] - 2026-07-29

### Features

- add custom MQTT topic overlays (#10)

## [Unreleased]

### Features

- add custom `victron_mqtt.json` topic overlay loaded at setup time
- expose GX system runtime timers (time on grid, generator, inverting, inverter off)

### Fixed

- map system runtime timers to Duration device class with 2-decimal hour precision

## [1.1.0] - 2026-07-29

### Features

- add Realtime update interval option as the default (#7)
