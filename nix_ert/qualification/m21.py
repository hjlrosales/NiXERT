"""M21 scientific qualification and benchmark-readiness evidence.

This module consumes the existing VES/2D/3D engines and qualification fixtures.
It records evidence without changing solver mathematics or turning synthetic
results into field or commercial validation claims.
"""

from __future__ import annotations

import hashlib
import json
import math
import platform
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from nix_ert import __version__
from nix_ert.ert.inversion2d import ERT2DError, ERTObservation, Mesh2D, invert_ert
from nix_ert.ert.inversion3d import ERT3DError, ERT3DObservation, Mesh3D, invert_ert3d
from nix_ert.qualification.datasets import ert2d_qualification, ert3d_qualification, ves_qualification
from nix_ert.qualification.release import QualificationManifest
from nix_ert.ves.engine import LayeredEarthModel, VESError, VESPoint, invert_ves


PROCEDURE_VERSION = "m21-scientific-qualification-v1"


class QualificationOutcome(str, Enum):
    CONVERGED = "CONVERGED"
    TERMINATED = "TERMINATED"
    FAILED = "FAILED"
    INVALID_INPUT = "INVALID_INPUT"
    CANCELLED = "CANCELLED"
    NOT_VALIDATED = "NOT_VALIDATED"


class EvidenceClass(str, Enum):
    VALIDATED = "VALIDATED"
    QUALITATIVELY_CONSISTENT = "QUALITATIVELY CONSISTENT"
    NOT_VALIDATED = "NOT VALIDATED"


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def environment_snapshot() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "software_version": __version__,
    }


@dataclass(frozen=True)
class ConvergenceRecord:
    domain: str
    outcome: QualificationOutcome
    initial_objective: float | None
    objective_history: tuple[float, ...]
    final_objective: float | None
    iteration_count: int
    termination_reason: str
    successful_completion: bool
    error: str | None = None

    def __post_init__(self) -> None:
        values = (*self.objective_history,)
        if any(not math.isfinite(value) for value in values):
            raise ValueError("objective history must be finite")
        if self.iteration_count < 0:
            raise ValueError("iteration_count cannot be negative")
        if self.outcome is QualificationOutcome.CONVERGED and not self.successful_completion:
            raise ValueError("converged records must be successful")
        if self.outcome in {QualificationOutcome.FAILED, QualificationOutcome.INVALID_INPUT} and not self.error:
            raise ValueError("failed or invalid records require an error")

    def to_dict(self) -> dict[str, object]:
        return {
            "domain": self.domain,
            "outcome": self.outcome.value,
            "initial_objective": self.initial_objective,
            "objective_history": list(self.objective_history),
            "final_objective": self.final_objective,
            "iteration_count": self.iteration_count,
            "termination_reason": self.termination_reason,
            "successful_completion": self.successful_completion,
            "error": self.error,
        }


@dataclass(frozen=True)
class SensitivityCase:
    case_id: str
    changed_parameter: str
    value: object
    outcome: QualificationOutcome
    objective: float | None
    metrics: Mapping[str, float]
    result_summary: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "changed_parameter": self.changed_parameter,
            "value": self.value,
            "outcome": self.outcome.value,
            "objective": self.objective,
            "metrics": dict(self.metrics),
            "result_summary": dict(self.result_summary),
        }


@dataclass(frozen=True)
class SensitivityStudy:
    study_id: str
    domain: str
    baseline_configuration: Mapping[str, object]
    cases: tuple[SensitivityCase, ...]
    interpretation: str

    def __post_init__(self) -> None:
        if not self.cases:
            raise ValueError("sensitivity study requires at least one case")
        if not self.interpretation.strip():
            raise ValueError("sensitivity interpretation is required")

    def to_dict(self) -> dict[str, object]:
        return {
            "study_id": self.study_id,
            "domain": self.domain,
            "baseline_configuration": dict(self.baseline_configuration),
            "cases": [case.to_dict() for case in self.cases],
            "interpretation": self.interpretation,
        }


