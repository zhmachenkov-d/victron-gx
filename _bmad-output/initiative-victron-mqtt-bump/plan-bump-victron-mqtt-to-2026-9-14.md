---
title: 'Bump victron-mqtt to 2026.9.14'
type: 'chore'
ticket: ''
created: '2026-10-02'
status: 'built'
baseline_revision: '3726bb8762319e18adefe7abcf24b500a24f3db8'
route: 'oneshot'
route_source: 'auto'
review: 'quick'
review_source: 'pinned'
lenses_ran: ['quick']
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The integration pins `victron-mqtt==2026.9.5`, but newer library releases exist through `2026.9.14`. From `2026.9.6`, Hub dropped `model_name` and `serial` constructor kwargs; keeping the old pin (or bumping without call-site fixes) leaves CI/runtime incompatible with current library APIs.

**Approach:** Pin `victron-mqtt==2026.9.14` in the three versioned locations, stop passing removed Hub kwargs while retaining `CONF_MODEL` / `CONF_SERIAL` on the config entry for Home Assistant device metadata, and update tests that assert those kwargs.

</frozen-after-approval>

## Implementation Notes

Oneshot: three pin strings plus mechanical removal of two Hub kwargs and matching test assertions (~20–40 LOC, ≤5 files of real change). Library changelog between 9.5→9.14 is mostly docs/MQTT internals; the only breaking call-site impact for this repo is Hub `__init__` dropping `model_name` and `serial`.

Pin targets (all `2026.9.5` → `2026.9.14`):
- `requirements.txt` L3
- `custom_components/victron_gx_hub/manifest.json` `requirements[0]` (do **not** edit `"version"`)
- `README.md` L33

Call sites to drop kwargs only:
- `custom_components/victron_gx_hub/hub.py` VictronVenusHub(...)
- `custom_components/victron_gx_hub/config_flow.py` VictronVenusHub(...)

Tests asserting `kwargs["model_name"]` / related: `tests/test_hub.py`, `tests/test_config_flow.py`.

Decisions / surprises while implementing:
- Also updated `_synthesize_enum` in `topics.py` for VictronEnum’s new required `description` member field (fallback to `name` when overlay omits it).
- WritableMetric fakes in platform tests needed `short_id` on `_descriptor` because `Metric.generic_short_id` now reads `self._descriptor.short_id` instead of `_generic_short_id`.
- Removed unused `CONF_MODEL` / `CONF_SERIAL` imports from `hub.py`; config entry still stores model/serial for HA metadata.
- Quick review found missing TopicDescriptor `description` would assert-fail in `Metric.phase2_init`; added descriptions to shipped `victron_mqtt.json` and a decode-time fallback.
- Verification: full pytest suite 158 passed against `victron-mqtt==2026.9.14`.

## Plan Change Log

## Review Triage Log

- 2026-10-02 quick: 2 findings
  - high/patch — shipped overlay topics lacked `description`; `Metric.phase2_init` asserts it. Fixed by adding descriptions to `victron_mqtt.json` and defaulting missing `description` to `name`/`short_id` in `_decode_topic`.
  - high/patch — same root cause for replace-by-`short_id` wiping library descriptions to `None`. Same decode fallback.

## Verification

**Commands:**
- `rg -n 'victron-mqtt==' requirements.txt custom_components/victron_gx_hub/manifest.json README.md` -- expected: only `2026.9.14`
- `rg -n 'model_name=|serial=' custom_components/victron_gx_hub/hub.py custom_components/victron_gx_hub/config_flow.py` -- expected: no Hub constructor kwargs
- `.venv/bin/pytest` (or project’s usual pytest via pre-commit) -- expected: pass
