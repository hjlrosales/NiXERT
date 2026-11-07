"""VES text/CSV input and reproducible curve export.

Supported input dialect (documented, not inferred)
--------------------------------------------------
Rows are whitespace/comma/semicolon separated with exactly three or four columns:

    AB/2, MN/2, resistance[, apparent_resistivity]

* ``AB/2`` and ``MN/2`` are Schlumberger half-spacings in metres.
* column 3 is the measured resistance in ohms.
* column 4, when present, is an already supplied apparent resistivity in
  ohm-metres; it is retained and never silently recomputed from resistance.

An optional single header row is recognized only when its first two cells name
the supported columns (``AB/2`` and ``MN/2``, case-insensitive, with ``AB2`` /
``AB`` and ``MN2`` / ``MN`` accepted as aliases). Every other non-comment row is
data: a malformed or non-numeric first row is an error, never a header. Rows
with more than four columns, non-finite values, non-positive values, or invalid
geometry are rejected with the source name and line number. No row is ever
silently dropped.
"""

from __future__ import annotations

import csv
import io
import math
import re
from pathlib import Path
from typing import Iterable

from nix_ert.ves.engine import VESPoint, VESError, ves_apparent_resistivity

_HEADER_AB2 = frozenset({"ab/2", "ab2", "ab", "half-spacing"})
_HEADER_MN2 = frozenset({"mn/2", "mn2", "mn"})
_MAX_COLUMNS = 4
_COLUMN_LABELS = ("AB/2", "MN/2", "resistance", "apparent resistivity")


def _location(source_name: str, line: int) -> str:
    return f"{source_name} line {line}"


def _positive(value: str, label: str, source_name: str, line: int) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise VESError(
            f"{_location(source_name, line)}: {label} must be numeric, found {value!r}"
        ) from exc
    if not math.isfinite(parsed):
        raise VESError(
            f"{_location(source_name, line)}: {label} must be finite, found {value!r}"
        )
    if parsed <= 0:
        raise VESError(
            f"{_location(source_name, line)}: {label} must be positive, found {parsed:g}"
        )
    return parsed


def _normalized(token: str) -> str:
    return token.strip().lower().replace("_", "/")


def _is_header(tokens: list[str]) -> bool:
    """Return True only for the recognized optional header row."""
    if len(tokens) < 2:
        return False
    return _normalized(tokens[0]) in _HEADER_AB2 and _normalized(tokens[1]) in _HEADER_MN2


def parse_ves(text: str, source_name: str = "<memory>") -> tuple[VESPoint, ...]:
    """Parse the documented VES row dialect into validated curve points.

    Raises :class:`VESError` naming the source and line for a malformed header,
    a malformed or malformed-width row, an extra column, a non-numeric or
    non-finite value, or invalid electrode geometry.
    """
    rows: list[tuple[int, list[str]]] = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(("#", ";", "!")):
            continue
        delimiter_values = re.split(r"[;,\s]+", line)
        tokens = [value.strip() for value in delimiter_values if value.strip()]
        if not tokens:
            continue
        rows.append((number, tokens))
    if not rows:
        raise VESError(f"{source_name}: no VES rows")
    if _is_header(rows[0][1]):
        rows = rows[1:]
    if not rows:
        raise VESError(f"{source_name}: no VES data rows after the header")

    points: list[VESPoint] = []
    for number, tokens in rows:
        if len(tokens) > _MAX_COLUMNS:
            raise VESError(
                f"{_location(source_name, number)}: expected at most {_MAX_COLUMNS} columns "
                f"({', '.join(_COLUMN_LABELS)}), found {len(tokens)}"
            )
        if len(tokens) < 3:
            raise VESError(
                f"{_location(source_name, number)}: VES row requires AB/2, MN/2, and resistance"
            )
        ab2 = _positive(tokens[0], "AB/2", source_name, number)
        mn2 = _positive(tokens[1], "MN/2", source_name, number)
        resistance = _positive(tokens[2], "resistance", source_name, number)
        rho = (
            _positive(tokens[3], "apparent resistivity", source_name, number)
            if len(tokens) == 4
            else None
        )
        try:
            calculated_rho = (
                rho if rho is not None
                else ves_apparent_resistivity(VESPoint(ab2, mn2, resistance=resistance))
            )
            point = VESPoint(ab2, mn2, apparent_resistivity=calculated_rho, resistance=resistance)
            # Validate geometry and the selected electrical value at import time.
            ves_apparent_resistivity(point)
        except VESError as exc:
            raise VESError(f"{_location(source_name, number)}: {exc}") from exc
        points.append(point)
    if not points:
        raise VESError(f"{source_name}: no VES data rows")
    return tuple(points)


def parse_ves_file(path: Path | str) -> tuple[VESPoint, ...]:
    path = Path(path)
    try:
        return parse_ves(path.read_text(encoding="utf-8-sig"), path.name)
    except OSError as exc:
        raise VESError(f"Unable to read {path}: {exc}") from exc


def ves_curve_csv(points: Iterable[VESPoint]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("AB/2", "MN/2", "resistance", "apparent_resistivity", "log10_AB/2", "log10_apparent_resistivity", "excluded"))
    for point in points:
        rho = ves_apparent_resistivity(point)
        writer.writerow((point.ab2, point.mn2, point.resistance or "", rho, math.log10(point.ab2), math.log10(rho), point.excluded))
    return output.getvalue()


def export_ves_csv(points: Iterable[VESPoint], path: Path | str) -> None:
    Path(path).write_text(ves_curve_csv(points), encoding="utf-8", newline="")
