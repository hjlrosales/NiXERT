"""Deterministic, non-destructive measurement quality control."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Iterable

from nix_ert.data.measurements import Measurement, MeasurementStatus
from nix_ert.data.project import ProjectStore


@dataclass(frozen=True)
class QCSettings:
    """Thresholds are explicit so QC runs can be reproduced and recorded."""

    extreme_log10_distance: float = 2.0
    noise_log10_distance: float = 0.75
    minimum_valid_resistivity: float = 0.0
    minimum_valid_resistance: float = 0.0


@dataclass(frozen=True)
class QCFlag:
    row_number: int
    reasons: tuple[str, ...]
    source_id: str | None = None


@dataclass(frozen=True)
class QCStatistics:
    total: int
    active: int
    excluded: int
    flagged: int
    invalid: int
    duplicate: int
    minimum_apparent_resistivity: float | None
    maximum_apparent_resistivity: float | None
    median_apparent_resistivity: float | None


@dataclass(frozen=True)
class _StatusChange:
    survey_id: str
    changes: tuple[tuple[str | None, int, MeasurementStatus, MeasurementStatus], ...]


class QCEngine:
    """Run QC rules and persist only user-approved status changes."""

    def __init__(self, store: ProjectStore, settings: QCSettings | None = None):
        self.store = store
        self.settings = settings or QCSettings()
        self._undo: list[_StatusChange] = []
        self._redo: list[_StatusChange] = []

    def inspect(self, survey_id: str) -> tuple[QCFlag, ...]:
        measurements = self.store.list_measurements(survey_id)
        if not measurements:
            return ()
        rho_values = [
            item.apparent_resistivity for item in measurements
            if item.apparent_resistivity is not None and item.apparent_resistivity > self.settings.minimum_valid_resistivity
        ]
        log_values = [math.log10(value) for value in rho_values if math.isfinite(value)]
        median_log = statistics.median(log_values) if log_values else None
        seen: dict[tuple[int, int, int, int], int] = {}
        flags: list[QCFlag] = []
        referenced = {
            electrode for item in measurements
            for electrode in (item.a, item.b, item.m, item.n)
        }
        missing = bool(referenced) and referenced != set(range(1, max(referenced) + 1))

        for item in measurements:
            reasons: list[str] = []
            rho = item.apparent_resistivity
            if rho is None or not math.isfinite(rho) or rho <= self.settings.minimum_valid_resistivity:
                reasons.append("invalid apparent resistivity")
            if item.resistance is not None and (
                not math.isfinite(item.resistance) or item.resistance <= self.settings.minimum_valid_resistance
            ):
                reasons.append("invalid resistance")
            key = (item.a, item.b, item.m, item.n)
            if key in seen:
                reasons.append(f"duplicate electrode tuple (row {seen[key]})")
            else:
                seen[key] = item.row_number
            if missing:
                reasons.append("missing electrode number in survey")
            if median_log is not None and rho is not None and rho > self.settings.minimum_valid_resistivity:
                distance = abs(math.log10(rho) - median_log)
                if distance >= self.settings.extreme_log10_distance:
                    reasons.append("extreme apparent resistivity")
                elif distance >= self.settings.noise_log10_distance:
                    reasons.append("potential resistivity noise")
            if reasons:
                flags.append(QCFlag(item.row_number, tuple(reasons), item.source_id))
        return tuple(flags)

    def statistics(self, survey_id: str) -> QCStatistics:
        measurements = self.store.list_measurements(survey_id)
        flags = {
            (flag.source_id, flag.row_number)
            for flag in self.inspect(survey_id)
        }
        values = [
            item.apparent_resistivity for item in measurements
            if item.apparent_resistivity is not None and math.isfinite(item.apparent_resistivity)
            and item.apparent_resistivity > self.settings.minimum_valid_resistivity
        ]
        tuples = [(item.a, item.b, item.m, item.n) for item in measurements]
        duplicate = len(tuples) - len(set(tuples))
        statuses = [item.status for item in measurements]
        invalid = sum(
            (item.source_id, item.row_number) in flags
            and (
                item.apparent_resistivity is None
                or not math.isfinite(item.apparent_resistivity)
                or item.apparent_resistivity <= self.settings.minimum_valid_resistivity
            )
            for item in measurements
        )
        return QCStatistics(
            total=len(measurements), active=sum(status == MeasurementStatus.ACTIVE for status in statuses),
            excluded=sum(status == MeasurementStatus.EXCLUDED for status in statuses),
            flagged=sum(status == MeasurementStatus.FLAGGED for status in statuses),
            invalid=invalid,
            duplicate=duplicate,
            minimum_apparent_resistivity=min(values) if values else None,
            maximum_apparent_resistivity=max(values) if values else None,
            median_apparent_resistivity=statistics.median(values) if values else None,
        )

    def flag_detected(self, survey_id: str) -> tuple[QCFlag, ...]:
        """Mark detected rows FLAGGED; no row is deleted or excluded."""
        flags = self.inspect(survey_id)
        measurements = self.store.list_measurements(survey_id)
        targets = {(flag.source_id, flag.row_number) for flag in flags}
        changes = tuple(
            (item.source_id, item.row_number, item.status, MeasurementStatus.FLAGGED)
            for item in measurements
            if (item.source_id, item.row_number) in targets
            and item.status != MeasurementStatus.FLAGGED
        )
        self._apply_changes(survey_id, changes)
        return tuple(flag for flag in self.inspect(survey_id) if (flag.source_id, flag.row_number) in targets)

    def _apply_changes(
        self,
        survey_id: str,
        changes: tuple[tuple[str | None, int, MeasurementStatus, MeasurementStatus], ...],
    ) -> None:
        if not changes:
            return
        self.store.set_measurement_status(
            survey_id,
            [
                (source_id, row, after) if source_id is not None else (row, after)
                for source_id, row, _, after in changes
            ],
        )
        self._undo.append(_StatusChange(survey_id, changes))
        self._redo.clear()

    def set_status(self, survey_id: str, row_numbers: Iterable[int], status: MeasurementStatus) -> None:
        rows = set(row_numbers)
        measurements = self.store.list_measurements(survey_id)
        selected = [item for item in measurements if item.row_number in rows]
        source_ids_by_row: dict[int, set[str | None]] = {}
        for item in selected:
            source_ids_by_row.setdefault(item.row_number, set()).add(item.source_id)
        ambiguous = [row for row, source_ids in source_ids_by_row.items() if len(source_ids) > 1]
        if ambiguous:
            raise ValueError(
                "measurement row numbers are ambiguous across imported sources: "
                + ", ".join(str(row) for row in sorted(ambiguous))
            )
        changes = tuple(
            (item.source_id, item.row_number, item.status, status)
            for item in selected if item.status != status
        )
        if not changes:
            return
        self._apply_changes(survey_id, changes)

    def _change_matching(self, survey_id: str, rows: set[int], status: MeasurementStatus) -> tuple[QCFlag, ...]:
        self.set_status(survey_id, rows, status)
        return tuple(flag for flag in self.inspect(survey_id) if flag.row_number in rows)

    def undo(self) -> bool:
        if not self._undo:
            return False
        action = self._undo.pop()
        self.store.set_measurement_status(
            action.survey_id,
            [
                (source_id, row, before) if source_id is not None else (row, before)
                for source_id, row, before, _ in action.changes
            ],
        )
        self._redo.append(action)
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        action = self._redo.pop()
        self.store.set_measurement_status(
            action.survey_id,
            [
                (source_id, row, after) if source_id is not None else (row, after)
                for source_id, row, _, after in action.changes
            ],
        )
        self._undo.append(action)
        return True
