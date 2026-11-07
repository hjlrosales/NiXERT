"""Fail-closed admission and execution path for the external reference gate.

This module delivers the *readiness* gaps recorded in
``docs/external_benchmark_gap_analysis.md`` §5 (R-1 … R-4) without changing any
qualification status:

``R-1`` — execution path
    :func:`run_benchmark` loads a registered protocol, executes it over the
    existing, unmodified :func:`nix_ert.ves.engine.invert_ves`,
    :func:`nix_ert.ert.inversion2d.invert_ert`, or
    :func:`nix_ert.ert.inversion3d.invert_ert3d`, and records a
    :class:`~nix_ert.qualification.registry.BenchmarkComparison`.
``R-2`` — auditable records
    Every executed comparison carries :class:`BenchmarkProvenance`: the dataset
    digest, the canonical protocol digest computed **before** and re-checked
    **after** execution, the digest of the engine inputs actually executed, the
    environment snapshot, and the engine source digest. The comparison
    identifier and timestamp are still not deterministic; the provenance is what
    makes the record auditable.
``R-3`` — tolerance justification
    Admission refuses a protocol that does not state a written justification for
    every declared metric, and execution refuses to record if the protocol
    changed between admission and recording, so a tolerance can never be fitted
    to an observed result.
``R-4`` — dataset admission
    :func:`admit_benchmark_candidate` refuses internal-only data, unpermitted
    data, missing acquisition/geometry metadata, missing bytes, an unrecorded or
    mismatched source digest, an absent or self-produced reference result, and
    missing frozen parameters.

**The gate itself remains ``NOT VALIDATED``.** Nothing in this module can
validate an engine: no licensed independent dataset and no independent reference
result exists in the repository, so admission refuses every candidate reachable
from :func:`nix_ert.qualification.registry.internal_qualification_registry`.
The module only removes the engineering gap between "evidence arrives" and "the
evidence can be executed and recorded". It never fabricates, downloads, or
substitutes data, and it never promotes a status beyond what the frozen
tolerance rule computes.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar, Mapping, Sequence

import numpy as np

from nix_ert.ert.inversion2d import (
    ERT2DError,
    ERTObservation,
    Mesh2D,
    invert_ert,
)
from nix_ert.ert.inversion3d import (
    ERT3DError,
    ERT3DObservation,
    Mesh3D,
    invert_ert3d,
)
from nix_ert.qualification.m21 import (
    ConvergenceRecord,
    QualificationOutcome,
    comparison_metrics,
    environment_snapshot,
)
from nix_ert.qualification.registry import (
    TOLERANCE_JUSTIFICATION_KEY,
    BenchmarkComparison,
    BenchmarkProtocol,
    ComparisonStatus,
    QualificationRegistry,
    thaw,
)
from nix_ert.ves.engine import (
    LayeredEarthModel,
    VESError,
    VESPoint,
    invert_ves,
)


BENCHMARK_PROCEDURE_VERSION = "benchmark-execution-v1"

SUPPORTED_DOMAINS = ("VES", "2D ERT", "3D ERT")
"""Engine domains a frozen protocol may target."""

PROTOCOL_PARAMETER_KEY = "domain"
"""Key inside ``BenchmarkProtocol.inversion_parameters`` that names the domain."""

SUPPORTED_METRICS = (
    "rmse",
    "relative_rmse",
    "max_absolute_difference",
    "log10_rmse",
)
"""Metrics :func:`run_benchmark` can measure from a reference response."""

TOLERANCE_ABSOLUTE_KEY = "max_absolute"
"""Key every ``acceptable_tolerance`` entry must use for its absolute bound."""

DATASET_DIGEST_KEY = "sha256"
"""Acquisition-information key recording the licensed dataset's digest."""

REFERENCE_RESPONSE_KEY = "response"
REFERENCE_PRODUCER_KEY = "producer"
REFERENCE_PROVENANCE_KEY = "provenance"
REFERENCE_SEMANTICS_KEY = "semantics"
REFERENCE_SEMANTICS_FIELDS = ("model_space", "resistivity_unit", "depth_convention")

#: Reasons admission refuses a candidate. Every code is a fail-closed refusal.
PROTOCOL_NOT_REGISTERED = "protocol_not_registered"
DATASET_NOT_REGISTERED = "dataset_not_registered"
DATASET_NOT_INDEPENDENT = "dataset_not_independent"
DATASET_BYTES_MISSING = "dataset_bytes_missing"
DATASET_HASH_UNRECORDED = "dataset_hash_unrecorded"
DATASET_HASH_MISMATCH = "dataset_hash_mismatch"
DATASET_GEOMETRY_MISSING = "dataset_geometry_missing"
REFERENCE_RESULT_MISSING = "reference_result_missing"
REFERENCE_PROVENANCE_MISSING = "reference_provenance_missing"
REFERENCE_PRODUCED_BY_NIX = "reference_produced_by_nix_ert"
REFERENCE_SEMANTICS_MISSING = "reference_semantics_missing"
REFERENCE_RESPONSE_MISSING = "reference_response_missing"
TOLERANCE_MISSING = "tolerance_missing"
TOLERANCE_JUSTIFICATION_MISSING = "tolerance_justification_missing"
METRIC_UNSUPPORTED = "metric_unsupported"
DOMAIN_UNSUPPORTED = "domain_unsupported"
PROTOCOL_PARAMETER_MISSING = "protocol_parameter_missing"
PROTOCOL_PARAMETER_INVALID = "protocol_parameter_invalid"
STOPPING_CRITERIA_MISMATCH = "stopping_criteria_mismatch"

