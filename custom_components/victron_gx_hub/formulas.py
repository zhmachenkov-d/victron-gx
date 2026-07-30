"""Local formula functions registered into victron_mqtt's formula resolver."""

from __future__ import annotations

from typing import TYPE_CHECKING

from victron_mqtt import _victron_formulas as library_formulas

if TYPE_CHECKING:
    from victron_mqtt.constants import FormulaTransientState
    from victron_mqtt.metric import Metric

FORMULA_SUM_REQUIRED = "sum_required"


def sum_required(
    depends_on: dict[str, Metric],
    _transient_state: FormulaTransientState | None,
) -> tuple[float, None] | None:
    """Sum all dependency metric values.

    Returns None (unavailable) when any dependency value is missing.
    """
    total = 0.0
    for metric in depends_on.values():
        if metric.value is None:
            return None
        total += float(metric.value)
    return total, None


def register_formulas() -> None:
    """Expose local formula functions on the library formulas module."""
    setattr(library_formulas, FORMULA_SUM_REQUIRED, sum_required)