@dataclass(frozen=True)
class M21QualificationRecord:
    manifest: QualificationManifest
    evidence_class: EvidenceClass
    convergence: ConvergenceRecord
    metrics: Mapping[str, float]
    studies: tuple[SensitivityStudy, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "manifest": self.manifest.to_dict() | {"manifest_sha256": self.manifest.manifest_sha256},
            "evidence_class": self.evidence_class.value,
            "convergence": self.convergence.to_dict(),
            "metrics": dict(self.metrics),
            "studies": [study.to_dict() for study in self.studies],
        }


@dataclass(frozen=True)
class ExternalBenchmarkReadiness:
    benchmark_id: str
    dataset_id: str
    status: EvidenceClass = EvidenceClass.NOT_VALIDATED
    reason: str = ""
    required_evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status is not EvidenceClass.NOT_VALIDATED:
            raise ValueError("M21 external benchmark records require explicit evidence before validation")
        if not self.reason.strip():
            raise ValueError("an external benchmark readiness reason is required")

    def to_dict(self) -> dict[str, object]:
        return {
            "benchmark_id": self.benchmark_id,
            "dataset_id": self.dataset_id,
            "status": self.status.value,
            "reason": self.reason,
            "required_evidence": list(self.required_evidence),
        }


@dataclass(frozen=True)
class M21QualificationReport:
    procedure_version: str
    environment: Mapping[str, str]
    records: tuple[M21QualificationRecord, ...]
    external_benchmarks: tuple[ExternalBenchmarkReadiness, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.procedure_version != PROCEDURE_VERSION:
            raise ValueError("unsupported M21 procedure version")
        if not self.records:
            raise ValueError("qualification report requires at least one record")

    @property
    def report_sha256(self) -> str:
        return _sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "procedure_version": self.procedure_version,
            "environment": dict(self.environment),
            "records": [record.to_dict() for record in self.records],
            "external_benchmarks": [item.to_dict() for item in self.external_benchmarks],
            "limitations": list(self.limitations),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict() | {"report_sha256": self.report_sha256}, sort_keys=True, indent=2, ensure_ascii=True, default=str) + "\n"

    def to_markdown(self) -> str:
        lines = [
            "# M21 scientific qualification result", "",
            f"**Procedure:** `{self.procedure_version}`  ",
            f"**Report SHA-256:** `{self.report_sha256}`", "",
            "## Evidence summary", "",
        ]
        for record in self.records:
            lines.append(
                f"- `{record.manifest.dataset.get('dataset_id')}` ({record.manifest.project.get('survey_id')}): "
                f"{record.evidence_class.value}; outcome `{record.convergence.outcome.value}`; "
                f"final objective `{record.convergence.final_objective}`"
            )
        lines.extend(["", "## External benchmark readiness", ""])
        for benchmark in self.external_benchmarks:
            lines.append(f"- `{benchmark.benchmark_id}`: **{benchmark.status.value}** — {benchmark.reason}")
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in self.limitations)
        return "\n".join(lines) + "\n"

    def write_json(self, path: str) -> None:
        from pathlib import Path
        Path(path).write_text(self.to_json(), encoding="utf-8")

    def write_markdown(self, path: str) -> None:
        from pathlib import Path
        Path(path).write_text(self.to_markdown(), encoding="utf-8")


def build_m21_manifest(
    manifest_id: str,
    *,
    domain: str,
    dataset_id: str,
    project_id: str,
    survey_id: str,
    configuration: Mapping[str, object],
    expected_outputs: Mapping[str, object] | None = None,
    source_sha256: str | None = None,
) -> QualificationManifest:
    """Reuse the M19 manifest contract with an M21 procedure identifier."""
    return QualificationManifest(
        manifest_id=manifest_id,
        dataset={"dataset_id": dataset_id, "classification": "internal synthetic", "source_sha256": source_sha256},
        project={"project_id": project_id, "survey_id": survey_id, "domain": domain},
        processing={"qualification_procedure": PROCEDURE_VERSION},
        inversion=dict(configuration),
        configuration=environment_snapshot(),
        expected_outputs=dict(expected_outputs or {}),
        procedure_version=PROCEDURE_VERSION,
    )


