"""Validated apparent-resistivity and geometric-factor calculations.

The general geometric factor follows the homogeneous half-space potential
relationship for point electrodes on a surface:

    V = (rho / 2*pi) * I * (1/r_AM - 1/r_BM - 1/r_AN + 1/r_BN)

Therefore K = 2*pi / reciprocal_sum and rho_a = K * V/I. Named array
shortcuts are provided where their geometry is unambiguous. Coordinates are
in the same distance unit as electrode spacing; rho_a has the corresponding
resistance*distance unit.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Sequence

from nix_ert.data.measurements import Measurement


class ArrayType(str, Enum):
    WENNER = "Wenner"
    WENNER_SCHLUMBERGER = "Wenner-Schlumberger"
    DIPOLE_DIPOLE = "Dipole-Dipole"
    POLE_POLE = "Pole-Pole"
    POLE_DIPOLE = "Pole-Dipole"
    MULTIPLE_GRADIENT = "Multiple Gradient"


class ResistivityError(ValueError):
    """Raised for invalid geometry or non-finite electrical inputs."""


def _finite(value: float, label: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ResistivityError(f"{label} must be finite")
    return value


def _distance(first: Sequence[float], second: Sequence[float]) -> float:
    distance = math.dist(first, second)
    if not math.isfinite(distance) or distance <= 0:
        raise ResistivityError("Electrode positions must be distinct")
    return distance


def geometric_factor(
    a: Sequence[float], b: Sequence[float], m: Sequence[float], n: Sequence[float],
    *, absolute: bool = False,
) -> float:
    """Return K for four point electrodes using the general half-space equation.

    `absolute=False` preserves the sign implied by current/potential electrode
    ordering. Use `absolute=True` only when the data convention defines a
    positive resistance magnitude independent of polarity.
    """
    points = [tuple(_finite(coordinate, "coordinate") for coordinate in point) for point in (a, b, m, n)]
    reciprocal_sum = (
        1 / _distance(points[0], points[2])
        - 1 / _distance(points[1], points[2])
        - 1 / _distance(points[0], points[3])
        + 1 / _distance(points[1], points[3])
    )
    if not math.isfinite(reciprocal_sum) or reciprocal_sum == 0:
        raise ResistivityError("Electrode geometry has zero or invalid geometric sensitivity")
    factor = 2 * math.pi / reciprocal_sum
    return abs(factor) if absolute else factor


def array_geometric_factor(
    array: ArrayType | str, spacing: float, level: float = 1.0,
) -> float:
    """Return standard K for common collinear array parameterizations.

    For Wenner, `level` is unused. For dipole-dipole, level is the integer n
    separating the dipoles. Wenner-Schlumberger uses n as its expansion factor.
    Pole arrays use the conventional collinear half-space formulas.
    """
    spacing = _finite(spacing, "spacing")
    level = _finite(level, "level")
    if spacing <= 0:
        raise ResistivityError("spacing must be positive")
    if level <= 0:
        raise ResistivityError("array level must be positive")
    try:
        array = ArrayType(array)
    except ValueError as exc:
        raise ResistivityError(f"unsupported array type: {array}") from exc
    if array is ArrayType.WENNER:
        return 2 * math.pi * spacing
    if array is ArrayType.DIPOLE_DIPOLE:
        return math.pi * spacing * level * (level + 1) * (level + 2)
    if array is ArrayType.WENNER_SCHLUMBERGER:
        return math.pi * spacing * level * (level + 1)
    if array is ArrayType.POLE_POLE:
        return 2 * math.pi * spacing
    if array is ArrayType.POLE_DIPOLE:
        return 2 * math.pi * spacing * level * (level + 1)
    raise ResistivityError(f"no single standard factor for {array.value}")


def apparent_resistivity(resistance: float, factor: float) -> float:
    """Calculate rho_a = measured resistance times geometric factor."""
    resistance = _finite(resistance, "resistance")
    factor = _finite(factor, "geometric factor")
    return resistance * factor


def apparent_resistivity_from_measurement(
    measurement: Measurement, factor: float | None = None,
) -> float:
    """Calculate rho_a for a measurement with an existing K.

    A factor must be supplied when the row does not already have apparent
    resistivity; geometry-to-factor lookup belongs to the caller because array
    metadata and coordinate conventions are survey-specific.
    """
    if measurement.resistance is None:
        if measurement.apparent_resistivity is None:
            raise ResistivityError("measurement has neither resistance nor apparent resistivity")
        return _finite(measurement.apparent_resistivity, "apparent resistivity")
    if factor is None:
        raise ResistivityError("geometric factor is required to calculate from resistance")
    return apparent_resistivity(measurement.resistance, factor)
