"""Tests for custom victron_mqtt.json topic overlay loading."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from victron_mqtt._victron_topics import topics
from victron_mqtt.constants import (
    MetricKind,
    MetricNature,
    MetricType,
    ValueType,
    VictronEnum,
)

from custom_components.victron_gx_hub import topics as topics_module

if TYPE_CHECKING:
    from pathlib import Path

    from homeassistant.core import HomeAssistant

ATTRIBUTE_TOPIC_COUNT = 11
OVERRIDE_PRECISION = 7
APPEND_PRECISION = 3
TIMER_PRECISION = 2


@pytest.fixture(autouse=True)
def restore_library_topics() -> None:
    """Snapshot and restore the shared library topics list around each test."""
    snapshot = list(topics)
    previous_builtin_snapshot = topics_module._builtin_topics_snapshot  # noqa: SLF001
    topics_module._builtin_topics_snapshot = None  # noqa: SLF001
    yield
    topics[:] = snapshot
    topics_module._builtin_topics_snapshot = previous_builtin_snapshot  # noqa: SLF001


def _write_overlay(
    path: Path,
    *,
    topics_data: list[dict[str, Any]],
    enums: list[dict[str, Any]] | None = None,
) -> Path:
    path.write_text(
        json.dumps(
            {
                "SchemaVersion": "1.0.0",
                "Comment": "test overlay",
                "topics": topics_data,
                "enums": enums or [],
            }
        ),
        encoding="utf-8",
    )
    return path


def _sensor_topic(short_id: str, name: str, **overrides: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "topic": "N/{installation_id}/battery/{device_id}/Custom",
        "message_type": "MetricKind.SENSOR",
        "short_id": short_id,
        "name": name,
        "unit_of_measurement": None,
        "metric_type": "MetricType.NONE",
        "metric_nature": "MetricNature.NONE",
        "value_type": "ValueType.FLOAT",
        "precision": 1,
        "enum": None,
        "min_max_range": "RangeType.STATIC",
        "min": None,
        "max": None,
        "step": None,
        "is_adjustable_suffix": None,
        "output_type": None,
        "labels": None,
        "key_values": {},
        "experimental": False,
        "depends_on": [],
        "generic_name": name,
        "is_formula": False,
        "main_topic": False,
        "hidden": False,
        "sub_device_key": None,
    }
    entry.update(overrides)
    if entry.get("enum") is not None:
        entry["value_type"] = "ValueType.ENUM"
        entry["metric_type"] = "MetricType.ENUM"
        entry["precision"] = None
    return entry


async def test_overlay_overrides_existing_short_id(
    hass: HomeAssistant, tmp_path: Path
) -> None:
    """Override an existing short_id without changing the topic list length."""
    original = next(
        topic for topic in topics if topic.message_type != MetricKind.ATTRIBUTE
    )
    original_length = len(topics)
    overlay_path = _write_overlay(
        tmp_path / "victron_mqtt.json",
        topics_data=[
            _sensor_topic(
                original.short_id,
                "Overlay renamed metric",
                topic=original.topic,
                precision=OVERRIDE_PRECISION,
            )
        ],
    )

    await topics_module.async_apply_topic_overlay(hass, overlay_path)

    assert len(topics) == original_length
    updated = next(topic for topic in topics if topic.short_id == original.short_id)
    assert updated.name == "Overlay renamed metric"
    assert updated.precision == OVERRIDE_PRECISION


async def test_overlay_appends_new_short_id(
    hass: HomeAssistant, tmp_path: Path
) -> None:
    """Append a topic whose short_id is not present in the built-ins."""
    original_length = len(topics)
    overlay_path = _write_overlay(
        tmp_path / "victron_mqtt.json",
        topics_data=[_sensor_topic("custom_overlay_metric", "Custom overlay metric")],
    )

    await topics_module.async_apply_topic_overlay(hass, overlay_path)

    assert len(topics) == original_length + 1
    assert topics[-1].short_id == "custom_overlay_metric"
    assert topics[-1].name == "Custom overlay metric"


async def test_overlay_preserves_attribute_topics(
    hass: HomeAssistant, tmp_path: Path
) -> None:
    """ATTRIBUTE topics excluded from upstream dumps must survive the merge."""
    attribute_keys = {
        (topic.topic, topic.short_id)
        for topic in topics
        if topic.message_type == MetricKind.ATTRIBUTE
    }
    assert len(attribute_keys) == ATTRIBUTE_TOPIC_COUNT
    overlay_path = _write_overlay(
        tmp_path / "victron_mqtt.json",
        topics_data=[_sensor_topic("custom_overlay_metric", "Custom overlay metric")],
    )

    await topics_module.async_apply_topic_overlay(hass, overlay_path)

    preserved = [
        topic for topic in topics if topic.message_type == MetricKind.ATTRIBUTE
    ]
    assert len(preserved) == ATTRIBUTE_TOPIC_COUNT
    assert {(topic.topic, topic.short_id) for topic in preserved} == attribute_keys


async def test_overlay_synthesizes_enum_from_file(
    hass: HomeAssistant, tmp_path: Path
) -> None:
    """Resolve an enum defined only in the overlay enums section."""
    overlay_path = _write_overlay(
        tmp_path / "victron_mqtt.json",
        topics_data=[
            _sensor_topic(
                "custom_enum_metric",
                "Custom enum metric",
                enum="OverlayOnlyMode",
            )
        ],
        enums=[
            {
                "name": "OverlayOnlyMode",
                "EnumValues": [
                    {"id": "off", "name": "Off", "value": 0},
                    {"id": "on", "name": "On", "value": 1},
                ],
            }
        ],
    )

    await topics_module.async_apply_topic_overlay(hass, overlay_path)

    custom = next(topic for topic in topics if topic.short_id == "custom_enum_metric")
    assert custom.enum is not None
    assert custom.enum.__name__ == "OverlayOnlyMode"
    assert issubclass(custom.enum, VictronEnum)
    assert custom.enum.from_code(1).string == "On"


async def test_overlay_skips_malformed_entries(
    hass: HomeAssistant, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Skip malformed entries while still applying valid siblings."""
    original_length = len(topics)
    overlay_path = _write_overlay(
        tmp_path / "victron_mqtt.json",
        topics_data=[
            {"short_id": "broken"},
            _sensor_topic("custom_overlay_metric", "Custom overlay metric"),
        ],
    )

    with caplog.at_level("WARNING"):
        await topics_module.async_apply_topic_overlay(hass, overlay_path)

    assert len(topics) == original_length + 1
    assert any(topic.short_id == "custom_overlay_metric" for topic in topics)
    assert "Skipping malformed overlay topic at index 0" in caplog.text