def objective_from_residuals(residuals: Sequence[float]) -> float:
    values = np.asarray(tuple(float(value) for value in residuals), dtype=float)
    if values.size == 0 or not np.all(np.isfinite(values)):
        raise ValueError("residuals must be a finite non-empty sequence")
    return float(np.sqrt(np.mean(values**2)))


def comparison_metrics(
    observed: Sequence[float], predicted: Sequence[float],
    *, reference_model: Sequence[float] | None = None, result_model: Sequence[float] | None = None,
    model_discretization: object | None = None,
) -> dict[str, float]:
    """Return deterministic numerical metrics; these are not geological accuracy claims.

    A model L2 difference is only defined when both model vectors live in the
    *same* parameter space: matching length is not enough, because two meshes
    with the same cell count but different cell locations or volumes are not
    comparable parameter-wise. Callers must therefore supply a
    ``model_discretization`` identifier (mesh edges plus the parameter order) and
    it is recorded with the metrics. A missing identifier is rejected instead of
    silently producing a meaningless number.
    """
    observed_array = np.asarray(tuple(observed), dtype=float)
    predicted_array = np.asarray(tuple(predicted), dtype=float)
    if observed_array.shape != predicted_array.shape or observed_array.size == 0:
        raise ValueError("observed and predicted sequences must have equal non-zero length")
    if not np.all(np.isfinite(observed_array)) or not np.all(np.isfinite(predicted_array)):
        raise ValueError("observed and predicted values must be finite")
    difference = predicted_array - observed_array
    metrics = {
        "rmse": float(np.sqrt(np.mean(difference**2))),
        "relative_rmse": float(np.sqrt(np.mean((difference / np.maximum(np.abs(observed_array), np.finfo(float).eps))**2))),
        "max_absolute_difference": float(np.max(np.abs(difference))),
        "log10_rmse": float(np.sqrt(np.mean((np.log10(np.maximum(predicted_array, np.finfo(float).tiny)) - np.log10(np.maximum(observed_array, np.finfo(float).tiny)))**2))),
    }
    if reference_model is not None or result_model is not None:
        if reference_model is None or result_model is None:
            raise ValueError("reference_model and result_model must be supplied together")
        reference = np.asarray(tuple(reference_model), dtype=float)
        result = np.asarray(tuple(result_model), dtype=float)
        if reference.shape != result.shape or reference.size == 0 or not np.all(np.isfinite(reference)) or not np.all(np.isfinite(result)):
            raise ValueError("model sequences must be finite and have equal non-zero length")
        if model_discretization is None:
            raise ValueError(
                "model comparison requires an explicit shared discretization/parameter identity"
            )
        metrics["model_l2_difference"] = float(np.linalg.norm(result - reference))
        metrics["model_relative_l2_difference"] = float(np.linalg.norm(result - reference) / max(np.linalg.norm(reference), np.finfo(float).eps))
    return metrics


def _ert2d_run(
    fixture, initial: float, *, damping: float, max_iterations: int,
) -> tuple[QualificationOutcome, ConvergenceRecord, object]:
    try:
        result = invert_ert(fixture.noisy_observations, fixture.mesh, initial, damping=damping, max_iterations=max_iterations)
        history = tuple(item.rms_log10 for item in result.iterations)
        full_history = (history[0],) if not history else history
        outcome = QualificationOutcome.CONVERGED if result.converged else QualificationOutcome.TERMINATED
        record = ConvergenceRecord("2D ERT", outcome, full_history[0] if full_history else result.rms_log10, full_history, result.rms_log10, len(result.iterations), result.message, True)
        return outcome, record, result
    except (ERT2DError, ValueError) as exc:
        return QualificationOutcome.INVALID_INPUT, ConvergenceRecord("2D ERT", QualificationOutcome.INVALID_INPUT, None, (), None, 0, "input rejected", False, str(exc)), None
    except Exception as exc:  # numerical failures remain evidence, not silent skips
        return QualificationOutcome.FAILED, ConvergenceRecord("2D ERT", QualificationOutcome.FAILED, None, (), None, 0, "solver failure", False, str(exc)), None