_REQUIRED_PARAMETERS: Mapping[str, tuple[str, ...]] = {
    "VES": ("max_nfev", "initial_resistivities", "initial_thicknesses"),
    "2D ERT": ("max_iterations", "damping", "jacobian_step", "convergence_rms"),
    "3D ERT": ("max_iterations", "damping"),
}
"""Frozen parameters each domain requires; no engine default is ever assumed."""


class BenchmarkAdmissionError(ValueError):
    """Raised when a candidate is not admissible as independent evidence."""

    def __init__(self, admission: "BenchmarkAdmission") -> None:
        self.admission = admission
        details = "; ".join(
            f"{finding.code}: {finding.detail}" for finding in admission.findings
        )
        super().__init__(
            f"benchmark candidate {admission.protocol_id!r} is not admissible: {details}"
        )


class BenchmarkExecutionError(ValueError):
    """Raised when admissible evidence cannot be executed as frozen."""


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def protocol_digest(protocol: BenchmarkProtocol) -> str:
    """Return the canonical digest of every frozen protocol field."""
    return _digest(protocol.to_dict())


@dataclass(frozen=True)
class AdmissionFinding:
    """One reason a candidate is refused, with the offending field named."""

    code: str
    detail: str


@dataclass(frozen=True)
class BenchmarkAdmission:
    """The result of a fail-closed admissibility check.

    ``admitted`` is true only when *no* finding was produced. There is no
    partial or conditional admission: a single missing evidence item refuses the
    candidate, so an unexecutable or unfalsifiable comparison cannot be reached.
    """

    protocol_id: str
    dataset_id: str | None
    protocol_sha256: str
    dataset_sha256: str | None
    findings: tuple[AdmissionFinding, ...] = ()

    @property
    def admitted(self) -> bool:
        return not self.findings

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(finding.code for finding in self.findings)

    def require(self) -> None:
        if not self.admitted:
            raise BenchmarkAdmissionError(self)

    def to_dict(self) -> dict[str, object]:
        return {
            "protocol_id": self.protocol_id,
            "dataset_id": self.dataset_id,
            "protocol_sha256": self.protocol_sha256,
            "dataset_sha256": self.dataset_sha256,
            "admitted": self.admitted,
            "findings": [
                {"code": finding.code, "detail": finding.detail}
                for finding in self.findings
            ],
        }


@dataclass(frozen=True)
class BenchmarkProvenance:
    """Audit context bound to an executed comparison (gap R-2)."""

    domain: str
    dataset_id: str
    dataset_sha256: str
    dataset_path: str
    protocol_id: str
    protocol_sha256_pre_execution: str
    protocol_sha256_post_execution: str
    inputs_sha256: str
    discretization_sha256: str
    reference_producer: str
    reference_provenance: str
    engine_source_sha256: str
    environment: Mapping[str, str]
    procedure_version: str = BENCHMARK_PROCEDURE_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "environment", dict(self.environment))

    @property
    def protocol_unchanged(self) -> bool:
        return self.protocol_sha256_pre_execution == self.protocol_sha256_post_execution

    def to_dict(self) -> dict[str, object]:
        return {
            "domain": self.domain,
            "dataset_id": self.dataset_id,
            "dataset_sha256": self.dataset_sha256,
            "dataset_path": self.dataset_path,
            "protocol_id": self.protocol_id,
            "protocol_sha256_pre_execution": self.protocol_sha256_pre_execution,
            "protocol_sha256_post_execution": self.protocol_sha256_post_execution,
            "protocol_unchanged": self.protocol_unchanged,
            "inputs_sha256": self.inputs_sha256,
            "discretization_sha256": self.discretization_sha256,
            "reference_producer": self.reference_producer,
            "reference_provenance": self.reference_provenance,
            "engine_source_sha256": self.engine_source_sha256,
            "environment": dict(self.environment),
            "procedure_version": self.procedure_version,
        }


@dataclass(frozen=True)
class ToleranceOutcome:
    """Whether one measured metric stayed inside its frozen bound."""

    metric: str
    value: float
    max_absolute: float

    @property
    def passed(self) -> bool:
        return abs(self.value) <= self.max_absolute

    def to_dict(self) -> dict[str, object]:
        return {
            "metric": self.metric,
            "value": self.value,
            "max_absolute": self.max_absolute,
            "passed": self.passed,
        }


