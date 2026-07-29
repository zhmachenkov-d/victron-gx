"""Load a custom victron_mqtt.json overlay over the library topic list."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from victron_mqtt import _victron_enums
from victron_mqtt._victron_topics import topics
from victron_mqtt.constants import (
    MetricKind,
    MetricNature,
    MetricType,
    RangeType,
    ValueType,
    VictronEnum,
)
from victron_mqtt.data_classes import (
    ProductCapabilityRef,
    TopicDependency,
    TopicDescriptor,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

OVERLAY_PATH = Path(__file__).parent / "victron_mqtt.json"

_ENUM_TYPES: dict[str, type] = {
    "MetricKind": MetricKind,
    "MetricNature": MetricNature,
    "MetricType": MetricType,
    "RangeType": RangeType,
    "ValueType": ValueType,
}

_builtin_topics_snapshot: list[TopicDescriptor] | None = None


def _read_overlay_file(path: Path) -> dict[str, Any] | None:
    """Read and parse the overlay JSON file.

    Returns None when the file is missing. Raises on unreadable or invalid JSON.
    """
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        msg = f"Overlay root must be an object, got {type(data).__name__}"
        raise TypeError(msg)
    return data


def _decode_enum_member(raw: str) -> Any:
    """Decode a dumped enum member string such as ``MetricKind.SENSOR``."""
    kind, name = raw.split(".", 1)
    return _ENUM_TYPES[kind][name]


def _decode_range_value(raw: Any) -> Any:
    """Decode min/max/step, including ProductCapabilityRef dicts."""
    if isinstance(raw, dict):
        return ProductCapabilityRef(**raw)
    return raw


def _decode_dependency(raw: Any) -> str | TopicDependency:
    """Decode a depends_on entry."""
    if isinstance(raw, dict):
        return TopicDependency(**raw)
    return raw


def _synthesize_enum(enum_dump: dict[str, Any]) -> type[VictronEnum]:
    """Build a VictronEnum subclass from an overlay enums section entry."""
    members = {
        entry["id"].upper(): (entry["value"], entry["id"], entry["name"])
        for entry in enum_dump["EnumValues"]
    }
    return VictronEnum(enum_dump["name"], members)


def _build_enum_map(
    enums_section: list[dict[str, Any]],
) -> dict[str, type[VictronEnum]]:
    """Resolve enum names to library classes or synthesized overlay enums."""
    enum_map: dict[str, type[VictronEnum]] = {}
    for enum_dump in enums_section:
        name = enum_dump["name"]
        library_enum = getattr(_victron_enums, name, None)
        if isinstance(library_enum, type) and issubclass(library_enum, VictronEnum):
            enum_map[name] = library_enum
        else:
            enum_map[name] = _synthesize_enum(enum_dump)
    return enum_map


def _decode_topic_entry(
    raw: Any, enum_map: dict[str, type[VictronEnum]]
) -> TopicDescriptor:
    """Validate and decode one overlay topic entry."""
    if not isinstance(raw, dict):
        msg = f"Topic entry must be an object, got {type(raw).__name__}"
        raise TypeError(msg)
    return _decode_topic(raw, enum_map)


def _decode_topic(
    raw: dict[str, Any], enum_map: dict[str, type[VictronEnum]]
) -> TopicDescriptor:
    """Decode one overlay topic entry into a TopicDescriptor."""
    data = dict(raw)
    data.pop("generic_name", None)
    data.pop("is_formula", None)

    for key in (
        "message_type",
        "metric_type",
        "metric_nature",
        "value_type",
        "min_max_range",
    ):
        value = data.get(key)
        if isinstance(value, str) and "." in value:
            data[key] = _decode_enum_member(value)

    for key in ("min", "max", "step"):
        if key in data:
            data[key] = _decode_range_value(data[key])

    if "depends_on" in data:
        data["depends_on"] = [_decode_dependency(item) for item in data["depends_on"]]

    enum_name = data.get("enum")
    if isinstance(enum_name, str):
        if enum_name not in enum_map:
            library_enum = getattr(_victron_enums, enum_name, None)
            if isinstance(library_enum, type) and issubclass(library_enum, VictronEnum):
                enum_map[enum_name] = library_enum
            else:
                msg = f"Unknown enum {enum_name!r}"
                raise KeyError(msg)
        data["enum"] = enum_map[enum_name]

    return TopicDescriptor(**data)


def _parse_overlay_topics(
    data: dict[str, Any],
) -> list[TopicDescriptor]:
    """Parse topic entries from overlay data, skipping malformed ones."""
    enums_section = data.get("enums") or []
    if not isinstance(enums_section, list):
        msg = "Overlay 'enums' must be a list"
        raise TypeError(msg)

    topics_section = data.get("topics") or []
    if not isinstance(topics_section, list):
        msg = "Overlay 'topics' must be a list"
        raise TypeError(msg)

    enum_map = _build_enum_map(enums_section)
    decoded: list[TopicDescriptor] = []
    for index, raw in enumerate(topics_section):
        try:
            decoded.append(_decode_topic_entry(raw, enum_map))
        except Exception:  # noqa: BLE001 - keep overlay resilient
            _LOGGER.warning(
                "Skipping malformed overlay topic at index %s",
                index,
                exc_info=True,
            )
    return decoded


def _merge_topics(
    builtins: list[TopicDescriptor], overlay: list[TopicDescriptor]
) -> tuple[list[TopicDescriptor], int, int]:
    """Merge overlay topics over builtins by short_id.

    Returns the merged list plus counts of overridden and added topics.
    """
    merged = list(builtins)
    index_by_short_id = {topic.short_id: index for index, topic in enumerate(merged)}
    overridden = 0
    added = 0
    for topic in overlay:
        existing_index = index_by_short_id.get(topic.short_id)
        if existing_index is None:
            index_by_short_id[topic.short_id] = len(merged)
            merged.append(topic)
            added += 1
        else:
            merged[existing_index] = topic
            overridden += 1
    return merged, overridden, added


def apply_topic_overlay(path: Path = OVERLAY_PATH) -> None:
    """Read ``path`` and mutate the library topics list in place."""
    global _builtin_topics_snapshot  # noqa: PLW0603 - module-level pristine cache

    if _builtin_topics_snapshot is None:
        _builtin_topics_snapshot = list(topics)

    try:
        data = _read_overlay_file(path)
    except Exception:  # noqa: BLE001 - never fail setup on overlay errors
        _LOGGER.warning(
            "Failed to read topic overlay at %s; leaving built-in topics intact",
            path,
            exc_info=True,
        )
        topics[:] = list(_builtin_topics_snapshot)
        return

    if data is None:
        topics[:] = list(_builtin_topics_snapshot)
        return

    try:
        overlay_topics = _parse_overlay_topics(data)
    except Exception:  # noqa: BLE001 - never fail setup on overlay errors
        _LOGGER.warning(
            "Failed to parse topic overlay at %s; leaving built-in topics intact",
            path,
            exc_info=True,
        )
        topics[:] = list(_builtin_topics_snapshot)
        return

    merged, overridden, added = _merge_topics(_builtin_topics_snapshot, overlay_topics)
    topics[:] = merged
    _LOGGER.info(
        "Applied topic overlay from %s (%s overridden, %s added)",
        path,
        overridden,
        added,
    )


async def async_apply_topic_overlay(
    hass: HomeAssistant, path: Path = OVERLAY_PATH
) -> None:
    """Apply the topic overlay off the event loop."""
    await hass.async_add_executor_job(apply_topic_overlay, path)