def _ves_run(fixture, initial: LayeredEarthModel, *, max_nfev: int) -> tuple[QualificationOutcome, ConvergenceRecord, object]:
    try:
        result = invert_ves(fixture.noisy_points, initial, max_nfev=max_nfev)
        objective = result.rms_log10
        outcome = QualificationOutcome.CONVERGED if result.converged else QualificationOutcome.TERMINATED
        record = ConvergenceRecord("VES", outcome, None, (objective,), objective, result.iterations, result.message, True)
        return outcome, record, result
    except (VESError, ValueError) as exc:
        return QualificationOutcome.INVALID_INPUT, ConvergenceRecord("VES", QualificationOutcome.INVALID_INPUT, None, (), None, 0, "input rejected", False, str(exc)), None
    except Exception as exc:
        return QualificationOutcome.FAILED, ConvergenceRecord("VES", QualificationOutcome.FAILED, None, (), None, 0, "solver failure", False, str(exc)), None


def _ert3d_run(fixture, initial: float, *, damping: float, max_iterations: int) -> tuple[QualificationOutcome, ConvergenceRecord, object]:
    try:
        model, predicted, history, converged = invert_ert3d(fixture.noisy_observations, fixture.mesh, fixture.electrodes, initial, damping=damping, max_iterations=max_iterations)
        outcome = QualificationOutcome.CONVERGED if converged else QualificationOutcome.TERMINATED
        objective = float(history[-1]) if history else None
        record = ConvergenceRecord("3D ERT", outcome, float(history[0]) if history else None, tuple(float(value) for value in history), objective, len(history), "converged" if converged else "maximum iterations reached", True)
        return outcome, record, (model, predicted)
    except (ERT3DError, ValueError) as exc:
        return QualificationOutcome.INVALID_INPUT, ConvergenceRecord("3D ERT", QualificationOutcome.INVALID_INPUT, None, (), None, 0, "input rejected", False, str(exc)), None
    except Exception as exc:
        return QualificationOutcome.FAILED, ConvergenceRecord("3D ERT", QualificationOutcome.FAILED, None, (), None, 0, "solver failure", False, str(exc)), None


def cancelled_record(domain: str, reason: str = "cancelled before persistence") -> ConvergenceRecord:
    return ConvergenceRecord(domain, QualificationOutcome.CANCELLED, None, (), None, 0, reason, False)


def _make_2d_case(
    fixture, case_id: str, parameter: str, value: object, *, initial: float = 1.0,
    damping: float = 0.3, max_iterations: int = 1, mesh: Mesh2D | None = None,
    observations: Sequence[ERTObservation] | None = None, baseline_prediction: Sequence[float] | None = None,
) -> SensitivityCase:
    selected_mesh = mesh or fixture.mesh
    selected_observations = tuple(observations or fixture.noisy_observations)
    outcome, convergence, result = _ert2d_run(fixture.__class__(fixture.spec, selected_mesh, fixture.observations, selected_observations, fixture.true_model), initial, damping=damping, max_iterations=max_iterations)
    metrics = {}
    summary: dict[str, object] = {"termination_reason": convergence.termination_reason, "iteration_count": convergence.iteration_count}
    if result is not None:
        if baseline_prediction is not None:
            metrics = comparison_metrics(baseline_prediction, result.predicted)
        summary.update({"rms_log10": result.rms_log10, "rms_percent": result.rms_percent, "resistivity_min": float(np.min(result.resistivity)), "resistivity_max": float(np.max(result.resistivity))})
    return SensitivityCase(case_id, parameter, value, outcome, convergence.final_objective, metrics, summary)