@dataclass(frozen=True)
class BenchmarkRun:
    """Everything an executed comparison produced, including a refusal outcome."""

    admission: BenchmarkAdmission
    provenance: BenchmarkProvenance
    convergence: ConvergenceRecord
    metrics: Mapping[str, float]
    tolerances: tuple[ToleranceOutcome, ...]
    status: ComparisonStatus
    comparison: BenchmarkComparison
    notes: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "metrics", dict(self.metrics))

    def to_dict(self) -> dict[str, object]:
        return {
            "admission": self.admission.to_dict(),
            "provenance": self.provenance.to_dict(),
            "convergence": self.convergence.to_dict(),
            "metrics": dict(self.metrics),
            "tolerances": [item.to_dict() for item in self.tolerances],
            "status": self.status.value,
            "comparison": self.comparison.to_dict(),
            "notes": self.notes,
        }


class _BenchmarkCase:
    """Shared behaviour of the engine inputs prepared from a dataset."""

    domain: ClassVar[str] = ""

    def discretization(self) -> Mapping[str, object]:
        raise NotImplementedError

    def inputs(self) -> Mapping[str, object]:
        raise NotImplementedError

    def active_observation_count(self) -> int:
        raise NotImplementedError

    def discretization_sha256(self) -> str:
        return _digest(thaw(self.discretization()))

    def inputs_sha256(self) -> str:
        return _digest(thaw(self.inputs()))


@dataclass(frozen=True)
class VESBenchmarkCase(_BenchmarkCase):
    """VES sounding loaded from a dataset; geometry is the dataset's."""

    domain: ClassVar[str] = "VES"
    points: tuple[VESPoint, ...]

    def __post_init__(self) -> None:
        if not self.points:
            raise BenchmarkExecutionError("a VES benchmark case requires at least one point")
        if not all(isinstance(point, VESPoint) for point in self.points):
            raise BenchmarkExecutionError("VES benchmark points must be VESPoint instances")
        if self.active_observation_count() == 0:
            raise BenchmarkExecutionError("a VES benchmark case requires an active point")

    def active_points(self) -> tuple[VESPoint, ...]:
        return tuple(point for point in self.points if not point.excluded)

    def active_observation_count(self) -> int:
        return len(self.active_points())

    def discretization(self) -> Mapping[str, object]:
        return {
            "domain": self.domain,
            "ab2": [point.ab2 for point in self.points],
            "mn2": [point.mn2 for point in self.points],
        }

    def inputs(self) -> Mapping[str, object]:
        return {
            "domain": self.domain,
            "points": [
                [point.ab2, point.mn2, point.apparent_resistivity, point.resistance, point.excluded]
                for point in self.points
            ],
        }


@dataclass(frozen=True)
class ERT2DBenchmarkCase(_BenchmarkCase):
    """2D ERT survey loaded from a dataset, on the dataset's own discretization."""

    domain: ClassVar[str] = "2D ERT"
    mesh: Mesh2D
    observations: tuple[ERTObservation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.mesh, Mesh2D):
            raise BenchmarkExecutionError("2D benchmark cases require a Mesh2D")
        if not self.observations:
            raise BenchmarkExecutionError("a 2D benchmark case requires observations")
        if not all(isinstance(item, ERTObservation) for item in self.observations):
            raise BenchmarkExecutionError("2D observations must be ERTObservation instances")
        if self.active_observation_count() == 0:
            raise BenchmarkExecutionError("a 2D benchmark case requires an active observation")

    def active_observation_count(self) -> int:
        return sum(1 for item in self.observations if not item.excluded)

    def discretization(self) -> Mapping[str, object]:
        return {
            "domain": self.domain,
            "x_edges": list(self.mesh.x_edges),
            "depth_edges": list(self.mesh.depth_edges),
        }

    def inputs(self) -> Mapping[str, object]:
        return {
            "domain": self.domain,
            "observations": [
                [item.a, item.b, item.m, item.n, item.apparent_resistivity, item.excluded]
                for item in self.observations
            ],
        }


@dataclass(frozen=True)
class ERT3DBenchmarkCase(_BenchmarkCase):
    """3D ERT survey loaded from a dataset, on the dataset's own discretization."""

    domain: ClassVar[str] = "3D ERT"
    mesh: Mesh3D
    electrodes: tuple[tuple[float, float], ...]
    observations: tuple[ERT3DObservation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.mesh, Mesh3D):
            raise BenchmarkExecutionError("3D benchmark cases require a Mesh3D")
        if not self.electrodes:
            raise BenchmarkExecutionError("a 3D benchmark case requires electrode positions")
        if not self.observations:
            raise BenchmarkExecutionError("a 3D benchmark case requires observations")
        if not all(isinstance(item, ERT3DObservation) for item in self.observations):
            raise BenchmarkExecutionError("3D observations must be ERT3DObservation instances")
        if self.active_observation_count() == 0:
            raise BenchmarkExecutionError("a 3D benchmark case requires an active observation")

    def active_observation_count(self) -> int:
        return sum(1 for item in self.observations if not item.excluded)

    def discretization(self) -> Mapping[str, object]:
        return {
            "domain": self.domain,
            "x_edges": list(self.mesh.x_edges),
            "y_edges": list(self.mesh.y_edges),
            "depth_edges": list(self.mesh.depth_edges),
            "electrodes": [list(position) for position in self.electrodes],
        }

    def inputs(self) -> Mapping[str, object]:
        return {
            "domain": self.domain,
            "observations": [
                [item.a, item.b, item.m, item.n, item.apparent_resistivity, item.excluded]
                for item in self.observations
            ],
        }


