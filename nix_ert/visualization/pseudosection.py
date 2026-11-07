"""Transparent ERT pseudosection point generation and CSV export."""

from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from nix_ert.data.measurements import Measurement, MeasurementStatus


class PseudosectionError(ValueError):
    """Raised for invalid pseudosection inputs."""


@dataclass(frozen=True)
class PseudosectionPoint:
    row_number: int
    x: float
    pseudo_depth: float
    apparent_resistivity: float
    status: MeasurementStatus
    a: int
    b: int
    m: int
    n: int

    @property
    def display_log10(self) -> float:
        return math.log10(self.apparent_resistivity)


def _coordinate(electrodes: Sequence[float], number: int) -> float:
    if number <= 0 or number > len(electrodes):
        raise PseudosectionError(f"electrode {number} has no coordinate")
    value = float(electrodes[number - 1])
    if not math.isfinite(value):
        raise PseudosectionError(f"electrode {number} coordinate is not finite")
    return value


def _pseudo_depth(a: float, b: float, m: float, n: float) -> float:
    """Use the median current/potential separation as a display depth proxy.

    This is not inversion depth and must not be used as a subsurface model.
    """
    separations = sorted((abs(m - a), abs(n - a), abs(m - b), abs(n - b)))
    return max(separations[1], separations[2]) * 0.5


def build_pseudosection(
    measurements: Iterable[Measurement], electrodes: Sequence[float], *, include_excluded: bool = False,
) -> tuple[PseudosectionPoint, ...]:
    """Build display points from electrode x coordinates and apparent rho."""
    points: list[PseudosectionPoint] = []
    for item in measurements:
        if item.status == MeasurementStatus.EXCLUDED and not include_excluded:
            continue
        rho = item.apparent_resistivity
        if rho is None or not math.isfinite(rho) or rho <= 0:
            continue
        positions = tuple(_coordinate(electrodes, number) for number in (item.a, item.b, item.m, item.n))
        points.append(
            PseudosectionPoint(
                row_number=item.row_number,
                x=sum(positions) / 4,
                pseudo_depth=_pseudo_depth(*positions),
                apparent_resistivity=rho,
                status=item.status,
                a=item.a, b=item.b, m=item.m, n=item.n,
            )
        )
    return tuple(points)


def pseudosection_csv(points: Iterable[PseudosectionPoint]) -> str:
    """Return a stable CSV suitable for reproducible exports."""
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("row_number", "x", "pseudo_depth", "apparent_resistivity", "log10_apparent_resistivity", "status", "A", "B", "M", "N"))
    for point in points:
        writer.writerow((point.row_number, point.x, point.pseudo_depth, point.apparent_resistivity, point.display_log10, point.status.value, point.a, point.b, point.m, point.n))
    return output.getvalue()


def export_pseudosection_csv(points: Iterable[PseudosectionPoint], path: Path | str) -> None:
    Path(path).write_text(pseudosection_csv(points), encoding="utf-8", newline="")
