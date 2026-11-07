"""Build a benchmark case payload from the documented NiX DAT dialect.

A benchmark case needs the engine inputs that were prepared from a dataset. For
2D ERT those inputs already exist in an imported NiX DAT file: electrode
geometry, quadrupole observations, and apparent resistivities. This module turns
such a file into a ``benchmark-case-v1`` payload so an operator does not have to
transcribe measurements into JSON by hand.

It is a converter, not evidence. It reads the dialect documented in
:mod:`nix_ert.data.dat_import`, refuses anything that file cannot state
unambiguously, and never invents a value:

* the mesh resolution and depth come from the frozen protocol's
  ``mesh_assumptions`` (``nz`` required, ``depth`` optional); nothing is guessed;
* terrain and invalid rows are refused rather than flattened or dropped, because
  either would silently change which observations the reference response must
  match;
* the DAT's own array declaration is reported for the operator's inspection but is
  not treated as a benchmark result.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from nix_ert.data.dat_import import DATParseError, ImportedDataset, parse_dat_file
from nix_ert.ert.inversion2d import ERT2DError, Mesh2D


CASE_DOMAIN = "2D ERT"
"""DAT files describe a single line of quadrupoles, so the domain is 2D ERT."""

CASE_FORMAT_VERSION = "benchmark-case-v1"


class DATBenchmarkCaseError(ValueError):
    """Raised when a DAT file cannot become an unambiguous benchmark case."""


@dataclass(frozen=True)
class DATBenchmarkCase:
    """A converted DAT dataset: the payload plus the facts it was built from."""

    payload: Mapping[str, object]
    dataset: ImportedDataset
    source_path: str

    def to_payload(self) -> dict[str, object]:
        return {str(key): value for key, value in self.payload.items()}

    def to_json(self) -> str:
        import json

        return json.dumps(self.to_payload(), sort_keys=True, indent=2, default=str)


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DATBenchmarkCaseError(f"mesh_assumptions.{label} must be an integer")
    if value < 1:
        raise DATBenchmarkCaseError(f"mesh_assumptions.{label} must be positive")
    return value


def _optional_depth(mesh_assumptions: Mapping[str, object]) -> float | None:
    if "depth" not in mesh_assumptions:
        return None
    raw = mesh_assumptions["depth"]
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise DATBenchmarkCaseError("mesh_assumptions.depth must be a number when supplied")
    depth = float(raw)
    if not math.isfinite(depth) or depth <= 0:
        raise DATBenchmarkCaseError("mesh_assumptions.depth must be finite and positive")
    return depth


def _mesh(dataset: ImportedDataset, mesh_assumptions: Mapping[str, object]) -> Mesh2D:
    if not mesh_assumptions:
        raise DATBenchmarkCaseError(
            "the protocol must freeze mesh_assumptions (at least 'nz') before a DAT case "
            "can be built; no mesh resolution is assumed"
        )
    nz = _positive_int(mesh_assumptions.get("nz"), "nz")
    depth = _optional_depth(mesh_assumptions)
    if dataset.topography:
        raise DATBenchmarkCaseError(
            f"{dataset.source_name} declares {len(dataset.topography)} topography point(s); "
            "the 2D engine has no topography support, so the terrain must not be flattened "
            "into a benchmark case"
        )
    if len(dataset.electrodes) < 2:
        raise DATBenchmarkCaseError(
            f"{dataset.source_name} references {len(dataset.electrodes)} electrode(s); at "
            "least two are required to form a 2D mesh"
        )
    try:
        return Mesh2D.from_electrodes(
            [electrode.x for electrode in dataset.electrodes], nz=nz, depth=depth
        )
    except ERT2DError as exc:
        raise DATBenchmarkCaseError(f"{dataset.source_name}: cannot build a mesh: {exc}") from exc


def build_dat_benchmark_case(
    path: Path | str,
    protocol_id: str,
    mesh_assumptions: Mapping[str, object],
) -> DATBenchmarkCase:
    """Convert one NiX DAT file into a frozen, validated benchmark case payload."""
    if not str(protocol_id).strip():
        raise DATBenchmarkCaseError("a protocol ID is required to bind the case")
    source_path = Path(path)
    try:
        dataset = parse_dat_file(source_path)
    except DATParseError as exc:
        raise DATBenchmarkCaseError(str(exc)) from exc

    mesh = _mesh(dataset, mesh_assumptions)
    observations: list[dict[str, object]] = []
    for index, measurement in enumerate(dataset.measurements, start=1):
        rho = measurement.apparent_resistivity
        if rho is None or not math.isfinite(float(rho)) or float(rho) <= 0:
            raise DATBenchmarkCaseError(
                f"{dataset.source_name} measurement {index} has no usable apparent "
                "resistivity; an invalid value cannot be included in or dropped from a "
                "benchmark case without changing which observations the reference matches"
            )
        observations.append(
            {
                "a": measurement.a,
                "b": measurement.b,
                "m": measurement.m,
                "n": measurement.n,
                "apparent_resistivity": float(rho),
                "excluded": False,
            }
        )
    if not observations:
        raise DATBenchmarkCaseError(f"{dataset.source_name} contains no measurements")

    payload: dict[str, object] = {
        "protocol_id": str(protocol_id),
        "domain": CASE_DOMAIN,
        "case_format_version": CASE_FORMAT_VERSION,
        "x_edges": [float(value) for value in mesh.x_edges],
        "depth_edges": [float(value) for value in mesh.depth_edges],
        "observations": observations,
    }
    return DATBenchmarkCase(payload=payload, dataset=dataset, source_path=str(source_path))


def describe_dat_case(case: DATBenchmarkCase) -> dict[str, object]:
    """Return the facts a case was derived from, for operator review."""
    dataset = case.dataset
    return {
        "source": case.source_path,
        "source_name": dataset.source_name,
        "domain": CASE_DOMAIN,
        "declared_array": dataset.array_type,
        "electrode_spacing": dataset.electrode_spacing,
        "electrode_count": len(dataset.electrodes),
        "observation_count": len(dataset.measurements),
        "topography_points": len(dataset.topography),
        "note": (
            "Geometry and observations are read from the documented NiX DAT dialect; "
            "the declared array name is reported, not used as scientific evidence."
        ),
    }