BenchmarkCase = VESBenchmarkCase | ERT2DBenchmarkCase | ERT3DBenchmarkCase


def _is_self_produced(producer: str) -> bool:
    """Return True when a reference result names NiX ERT as its own producer.

    Separators and whitespace are collapsed first, so spelling a producer as
    ``NiX-ERT``, ``nix_ert``, ``NIX\tERT``, or ``NiX  ERT`` cannot slip past the
    self-reference check.
    """
    normalised = " ".join(
        producer.lower().replace("-", " ").replace("_", " ").split()
    )
    return "nix ert" in normalised or "nixert" in normalised.replace(" ", "")


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= 1 else None


def _reference_response(protocol: BenchmarkProtocol) -> tuple[float, ...] | None:
    raw = protocol.expected_reference_result.get(REFERENCE_RESPONSE_KEY)
    if not isinstance(raw, (list, tuple)) or not raw:
        return None
    values: list[float] = []
    for item in raw:
        number = _number(item)
        if number is None or number <= 0:
            return None
        values.append(number)
    return tuple(values)


def _parameter_findings(domain: str, protocol: BenchmarkProtocol) -> list[AdmissionFinding]:
    """Validate the frozen engine parameters for one domain."""
    findings: list[AdmissionFinding] = []
    parameters = protocol.inversion_parameters

    def missing(key: str) -> None:
        findings.append(
            AdmissionFinding(
                PROTOCOL_PARAMETER_MISSING,
                f"inversion_parameters.{key} is required for {domain} and has no engine default",
            )
        )

    def invalid(key: str, reason: str) -> None:
        findings.append(
            AdmissionFinding(PROTOCOL_PARAMETER_INVALID, f"inversion_parameters.{key} {reason}")
        )

    if domain == "VES":
        resistivities = parameters.get("initial_resistivities")
        thicknesses = parameters.get("initial_thicknesses")
        if not isinstance(resistivities, (list, tuple)) or not resistivities:
            missing("initial_resistivities")
        elif any((value := _number(item)) is None or value <= 0 for item in resistivities):
            invalid("initial_resistivities", "must be finite positive numbers")
        if not isinstance(thicknesses, (list, tuple)):
            missing("initial_thicknesses")
        elif any((value := _number(item)) is None or value <= 0 for item in thicknesses):
            invalid("initial_thicknesses", "must be finite positive numbers")
        if (
            isinstance(resistivities, (list, tuple))
            and isinstance(thicknesses, (list, tuple))
            and resistivities
            and len(thicknesses) != len(resistivities) - 1
        ):
            invalid(
                "initial_thicknesses",
                "must contain one thickness between each pair of layers",
            )

    if domain in {"2D ERT", "3D ERT"}:
        if "initial_model" in parameters:
            model = parameters.get("initial_model")
            if not isinstance(model, (list, tuple)) or not model:
                invalid("initial_model", "must be a non-empty matrix")
            else:
                rows = [
                    row for row in model if isinstance(row, (list, tuple)) and row
                ]
                if len(rows) != len(model):
                    invalid("initial_model", "must be a rectangular matrix of numbers")
                elif any(
                    (value := _number(item)) is None or value <= 0
                    for row in rows
                    for item in row
                ):
                    invalid("initial_model", "must contain finite positive resistivities")
            if "initial_resistivity" in parameters:
                invalid(
                    "initial_model",
                    "must not be combined with initial_resistivity (ambiguous start)",
                )
        else:
            value = _number(parameters.get("initial_resistivity"))
            if parameters.get("initial_resistivity") is None:
                missing("initial_resistivity (or initial_model)")
            elif value is None or value <= 0:
                invalid("initial_resistivity", "must be a finite positive number")

    for key in _REQUIRED_PARAMETERS[domain]:
        if key in {"initial_resistivities", "initial_thicknesses"}:
            continue
        value = parameters.get(key)
        if value is None:
            missing(key)
            continue
        if key in {"max_nfev", "max_iterations"}:
            if _positive_int(value) is None:
                invalid(key, "must be a positive integer")
        elif (number := _number(value)) is None or number <= 0:
            invalid(key, "must be a finite positive number")

    return findings


