"""External qualification dataset and benchmark metadata contracts.

This module stores provenance and protocol metadata only. It intentionally does
not bundle or download external data, and it never treats internal synthetic
data as an independent benchmark.

Admission rules (structural cross-references are *not* sufficient)
-----------------------------------------------------------------
``QualificationRegistry.add_comparison`` and ``QualificationRegistry.validate``
enforce the evidence a status actually requires:

``VALIDATED``
    requires a licensed independent dataset (``independent_benchmark_eligible``),
    a non-empty protocol reference result, a non-empty convergence record, a
    measured value for every metric the protocol declares, and a documented
    per-metric tolerance justification (``acceptable_tolerance[metric]["justification"]``).
``QUALITATIVELY CONSISTENT``
    requires a non-empty convergence record and measured values for every
    protocol metric. It deliberately does not require an independent dataset.
``NOT_VALIDATED``
    records an unsuccessful or unexecuted comparison and needs no metrics, so
    failures stay representable.

Record immutability
-------------------
Frozen dataclasses only prevent attribute rebinding: a mutable ``dict`` handed
to or returned from a record could still be edited afterwards and silently
change what a validation claims. Every mapping stored in a record is therefore
converted to a recursively read-only mapping on construction, and ``to_dict``
returns freshly built plain copies, so mutating a caller's object can neither
change nor invalidate a registered record.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Mapping


class DatasetClassification(str, Enum):
    INTERNAL_SYNTHETIC = "internal synthetic"
    PUBLISHED_REFERENCE = "published/reference"
    FIELD = "field"
    COMMERCIAL_REFERENCE = "commercial/reference"
    USER_SUPPLIED = "user-supplied"


class LicenseStatus(str, Enum):
    INTERNAL = "internal"
    PERMISSION_CONFIRMED = "permission confirmed"
    PERMISSION_PENDING = "permission pending"
    NOT_APPLICABLE = "not applicable"
    UNKNOWN = "unknown"


class ComparisonStatus(str, Enum):
    VALIDATED = "VALIDATED"
    QUALITATIVELY_CONSISTENT = "QUALITATIVELY CONSISTENT"
    NOT_VALIDATED = "NOT VALIDATED"


TOLERANCE_JUSTIFICATION_KEY = "justification"
"""Key every ``acceptable_tolerance`` entry must use to state its rationale."""


def freeze_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    """Return a recursively read-only copy of a nested mapping."""
    return MappingProxyType({str(key): _freeze(item) for key, item in dict(value).items()})


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return freeze_mapping(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def thaw(value: object) -> object:
    """Return a plain, JSON-serializable copy of a frozen record value."""
    if isinstance(value, Mapping):
        return {str(key): thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [thaw(item) for item in value]
    return value


@dataclass(frozen=True)
class QualificationDataset:
    """A dataset descriptor independent of the dataset bytes themselves."""

    dataset_id: str
    classification: DatasetClassification
    source: str
    license_status: LicenseStatus
    permission_note: str = ""
    acquisition_information: Mapping[str, object] = field(default_factory=dict)
    electrode_configuration: str = ""
    electrode_spacing: float | None = None
    coordinate_context: Mapping[str, object] = field(default_factory=dict)
    expected_reference_result: Mapping[str, object] = field(default_factory=dict)
    known_limitations: tuple[str, ...] = ()
    qualification_purpose: str = ""
    data_path: str | None = None

    def __post_init__(self) -> None:
        if not str(self.dataset_id).strip() or not str(self.source).strip():
            raise ValueError("dataset ID and source are required")
        if self.electrode_spacing is not None and self.electrode_spacing <= 0:
            raise ValueError("electrode spacing must be positive when supplied")
        if not str(self.qualification_purpose).strip():
            raise ValueError("qualification purpose is required")
        if self.classification is DatasetClassification.INTERNAL_SYNTHETIC:
            if self.license_status is not LicenseStatus.INTERNAL:
                raise ValueError("internal synthetic datasets must use internal license status")
        elif self.license_status in {LicenseStatus.UNKNOWN, LicenseStatus.NOT_APPLICABLE}:
            raise ValueError("external dataset license/permission status must be explicit")
        for name in (
            "acquisition_information", "coordinate_context", "expected_reference_result",
        ):
            object.__setattr__(self, name, freeze_mapping(getattr(self, name)))

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "QualificationDataset":
        try:
            spacing = payload.get("electrode_spacing")
            return cls(
                dataset_id=str(payload["dataset_id"]),
                classification=DatasetClassification(str(payload["classification"])),
                source=str(payload["source"]),
                license_status=LicenseStatus(str(payload["license_status"])),
                permission_note=str(payload.get("permission_note", "")),
                acquisition_information=dict(payload.get("acquisition_information", {})),
                electrode_configuration=str(payload.get("electrode_configuration", "")),
                electrode_spacing=float(spacing) if spacing is not None else None,
                coordinate_context=dict(payload.get("coordinate_context", {})),
                expected_reference_result=dict(payload.get("expected_reference_result", {})),
                known_limitations=tuple(str(item) for item in payload.get("known_limitations", [])),
                qualification_purpose=str(payload.get("qualification_purpose", "")),
                data_path=str(payload["data_path"]) if payload.get("data_path") is not None else None,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid qualification dataset manifest entry") from exc

    @property
    def independent_benchmark_eligible(self) -> bool:
        return (
            self.classification is not DatasetClassification.INTERNAL_SYNTHETIC
            and self.license_status is LicenseStatus.PERMISSION_CONFIRMED
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "dataset_id": str(self.dataset_id),
            "classification": self.classification.value,
            "source": str(self.source),
            "license_status": self.license_status.value,
            "permission_note": str(self.permission_note),
            "acquisition_information": thaw(self.acquisition_information),
            "electrode_configuration": str(self.electrode_configuration),
            "electrode_spacing": self.electrode_spacing,
            "coordinate_context": thaw(self.coordinate_context),
            "expected_reference_result": thaw(self.expected_reference_result),
            "known_limitations": [str(item) for item in self.known_limitations],
            "qualification_purpose": str(self.qualification_purpose),
            "data_path": self.data_path,
        }


@dataclass(frozen=True)
class BenchmarkProtocol:
    """Frozen comparison instructions that prevent tuning toward a result."""

    protocol_id: str
    dataset_id: str
    preprocessing_rules: tuple[str, ...]
    qc_rules: tuple[str, ...]
    inversion_parameters: Mapping[str, object]
    mesh_assumptions: Mapping[str, object]
    stopping_criteria: Mapping[str, object]
    expected_reference_result: Mapping[str, object]
    comparison_metrics: tuple[str, ...]
    acceptable_tolerance: Mapping[str, object]
    known_differences: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not str(self.protocol_id).strip() or not str(self.dataset_id).strip():
            raise ValueError("protocol and dataset IDs are required")
        if not self.comparison_metrics:
            raise ValueError("at least one comparison metric is required")
        if not self.stopping_criteria:
            raise ValueError("stopping criteria are required")
        for name in (
            "inversion_parameters", "mesh_assumptions", "stopping_criteria",
            "expected_reference_result", "acceptable_tolerance",
        ):
            object.__setattr__(self, name, freeze_mapping(getattr(self, name)))

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "BenchmarkProtocol":
        try:
            return cls(
                protocol_id=str(payload["protocol_id"]),
                dataset_id=str(payload["dataset_id"]),
                preprocessing_rules=tuple(str(item) for item in payload.get("preprocessing_rules", [])),
                qc_rules=tuple(str(item) for item in payload.get("qc_rules", [])),
                inversion_parameters=dict(payload.get("inversion_parameters", {})),
                mesh_assumptions=dict(payload.get("mesh_assumptions", {})),
                stopping_criteria=dict(payload["stopping_criteria"]),
                expected_reference_result=dict(payload.get("expected_reference_result", {})),
                comparison_metrics=tuple(str(item) for item in payload["comparison_metrics"]),
                acceptable_tolerance=dict(payload.get("acceptable_tolerance", {})),
                known_differences=tuple(str(item) for item in payload.get("known_differences", [])),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid benchmark protocol manifest entry") from exc

    def to_dict(self) -> dict[str, object]:
        return {
            "protocol_id": str(self.protocol_id),
            "dataset_id": str(self.dataset_id),
            "preprocessing_rules": [str(item) for item in self.preprocessing_rules],
            "qc_rules": [str(item) for item in self.qc_rules],
            "inversion_parameters": thaw(self.inversion_parameters),
            "mesh_assumptions": thaw(self.mesh_assumptions),
            "stopping_criteria": thaw(self.stopping_criteria),
            "expected_reference_result": thaw(self.expected_reference_result),
            "comparison_metrics": [str(item) for item in self.comparison_metrics],
            "acceptable_tolerance": thaw(self.acceptable_tolerance),
            "known_differences": [str(item) for item in self.known_differences],
        }


@dataclass(frozen=True)
class BenchmarkComparison:
    """An immutable record of a comparison, including unsuccessful outcomes.

    ``provenance`` carries the audit context for an executed comparison (dataset
    digest, canonical protocol digest, environment and engine identity). It is
    empty for a hand-recorded judgement, which is why it is optional; see
    :mod:`nix_ert.qualification.benchmark` for the executed form.
    """

    comparison_id: str
    protocol_id: str
    dataset_id: str
    status: ComparisonStatus
    metrics: Mapping[str, object]
    convergence: Mapping[str, object]
    notes: str
    created_at: str
    provenance: Mapping[str, object] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        protocol: BenchmarkProtocol,
        status: ComparisonStatus,
        metrics: Mapping[str, object],
        convergence: Mapping[str, object],
        notes: str,
        provenance: Mapping[str, object] | None = None,
    ) -> "BenchmarkComparison":
        if not notes.strip():
            raise ValueError("comparison notes are required")
        return cls(
            str(uuid.uuid4()), protocol.protocol_id, protocol.dataset_id, status,
            dict(metrics), dict(convergence), notes.strip(),
            datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            dict(provenance or {}),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "BenchmarkComparison":
        try:
            return cls(
                comparison_id=str(payload["comparison_id"]),
                protocol_id=str(payload["protocol_id"]),
                dataset_id=str(payload["dataset_id"]),
                status=ComparisonStatus(str(payload["status"])),
                metrics=dict(payload.get("metrics", {})),
                convergence=dict(payload.get("convergence", {})),
                notes=str(payload["notes"]),
                created_at=str(payload["created_at"]),
                provenance=dict(payload.get("provenance", {})),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid benchmark comparison manifest entry") from exc

    def __post_init__(self) -> None:
        if not str(self.notes).strip():
            raise ValueError("comparison notes are required")
        object.__setattr__(self, "metrics", freeze_mapping(self.metrics))
        object.__setattr__(self, "convergence", freeze_mapping(self.convergence))
        object.__setattr__(self, "provenance", freeze_mapping(self.provenance))

    def to_dict(self) -> dict[str, object]:
        return {
            "comparison_id": str(self.comparison_id),
            "protocol_id": str(self.protocol_id),
            "dataset_id": str(self.dataset_id),
            "status": self.status.value,
            "metrics": thaw(self.metrics),
            "convergence": thaw(self.convergence),
            "notes": str(self.notes),
            "created_at": str(self.created_at),
            "provenance": thaw(self.provenance),
        }


@dataclass
class QualificationRegistry:
    """In-memory registry suitable for a checked-in manifest or test fixture."""

    datasets: dict[str, QualificationDataset] = field(default_factory=dict)
    protocols: dict[str, BenchmarkProtocol] = field(default_factory=dict)
    comparisons: list[BenchmarkComparison] = field(default_factory=list)

    def add_dataset(self, dataset: QualificationDataset) -> None:
        if dataset.dataset_id in self.datasets:
            raise ValueError(f"dataset already registered: {dataset.dataset_id}")
        self.datasets[dataset.dataset_id] = dataset

    def add_protocol(self, protocol: BenchmarkProtocol) -> None:
        if protocol.dataset_id not in self.datasets:
            raise KeyError(f"unknown qualification dataset: {protocol.dataset_id}")
        dataset = self.datasets[protocol.dataset_id]
        if not dataset.independent_benchmark_eligible and protocol.expected_reference_result:
            raise ValueError("internal or unpermitted datasets cannot define independent reference results")
        if protocol.protocol_id in self.protocols:
            raise ValueError(f"protocol already registered: {protocol.protocol_id}")
        self.protocols[protocol.protocol_id] = protocol

    def admission_errors(
        self, protocol: BenchmarkProtocol, comparison: BenchmarkComparison,
    ) -> tuple[str, ...]:
        """Return the reasons a comparison status is not supported by evidence.

        Structural cross-references alone never establish a status. The checks
        below encode what each status actually requires; see the module
        docstring. Internal synthetic data can never satisfy ``VALIDATED``.
        """
        errors: list[str] = []
        dataset = self.datasets.get(protocol.dataset_id)
        if comparison.status is ComparisonStatus.NOT_VALIDATED:
            return ()
        if not comparison.metrics:
            errors.append(f"{comparison.status.value} requires measured metrics")
        if not comparison.convergence:
            errors.append(f"{comparison.status.value} requires a recorded convergence outcome")
        declared = [str(metric) for metric in protocol.comparison_metrics]
        missing = [metric for metric in declared if metric not in comparison.metrics]
        if missing:
            errors.append(
                f"{comparison.status.value} is missing measured metrics: {', '.join(missing)}"
            )
        if comparison.status is ComparisonStatus.QUALITATIVELY_CONSISTENT:
            return tuple(errors)
        if dataset is None:
            errors.append("VALIDATED requires a registered dataset")
        elif not dataset.independent_benchmark_eligible:
            errors.append(
                "VALIDATED requires an independent (non-synthetic, permission-confirmed) dataset; "
                f"{dataset.dataset_id} is {dataset.classification.value!r} with license "
                f"{dataset.license_status.value!r}"
            )
        if not protocol.expected_reference_result:
            errors.append("VALIDATED requires a recorded independent reference result")
        for metric in declared:
            entry = protocol.acceptable_tolerance.get(metric)
            if not isinstance(entry, Mapping):
                errors.append(f"VALIDATED requires an acceptable tolerance for metric {metric!r}")
                continue
            justification = entry.get(TOLERANCE_JUSTIFICATION_KEY)
            if not isinstance(justification, str) or not justification.strip():
                errors.append(
                    f"VALIDATED requires a written tolerance justification "
                    f"({TOLERANCE_JUSTIFICATION_KEY}) for metric {metric!r}"
                )
        return tuple(errors)

    def add_comparison(self, comparison: BenchmarkComparison) -> None:
        protocol = self.protocols.get(comparison.protocol_id)
        if protocol is None or protocol.dataset_id != comparison.dataset_id:
            raise KeyError("comparison does not match a registered protocol")
        errors = self.admission_errors(protocol, comparison)
        if errors:
            raise ValueError(
                f"comparison {comparison.comparison_id} cannot be recorded as "
                f"{comparison.status.value}: " + "; ".join(errors)
            )
        self.comparisons.append(comparison)

    def validate(self) -> None:
        """Recheck cross-record references *and* admission evidence."""
        for protocol in self.protocols.values():
            if protocol.dataset_id not in self.datasets:
                raise ValueError(f"protocol references unknown dataset: {protocol.dataset_id}")
            dataset = self.datasets[protocol.dataset_id]
            if not dataset.independent_benchmark_eligible and protocol.expected_reference_result:
                raise ValueError("internal or unpermitted datasets cannot define independent reference results")
        for comparison in self.comparisons:
            protocol = self.protocols.get(comparison.protocol_id)
            if protocol is None or protocol.dataset_id != comparison.dataset_id:
                raise ValueError("comparison references an incompatible protocol")
            errors = self.admission_errors(protocol, comparison)
            if errors:
                raise ValueError(
                    f"comparison {comparison.comparison_id} is recorded as "
                    f"{comparison.status.value} without the required evidence: " + "; ".join(errors)
                )

    @classmethod
    def from_json(cls, text: str) -> "QualificationRegistry":
        try:
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise ValueError("manifest root must be an object")
            datasets = payload.get("datasets", [])
            protocols = payload.get("protocols", [])
            comparisons = payload.get("comparisons", [])
            if not all(isinstance(items, list) for items in (datasets, protocols, comparisons)):
                raise ValueError("manifest collections must be arrays")
            registry = cls()
            for item in datasets:
                if not isinstance(item, Mapping):
                    raise ValueError("invalid dataset manifest entry")
                registry.add_dataset(QualificationDataset.from_dict(item))
            for item in protocols:
                if not isinstance(item, Mapping):
                    raise ValueError("invalid protocol manifest entry")
                registry.add_protocol(BenchmarkProtocol.from_dict(item))
            for item in comparisons:
                if not isinstance(item, Mapping):
                    raise ValueError("invalid comparison manifest entry")
                registry.add_comparison(BenchmarkComparison.from_dict(item))
            registry.validate()
            return registry
        except (json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
            raise ValueError("invalid qualification manifest") from exc

    @classmethod
    def read_manifest(cls, path: Path | str) -> "QualificationRegistry":
        try:
            return cls.from_json(Path(path).read_text(encoding="utf-8"))
        except OSError as exc:
            raise ValueError(f"unable to read qualification manifest: {path}") from exc

    def to_json(self) -> str:
        self.validate()
        payload = {
            "datasets": [item.to_dict() for item in self.datasets.values()],
            "protocols": [item.to_dict() for item in self.protocols.values()],
            "comparisons": [item.to_dict() for item in self.comparisons],
        }
        return json.dumps(payload, sort_keys=True, indent=2, default=str)

    def write_manifest(self, path: Path | str) -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8")


def internal_qualification_registry() -> QualificationRegistry:
    """Return the checked-in internal fixture registry with no external claims."""
    registry = QualificationRegistry()
    for dataset_id, purpose, limitations in (
        (
            "ves-layered-internal-v1",
            "Exercise layered-earth forward modeling and bounded VES inversion.",
            ("Internal synthetic only; no field noise model or external reference.",),
        ),
        (
            "ert-2d-anomaly-internal-v1",
            "Exercise flat finite-volume 2D forward modeling and inversion.",
            ("Internal synthetic only; no topography or commercial benchmark.",),
        ),
        (
            "ert-3d-anomaly-internal-v1",
            "Exercise small rectangular finite-volume 3D forward modeling and inversion.",
            ("Internal synthetic only; no topography or production-scale evidence.",),
        ),
    ):
        registry.add_dataset(
            QualificationDataset(
                dataset_id=dataset_id,
                classification=DatasetClassification.INTERNAL_SYNTHETIC,
                source="Internal deterministic fixture generated by NiX ERT",
                license_status=LicenseStatus.INTERNAL,
                known_limitations=limitations,
                qualification_purpose=purpose,
            )
        )
    return registry
