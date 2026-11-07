"""Domain models for imported resistivity measurements."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class MeasurementStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXCLUDED = "EXCLUDED"
    FLAGGED = "FLAGGED"


@dataclass(frozen=True)
class Electrode:
    number: int
    x: float
    y: float = 0.0
    elevation: float | None = None


@dataclass(frozen=True)
class Measurement:
    """A non-destructive imported datum.

    `resistance` is optional because some exports provide apparent resistivity
    directly. The importer never derives one from the other without an
    explicitly validated geometric-factor processor.
    """

    row_number: int
    a: int
    b: int
    m: int
    n: int
    apparent_resistivity: float | None = None
    resistance: float | None = None
    current: float | None = None
    voltage: float | None = None
    measurement_index: int | None = None
    status: MeasurementStatus = MeasurementStatus.ACTIVE
    quality: str | None = None
    extra: dict[str, Any] | None = None
    source_id: str | None = None


@dataclass(frozen=True)
class ImportedDataset:
    source_name: str
    data_count: int
    electrode_spacing: float
    array_type: str
    measurements: tuple[Measurement, ...]
    electrodes: tuple[Electrode, ...]
    header_lines: tuple[str, ...] = ()
    topography: tuple[tuple[float, float], ...] = ()

    @property
    def invalid_measurement_count(self) -> int:
        return sum(
            1 for measurement in self.measurements
            if measurement.apparent_resistivity is not None
            and measurement.apparent_resistivity <= 0
        )