def admit_benchmark_candidate(
    registry: QualificationRegistry, protocol_id: str,
) -> BenchmarkAdmission:
    """Return a fail-closed admissibility decision for one frozen protocol.

    A candidate is admitted only when every item of independent evidence is
    present and internally consistent. Synthetic, unpermitted, undocumented, or
    self-produced evidence is refused with a named reason instead of being
    executed and reported.
    """
    protocol = registry.protocols.get(protocol_id)
    if protocol is None:
        return BenchmarkAdmission(
            protocol_id=str(protocol_id),
            dataset_id=None,
            protocol_sha256="",
            dataset_sha256=None,
            findings=(
                AdmissionFinding(
                    PROTOCOL_NOT_REGISTERED,
                    f"no frozen protocol is registered as {protocol_id!r}",
                ),
            ),
        )

    findings: list[AdmissionFinding] = []
    digest = protocol_digest(protocol)
    dataset = registry.datasets.get(protocol.dataset_id)
    dataset_digest: str | None = None

    if dataset is None:
        findings.append(
            AdmissionFinding(
                DATASET_NOT_REGISTERED,
                f"protocol references unregistered dataset {protocol.dataset_id!r}",
            )
        )
    else:
        if not dataset.independent_benchmark_eligible:
            findings.append(
                AdmissionFinding(
                    DATASET_NOT_INDEPENDENT,
                    f"dataset {dataset.dataset_id!r} is {dataset.classification.value!r} with "
                    f"license {dataset.license_status.value!r}; an independent, "
                    "permission-confirmed dataset is required",
                )
            )

        if not dataset.data_path:
            findings.append(
                AdmissionFinding(DATASET_BYTES_MISSING, "the dataset has no recorded local data path")
            )
        else:
            path = Path(dataset.data_path)
            if not path.is_file():
                findings.append(
                    AdmissionFinding(
                        DATASET_BYTES_MISSING,
                        f"no readable dataset file at {dataset.data_path!r}",
                    )
                )
            else:
                try:
                    dataset_digest = _file_digest(path)
                except OSError as exc:
                    findings.append(
                        AdmissionFinding(
                            DATASET_BYTES_MISSING,
                            f"dataset file {dataset.data_path!r} could not be read: {exc}",
                        )
                    )
        recorded_digest = dataset.acquisition_information.get(DATASET_DIGEST_KEY)
        if not isinstance(recorded_digest, str) or len(recorded_digest.strip()) != 64:
            findings.append(
                AdmissionFinding(
                    DATASET_HASH_UNRECORDED,
                    f"acquisition_information.{DATASET_DIGEST_KEY} must record the dataset's "
                    "SHA-256 before a comparison can be tied to it",
                )
            )
        elif dataset_digest is not None and dataset_digest != recorded_digest.strip().lower():
            findings.append(
                AdmissionFinding(
                    DATASET_HASH_MISMATCH,
                    "the dataset file no longer matches its recorded SHA-256 "
                    f"({dataset_digest} != {recorded_digest.strip().lower()})",
                )
            )

        if not dataset.acquisition_information:
            findings.append(
                AdmissionFinding(
                    DATASET_GEOMETRY_MISSING,
                    "acquisition_information must state the acquisition metadata",
                )
            )
        if not str(dataset.electrode_configuration).strip():
            findings.append(
                AdmissionFinding(
                    DATASET_GEOMETRY_MISSING, "electrode_configuration is required"
                )
            )
        if dataset.electrode_spacing is None:
            findings.append(
                AdmissionFinding(DATASET_GEOMETRY_MISSING, "electrode_spacing is required")
            )
        if not dataset.coordinate_context:
            findings.append(
                AdmissionFinding(
                    DATASET_GEOMETRY_MISSING,
                    "coordinate_context must state the coordinate/CRS context",
                )
            )

    reference = protocol.expected_reference_result
    if not reference:
        findings.append(
            AdmissionFinding(
                REFERENCE_RESULT_MISSING,
                "the protocol defines no independent reference result",
            )
        )
    else:
        producer = reference.get(REFERENCE_PRODUCER_KEY)
        if not isinstance(producer, str) or not producer.strip():
            findings.append(
                AdmissionFinding(
                    REFERENCE_PROVENANCE_MISSING,
                    f"expected_reference_result.{REFERENCE_PRODUCER_KEY} is required",
                )
            )
        elif _is_self_produced(producer):
            findings.append(
                AdmissionFinding(
                    REFERENCE_PRODUCED_BY_NIX,
                    f"the reference result is produced by {producer!r}; an independent "
                    "producer is required",
                )
            )
        provenance = reference.get(REFERENCE_PROVENANCE_KEY)
        if not isinstance(provenance, str) or not provenance.strip():
            findings.append(
                AdmissionFinding(
                    REFERENCE_PROVENANCE_MISSING,
                    f"expected_reference_result.{REFERENCE_PROVENANCE_KEY} must record the "
                    "reference's own origin and settings",
                )
            )
        semantics = reference.get(REFERENCE_SEMANTICS_KEY)
        if not isinstance(semantics, Mapping):
            findings.append(
                AdmissionFinding(
                    REFERENCE_SEMANTICS_MISSING,
                    f"expected_reference_result.{REFERENCE_SEMANTICS_KEY} must state "
                    + ", ".join(REFERENCE_SEMANTICS_FIELDS),
                )
            )
        else:
            absent = [
                name
                for name in REFERENCE_SEMANTICS_FIELDS
                if not isinstance(semantics.get(name), str)
                or not str(semantics.get(name)).strip()
            ]
            if absent:
                findings.append(
                    AdmissionFinding(
                        REFERENCE_SEMANTICS_MISSING,
                        "reference semantics are incomplete: " + ", ".join(absent),
                    )
                )
        if _reference_response(protocol) is None:
            findings.append(
                AdmissionFinding(
                    REFERENCE_RESPONSE_MISSING,
                    f"expected_reference_result.{REFERENCE_RESPONSE_KEY} must list finite "
                    "positive reference values in observation order",
                )
            )

    for metric in protocol.comparison_metrics:
        name = str(metric)
        if name not in SUPPORTED_METRICS:
            findings.append(
                AdmissionFinding(
                    METRIC_UNSUPPORTED,
                    f"metric {name!r} cannot be measured; supported metrics are "
                    + ", ".join(SUPPORTED_METRICS),
                )
            )
            continue
        entry = protocol.acceptable_tolerance.get(name)
        if not isinstance(entry, Mapping):
            findings.append(
                AdmissionFinding(
                    TOLERANCE_MISSING,
                    f"metric {name!r} has no acceptable_tolerance entry",
                )
            )
            continue
        bound = _number(entry.get(TOLERANCE_ABSOLUTE_KEY))
        if bound is None or bound < 0:
            findings.append(
                AdmissionFinding(
                    TOLERANCE_MISSING,
                    f"metric {name!r} tolerance requires a finite non-negative "
                    f"{TOLERANCE_ABSOLUTE_KEY}",
                )
            )
        justification = entry.get(TOLERANCE_JUSTIFICATION_KEY)
        if not isinstance(justification, str) or not justification.strip():
            findings.append(
                AdmissionFinding(
                    TOLERANCE_JUSTIFICATION_MISSING,
                    f"metric {name!r} tolerance requires a written "
                    f"{TOLERANCE_JUSTIFICATION_KEY}",
                )
            )

    domain = protocol.inversion_parameters.get(PROTOCOL_PARAMETER_KEY)
    if domain not in SUPPORTED_DOMAINS:
        findings.append(
            AdmissionFinding(
                DOMAIN_UNSUPPORTED,
                f"inversion_parameters.{PROTOCOL_PARAMETER_KEY} must be one of "
                + ", ".join(SUPPORTED_DOMAINS),
            )
        )
    else:
        findings.extend(_parameter_findings(str(domain), protocol))

    for key, frozen in protocol.stopping_criteria.items():
        if key in protocol.inversion_parameters:
            if protocol.inversion_parameters[key] != frozen:
                findings.append(
                    AdmissionFinding(
                        STOPPING_CRITERIA_MISMATCH,
                        f"stopping_criteria.{key} ({frozen!r}) contradicts "
                        f"inversion_parameters.{key} "
                        f"({protocol.inversion_parameters[key]!r})",
                    )
                )

    return BenchmarkAdmission(
        protocol_id=protocol.protocol_id,
        dataset_id=protocol.dataset_id,
        protocol_sha256=digest,
        dataset_sha256=dataset_digest,
        findings=tuple(findings),
    )