def run_2d_sensitivity_studies() -> tuple[SensitivityStudy, ...]:
    """Run bounded deterministic studies against the existing 2D fixture."""
    fixture = ert2d_qualification()
    _, baseline_convergence, baseline = _ert2d_run(fixture, 1.0, damping=0.3, max_iterations=1)
    baseline_prediction = baseline.predicted if baseline is not None else ()
    starting = tuple(_make_2d_case(fixture, f"starting-{value:g}", "starting_resistivity", value, initial=value, baseline_prediction=baseline_prediction) for value in (0.5, 2.0))
    damping = tuple(_make_2d_case(fixture, f"damping-{value:g}", "damping", value, damping=value, baseline_prediction=baseline_prediction) for value in (0.1, 0.8))
    stopping = tuple(_make_2d_case(fixture, f"iterations-{value}", "max_iterations", value, max_iterations=value, baseline_prediction=baseline_prediction) for value in (1, 2))
    meshes = tuple(
        _make_2d_case(fixture, f"mesh-nz-{value}", "mesh_nz", value, mesh=Mesh2D.from_electrodes(fixture.mesh.x_centres, nz=value, depth=3.0), baseline_prediction=baseline_prediction)
        for value in (2, 4)
    )
    factors = (1.01, 0.99, 1.02, 0.98, 1.01, 0.99)
    noisy = tuple(ERTObservation(item.a, item.b, item.m, item.n, item.apparent_resistivity * factor) for item, factor in zip(fixture.observations, factors))
    noise = (_make_2d_case(fixture, "noise-deterministic-v1", "deterministic_noise", "multiplicative_factors_v1", observations=noisy, baseline_prediction=baseline_prediction),)
    interpretation = "Measured differences are configuration sensitivity evidence only; no universal pass/fail threshold is asserted."
    return (
        SensitivityStudy("m21-ert2d-starting-model-v1", "2D ERT", {"damping": 0.3, "max_iterations": 1, "initial_resistivity": 1.0}, starting, interpretation),
        SensitivityStudy("m21-ert2d-mesh-v1", "2D ERT", {"mesh_nz": fixture.mesh.nz}, meshes, interpretation),
        SensitivityStudy("m21-ert2d-damping-v1", "2D ERT", {"damping": 0.3}, damping, interpretation),
        SensitivityStudy("m21-ert2d-stopping-v1", "2D ERT", {"max_iterations": 1}, stopping, interpretation),
        SensitivityStudy("m21-ert2d-noise-v1", "2D ERT", {"noise": "none"}, noise, interpretation),
    )


def run_ves_starting_model_sensitivity() -> SensitivityStudy:
    fixture = ves_qualification()
    _, _, baseline = _ves_run(fixture, LayeredEarthModel((80.0, 30.0, 180.0), (4.0, 10.0)), max_nfev=20)
    cases: list[SensitivityCase] = []
    for case_id, model in (("ves-starting-low", LayeredEarthModel((50.0, 15.0, 120.0), (3.0, 8.0))), ("ves-starting-high", LayeredEarthModel((150.0, 50.0, 300.0), (8.0, 16.0)))):
        outcome, convergence, result = _ves_run(fixture, model, max_nfev=20)
        metrics = comparison_metrics(baseline.predicted, result.predicted) if baseline is not None and result is not None else {}
        cases.append(SensitivityCase(case_id, "starting_model", {"resistivities": list(model.resistivities), "thicknesses": list(model.thicknesses)}, outcome, convergence.final_objective, metrics, {"iterations": convergence.iteration_count}))
    return SensitivityStudy("m21-ves-starting-model-v1", "VES", {"max_nfev": 20}, tuple(cases), "Measured differences describe non-uniqueness and starting-model sensitivity; no geological threshold is asserted.")


