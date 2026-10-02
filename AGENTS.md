<!-- bmad:context -->
<!-- Verified 2026-10-02 against f099d192ab7c3a8176edc079310b7dcbbbf9ff0a. Managed by bmad-project-context; edits inside this block are replaced on refresh. Keep anything you want preserved outside the markers. -->

## victron-gx

Home Assistant custom integration for Victron GX over local MQTT (`victron-mqtt`). Domain vocabulary lives in `CONTEXT.md`; accepted design decisions in `docs/adr/`.

## Policy

- Never commit to `main`; open a PR instead (local hook also blocks commits on `main`).
- Use Conventional Commit subjects on every commit — release automation bumps from `feat` / `fix` / `refactor` / breaking markers only.
- Never hand-edit `custom_components/victron_gx_hub/manifest.json` `version` or `CHANGELOG.md` — the release workflow owns both.
- Never change the default TLS verify-off behavior without updating `docs/adr/0001-default-unverified-tls.md`.
- Never commit `.env` or Home Assistant runtime state under `config/`.

## Where things are

- Integration code: `custom_components/victron_gx_hub/`
- Domain terms (Installation, update interval, …): `CONTEXT.md` — follow its Avoid list
- Topic overlay / formulas: `victron_mqtt.json`, `topics.py`, `formulas.py`
- Local Home Assistant: `scripts/run.sh` (needs `.venv` from `scripts/setup-dev.sh`)

## Running and verifying

- Run `scripts/setup-dev.sh` before the first commit — Cursor's commit hook requires `.venv/bin/pre-commit`.
- Commits run the full pre-commit suite including pytest; if hooks rewrite files, stage them and retry the commit.
- Load the integration in Home Assistant with `scripts/run.sh`, not by inventing a separate `hass` invocation.
- CI also runs hassfest and HACS validation — local pre-commit does not cover those.

## Conventions that differ from defaults

- Config key is `update_interval` (default `"realtime"` → push-on-change); do not introduce `scan_interval` or treat polling as the default.
- Setup order is overlay → Hub → platforms → `hub.start()`; never start the hub before platforms register.
- Overlay matches by `short_id` (replace or append); a missing/bad overlay must not fail setup or wipe already-applied customs.
- Topic/enum/formula overlays mutate private `victron-mqtt` module state — keep changes behind `topics.py` / `formulas.py`.

## Known pitfalls

- Overlay `metric_type` / `metric_nature` for GX system runtime timers have been flipped repeatedly — prefer `DURATION` + `TOTAL_INCREASING` with the reboot-reset rationale already in recent history; do not "correct" them to `TIME` / `TOTAL` without evidence.

<!-- /bmad:context -->