def _engine_source_digest(domain: str) -> str:
    """Digest the source file of the engine that will actually be executed."""
    engine = {"VES": invert_ves, "2D ERT": invert_ert, "3D ERT": invert_ert3d}[domain]
    source = inspect.getsourcefile(engine)
    if source is None:  # pragma: no cover - only reachable for frozen/binary builds
        raise BenchmarkExecutionError(f"cannot locate the {domain} engine source")
    return _file_digest(Path(source))


def _execute(
    domain: str, protocol: BenchmarkProtocol, case: BenchmarkCase,
) -> tuple[ConvergenceRecord, tuple[float, ...] | None]:
    """Run the frozen protocol on the unmodified engine, recording every outcome."""
    parameters = protocol.inversion_parameters
    if isinstance(case, VESBenchmarkCase):
        initial = LayeredEarthModel(
            tuple(float(value) for value in parameters["initial_resistivities"]),
            tuple(float(value) for value in parameters["initial_thicknesses"]),
        )
        try:
            result = invert_ves(
                case.points, initial, max_nfev=int(parameters["max_nfev"])
            )
        except (VESError, ValueError) as exc:
            return (
                ConvergenceRecord(
                    "VES", QualificationOutcome.INVALID_INPUT, None, (), None, 0,
                    "input rejected", False, str(exc),
                ),
                None,
            )
        except Exception as exc:  # numerical failures are evidence, not skips
            return (
                ConvergenceRecord(
                    "VES", QualificationOutcome.FAILED, None, (), None, 0,
                    "solver failure", False, str(exc),
                ),
                None,
            )
        objective = float(result.rms_log10)
        if not math.isfinite(objective):
            return (
                ConvergenceRecord(
                    "VES", QualificationOutcome.FAILED, None, (), None, 0,
                    "non-finite objective", False, "the engine reported a non-finite rms_log10",
                ),
                None,
            )
        outcome = (
            QualificationOutcome.CONVERGED
            if result.converged
            else QualificationOutcome.TERMINATED
        )
        # scipy's least_squares exposes no per-evaluation objective trajectory,
        # so only the final objective is recorded; nothing is invented.
        record = ConvergenceRecord(
            "VES", outcome, None, (objective,), objective, int(result.iterations),
            f"{result.message}; objective history unavailable from the optimizer", True,
        )
        return record, tuple(float(value) for value in result.predicted)

    if isinstance(case, ERT2DBenchmarkCase):
        initial_model: float | Sequence[object]
        initial_model: np.ndarray | float
        if "initial_model" in parameters:
            initial_model = np.asarray(parameters["initial_model"], dtype=float)
        else:
            initial_model = float(parameters["initial_resistivity"])
        try:
            result = invert_ert(
                case.observations,
                case.mesh,
                initial_model,
                max_iterations=int(parameters["max_iterations"]),
                damping=float(parameters["damping"]),
                jacobian_step=float(parameters["jacobian_step"]),
                convergence_rms=float(parameters["convergence_rms"]),
            )
        except (ERT2DError, ValueError) as exc:
            return (
                ConvergenceRecord(
                    "2D ERT", QualificationOutcome.INVALID_INPUT, None, (), None, 0,
                    "input rejected", False, str(exc),
                ),
                None,
            )
        except Exception as exc:
            return (
                ConvergenceRecord(
                    "2D ERT", QualificationOutcome.FAILED, None, (), None, 0,
                    "solver failure", False, str(exc),
                ),
                None,
            )
        history = tuple(float(item.rms_log10) for item in result.iterations)
        if any(not math.isfinite(value) for value in history) or not math.isfinite(
            float(result.rms_log10)
        ):
            return (
                ConvergenceRecord(
                    "2D ERT", QualificationOutcome.FAILED, None, (), None, 0,
                    "non-finite objective", False, "the engine reported a non-finite rms_log10",
                ),
                None,
            )
        outcome = (
            QualificationOutcome.CONVERGED
            if result.converged
            else QualificationOutcome.TERMINATED
        )
        record = ConvergenceRecord(
            "2D ERT", outcome, history[0] if history else float(result.rms_log10),
            history, float(result.rms_log10), len(history),
            "converged" if result.converged else "maximum iterations reached", True,
        )
        return record, tuple(float(value) for value in result.predicted)

    try:
        model, predicted, raw_history, converged = invert_ert3d(
            case.observations,
            case.mesh,
            case.electrodes,
            float(parameters["initial_resistivity"]),
            max_iterations=int(parameters["max_iterations"]),
            damping=float(parameters["damping"]),
        )
    except (ERT3DError, ValueError) as exc:
        return (
            ConvergenceRecord(
                "3D ERT", QualificationOutcome.INVALID_INPUT, None, (), None, 0,
                "input rejected", False, str(exc),
            ),
            None,
        )
    except Exception as exc:
        return (
            ConvergenceRecord(
                "3D ERT", QualificationOutcome.FAILED, None, (), None, 0,
                "solver failure", False, str(exc),
            ),
            None,
        )
    history = tuple(float(value) for value in raw_history)
    if any(not math.isfinite(value) for value in history):
        return (
            ConvergenceRecord(
                "3D ERT", QualificationOutcome.FAILED, None, (), None, 0,
                "non-finite objective", False, "the engine reported a non-finite objective",
            ),
            None,
        )
    outcome = (
        QualificationOutcome.CONVERGED if converged else QualificationOutcome.TERMINATED
    )
    record = ConvergenceRecord(
        "3D ERT", outcome, history[0] if history else None, history,
        history[-1] if history else None, len(history),
        "converged" if converged else "maximum iterations reached", True,
    )
    return record, tuple(float(value) for value in predicted)


