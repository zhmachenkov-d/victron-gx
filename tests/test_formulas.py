"""Tests for local victron_mqtt formula helpers."""

from __future__ import annotations

from types import SimpleNamespace

from victron_mqtt import _victron_formulas as library_formulas

from custom_components.victron_gx_hub.formulas import (
    FORMULA_SUM_REQUIRED,
    register_formulas,
    sum_required,
)


def test_sum_required_adds_dependency_values() -> None:
    """Sum all dependency values when every value is present."""
    depends_on = {
        "a": SimpleNamespace(value=12.5),
        "b": SimpleNamespace(value=7.3),
    }

    result = sum_required(depends_on, None)

    assert result == (19.8, None)


def test_sum_required_returns_none_when_any_value_missing() -> None:
    """Remain unavailable when any required dependency value is missing."""
    depends_on = {
        "a": SimpleNamespace(value=12.5),
        "b": SimpleNamespace(value=None),
    }

    assert sum_required(depends_on, None) is None


def test_register_formulas_exposes_sum_required() -> None:
    """Register the local sum formula on the library formulas module."""
    register_formulas()

    assert getattr(library_formulas, FORMULA_SUM_REQUIRED) is sum_required


def test_formula_topic_path_resolves_registered_sum_required() -> None:
    """Resolve the local formula the same way FormulaMetric looks up functions."""
    register_formulas()
    topic = f"$$func/vebus/{FORMULA_SUM_REQUIRED}"
    func_name = topic.rsplit("/", maxsplit=1)[-1]

    assert getattr(library_formulas, func_name) is sum_required