async def test_overlay_missing_file_is_noop(
    hass: HomeAssistant, tmp_path: Path
) -> None:
    """A missing overlay file leaves the built-in topic list unchanged."""
    snapshot = list(topics)
    missing = tmp_path / "does-not-exist.json"

    await topics_module.async_apply_topic_overlay(hass, missing)

    assert topics == snapshot


async def test_overlay_apply_twice_is_idempotent(
    hass: HomeAssistant, tmp_path: Path
) -> None:
    """Re-applying the same overlay does not duplicate appended topics."""
    overlay_path = _write_overlay(
        tmp_path / "victron_mqtt.json",
        topics_data=[
            _sensor_topic(
                "custom_overlay_metric",
                "Custom overlay metric",
                precision=APPEND_PRECISION,
            )
        ],
    )

    await topics_module.async_apply_topic_overlay(hass, overlay_path)
    first_length = len(topics)
    first_custom = next(
        topic for topic in topics if topic.short_id == "custom_overlay_metric"
    )

    await topics_module.async_apply_topic_overlay(hass, overlay_path)

    assert len(topics) == first_length
    customs = [topic for topic in topics if topic.short_id == "custom_overlay_metric"]
    assert len(customs) == 1
    assert customs[0].precision == first_custom.precision == APPEND_PRECISION


