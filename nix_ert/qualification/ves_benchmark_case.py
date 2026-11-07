"""Build a benchmark case payload from the documented NiX VES text/CSV dialect.

A VES benchmark case needs the sounding the engine was asked to invert: the
Schlumberger half-spacings and the apparent resistivity at each spacing. Such a
sounding already exists in the text/CSV dialect documented in
:mod:`nix_ert.ves.data`, so this module turns that file into a
``benchmark-case-v1`` payload instead of requiring hand-written JSON.

It is a converter, not evidence: it reads that dialect through
:func:`nix_ert.ves.data.parse_ves_file`, refuses anything it cannot state
unambiguously, and never invents a value.

The dialect states, per row, ``AB/2, MN/2, resistance[, apparent_resistivity]``.
A supplied fourth column is carried through unchanged; when it is absent the
documented Schlumberger geometric factor derives the apparent resistivity from
the measured resistance. Both the resistance and the resulting apparent
resistivity are written to the case, so the payload never hides which quantity
was measured and which was derived. The dialect carries no exclusion marker, so
every converted point is active; nothing is marked excluded on the operator's
behalf.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from nix_ert.ves.data import parse_ves_file
from nix_ert.ves.engine import VESError, VESPoint, ves_apparent_resistivity


CASE_DOMAIN = "VES"
"""A VES sounding is a single 1D curve, so the domain is VES."""

CASE_FORMAT_VERSION = "benchmark-case-v1"


class VESBenchmarkCaseError(ValueError):
    """Raised when a VES file cannot become an unambiguous benchmark case."""


@dataclass(frozen=True)
class VESBenchmarkCase:
    """A converted VES sounding: the payload plus the points it was built from."""

    payload: Mapping[str, object]
    points: tuple[VESPoint, ...]
    source_path: str

    def to_payload(self) -> dict[str, object]:
        return {str(key): value for key, value in self.payload.items()}

    def to_json(self) -> str:
        import json

        return json.dumps(self.to_payload(), sort_keys=True, indent=2, default=str)


def _apparent_resistivity(point: VESPoint, index: int, source_name: str) -> float:
    try:
        value = float(ves_apparent_resistivity(point))
    except (VESError, TypeError, ValueError) as exc:
        raise VESBenchmarkCaseError(
            f"{source_name} point {index} has no certified apparent resistivity: {exc}"
        ) from exc
    if not math.isfinite(value) or value <= 0:
        raise VESBenchmarkCaseError(
            f"{source_name} point {index} has no usable apparent resistivity; a value "
            "that is not finite and positive cannot be included in or dropped from a "
            "benchmark case without changing which observations the reference matches"
        )
    return value


def build_ves_benchmark_case(path: Path | str, protocol_id: str) -> VESBenchmarkCase:
    """Convert one VES text/CSV sounding into a frozen benchmark case payload."""
    if not str(protocol_id).strip():
        raise VESBenchmarkCaseError("a protocol ID is required to bind the case")
    source_path = Path(path)
    try:
        points = parse_ves_file(source_path)
    except VESError as exc:
        raise VESBenchmarkCaseError(str(exc)) from exc
    if not points:
        raise VESBenchmarkCaseError(f"{source_path.name} contains no VES points")

    records: list[dict[str, object]] = []
    for index, point in enumerate(points, start=1):
        records.append(
            {
                "ab2": float(point.ab2),
                "mn2": float(point.mn2),
                "apparent_resistivity": _apparent_resistivity(point, index, source_path.name),
                "resistance": None if point.resistance is None else float(point.resistance),
                "excluded": bool(point.excluded),
            }
        )
    if not any(not record["excluded"] for record in records):
        raise VESBenchmarkCaseError(
            f"{source_path.name} has no active VES point; a case with no active "
            "observation cannot be executed"
        )

    payload: dict[str, object] = {
        "protocol_id": str(protocol_id),
        "domain": CASE_DOMAIN,
        "case_format_version": CASE_FORMAT_VERSION,
        "points": records,
    }
    return VESBenchmarkCase(payload=payload, points=points, source_path=str(source_path))


def describe_ves_case(case: VESBenchmarkCase) -> dict[str, object]:
    """Return the facts a case was derived from, for operator review."""
    active = [point for point in case.points if not point.excluded]
    resistivities = [float(ves_apparent_resistivity(point)) for point in active]
    return {
        "source": case.source_path,
        "domain": CASE_DOMAIN,
        "point_count": len(case.points),
        "active_point_count": len(active),
        "excluded_point_count": len(case.points) - len(active),
        "ab2_range": [min(point.ab2 for point in active), max(point.ab2 for point in active)],
        "mn2_range": [min(point.mn2 for point in active), max(point.mn2 for point in active)],
        "apparent_resistivity_range": [min(resistivities), max(resistivities)],
        "note": (
            "Schlumberger half-spacings and apparent resistivities are read from the "
            "documented VES text/CSV dialect; a supplied resistivity column is carried "
            "through unchanged and is otherwise derived from the measured resistance by "
            "the documented geometric factor. The dialect records no exclusions. This "
            "description is not scientific evidence."
        ),
    }