def evaluate_tolerances(
    metrics: Mapping[str, float], protocol: BenchmarkProtocol,
) -> tuple[ToleranceOutcome, ...]:
    """Compare every measured protocol metric with its frozen absolute bound."""
    outcomes: list[ToleranceOutcome] = []
    for metric in protocol.comparison_metrics:
        name = str(metric)
        value = metrics.get(name)
        if value is None:
            continue
        entry = protocol.acceptable_tolerance.get(name)
        bound = _number(entry.get(TOLERANCE_ABSOLUTE_KEY)) if isinstance(entry, Mapping) else None
        if bound is None:
            raise BenchmarkExecutionError(
                f"metric {name!r} has no usable frozen tolerance; admission should have refused it"
            )
        outcomes.append(ToleranceOutcome(name, float(value), float(bound)))
    return tuple(outcomes)


def run_benchmark(
    registry: QualificationRegistry,
    protocol_id: str,
    case: BenchmarkCase,
    *,
    created_at: str | None = None,
) -> BenchmarkRun:
    """Execute one frozen protocol against one prepared case and record it.

    The engines are called exactly as their public API defines them; no
    parameter is inferred and no default is substituted. Every outcome is
    recorded, including a failed or terminated run, and the status is derived
    from the frozen tolerance rule rather than chosen after seeing the metrics.
    """
    admission = admit_benchmark_candidate(registry, protocol_id)
    admission.require()

    protocol = registry.protocols[protocol_id]
    domain = str(protocol.inversion_parameters[PROTOCOL_PARAMETER_KEY])
    if case.domain != domain:
        raise BenchmarkExecutionError(
            f"the protocol targets {domain!r} but the case is {case.domain!r}"
        )
    reference = _reference_response(protocol)
    if reference is None:  # pragma: no cover - admission already refused this
        raise BenchmarkExecutionError("the protocol has no usable reference response")
    if len(reference) != case.active_observation_count():
        raise BenchmarkExecutionError(
            f"the reference response has {len(reference)} values but the case has "
            f"{case.active_observation_count()} active observations"
        )

    convergence, predicted = _execute(domain, protocol, case)

    metrics: dict[str, float] = {}
    tolerances: tuple[ToleranceOutcome, ...] = ()
    status = ComparisonStatus.NOT_VALIDATED
    if predicted is not None:
        measured = comparison_metrics(
            observed=reference,
            predicted=predicted,
        )
        metrics = {
            name: float(value)
            for name, value in measured.items()
            if name in protocol.comparison_metrics
        }
        tolerances = evaluate_tolerances(metrics, protocol)
        complete = len(tolerances) == len(protocol.comparison_metrics)
        if complete and all(item.passed for item in tolerances):
            status = ComparisonStatus.VALIDATED

    # The protocol must be byte-identical across the run, so a tolerance or
    # parameter cannot have been adjusted while the result was being produced.
    post_digest = protocol_digest(protocol)
    if post_digest != admission.protocol_sha256:
        raise BenchmarkExecutionError(
            "the frozen protocol changed during execution; the result is not recordable"
        )

    dataset = registry.datasets[protocol.dataset_id]
    provenance = BenchmarkProvenance(
        domain=domain,
        dataset_id=dataset.dataset_id,
        dataset_sha256=admission.dataset_sha256 or "",
        dataset_path=str(dataset.data_path),
        protocol_id=protocol.protocol_id,
        protocol_sha256_pre_execution=admission.protocol_sha256,
        protocol_sha256_post_execution=post_digest,
        inputs_sha256=case.inputs_sha256(),
        discretization_sha256=case.discretization_sha256(),
        reference_producer=str(protocol.expected_reference_result.get(REFERENCE_PRODUCER_KEY, "")),
        reference_provenance=str(
            protocol.expected_reference_result.get(REFERENCE_PROVENANCE_KEY, "")
        ),
        engine_source_sha256=_engine_source_digest(domain),
        environment={
            **environment_snapshot(),
            "numpy": _module_version("numpy"),
            "scipy": _module_version("scipy"),
        },
    )

    if predicted is None:
        notes = (
            f"{domain} did not produce a response ({convergence.outcome.value}: "
            f"{convergence.termination_reason}); the comparison is recorded as "
            "NOT VALIDATED and no metric is reported."
        )
    elif status is ComparisonStatus.VALIDATED:
        notes = (
            f"Every frozen metric for protocol {protocol.protocol_id!r} stayed inside its "
            "stated tolerance against the recorded independent reference; the result is "
            "scoped to this dataset and protocol pair only."
        )
    else:
        failed = ", ".join(item.metric for item in tolerances if not item.passed)
        notes = (
            f"Frozen metrics outside tolerance for protocol {protocol.protocol_id!r}: "
            f"{failed or 'none measured'}. The comparison is recorded as NOT VALIDATED "
            "without adjusting the protocol."
        )

    comparison = BenchmarkComparison(
        comparison_id=str(uuid.uuid4()),
        protocol_id=protocol.protocol_id,
        dataset_id=protocol.dataset_id,
        status=status,
        metrics=dict(metrics),
        convergence=convergence.to_dict(),
        notes=notes,
        created_at=(
            created_at
            if created_at is not None
            else datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        ),
        provenance=provenance.to_dict(),
    )
    registry.add_comparison(comparison)
    return BenchmarkRun(
        admission=admission,
        provenance=provenance,
        convergence=convergence,
        metrics=dict(metrics),
        tolerances=tolerances,
        status=status,
        comparison=comparison,
        notes=notes,
    )


def _module_version(name: str) -> str:
    module = __import__(name)
    return str(getattr(module, "__version__", "unknown"))