def run_m21_internal_qualification() -> M21QualificationReport:
    """Run one bounded deterministic qualification record per existing domain."""
    records: list[M21QualificationRecord] = []

    ves = ves_qualification()
    _, ves_convergence, ves_result = _ves_run(ves, LayeredEarthModel((80.0, 30.0, 180.0), (4.0, 10.0)), max_nfev=20)
    ves_metrics = comparison_metrics(ves_result.predicted, [point.apparent_resistivity for point in ves.noisy_points]) if ves_result else {}
    records.append(M21QualificationRecord(
        build_m21_manifest("m21-ves-internal-v1", domain="VES", dataset_id=ves.spec.name, project_id="qualification", survey_id="ves", configuration={"initial_model": {"resistivities": [80.0, 30.0, 180.0], "thicknesses": [4.0, 10.0]}, "max_nfev": 20}, expected_outputs={"status": "internal synthetic"}),
        EvidenceClass.QUALITATIVELY_CONSISTENT, ves_convergence, ves_metrics,
    ))

    ert2d = ert2d_qualification()
    _, ert2d_convergence, ert2d_result = _ert2d_run(ert2d, 1.0, damping=0.3, max_iterations=1)
    ert2d_metrics = comparison_metrics([item.apparent_resistivity for item in ert2d.noisy_observations], ert2d_result.predicted) if ert2d_result else {}
    records.append(M21QualificationRecord(
        build_m21_manifest("m21-ert2d-internal-v1", domain="2D ERT", dataset_id=ert2d.spec.name, project_id="qualification", survey_id="ert2d", configuration={"initial_resistivity": 1.0, "damping": 0.3, "max_iterations": 1, "mesh_cells": ert2d.mesh.cell_count}, expected_outputs={"status": "internal synthetic"}),
        EvidenceClass.QUALITATIVELY_CONSISTENT, ert2d_convergence, ert2d_metrics,
        run_2d_sensitivity_studies(),
    ))

    ert3d = ert3d_qualification()
    _, ert3d_convergence, ert3d_result = _ert3d_run(ert3d, 1.0, damping=0.5, max_iterations=1)
    ert3d_metrics = comparison_metrics([item.apparent_resistivity for item in ert3d.noisy_observations], ert3d_result[1]) if ert3d_result else {}
    records.append(M21QualificationRecord(
        build_m21_manifest("m21-ert3d-internal-v1", domain="3D ERT", dataset_id=ert3d.spec.name, project_id="qualification", survey_id="ert3d", configuration={"initial_resistivity": 1.0, "damping": 0.5, "max_iterations": 1, "mesh_cells": ert3d.mesh.cell_count}, expected_outputs={"status": "internal synthetic"}),
        EvidenceClass.QUALITATIVELY_CONSISTENT, ert3d_convergence, ert3d_metrics,
    ))

    return M21QualificationReport(
        PROCEDURE_VERSION, environment_snapshot(), tuple(records),
        (ExternalBenchmarkReadiness(
            "m21-external-reference-gate", "no-authorized-reference-dataset",
            reason="No legally usable independent dataset with trustworthy expected results is available in the repository.",
            required_evidence=("licensed dataset bytes", "known acquisition/geometry metadata", "trustworthy reference result", "frozen comparison protocol"),
        ),),
        (
            "Internal synthetic evidence is not an independent benchmark.",
            "Residual and convergence behavior do not establish geological certainty or uniqueness.",
            "Topography-aware inversion and uncertainty/resolution analysis are not implemented.",
            "M15 physical LS2 validation remains pending and the ABEM importer remains NOT_READY.",
        ),
    )


__all__ = [
    "PROCEDURE_VERSION", "QualificationOutcome", "EvidenceClass", "ConvergenceRecord",
    "SensitivityCase", "SensitivityStudy", "M21QualificationRecord", "ExternalBenchmarkReadiness",
    "M21QualificationReport", "build_m21_manifest", "objective_from_residuals",
    "comparison_metrics", "cancelled_record", "run_2d_sensitivity_studies",
    "run_ves_starting_model_sensitivity", "run_m21_internal_qualification",
    "environment_snapshot",
]