async def test_overlay_unreadable_file_leaves_builtins(
    hass: HomeAssistant, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """An invalid overlay file logs a warning and leaves topics unchanged."""
    snapshot = list(topics)
    overlay_path = tmp_path / "victron_mqtt.json"
    overlay_path.write_text("{not-json", encoding="utf-8")

    with caplog.at_level("WARNING"):
        await topics_module.async_apply_topic_overlay(hass, overlay_path)

    assert topics == snapshot
    assert "Failed to read topic overlay" in caplog.text


async def test_shipped_overlay_exposes_system_runtime_timers(
    hass: HomeAssistant,
) -> None:
    """Load the production overlay and verify the four GX runtime timers."""
    expected = {
        "system_timers_time_on_grid": (
            "N/{installation_id}/system/{device_id}/Timers/TimeOnGrid",
            "Time on grid",
        ),
        "system_timers_time_on_generator": (
            "N/{installation_id}/system/{device_id}/Timers/TimeOnGenerator",
            "Time on generator",
        ),
        "system_timers_time_on_inverter": (
            "N/{installation_id}/system/{device_id}/Timers/TimeOnInverter",
            "Time inverting",
        ),
        "system_timers_time_off": (
            "N/{installation_id}/system/{device_id}/Timers/TimeOff",
            "Time inverter off",
        ),
    }

    await topics_module.async_apply_topic_overlay(hass)

    for short_id, (topic_path, name) in expected.items():
        timer = next(topic for topic in topics if topic.short_id == short_id)
        assert timer.topic == topic_path
        assert timer.name == name
        assert timer.generic_name == name
        assert timer.message_type == MetricKind.SENSOR
        assert timer.metric_type == MetricType.DURATION
        assert timer.metric_nature == MetricNature.TOTAL
        assert timer.value_type == ValueType.INT_SECONDS_TO_HOURS
        assert timer.precision == TIMER_PRECISION
        assert timer.unit_of_measurement == "h"


async def test_shipped_overlay_exposes_ac_input_1_energy_formula(
    hass: HomeAssistant,
) -> None:
    """Load the production overlay and verify the AC input 1 energy formula."""
    await topics_module.async_apply_topic_overlay(hass)

    formula = next(
        topic for topic in topics if topic.short_id == "vebus_energy_ac_in1_total"
    )
    assert formula.topic == "$$func/vebus/sum_required"
    assert formula.name == "AC input 1 energy"
    assert formula.generic_name == "AC input 1 energy"
    assert formula.message_type == MetricKind.SENSOR
    assert formula.metric_type == MetricType.ENERGY
    assert formula.metric_nature == MetricNature.TOTAL
    assert formula.value_type == ValueType.FLOAT
    assert formula.precision == 1
    assert formula.unit_of_measurement == "kWh"
    assert formula.is_formula is True
    assert formula.hidden is False
    assert formula.depends_on == [
        "vebus_energy_ac_in1_to_ac_out",
        "vebus_energy_ac_in1_to_inverter",
    ]

    # Source path sensors remain visible in the library topic list.
    for short_id in (
        "vebus_energy_ac_in1_to_ac_out",
        "vebus_energy_ac_in1_to_inverter",
    ):
        source = next(topic for topic in topics if topic.short_id == short_id)
        assert source.hidden is False
        assert source.is_formula is False


async def test_failed_overlay_preserves_active_custom_topics(
    hass: HomeAssistant, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A later failed or missing overlay must not strip an active custom topic."""
    valid_path = _write_overlay(
        tmp_path / "valid.json",
        topics_data=[_sensor_topic("custom_overlay_metric", "Custom overlay metric")],
    )
    await topics_module.async_apply_topic_overlay(hass, valid_path)
    assert any(topic.short_id == "custom_overlay_metric" for topic in topics)
    active_snapshot = list(topics)

    missing_path = tmp_path / "missing.json"
    await topics_module.async_apply_topic_overlay(hass, missing_path)
    assert topics == active_snapshot

    bad_json_path = tmp_path / "bad.json"
    bad_json_path.write_text("{not-json", encoding="utf-8")
    with caplog.at_level("WARNING"):
        await topics_module.async_apply_topic_overlay(hass, bad_json_path)
    assert topics == active_snapshot
    assert "Failed to read topic overlay" in caplog.text

    bad_structure_path = tmp_path / "bad_structure.json"
    bad_structure_path.write_text(
        json.dumps({"SchemaVersion": "1.0.0", "topics": "not-a-list", "enums": []}),
        encoding="utf-8",
    )
    with caplog.at_level("WARNING"):
        await topics_module.async_apply_topic_overlay(hass, bad_structure_path)
    assert topics == active_snapshot
    assert "Failed to parse topic overlay" in caplog.text
