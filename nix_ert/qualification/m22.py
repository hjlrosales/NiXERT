"""M22 inversion robustness and scientific hardening evidence.

M22 does not replace any inversion algorithm. It adds

1. a **common convergence/outcome contract** that normalizes how the VES, 2D ERT,
   and 3D ERT engines report bounded completion, convergence, invalid input,
   numerical failure, and cancellation;
2. **expanded bounded deterministic studies** (starting models, damping,
   mesh/domain resolution, stopping limits, deterministic noise) for every
   engine that exposes the corresponding control; and
3. machine-readable and human-readable qualification artifacts that keep
   measured evidence, unavailable evidence, and unvalidated claims separate.

Outcome semantics are strict:

* ``CONVERGED`` requires that the engine's own convergence criterion was
  satisfied. Solver completion alone is never enough.
* ``TERMINATED`` means the evidence only establishes bounded completion, for
  example a configured iteration/evaluation limit.
* ``FAILED`` requires a demonstrated numerical/solver failure. Reaching a
  configured limit is never classified as ``FAILED``.
* ``INVALID_INPUT`` requires rejection before any scientific result.
* ``CANCELLED`` requires a cancellation request and no committed model state.

Numerical evidence recorded here (objective trajectories, reproducibility, model
differences) does **not** establish scientific validity, geological
correctness, field accuracy, uniqueness, or agreement with an external
reference. Those remain separate and unvalidated.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

import numpy as np

from nix_ert.ert.inversion2d import (
    FORWARD_FACTORIZATION_PHASE,
    ERT2DError,
    ERT2DNumericalError,
    ERTObservation,
    Mesh2D,
    forward_apparent_resistivity as forward_2d,
    invert_ert,
)
from nix_ert.ert.inversion3d import (
    ERT3D_CONVERGENCE_RMS,
    ERT3DError,
    ERT3DNumericalError,
    ERT3DObservation,
    Mesh3D,
    invert_ert3d,
)
from nix_ert.qualification.datasets import (
    ert2d_qualification,
    ert3d_qualification,
    ves_qualification,
)
from nix_ert.qualification.m21 import (
    EvidenceClass,
    ExternalBenchmarkReadiness,
    QualificationOutcome,
    SensitivityCase,
    SensitivityStudy,
    comparison_metrics,
    environment_snapshot,
)
from nix_ert.qualification.release import QualificationManifest
from nix_ert.ves.engine import (
    LayeredEarthModel,
    VESError,
    VESNumericalError,
    invert_ves,
    layered_apparent_resistivity,
    ves_apparent_resistivity,
)


PROCEDURE_VERSION = "m22-inversion-hardening-v2"
"""Procedure identifier; v2 records the failure phases added by M23."""

SUPERSEDED_ARTIFACTS: tuple[Mapping[str, object], ...] = (
    {
        "artifact": "docs/m22_scientific_hardening.json",
        "artifact_report_sha256": "df6847c8073f86bda8e6e8d6aef178780972795307ba5b4c95efd17c0be37367",
        "artifact_procedure_version": "m22-inversion-hardening-v1",
        "status": "SUPERSEDED",
        "superseded_by": "docs/m22_scientific_hardening.json (m22-inversion-hardening-v2)",
        "reason": (
            "The M23 audit-corrected forward physics changed the numbers this artifact records. The A1 VES "
            "layered-earth kernel correction changes every VES objective, trajectory, and model; the A2/A3 "
            "nonuniform-mesh transmissibility corrections change every 2D and 3D nonuniform-mesh forward "
            "response; and the B1-B4 integrity corrections change the recorded failure phases, the admission "
            "rules, the model-comparison discretization requirement, and the VES input-failure behaviour. "
            "The v1 records were produced by the pre-correction implementation."
        ),
        "historical_evidence_retained": (
            "The superseded v1 values are not overwritten silently: the pre-correction 3D reporting values are "
            "retained in the `corrections` block of docs/m21_scientific_qualification.json, the pre-correction "
            "VES and nonuniform-mesh values are recorded in docs/m23_forward_physics_correction.md and the "
            "M23 evidence notes, and the changelog records the transition."
        ),
    },
)
"""Artifacts whose recorded numbers the M23 corrections invalidated (kept, never silently overwritten)."""

PHASE_NOT_APPLICABLE = "not_applicable"
PHASE_INPUT_VALIDATION = "input_validation"
PHASE_INITIAL_MODEL = "initial_model_evaluation"
PHASE_FORWARD_MODEL = "forward_model_evaluation"
PHASE_FORWARD_FACTORIZATION = FORWARD_FACTORIZATION_PHASE
"""The accepted forward problem's system could not be factorized.

Distinct from ``PHASE_FORWARD_MODEL`` and ``PHASE_SOLVER`` so that a
factorization failure is never reported as a solver-update failure when no
update was attempted, and never as invalid input.
"""
PHASE_SOLVER = "solver_update"

FAILURE_PHASES = (
    PHASE_NOT_APPLICABLE,
    PHASE_INPUT_VALIDATION,
    PHASE_INITIAL_MODEL,
    PHASE_FORWARD_MODEL,
    PHASE_FORWARD_FACTORIZATION,
    PHASE_SOLVER,
)

HISTORY_RECORDED = "RECORDED"
HISTORY_UNAVAILABLE = "HISTORY_UNAVAILABLE"

MAXIMUM_UNITS_ITERATIONS = "iterations"
MAXIMUM_UNITS_EVALUATIONS = "function_evaluations"
MAXIMUM_UNITS_NOT_APPLICABLE = "not_applicable"

_INITIAL_OBJECTIVE_SOURCE = "qualification forward evaluation at the declared initial parameters"
_INITIAL_OBJECTIVE_UNAVAILABLE = "unavailable: no finite initial-model evaluation was produced"

_VES_CRITERION = "scipy.optimize.least_squares termination with xtol=ftol=gtol=1e-8 within max_nfev"
_VES_TOLERANCE = 1e-8
_VES_BASELINE_INITIAL = LayeredEarthModel((80.0, 30.0, 180.0), (4.0, 10.0))
_ERT2D_CRITERION = "log10-RMS <= configured convergence_rms"
_ERT3D_CRITERION = "log10-RMS <= ERT3D_CONVERGENCE_RMS"

# Deterministic M22 noise realizations. These are deliberately different from
# the noise factors baked into the M21 fixtures, so the M22 noise study is an
# independent deterministic realization rather than a repeat of the fixture.
VES_NOISE_FACTORS_V1 = (1.02, 0.97, 1.03, 0.95, 1.01, 1.04, 0.98, 1.02)
ERT2D_NOISE_FACTORS_V1 = (0.95, 1.05, 0.97, 1.03, 0.99, 1.02)
ERT3D_NOISE_FACTORS_V1 = (0.96, 1.05)


class FinalModelStatus(str, Enum):
    """Whether the run produced a model that may be treated as a result."""

    VALID = "VALID"
    INVALID = "INVALID"
    NOT_PRODUCED = "NOT_PRODUCED"


@dataclass(frozen=True)
class TrajectoryPoint:
    """One recorded objective evaluation, with its limited solver state."""

    step: int
    objective: float
    origin: str
    solver_state: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.step < 1:
            raise ValueError("trajectory step numbers are 1-based")
        if not math.isfinite(self.objective):
            raise ValueError("trajectory objectives must be finite")
        if not self.origin.strip():
            raise ValueError("trajectory points require an origin")

    def to_dict(self) -> dict[str, object]:
        return {
            "step": self.step,
            "objective": self.objective,
            "origin": self.origin,
            "solver_state": dict(self.solver_state),
        }


@dataclass(frozen=True)
class ConvergenceContract:
    """Common convergence/outcome record for VES, 2D ERT, and 3D ERT runs.

    The record states what was measured, not what the result means. A recorded
    objective history always begins at the declared initial objective and always
    ends at the declared final objective, so no caller has to infer which model a
    stored objective belongs to.
    """

    domain: str
    outcome: QualificationOutcome
    history_status: str
    objective_history: tuple[float, ...]
    trajectory: tuple[TrajectoryPoint, ...]
    initial_objective: float | None
    initial_objective_source: str
    final_objective: float | None
    iteration_count: int | None
    evaluation_count: int | None
    configured_maximum: int | None
    configured_maximum_units: str
    configured_maximum_reached: bool
    convergence_criterion: str
    convergence_tolerance: float | None
    convergence_criterion_satisfied: bool
    termination_reason: str
    cancellation_requested: bool
    invalid_input: bool
    numerical_failure: bool
    final_model_status: FinalModelStatus
    error: str | None = None
    error_class: str | None = None
    failure_phase: str = PHASE_NOT_APPLICABLE
    """Where an unsuccessful run failed (see :data:`FAILURE_PHASES`).

    ``input_validation`` means rejected before evaluation, ``forward_factorization``
    means the accepted forward problem's system could not be factorized,
    ``forward_model_evaluation`` means the accepted inputs failed elsewhere while
    the response was computed, and ``solver_update`` means the numerical
    solver/update failed. Preserving the phase keeps a numerical failure
    distinguishable from a configuration error, and keeps a factorization
    failure distinguishable from a model update that never happened.
    """

    def __post_init__(self) -> None:
        if not self.domain.strip():
            raise ValueError("a convergence contract requires a domain")
        if self.failure_phase not in FAILURE_PHASES:
            raise ValueError("unsupported failure phase")
        if self.history_status not in {HISTORY_RECORDED, HISTORY_UNAVAILABLE}:
            raise ValueError("unsupported objective-history status")
        if self.configured_maximum_units not in {
            MAXIMUM_UNITS_ITERATIONS,
            MAXIMUM_UNITS_EVALUATIONS,
            MAXIMUM_UNITS_NOT_APPLICABLE,
        }:
            raise ValueError("unsupported configured-maximum unit")
        if self.history_status == HISTORY_UNAVAILABLE and (self.objective_history or self.trajectory):
            raise ValueError("unavailable objective history must stay empty; it is never invented")
        if self.history_status == HISTORY_RECORDED and not (self.objective_history and self.trajectory):
            raise ValueError("a recorded objective history requires at least one evaluation")
        expected_history = tuple(point.objective for point in self.trajectory)
        if self.objective_history != expected_history:
            raise ValueError("objective_history must match the recorded trajectory")
        if any(point.step != index for index, point in enumerate(self.trajectory, start=1)):
            raise ValueError("trajectory steps must be consecutive and 1-based")
        if any(not math.isfinite(value) for value in self.objective_history):
            raise ValueError("objective history values must be finite")
        for count in (self.iteration_count, self.evaluation_count, self.configured_maximum):
            if count is not None and count < 0:
                raise ValueError("counts and limits cannot be negative")
        if not self.convergence_criterion.strip():
            raise ValueError("a convergence criterion description is required")
        if not self.termination_reason.strip():
            raise ValueError("a termination reason is required")
        if self.final_model_status is FinalModelStatus.VALID and self.final_objective is None:
            raise ValueError("a valid final model requires a measured final objective")
        if self.objective_history and self.initial_objective is not None:
            if abs(self.objective_history[0] - self.initial_objective) > 1e-12:
                raise ValueError("recorded history must begin at the declared initial objective")
        if self.objective_history and self.final_objective is not None:
            if abs(self.objective_history[-1] - self.final_objective) > 1e-12:
                raise ValueError("recorded history must end at the declared final objective")
        self._validate_outcome_semantics()

    def _validate_outcome_semantics(self) -> None:
        bounded = self.outcome in {QualificationOutcome.CONVERGED, QualificationOutcome.TERMINATED}
        if self.outcome is QualificationOutcome.CONVERGED:
            if not self.convergence_criterion_satisfied:
                raise ValueError("CONVERGED requires a satisfied engine convergence criterion")
        if self.outcome is QualificationOutcome.TERMINATED:
            if self.convergence_criterion_satisfied:
                raise ValueError("TERMINATED must not claim a satisfied convergence criterion")
        if self.outcome is QualificationOutcome.FAILED:
            if not (self.numerical_failure and self.error):
                raise ValueError("FAILED requires a demonstrated numerical failure and an error")
        if self.outcome is QualificationOutcome.INVALID_INPUT:
            if not (self.invalid_input and self.error):
                raise ValueError("INVALID_INPUT requires rejected input and an error")
            if self.final_model_status is not FinalModelStatus.NOT_PRODUCED:
                raise ValueError("rejected input cannot produce a final model")
            if self.failure_phase != PHASE_INPUT_VALIDATION:
                raise ValueError(
                    "INVALID_INPUT must record the input_validation phase; a numerical "
                    "failure in the forward model or solver is FAILED, not INVALID_INPUT"
                )
        if self.outcome is QualificationOutcome.FAILED:
            if self.failure_phase not in {
                PHASE_FORWARD_MODEL, PHASE_FORWARD_FACTORIZATION, PHASE_SOLVER, PHASE_INITIAL_MODEL,
            }:
                raise ValueError(
                    "FAILED must record the forward-model, forward-factorization, "
                    "initial-model, or solver failure phase"
                )
        if self.outcome is QualificationOutcome.CANCELLED:
            if not self.cancellation_requested:
                raise ValueError("CANCELLED requires a cancellation request")
            if self.final_model_status is FinalModelStatus.VALID:
                raise ValueError("a cancelled run must not commit a final model")
            if self.error:
                raise ValueError("CANCELLED is a safe stop, not an error")
        if bounded and any((self.cancellation_requested, self.invalid_input, self.numerical_failure)):
            raise ValueError("bounded completion cannot also be cancelled, invalid, or failed")
        if bounded and self.error:
            raise ValueError("bounded completion cannot carry a solver error")
        if bounded and self.final_model_status is not FinalModelStatus.VALID:
            raise ValueError("bounded completion must expose a valid final model")
        if self.outcome is QualificationOutcome.FAILED and self.final_model_status is FinalModelStatus.VALID:
            raise ValueError("a numerical failure must not expose a valid final model")
        if self.outcome is QualificationOutcome.INVALID_INPUT and self.convergence_criterion_satisfied:
            raise ValueError("rejected input cannot satisfy a convergence criterion")

    @property
    def bounded_completion_only(self) -> bool:
        """True when the record only establishes bounded completion."""
        return self.outcome is QualificationOutcome.TERMINATED

    def to_dict(self) -> dict[str, object]:
        return {
            "domain": self.domain,
            "outcome": self.outcome.value,
            "history_status": self.history_status,
            "objective_history": list(self.objective_history),
            "trajectory": [point.to_dict() for point in self.trajectory],
            "initial_objective": self.initial_objective,
            "initial_objective_source": self.initial_objective_source,
            "final_objective": self.final_objective,
            "iteration_count": self.iteration_count,
            "evaluation_count": self.evaluation_count,
            "configured_maximum": self.configured_maximum,
            "configured_maximum_units": self.configured_maximum_units,
            "configured_maximum_reached": self.configured_maximum_reached,
            "convergence_criterion": self.convergence_criterion,
            "convergence_tolerance": self.convergence_tolerance,
            "convergence_criterion_satisfied": self.convergence_criterion_satisfied,
            "termination_reason": self.termination_reason,
            "cancellation_requested": self.cancellation_requested,
            "invalid_input": self.invalid_input,
            "numerical_failure": self.numerical_failure,
            "final_model_status": self.final_model_status.value,
            "error": self.error,
            "error_class": self.error_class,
            "failure_phase": self.failure_phase,
        }


def classify_outcome(
    *,
    invalid_input: bool = False,
    numerical_failure: bool = False,
    cancelled: bool = False,
    convergence_criterion_satisfied: bool = False,
    error: str | None = None,
) -> QualificationOutcome:
    """Map engine-independent signals onto the normalized M22 outcome vocabulary.

    The mapper refuses ambiguous combinations instead of silently preferring an
    outcome. In particular, invalid input and a numerical failure cannot both be
    claimed, and neither can be claimed without a recorded error.
    """
    if invalid_input and numerical_failure:
        raise ValueError("a run cannot be both invalid input and a numerical failure")
    if (invalid_input or numerical_failure) and not (error or "").strip():
        raise ValueError("invalid input and numerical failure outcomes require an error message")
    if invalid_input:
        return QualificationOutcome.INVALID_INPUT
    if numerical_failure:
        return QualificationOutcome.FAILED
    if cancelled:
        return QualificationOutcome.CANCELLED
    if convergence_criterion_satisfied:
        return QualificationOutcome.CONVERGED
    return QualificationOutcome.TERMINATED


def invalid_input_contract(
    domain: str,
    error: str,
    *,
    error_class: str | None = None,
    failure_phase: str = PHASE_INPUT_VALIDATION,
    configured_maximum: int | None = None,
    configured_maximum_units: str = MAXIMUM_UNITS_ITERATIONS,
    convergence_criterion: str = "not applicable: input rejected before evaluation",
) -> ConvergenceContract:
    """Build an ``INVALID_INPUT`` record for input rejected before any result."""
    return ConvergenceContract(
        domain=domain,
        outcome=QualificationOutcome.INVALID_INPUT,
        history_status=HISTORY_UNAVAILABLE,
        objective_history=(),
        trajectory=(),
        initial_objective=None,
        initial_objective_source=_INITIAL_OBJECTIVE_UNAVAILABLE,
        final_objective=None,
        iteration_count=0,
        evaluation_count=0,
        configured_maximum=configured_maximum,
        configured_maximum_units=configured_maximum_units,
        configured_maximum_reached=False,
        convergence_criterion=convergence_criterion,
        convergence_tolerance=None,
        convergence_criterion_satisfied=False,
        termination_reason="input rejected before a scientific result was produced",
        cancellation_requested=False,
        invalid_input=True,
        numerical_failure=False,
        final_model_status=FinalModelStatus.NOT_PRODUCED,
        error=error,
        error_class=error_class,
        failure_phase=failure_phase,
    )


def failed_contract(
    domain: str,
    error: str,
    *,
    error_class: str | None = None,
    failure_phase: str = PHASE_SOLVER,
    configured_maximum: int | None = None,
    configured_maximum_units: str = MAXIMUM_UNITS_ITERATIONS,
    convergence_criterion: str = "not applicable: solver failure",
) -> ConvergenceContract:
    """Build a ``FAILED`` record for a demonstrated numerical/solver failure."""
    return ConvergenceContract(
        domain=domain,
        outcome=QualificationOutcome.FAILED,
        history_status=HISTORY_UNAVAILABLE,
        objective_history=(),
        trajectory=(),
        initial_objective=None,
        initial_objective_source=_INITIAL_OBJECTIVE_UNAVAILABLE,
        final_objective=None,
        iteration_count=None,
        evaluation_count=None,
        configured_maximum=configured_maximum,
        configured_maximum_units=configured_maximum_units,
        configured_maximum_reached=False,
        convergence_criterion=convergence_criterion,
        convergence_tolerance=None,
        convergence_criterion_satisfied=False,
        termination_reason="solver failure before a usable result was produced",
        cancellation_requested=False,
        invalid_input=False,
        numerical_failure=True,
        final_model_status=FinalModelStatus.NOT_PRODUCED,
        error=error,
        error_class=error_class,
        failure_phase=failure_phase,
    )


def cancelled_contract(
    domain: str,
    *,
    reason: str = "cooperative cancellation requested before the guarded commit point",
    configured_maximum: int | None = None,
    configured_maximum_units: str = MAXIMUM_UNITS_ITERATIONS,
    convergence_criterion: str = "not applicable: cancelled before completion",
) -> ConvergenceContract:
    """Build a ``CANCELLED`` record that commits no partial model state."""
    return ConvergenceContract(
        domain=domain,
        outcome=QualificationOutcome.CANCELLED,
        history_status=HISTORY_UNAVAILABLE,
        objective_history=(),
        trajectory=(),
        initial_objective=None,
        initial_objective_source=_INITIAL_OBJECTIVE_UNAVAILABLE,
        final_objective=None,
        iteration_count=None,
        evaluation_count=None,
        configured_maximum=configured_maximum,
        configured_maximum_units=configured_maximum_units,
        configured_maximum_reached=False,
        convergence_criterion=convergence_criterion,
        convergence_tolerance=None,
        convergence_criterion_satisfied=False,
        termination_reason=reason,
        cancellation_requested=True,
        invalid_input=False,
        numerical_failure=False,
        final_model_status=FinalModelStatus.NOT_PRODUCED,
    )


def model_log10_vector(values: Sequence[float]) -> tuple[float, ...]:
    """Return the log10 parameter vector the inversion engines actually fit.

    Model differences are compared in this space because every engine fits
    log10(resistivity) and, for VES, log10(thickness). A linear-space L2 distance
    would weight the deepest layer far more heavily than a log-space residual.
    """
    array = np.asarray(tuple(float(value) for value in values), dtype=float)
    if array.size == 0 or not np.all(np.isfinite(array)) or np.any(array <= 0):
        raise ValueError("model parameters must be finite and positive")
    return tuple(float(value) for value in np.log10(array))


def _rms_log10(observed_log10: Sequence[float], predicted: Sequence[float]) -> float:
    observed = np.asarray(tuple(float(value) for value in observed_log10), dtype=float)
    values = np.asarray(tuple(float(value) for value in predicted), dtype=float)
    if observed.shape != values.shape or observed.size == 0:
        raise ValueError("observed and predicted responses must have equal non-zero length")
    return float(np.sqrt(np.mean((observed - np.log10(values)) ** 2)))


def _target_log10(values: Sequence[float]) -> tuple[float, ...]:
    return tuple(float(value) for value in np.log10(np.asarray(tuple(float(value) for value in values), dtype=float)))


def mesh2d_discretization(mesh: Mesh2D) -> tuple[object, ...]:
    """Return the comparison identity of a 2D model space.

    Cell locations and volumes of a cell-centred mesh are fixed by the mesh
    edges, so two meshes are only comparable parameter-wise when their edges
    match exactly. Cell count alone is not an identity: the same number of cells
    can describe a different domain, different cell centres, and different cell
    volumes.
    """
    return ("2d", "resistivity", tuple(mesh.x_edges), tuple(mesh.depth_edges))


def mesh3d_discretization(mesh: Mesh3D) -> tuple[object, ...]:
    """Return the comparison identity of a 3D model space (see mesh2d)."""
    return (
        "3d", "resistivity",
        tuple(mesh.x_edges), tuple(mesh.y_edges), tuple(mesh.depth_edges),
    )


def ves_discretization(model: LayeredEarthModel) -> tuple[object, ...]:
    """Return the comparison identity of a layered-earth parameter space.

    The VES parameter vector is ``(resistivities..., thicknesses...)``, so two
    models are only comparable when they declare the same number of layers and
    the same ordering.
    """
    return (
        "ves", "resistivity_then_thickness",
        len(model.resistivities), len(model.thicknesses),
    )


def _response_metrics(
    baseline_predicted: Sequence[float] | None,
    case_predicted: Sequence[float] | None,
    baseline_model_vector: Sequence[float] | None = None,
    case_model_vector: Sequence[float] | None = None,
    baseline_discretization: object | None = None,
    case_discretization: object | None = None,
) -> dict[str, float]:
    """Reuse the M21 comparison metrics where the two cases are comparable.

    Model metrics are produced only when both vectors exist *and* both cases
    declare an identical discretization/parameter identity. A cell-wise L2
    distance across different meshes (different edges, cell volumes, or layer
    counts) has no meaning, so the metric is omitted rather than computed from a
    length match. :func:`model_comparison_omission_reason` documents the omission
    for the report.
    """
    if baseline_predicted is None or case_predicted is None:
        return {}
    if len(baseline_predicted) != len(case_predicted):
        return {}
    reference = result = None
    discretization = None
    if (
        baseline_model_vector is not None and case_model_vector is not None
        and baseline_discretization is not None and case_discretization is not None
        and baseline_discretization == case_discretization
        and len(baseline_model_vector) == len(case_model_vector)
    ):
        reference, result = baseline_model_vector, case_model_vector
        discretization = baseline_discretization
    return comparison_metrics(
        baseline_predicted, case_predicted,
        reference_model=reference, result_model=result,
        model_discretization=discretization,
    )


def model_comparison_omission_reason(
    baseline_discretization: object | None, case_discretization: object | None,
) -> str | None:
    """Explain why no model-to-model metric was recorded, when none was."""
    if baseline_discretization is None or case_discretization is None:
        return "no model parameter vector was available for one of the cases"
    if baseline_discretization != case_discretization:
        return (
            "the cases use different discretizations/parameter spaces, so a "
            "cell-wise model distance is not defined and was omitted"
        )
    return None


def _ert2d_initial_matrix(mesh: Mesh2D, initial_model: np.ndarray | float) -> np.ndarray:
    if isinstance(initial_model, (int, float)):
        return np.full((mesh.nz, mesh.nx), float(initial_model), dtype=float)
    return np.asarray(initial_model, dtype=float).copy()


def _ert2d_initial_objective(
    mesh: Mesh2D, observations: Sequence[ERTObservation], initial_model: np.ndarray | float
) -> tuple[float | None, str]:
    """Evaluate the declared initial model with the engine's own public forward model."""
    if not observations:
        return None, _INITIAL_OBJECTIVE_UNAVAILABLE
    try:
        target = _target_log10([item.apparent_resistivity for item in observations])
        predicted = forward_2d(_ert2d_initial_matrix(mesh, initial_model), mesh, observations)
        return _rms_log10(target, predicted), _INITIAL_OBJECTIVE_SOURCE
    except Exception:  # the engine rejects the initial model or geometry
        return None, _INITIAL_OBJECTIVE_UNAVAILABLE


def _ves_initial_objective(
    points: Sequence[Any], initial_model: LayeredEarthModel
) -> tuple[float | None, str]:
    if not points:
        return None, _INITIAL_OBJECTIVE_UNAVAILABLE
    try:
        target = _target_log10([ves_apparent_resistivity(point) for point in points])
        predicted = tuple(layered_apparent_resistivity(initial_model, point.ab2, point.mn2) for point in points)
        return _rms_log10(target, predicted), _INITIAL_OBJECTIVE_SOURCE
    except Exception:
        return None, _INITIAL_OBJECTIVE_UNAVAILABLE


def run_ves_contract(
    fixture,
    initial_model: LayeredEarthModel,
    *,
    max_nfev: int = 20,
    points: Sequence[Any] | None = None,
) -> tuple[QualificationOutcome, ConvergenceContract, object | None]:
    """Run the existing VES engine and record a common convergence contract.

    The VES engine exposes a final objective and an optimizer function-evaluation
    count but no per-evaluation objective history, so the record is marked
    ``HISTORY_UNAVAILABLE`` rather than given an invented trajectory.
    """
    selected = tuple(points if points is not None else fixture.noisy_points)
    usable = tuple(point for point in selected if not point.excluded)
    initial_objective, initial_source = _ves_initial_objective(usable, initial_model)
    try:
        result = invert_ves(selected, initial_model, max_nfev=max_nfev)
    except np.linalg.LinAlgError as exc:
        contract = failed_contract(
            "VES", str(exc), error_class=type(exc).__name__, failure_phase=PHASE_SOLVER,
            configured_maximum=max_nfev, configured_maximum_units=MAXIMUM_UNITS_EVALUATIONS,
            convergence_criterion=_VES_CRITERION,
        )
        return contract.outcome, contract, None
    except VESNumericalError as exc:
        # The engine accepted the controls and failed while evaluating or
        # solving: a numerical failure, never INVALID_INPUT.
        contract = failed_contract(
            "VES", str(exc), error_class=type(exc).__name__,
            failure_phase=getattr(exc, "phase", PHASE_FORWARD_MODEL),
            configured_maximum=max_nfev, configured_maximum_units=MAXIMUM_UNITS_EVALUATIONS,
            convergence_criterion=_VES_CRITERION,
        )
        return contract.outcome, contract, None
    except (VESError, ValueError) as exc:
        contract = invalid_input_contract(
            "VES", str(exc), error_class=type(exc).__name__, failure_phase=PHASE_INPUT_VALIDATION,
            configured_maximum=max_nfev, configured_maximum_units=MAXIMUM_UNITS_EVALUATIONS,
            convergence_criterion=_VES_CRITERION,
        )
        return contract.outcome, contract, None
    except Exception as exc:
        contract = failed_contract(
            "VES", str(exc), error_class=type(exc).__name__, failure_phase=PHASE_SOLVER,
            configured_maximum=max_nfev, configured_maximum_units=MAXIMUM_UNITS_EVALUATIONS,
            convergence_criterion=_VES_CRITERION,
        )
        return contract.outcome, contract, None
    evaluation_count = int(result.iterations)
    outcome = classify_outcome(convergence_criterion_satisfied=bool(result.converged))
    contract = ConvergenceContract(
        domain="VES",
        outcome=outcome,
        history_status=HISTORY_UNAVAILABLE,
        objective_history=(),
        trajectory=(),
        initial_objective=initial_objective,
        initial_objective_source=initial_source,
        final_objective=float(result.rms_log10),
        iteration_count=None,
        evaluation_count=evaluation_count,
        configured_maximum=max_nfev,
        configured_maximum_units=MAXIMUM_UNITS_EVALUATIONS,
        configured_maximum_reached=bool(not result.converged and evaluation_count >= max_nfev),
        convergence_criterion=_VES_CRITERION,
        convergence_tolerance=_VES_TOLERANCE,
        convergence_criterion_satisfied=bool(result.converged),
        termination_reason=str(result.message),
        cancellation_requested=False,
        invalid_input=False,
        numerical_failure=False,
        final_model_status=FinalModelStatus.VALID,
    )
    return outcome, contract, result


def run_ert2d_contract(
    fixture,
    *,
    initial_model: np.ndarray | float = 1.0,
    damping: float = 0.3,
    max_iterations: int = 1,
    mesh: Mesh2D | None = None,
    observations: Sequence[ERTObservation] | None = None,
    convergence_rms: float = 1e-3,
) -> tuple[QualificationOutcome, ConvergenceContract, object | None]:
    """Run the existing 2D engine and record a common convergence contract."""
    selected_mesh = mesh if mesh is not None else fixture.mesh
    selected = tuple(observations if observations is not None else fixture.noisy_observations)
    usable = tuple(observation for observation in selected if not observation.excluded)
    initial_objective, initial_source = _ert2d_initial_objective(selected_mesh, usable, initial_model)
    try:
        result = invert_ert(
            selected, selected_mesh, initial_model,
            max_iterations=max_iterations, damping=damping, convergence_rms=convergence_rms,
        )
    except np.linalg.LinAlgError as exc:
        return _ert2d_failure(fixture, exc, max_iterations, numerical=True, phase=PHASE_SOLVER)
    except ERT2DNumericalError as exc:
        # The engine records which stage failed; a factorization failure must
        # not be reported as a model update.
        return _ert2d_failure(
            fixture, exc, max_iterations, numerical=True,
            phase=getattr(exc, "phase", PHASE_FORWARD_MODEL),
        )
    except (ERT2DError, ValueError) as exc:
        return _ert2d_failure(fixture, exc, max_iterations, numerical=False, phase=PHASE_INPUT_VALIDATION)
    except Exception as exc:
        return _ert2d_failure(fixture, exc, max_iterations, numerical=True, phase=PHASE_SOLVER)

    target = _target_log10([item.apparent_resistivity for item in usable])
    final_objective = _rms_log10(target, result.predicted)
    trajectory = tuple(
        TrajectoryPoint(
            step=item.iteration,
            objective=float(item.rms_log10),
            origin="solver_evaluation",
            solver_state={
                "phase": "pre_update",
                "damping": float(item.damping),
                "accepted_step": float(item.accepted_step),
                "rms_percent": float(item.rms_percent),
            },
        )
        for item in result.iterations
    )
    if not trajectory or abs(trajectory[-1].objective - final_objective) > 1e-12:
        # The engine evaluates the returned model once more after its last
        # update; record that evaluation so the history ends at the result.
        trajectory = (*trajectory, TrajectoryPoint(
            step=len(trajectory) + 1,
            objective=final_objective,
            origin="final_model_evaluation",
            solver_state={"phase": "post_update", "rms_percent": float(result.rms_percent)},
        ))
    outcome = classify_outcome(convergence_criterion_satisfied=bool(result.converged))
    contract = ConvergenceContract(
        domain="2D ERT",
        outcome=outcome,
        history_status=HISTORY_RECORDED,
        objective_history=tuple(point.objective for point in trajectory),
        trajectory=trajectory,
        initial_objective=initial_objective,
        initial_objective_source=initial_source,
        final_objective=final_objective,
        iteration_count=len(result.iterations),
        evaluation_count=len(trajectory),
        configured_maximum=max_iterations,
        configured_maximum_units=MAXIMUM_UNITS_ITERATIONS,
        configured_maximum_reached=bool(not result.converged and len(result.iterations) >= max_iterations),
        convergence_criterion=_ERT2D_CRITERION,
        convergence_tolerance=float(convergence_rms),
        convergence_criterion_satisfied=bool(result.converged),
        termination_reason=str(result.message),
        cancellation_requested=False,
        invalid_input=False,
        numerical_failure=False,
        final_model_status=FinalModelStatus.VALID,
    )
    return outcome, contract, result


def _ert2d_failure(
    fixture, exc: BaseException, max_iterations: int, *, numerical: bool,
    phase: str = PHASE_SOLVER,
) -> tuple[QualificationOutcome, ConvergenceContract, object | None]:
    if numerical:
        contract = failed_contract(
            "2D ERT", str(exc), error_class=type(exc).__name__, failure_phase=phase,
            configured_maximum=max_iterations, convergence_criterion=_ERT2D_CRITERION,
        )
    else:
        contract = invalid_input_contract(
            "2D ERT", str(exc), error_class=type(exc).__name__, failure_phase=phase,
            configured_maximum=max_iterations, convergence_criterion=_ERT2D_CRITERION,
        )
    return contract.outcome, contract, None


def run_ert3d_contract(
    fixture,
    *,
    initial_model: np.ndarray | float = 1.0,
    damping: float = 0.5,
    max_iterations: int = 1,
    mesh: Mesh3D | None = None,
    observations: Sequence[ERT3DObservation] | None = None,
) -> tuple[QualificationOutcome, ConvergenceContract, object | None]:
    """Run the existing 3D engine and record a common convergence contract.

    The 3D engine returns its objective evaluation history; after the M22
    reporting correction that history terminates at the objective of the
    returned model, so ``objective_history[-1]`` is a measurement of the result
    rather than of a discarded intermediate update.
    """
    selected_mesh = mesh if mesh is not None else fixture.mesh
    selected = tuple(observations if observations is not None else fixture.noisy_observations)
    usable = tuple(observation for observation in selected if not observation.excluded)
    try:
        model, predicted, history, converged = invert_ert3d(
            selected, selected_mesh, fixture.electrodes, initial_model,
            damping=damping, max_iterations=max_iterations,
        )
    except np.linalg.LinAlgError as exc:
        return _ert3d_failure(exc, max_iterations, numerical=True, phase=PHASE_SOLVER)
    except ERT3DNumericalError as exc:
        # The engine records which stage failed; a factorization failure must
        # not be reported as a model update.
        return _ert3d_failure(
            exc, max_iterations, numerical=True,
            phase=getattr(exc, "phase", PHASE_FORWARD_MODEL),
        )
    except (ERT3DError, ValueError) as exc:
        return _ert3d_failure(exc, max_iterations, numerical=False, phase=PHASE_INPUT_VALIDATION)
    except Exception as exc:
        return _ert3d_failure(exc, max_iterations, numerical=True, phase=PHASE_SOLVER)

    target = _target_log10([item.apparent_resistivity for item in usable])
    final_objective = _rms_log10(target, predicted)
    trajectory = tuple(
        TrajectoryPoint(
            step=index,
            objective=float(value),
            origin="final_model_evaluation" if index == len(history) else "solver_evaluation",
            solver_state={
                "phase": "post_update" if index == len(history) else "pre_update",
                "configured_damping": float(damping),
                "convergence_tolerance": ERT3D_CONVERGENCE_RMS,
            },
        )
        for index, value in enumerate(history, start=1)
    )
    if not trajectory or abs(trajectory[-1].objective - final_objective) > 1e-12:
        trajectory = (*trajectory, TrajectoryPoint(
            step=len(trajectory) + 1,
            objective=final_objective,
            origin="final_model_evaluation",
            solver_state={"phase": "post_update", "convergence_tolerance": ERT3D_CONVERGENCE_RMS},
        ))
    initial_objective = trajectory[0].objective
    outcome = classify_outcome(convergence_criterion_satisfied=bool(converged))
    contract = ConvergenceContract(
        domain="3D ERT",
        outcome=outcome,
        history_status=HISTORY_RECORDED,
        objective_history=tuple(point.objective for point in trajectory),
        trajectory=trajectory,
        initial_objective=initial_objective,
        initial_objective_source="engine solver evaluation at the declared initial parameters",
        final_objective=final_objective,
        iteration_count=max(len(history) - 1, 0),
        evaluation_count=len(trajectory),
        configured_maximum=max_iterations,
        configured_maximum_units=MAXIMUM_UNITS_ITERATIONS,
        configured_maximum_reached=bool(not converged and len(history) - 1 >= max_iterations),
        convergence_criterion=_ERT3D_CRITERION,
        convergence_tolerance=ERT3D_CONVERGENCE_RMS,
        convergence_criterion_satisfied=bool(converged),
        termination_reason="converged" if converged else "maximum iterations reached",
        cancellation_requested=False,
        invalid_input=False,
        numerical_failure=False,
        final_model_status=FinalModelStatus.VALID,
    )
    return outcome, contract, (model, predicted)


def _ert3d_failure(
    exc: BaseException, max_iterations: int, *, numerical: bool, phase: str = PHASE_SOLVER,
) -> tuple[QualificationOutcome, ConvergenceContract, object | None]:
    if numerical:
        contract = failed_contract(
            "3D ERT", str(exc), error_class=type(exc).__name__, failure_phase=phase,
            configured_maximum=max_iterations, convergence_criterion=_ERT3D_CRITERION,
        )
    else:
        contract = invalid_input_contract(
            "3D ERT", str(exc), error_class=type(exc).__name__, failure_phase=phase,
            configured_maximum=max_iterations, convergence_criterion=_ERT3D_CRITERION,
        )
    return contract.outcome, contract, None


@dataclass(frozen=True)
class StudyEvidence:
    """Sensitivity studies plus the convergence contract behind each case."""

    domain: str
    studies: tuple[SensitivityStudy, ...]
    contracts: tuple[ConvergenceContract, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "domain": self.domain,
            "studies": [study.to_dict() for study in self.studies],
            "contracts": [contract.to_dict() for contract in self.contracts],
        }


class _StudyBuilder:
    """Accumulate cases and their contracts for one controlled study."""

    def __init__(self, study_id: str, domain: str, baseline: Mapping[str, object]) -> None:
        self.study_id = study_id
        self.domain = domain
        self.baseline = dict(baseline)
        self.cases: list[SensitivityCase] = []
        self.contracts: list[ConvergenceContract] = []

    def add(self, case: SensitivityCase, contract: ConvergenceContract) -> None:
        self.cases.append(case)
        self.contracts.append(contract)

    def build(self, interpretation: str) -> SensitivityStudy:
        return SensitivityStudy(self.study_id, self.domain, self.baseline, tuple(self.cases), interpretation)


_SENSITIVITY_INTERPRETATION = (
    "Measured differences are configuration sensitivity evidence only. No preferred setting is declared and no "
    "universal pass/fail threshold is asserted; a lower residual is not evidence of a more accurate model."
)


def _ves_case(
    fixture, case_id: str, parameter: str, value: object, *,
    points: Sequence[Any], initial_model: LayeredEarthModel, max_nfev: int,
    baseline_predicted: Sequence[float] | None, baseline_model: Sequence[float] | None,
    baseline_discretization: object | None = None,
) -> tuple[SensitivityCase, ConvergenceContract]:
    outcome, contract, result = run_ves_contract(fixture, initial_model, max_nfev=max_nfev, points=points)
    metrics: dict[str, float] = {}
    summary: dict[str, object] = {
        "convergence": contract.to_dict(),
        "initial_model": {
            "resistivities": list(initial_model.resistivities),
            "thicknesses": list(initial_model.thicknesses),
        },
    }
    if result is not None:
        vector = model_log10_vector((*result.model.resistivities, *result.model.thicknesses))
        case_discretization = ves_discretization(result.model)
        metrics = _response_metrics(
            baseline_predicted, result.predicted, baseline_model, vector,
            baseline_discretization, case_discretization,
        )
        reason = model_comparison_omission_reason(baseline_discretization, case_discretization)
        if reason is not None and "model_l2_difference" not in metrics:
            summary["model_comparison_omitted"] = reason
        else:
            summary["model_discretization"] = list(case_discretization)
        summary.update({
            "final_model": {
                "resistivities": list(result.model.resistivities),
                "thicknesses": list(result.model.thicknesses),
            },
            "model_log10_vector": list(vector),
            "rms_percent": float(result.rms_percent),
        })
    return SensitivityCase(case_id, parameter, value, outcome, contract.final_objective, metrics, summary), contract


def _ert2d_case(
    fixture, case_id: str, parameter: str, value: object, *,
    initial_model: np.ndarray | float, damping: float, max_iterations: int,
    mesh: Mesh2D | None = None, observations: Sequence[ERTObservation] | None = None,
    baseline_predicted: Sequence[float] | None, baseline_model: Sequence[float] | None,
    baseline_discretization: object | None,
) -> tuple[SensitivityCase, ConvergenceContract]:
    selected_mesh = mesh if mesh is not None else fixture.mesh
    outcome, contract, result = run_ert2d_contract(
        fixture, initial_model=initial_model, damping=damping, max_iterations=max_iterations,
        mesh=mesh, observations=observations,
    )
    metrics: dict[str, float] = {}
    summary: dict[str, object] = {
        "convergence": contract.to_dict(),
        "mesh_cells": selected_mesh.cell_count,
    }
    if result is not None:
        vector = model_log10_vector(result.resistivity.reshape(-1).tolist())
        case_discretization = mesh2d_discretization(selected_mesh)
        metrics = _response_metrics(
            baseline_predicted, result.predicted, baseline_model, vector,
            baseline_discretization, case_discretization,
        )
        reason = model_comparison_omission_reason(baseline_discretization, case_discretization)
        if reason is not None and "model_l2_difference" not in metrics:
            summary["model_comparison_omitted"] = reason
        else:
            summary["model_discretization"] = list(case_discretization)
        summary.update({
            "rms_percent": float(result.rms_percent),
            "resistivity_min": float(np.min(result.resistivity)),
            "resistivity_max": float(np.max(result.resistivity)),
            "model_log10_vector": list(vector),
        })
    return SensitivityCase(case_id, parameter, value, outcome, contract.final_objective, metrics, summary), contract


def _ert3d_case(
    fixture, case_id: str, parameter: str, value: object, *,
    initial_model: np.ndarray | float, damping: float, max_iterations: int,
    mesh: Mesh3D | None = None, observations: Sequence[ERT3DObservation] | None = None,
    baseline_predicted: Sequence[float] | None, baseline_model: Sequence[float] | None,
    baseline_discretization: object | None,
) -> tuple[SensitivityCase, ConvergenceContract]:
    selected_mesh = mesh if mesh is not None else fixture.mesh
    outcome, contract, result = run_ert3d_contract(
        fixture, initial_model=initial_model, damping=damping, max_iterations=max_iterations,
        mesh=mesh, observations=observations,
    )
    metrics: dict[str, float] = {}
    summary: dict[str, object] = {
        "convergence": contract.to_dict(),
        "mesh_cells": selected_mesh.cell_count,
    }
    if result is not None:
        model, predicted = result
        vector = model_log10_vector(np.asarray(model).reshape(-1).tolist())
        case_discretization = mesh3d_discretization(selected_mesh)
        metrics = _response_metrics(
            baseline_predicted, predicted, baseline_model, vector,
            baseline_discretization, case_discretization,
        )
        reason = model_comparison_omission_reason(baseline_discretization, case_discretization)
        if reason is not None and "model_l2_difference" not in metrics:
            summary["model_comparison_omitted"] = reason
        else:
            summary["model_discretization"] = list(case_discretization)
        summary.update({
            "resistivity_min": float(np.min(model)),
            "resistivity_max": float(np.max(model)),
            "model_log10_vector": list(vector),
        })
    return SensitivityCase(case_id, parameter, value, outcome, contract.final_objective, metrics, summary), contract


def run_ves_study_evidence(*, bounded_max_nfev: int = 20, complete_max_nfev: int = 40) -> StudyEvidence:
    """Bounded deterministic VES studies: starting model, stopping limit, noise.

    The starting-model and noise studies use a limit that the engine actually
    converges within, so measured differences are attributable to the changed
    parameter rather than to a shared truncation. The stopping-limit study then
    measures the truncation itself. VES exposes neither damping nor a mesh, so
    those studies are reported as unavailable evidence, not simulated.
    """
    fixture = ves_qualification()
    _, baseline_contract, baseline_result = run_ves_contract(
        fixture, _VES_BASELINE_INITIAL, max_nfev=complete_max_nfev
    )
    baseline_predicted = baseline_result.predicted if baseline_result is not None else None
    baseline_model = (
        model_log10_vector((*baseline_result.model.resistivities, *baseline_result.model.thicknesses))
        if baseline_result is not None else None
    )
    baseline_discretization = (
        ves_discretization(baseline_result.model) if baseline_result is not None else None
    )
    studies: list[SensitivityStudy] = []
    contracts: list[ConvergenceContract] = [baseline_contract]

    starting = _StudyBuilder(
        "m22-ves-starting-model-v1", "VES",
        {
            "artifact": "ves-layered-internal-v1",
            "max_nfev": complete_max_nfev,
            "initial_resistivities": list(_VES_BASELINE_INITIAL.resistivities),
            "initial_thicknesses": list(_VES_BASELINE_INITIAL.thicknesses),
            "damping": "not exposed by the VES engine",
            "mesh_or_domain": "not applicable: 1D layered model",
        },
    )
    for case_id, model in (
        ("ves-starting-low", LayeredEarthModel((50.0, 15.0, 120.0), (3.0, 8.0))),
        ("ves-starting-high", LayeredEarthModel((150.0, 50.0, 300.0), (8.0, 16.0))),
        ("ves-starting-two-layer", LayeredEarthModel((100.0, 20.0), (5.0,))),
    ):
        case, contract = _ves_case(
            fixture, case_id, "starting_model",
            {"resistivities": list(model.resistivities), "thicknesses": list(model.thicknesses)},
            points=fixture.noisy_points, initial_model=model, max_nfev=complete_max_nfev,
            baseline_predicted=baseline_predicted, baseline_model=baseline_model,
            baseline_discretization=baseline_discretization,
        )
        starting.add(case, contract)
    studies.append(starting.build(_SENSITIVITY_INTERPRETATION))
    contracts.extend(starting.contracts)

    stopping = _StudyBuilder(
        "m22-ves-stopping-limit-v1", "VES",
        {
            "artifact": "ves-layered-internal-v1",
            "max_nfev": complete_max_nfev,
            "limit_unit": MAXIMUM_UNITS_EVALUATIONS,
            "initial_resistivities": list(_VES_BASELINE_INITIAL.resistivities),
            "initial_thicknesses": list(_VES_BASELINE_INITIAL.thicknesses),
        },
    )
    for limit in (10, bounded_max_nfev, complete_max_nfev):
        case, contract = _ves_case(
            fixture, f"ves-max-nfev-{limit}", "max_nfev", limit,
            points=fixture.noisy_points, initial_model=_VES_BASELINE_INITIAL, max_nfev=limit,
            baseline_predicted=baseline_predicted, baseline_model=baseline_model,
            baseline_discretization=baseline_discretization,
        )
        stopping.add(case, contract)
    stopping_interpretation = (
        "The stopping-limit study measures how the recorded result changes with the configured function-evaluation "
        "limit. It does not declare the tightest limit preferable; it only shows whether the reported objective and "
        "model stabilize once more evaluations are allowed."
    )
    studies.append(stopping.build(stopping_interpretation))
    contracts.extend(stopping.contracts)

    noisy_points = tuple(
        type(point)(point.ab2, point.mn2, apparent_resistivity=point.apparent_resistivity * factor)
        for point, factor in zip(fixture.clean_points, VES_NOISE_FACTORS_V1)
    )
    noise = _StudyBuilder(
        "m22-ves-deterministic-noise-v1", "VES",
        {
            "artifact": "ves-layered-internal-v1",
            "max_nfev": complete_max_nfev,
            "noise": "deterministic multiplicative factors",
            "noise_factors": list(VES_NOISE_FACTORS_V1),
            "noise_applied_to": "clean fixture responses",
        },
    )
    case, contract = _ves_case(
        fixture, "ves-noise-deterministic-v1", "deterministic_noise", list(VES_NOISE_FACTORS_V1),
        points=noisy_points, initial_model=_VES_BASELINE_INITIAL, max_nfev=complete_max_nfev,
        baseline_predicted=baseline_predicted, baseline_model=baseline_model,
        baseline_discretization=baseline_discretization,
    )
    noise.add(case, contract)
    studies.append(noise.build(
        "The deterministic noise case is a reproducible perturbation realization applied to the clean fixture, not a "
        "field-instrument noise model. Metric differences are numerical robustness observations only."
    ))
    contracts.extend(noise.contracts)

    return StudyEvidence("VES", tuple(studies), tuple(contracts))


def run_ert2d_study_evidence() -> StudyEvidence:
    """Bounded deterministic 2D studies: starting model, damping, mesh, stopping, noise."""
    fixture = ert2d_qualification()
    baseline_iterations = 3
    _, baseline_contract, baseline_result = run_ert2d_contract(
        fixture, initial_model=1.0, damping=0.3, max_iterations=baseline_iterations
    )
    baseline_predicted = baseline_result.predicted if baseline_result is not None else None
    baseline_model = (
        model_log10_vector(baseline_result.resistivity.reshape(-1).tolist())
        if baseline_result is not None else None
    )
    baseline_discretization = (
        mesh2d_discretization(fixture.mesh) if baseline_result is not None else None
    )
    studies: list[SensitivityStudy] = []
    contracts: list[ConvergenceContract] = [baseline_contract]
    baseline_configuration = {
        "artifact": "ert-2d-anomaly-internal-v1",
        "initial_resistivity": 1.0,
        "damping": 0.3,
        "max_iterations": baseline_iterations,
        "mesh_cells": fixture.mesh.cell_count,
    }

    def add_study(
        study_id: str, parameter_cases: Sequence[tuple[str, str, object, dict[str, object]]],
        configuration: Mapping[str, object], interpretation: str = _SENSITIVITY_INTERPRETATION,
    ) -> None:
        builder = _StudyBuilder(study_id, "2D ERT", configuration)
        for case_id, parameter, value, overrides in parameter_cases:
            options = dict(overrides)
            case, contract = _ert2d_case(
                fixture, case_id, parameter, value,
                initial_model=options.get("initial_model", 1.0),
                damping=options.get("damping", 0.3),
                max_iterations=options.get("max_iterations", baseline_iterations),
                mesh=options.get("mesh"),
                observations=options.get("observations"),
                baseline_predicted=baseline_predicted, baseline_model=baseline_model,
                baseline_discretization=baseline_discretization,
            )
            builder.add(case, contract)
        studies.append(builder.build(interpretation))
        contracts.extend(builder.contracts)

    add_study(
        "m22-ert2d-starting-model-v1",
        (
            ("ert2d-starting-0.5", "starting_resistivity", 0.5, {"initial_model": 0.5}),
            ("ert2d-starting-2.0", "starting_resistivity", 2.0, {"initial_model": 2.0}),
        ),
        baseline_configuration,
    )
    add_study(
        "m22-ert2d-damping-v1",
        (
            ("ert2d-damping-0.1", "damping", 0.1, {"damping": 0.1}),
            ("ert2d-damping-0.8", "damping", 0.8, {"damping": 0.8}),
        ),
        baseline_configuration,
        "The 2D engine also adapts damping inside the loop, so these cases measure the configured starting damping "
        "under that documented adaptation. No damping value is declared preferable.",
    )
    mesh_cases: list[tuple[str, str, object, dict[str, object]]] = [
        ("ert2d-mesh-nz-2", "mesh_nz", 2, {"mesh": Mesh2D.from_electrodes(fixture.mesh.x_centres, nz=2, depth=3.0)}),
        ("ert2d-mesh-nz-4", "mesh_nz", 4, {"mesh": Mesh2D.from_electrodes(fixture.mesh.x_centres, nz=4, depth=3.0)}),
        ("ert2d-mesh-depth-6", "mesh_depth", 6.0, {"mesh": Mesh2D.from_electrodes(fixture.mesh.x_centres, nz=3, depth=6.0)}),
        # A domain that cannot resolve the observation electrodes is a real
        # bounded failure mode and is preserved as INVALID_INPUT evidence.
        ("ert2d-mesh-too-coarse", "mesh_nx", 5, {"mesh": Mesh2D.from_electrodes([0, 1, 2, 3, 4], nz=3, depth=3.0)}),
    ]
    add_study(
        "m22-ert2d-mesh-domain-v1",
        tuple(mesh_cases),
        {**baseline_configuration, "mesh_nz": 3, "mesh_depth": 3.0},
        "Mesh and domain variants are recorded as measured numerical differences. Cell-wise model L2 distance is only "
        "reported between meshes of identical shape; different discretizations are not compared model-to-model.",
    )
    add_study(
        "m22-ert2d-stopping-limit-v1",
        (
            ("ert2d-max-iterations-1", "max_iterations", 1, {"max_iterations": 1}),
            ("ert2d-max-iterations-2", "max_iterations", 2, {"max_iterations": 2}),
            ("ert2d-max-iterations-5", "max_iterations", 5, {"max_iterations": 5}),
        ),
        baseline_configuration,
        "Additional iterations are allowed under the same controls. The study shows whether the recorded objective and "
        "model stabilize; it does not assume stabilization because the residual decreases.",
    )
    noisy = tuple(
        ERTObservation(item.a, item.b, item.m, item.n, item.apparent_resistivity * factor)
        for item, factor in zip(fixture.observations, ERT2D_NOISE_FACTORS_V1)
    )
    add_study(
        "m22-ert2d-deterministic-noise-v1",
        (("ert2d-noise-deterministic-v1", "deterministic_noise", list(ERT2D_NOISE_FACTORS_V1), {"observations": noisy}),),
        {**baseline_configuration, "noise": "deterministic multiplicative factors", "noise_factors": list(ERT2D_NOISE_FACTORS_V1)},
        "The deterministic noise case is applied to the clean fixture responses, so it is a distinct reproducible "
        "realization from the M21 fixture noise. It is not a field-instrument noise model.",
    )
    return StudyEvidence("2D ERT", tuple(studies), tuple(contracts))


def run_ert3d_study_evidence() -> StudyEvidence:
    """Bounded deterministic 3D studies: starting model, damping, mesh, stopping, noise."""
    fixture = ert3d_qualification()
    baseline_iterations = 5
    _, baseline_contract, baseline_result = run_ert3d_contract(
        fixture, initial_model=1.0, damping=0.5, max_iterations=baseline_iterations
    )
    baseline_predicted = baseline_result[1] if baseline_result is not None else None
    baseline_model = (
        model_log10_vector(np.asarray(baseline_result[0]).reshape(-1).tolist())
        if baseline_result is not None else None
    )
    baseline_discretization = (
        mesh3d_discretization(fixture.mesh) if baseline_result is not None else None
    )
    studies: list[SensitivityStudy] = []
    contracts: list[ConvergenceContract] = [baseline_contract]
    baseline_configuration = {
        "artifact": "ert-3d-anomaly-internal-v1",
        "initial_resistivity": 1.0,
        "damping": 0.5,
        "max_iterations": baseline_iterations,
        "mesh_cells": fixture.mesh.cell_count,
        "convergence_tolerance": ERT3D_CONVERGENCE_RMS,
    }

    def add_study(
        study_id: str, parameter_cases: Sequence[tuple[str, str, object, dict[str, object]]],
        configuration: Mapping[str, object], interpretation: str = _SENSITIVITY_INTERPRETATION,
    ) -> None:
        builder = _StudyBuilder(study_id, "3D ERT", configuration)
        for case_id, parameter, value, overrides in parameter_cases:
            options = dict(overrides)
            case, contract = _ert3d_case(
                fixture, case_id, parameter, value,
                initial_model=options.get("initial_model", 1.0),
                damping=options.get("damping", 0.5),
                max_iterations=options.get("max_iterations", baseline_iterations),
                mesh=options.get("mesh"),
                observations=options.get("observations"),
                baseline_predicted=baseline_predicted, baseline_model=baseline_model,
                baseline_discretization=baseline_discretization,
            )
            builder.add(case, contract)
        studies.append(builder.build(interpretation))
        contracts.extend(builder.contracts)

    add_study(
        "m22-ert3d-starting-model-v1",
        (
            ("ert3d-starting-0.5", "starting_resistivity", 0.5, {"initial_model": 0.5}),
            ("ert3d-starting-2.0", "starting_resistivity", 2.0, {"initial_model": 2.0}),
        ),
        baseline_configuration,
    )
    add_study(
        "m22-ert3d-damping-v1",
        (
            ("ert3d-damping-0.1", "damping", 0.1, {"damping": 0.1}),
            ("ert3d-damping-0.9", "damping", 0.9, {"damping": 0.9}),
        ),
        baseline_configuration,
        "The 3D engine uses the configured damping both in its normal equations and as a fixed step multiplier, so "
        "these cases measure that documented behavior. No damping value is declared preferable.",
    )
    fine_x_edges = tuple(float(value) for value in np.linspace(0.0, 4.0, 9))
    add_study(
        "m22-ert3d-mesh-domain-v1",
        (
            ("ert3d-mesh-nz-3", "mesh_nz", 3, {"mesh": Mesh3D.regular((0, 1, 2, 3, 4), (0, 1, 2), (0, 1, 2, 3))}),
            ("ert3d-mesh-nz-4", "mesh_nz", 4, {"mesh": Mesh3D.regular((0, 1, 2, 3, 4), (0, 1, 2), (0, 1, 2, 3, 4))}),
            ("ert3d-mesh-x-refined-8", "mesh_nx", 8, {"mesh": Mesh3D.regular(fine_x_edges, (0, 1, 2), (0, 1, 2))}),
            # A domain too coarse to resolve four distinct electrode cells is a
            # real bounded failure mode and is preserved as INVALID_INPUT.
            ("ert3d-mesh-too-coarse", "mesh_nx", 2, {"mesh": Mesh3D.regular((0, 2, 4), (0, 1, 2), (0, 1, 2))}),
        ),
        {**baseline_configuration, "mesh_nz": 2, "mesh_nx": 4},
        "Mesh and domain variants are recorded as measured numerical differences. Cell-wise model L2 distance is only "
        "reported between meshes of identical shape; different discretizations are not compared model-to-model.",
    )
    add_study(
        "m22-ert3d-stopping-limit-v1",
        (
            ("ert3d-max-iterations-1", "max_iterations", 1, {"max_iterations": 1}),
            ("ert3d-max-iterations-3", "max_iterations", 3, {"max_iterations": 3}),
            ("ert3d-max-iterations-10", "max_iterations", 10, {"max_iterations": 10}),
        ),
        baseline_configuration,
        "Additional iterations are allowed under the same controls. The 3D engine's configured tolerance is much "
        "tighter than the fixture can reach, so bounded completion remains the recorded outcome.",
    )
    noisy = tuple(
        ERT3DObservation(item.a, item.b, item.m, item.n, item.apparent_resistivity * factor)
        for item, factor in zip(fixture.observations, ERT3D_NOISE_FACTORS_V1)
    )
    add_study(
        "m22-ert3d-deterministic-noise-v1",
        (("ert3d-noise-deterministic-v1", "deterministic_noise", list(ERT3D_NOISE_FACTORS_V1), {"observations": noisy}),),
        {**baseline_configuration, "noise": "deterministic multiplicative factors", "noise_factors": list(ERT3D_NOISE_FACTORS_V1)},
        "The deterministic noise case is applied to the clean fixture responses, so it is a distinct reproducible "
        "realization from the M21 fixture noise. It is not a field-instrument noise model.",
    )
    return StudyEvidence("3D ERT", tuple(studies), tuple(contracts))


def run_m22_studies() -> tuple[SensitivityStudy, ...]:
    """Return the flattened M22 sensitivity studies for all three engines."""
    studies: list[SensitivityStudy] = []
    for evidence in (run_ves_study_evidence(), run_ert2d_study_evidence(), run_ert3d_study_evidence()):
        studies.extend(evidence.studies)
    return tuple(studies)


def run_cancellation_evidence() -> tuple[ConvergenceContract, Mapping[str, object]]:
    """Prove that cooperative cancellation commits no partial model state.

    Uses the existing desktop operation executor. Cancellation is requested
    inside the operation, before the executor's guarded commit point, so the
    behaviour is deterministic and no timing assumption is involved.
    """
    from nix_ert.app.operations import OperationExecutor

    committed: list[str] = []
    executor = OperationExecutor()
    try:
        def operation(token) -> str:
            token.cancel()
            return "uncommitted-result"

        handle = executor.submit("m22-cancellation-probe", operation)
        result = None
        error: BaseException | None = None
        try:
            result = handle.future.result(timeout=60)
        except BaseException as exc:  # cancellation surfaces as an exception
            error = exc
        snapshot = handle.snapshot()
        if error is None and result is not None:
            committed.append(result)
    finally:
        executor.shutdown()
    contract = cancelled_contract("2D ERT", reason=str(snapshot.error) if snapshot.error else snapshot.detail or "cancelled before commit")
    evidence = {
        "executor_state": snapshot.state,
        "cancellation_exception": type(error).__name__ if error is not None else None,
        "committed_state_entries": len(committed),
    }
    return contract, evidence


def metric_definitions() -> dict[str, dict[str, str]]:
    """Document what each reused M21 metric measures, needs, and does not establish."""
    return {
        "rmse": {
            "measures": "Root-mean-square difference between a compared response and the baseline response.",
            "requires": "Two equal-length finite response sequences with identical observation order.",
            "does_not_establish": "Geological accuracy, uniqueness, resolution, or field validity.",
        },
        "relative_rmse": {
            "measures": "Root-mean-square of the response difference normalized by the baseline magnitude.",
            "requires": "Two equal-length finite response sequences with non-zero baseline values.",
            "does_not_establish": "Any statement about which configuration is scientifically preferable.",
        },
        "max_absolute_difference": {
            "measures": "Largest absolute response difference in the compared sequences.",
            "requires": "Two equal-length finite response sequences.",
            "does_not_establish": "Where or why a difference matters geologically.",
        },
        "log10_rmse": {
            "measures": "Root-mean-square difference in log10 response, the space the engines fit.",
            "requires": "Two equal-length finite positive response sequences.",
            "does_not_establish": "That a smaller log10 residual means a more accurate model.",
        },
        "model_l2_difference": {
            "measures": "Euclidean distance between two log10 model parameter vectors.",
            "requires": "Two equal-length finite model vectors *and* an identical declared discretization "
                        "(mesh edges, so cell locations and volumes match, plus the same parameter order). "
                        "Cases whose discretizations differ are omitted instead of compared.",
            "does_not_establish": "Model correctness; different discretizations are not comparable this way.",
        },
        "model_relative_l2_difference": {
            "measures": "Model L2 difference normalized by the baseline model-vector norm.",
            "requires": "Two equal-length finite non-zero model vectors and the same discretization/parameter "
                        "identity as ``model_l2_difference``.",
            "does_not_establish": "Uniqueness or resolution of the inverted model.",
        },
    }


def unavailable_evidence() -> tuple[Mapping[str, str], ...]:
    """Evidence M22 did not measure, with the reason it is absent."""
    return (
        {
            "domain": "VES",
            "evidence": "damping study",
            "status": "UNAVAILABLE",
            "reason": "The VES engine exposes no damping control; no variant is simulated.",
        },
        {
            "domain": "VES",
            "evidence": "mesh/domain-resolution study",
            "status": "UNAVAILABLE",
            "reason": "A 1D layered-earth model has no mesh or domain resolution to vary.",
        },
        {
            "domain": "VES",
            "evidence": "per-evaluation objective trajectory",
            "status": "HISTORY_UNAVAILABLE",
            "reason": "scipy.optimize.least_squares exposes no per-evaluation objective series; M22 records the "
                      "initial and final objective but refuses to invent a trajectory.",
        },
        {
            "domain": "2D ERT",
            "evidence": "line-search trial objective sequence",
            "status": "PARTIAL",
            "reason": "Only accepted/attempted step objectives and the returned model evaluation are exposed; internal "
                      "line-search and Jacobian evaluations are not recorded.",
        },
        {
            "domain": "3D ERT",
            "evidence": "line-search trial objective sequence",
            "status": "PARTIAL",
            "reason": "Only solver step objectives and the returned model evaluation are exposed; internal Jacobian "
                      "evaluations are not recorded.",
        },
        {
            "domain": "all",
            "evidence": "uncertainty, resolution, and uniqueness analysis",
            "status": "UNAVAILABLE",
            "reason": "Not implemented; out of M22 scope.",
        },
        {
            "domain": "all",
            "evidence": "external reference or field agreement",
            "status": "NOT_VALIDATED",
            "reason": "No authorized independent dataset with a trustworthy reference result is available.",
        },
    )


def unvalidated_claims() -> tuple[str, ...]:
    """Claims that the M22 evidence explicitly does not support."""
    return (
        "A lower residual, a decreasing trajectory, or a nominal convergence criterion does not establish a more "
        "accurate geological model.",
        "Stable repeat results do not establish field accuracy or instrument validity.",
        "Reproducibility does not establish correctness or agreement with an external reference.",
        "Bounded completion at a configured limit is not evidence of an implementation defect.",
        "No RES2DINV, commercial-solver, or published-dataset equivalence is claimed.",
        "No uncertainty, resolution, or inversion-uniqueness result is provided.",
    )


@dataclass(frozen=True)
class M22QualificationRecord:
    manifest: QualificationManifest
    domain: str
    evidence_class: EvidenceClass
    convergence: ConvergenceContract
    metrics: Mapping[str, float]

    def to_dict(self) -> dict[str, object]:
        return {
            "manifest": self.manifest.to_dict() | {"manifest_sha256": self.manifest.manifest_sha256},
            "domain": self.domain,
            "evidence_class": self.evidence_class.value,
            "convergence": self.convergence.to_dict(),
            "metrics": dict(self.metrics),
        }


@dataclass(frozen=True)
class M22QualificationReport:
    procedure_version: str
    evidence_class: EvidenceClass
    environment: Mapping[str, str]
    records: tuple[M22QualificationRecord, ...]
    studies: tuple[SensitivityStudy, ...]
    study_manifests: tuple[QualificationManifest, ...]
    outcome_coverage: Mapping[str, int]
    cancellation_evidence: Mapping[str, object]
    selection_rule: str
    metric_definitions: Mapping[str, Mapping[str, str]]
    unavailable_evidence: tuple[Mapping[str, str], ...]
    unvalidated_claims: tuple[str, ...]
    external_benchmarks: tuple[ExternalBenchmarkReadiness, ...]
    limitations: tuple[str, ...]
    superseded_artifacts: tuple[Mapping[str, object], ...] = SUPERSEDED_ARTIFACTS

    def __post_init__(self) -> None:
        if self.procedure_version != PROCEDURE_VERSION:
            raise ValueError("unsupported M22 procedure version")
        if not self.records:
            raise ValueError("an M22 qualification report requires at least one record")
        if not self.studies:
            raise ValueError("an M22 qualification report requires at least one study")
        if not self.external_benchmarks:
            raise ValueError("an M22 qualification report requires an external benchmark record")
        if not self.selection_rule.strip():
            raise ValueError("the result-selection rule must be documented")

    @property
    def report_sha256(self) -> str:
        return hashlib.sha256(
            json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
        ).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "procedure_version": self.procedure_version,
            "evidence_class": self.evidence_class.value,
            "environment": dict(self.environment),
            "records": [record.to_dict() for record in self.records],
            "studies": [study.to_dict() for study in self.studies],
            "study_manifests": [
                manifest.to_dict() | {"manifest_sha256": manifest.manifest_sha256}
                for manifest in self.study_manifests
            ],
            "outcome_coverage": dict(self.outcome_coverage),
            "cancellation_evidence": dict(self.cancellation_evidence),
            "selection_rule": self.selection_rule,
            "metric_definitions": {key: dict(value) for key, value in self.metric_definitions.items()},
            "unavailable_evidence": [dict(item) for item in self.unavailable_evidence],
            "unvalidated_claims": list(self.unvalidated_claims),
            "external_benchmarks": [item.to_dict() for item in self.external_benchmarks],
            "limitations": list(self.limitations),
            "superseded_artifacts": [dict(item) for item in self.superseded_artifacts],
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict() | {"report_sha256": self.report_sha256},
            sort_keys=True, indent=2, ensure_ascii=True, default=str,
        ) + "\n"

    @staticmethod
    def _number(value: object) -> str:
        if value is None:
            return "not exposed"
        if isinstance(value, float):
            return f"{value:.8g}"
        return str(value)

    def to_markdown(self) -> str:
        lines = [
            "# M22 inversion robustness and scientific hardening result",
            "",
            f"**Procedure:** `{self.procedure_version}`  ",
            f"**Evidence class:** `{self.evidence_class.value}`  ",
            f"**Report SHA-256:** `{self.report_sha256}`",
            "",
            "## Environment",
            "",
        ]
        lines.extend(f"- **{key}:** {value}" for key, value in self.environment.items())
        lines.extend([
            "",
            "## Convergence and outcome records",
            "",
            "| Domain | Record | Outcome | History | Initial objective | Final objective | Iterations | Evaluations | Configured maximum | Criterion satisfied |",
            "|---|---|---|---|---:|---:|---:|---:|---:|---|",
        ])
        for record in self.records:
            convergence = record.convergence
            maximum = "-" if convergence.configured_maximum is None else (
                f"{convergence.configured_maximum} {convergence.configured_maximum_units}"
            )
            lines.append(
                f"| {record.domain} | `{record.manifest.manifest_id}` | `{convergence.outcome.value}` | "
                f"{convergence.history_status} | {self._number(convergence.initial_objective)} | "
                f"{self._number(convergence.final_objective)} | "
                f"{'-' if convergence.iteration_count is None else convergence.iteration_count} | "
                f"{'-' if convergence.evaluation_count is None else convergence.evaluation_count} | "
                f"{maximum} | {convergence.convergence_criterion_satisfied} |"
            )
        lines.extend(["", "### Termination detail", ""])
        for record in self.records:
            convergence = record.convergence
            lines.append(
                f"- `{record.manifest.manifest_id}`: {convergence.termination_reason} "
                f"(final model status `{convergence.final_model_status.value}`"
                + (f", error class `{convergence.error_class}`" if convergence.error_class else "")
                + ")"
            )
        lines.extend([
            "",
            "Outcome coverage across every committed M22 record and study case:",
            "",
        ])
        lines.extend(f"- `{key}`: {value}" for key, value in self.outcome_coverage.items())
        lines.extend(["", "## Sensitivity studies", ""])
        for study in self.studies:
            lines.append(f"### `{study.study_id}` ({study.domain})")
            lines.append("")
            lines.append("| Case | Changed parameter | Value | Outcome | Final objective | Response RMSE | Log10 RMSE | Model L2 |")
            lines.append("|---|---|---|---|---:|---:|---:|---:|")
            for case in study.cases:
                metrics = case.metrics
                lines.append(
                    f"| `{case.case_id}` | {case.changed_parameter} | {self._number(case.value if not isinstance(case.value, (list, dict)) else str(case.value))} | "
                    f"`{case.outcome.value}` | {self._number(case.objective)} | "
                    f"{self._number(metrics.get('rmse'))} | {self._number(metrics.get('log10_rmse'))} | "
                    f"{self._number(metrics.get('model_l2_difference'))} |"
                )
            lines.extend(["", study.interpretation, ""])
        lines.extend([
            "## Result-selection rule",
            "",
            self.selection_rule,
            "",
            "## Cancellation evidence",
            "",
        ])
        lines.extend(f"- **{key}:** {value}" for key, value in self.cancellation_evidence.items())
        lines.extend(["", "## Metric definitions", ""])
        for name, definition in self.metric_definitions.items():
            lines.append(
                f"- **`{name}`** — measures: {definition['measures']} Requires: {definition['requires']} "
                f"Does not establish: {definition['does_not_establish']}"
            )
        lines.extend(["", "## Unavailable evidence", ""])
        for item in self.unavailable_evidence:
            lines.append(f"- **{item['domain']} / {item['evidence']}** — `{item['status']}`: {item['reason']}")
        lines.extend(["", "## Unvalidated claims", ""])
        lines.extend(f"- {item}" for item in self.unvalidated_claims)
        lines.extend(["", "## External benchmark readiness", ""])
        for benchmark in self.external_benchmarks:
            lines.append(f"- `{benchmark.benchmark_id}` ({benchmark.dataset_id}): **{benchmark.status.value}** — {benchmark.reason}")
            if benchmark.required_evidence:
                lines.append(f"  - Required evidence: {', '.join(benchmark.required_evidence)}")
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in self.limitations)
        lines.extend(["", "## Superseded artifacts", ""])
        if not self.superseded_artifacts:
            lines.append("- None.")
        for item in self.superseded_artifacts:
            lines.append(f"- **`{item['artifact']}`** — `{item['status']}` (was `{item['artifact_procedure_version']}`, "
                         f"sha256 `{item['artifact_report_sha256']}`)")
            lines.append(f"  - Superseded by: {item['superseded_by']}")
            lines.append(f"  - Reason: {item['reason']}")
            lines.append(f"  - Historical evidence retained: {item['historical_evidence_retained']}")
        return "\n".join(lines) + "\n"

    def write_json(self, path: str) -> None:
        # newline="\n" keeps the artifact bytes identical across platforms.
        from pathlib import Path
        Path(path).write_text(self.to_json(), encoding="utf-8", newline="\n")

    def write_markdown(self, path: str) -> None:
        from pathlib import Path
        Path(path).write_text(self.to_markdown(), encoding="utf-8", newline="\n")


def build_m22_manifest(
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
    """Reuse the M19 manifest contract with an M22 procedure identifier."""
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


def _study_manifest(study: SensitivityStudy) -> QualificationManifest:
    counts: dict[str, int] = {}
    for case in study.cases:
        counts[case.outcome.value] = counts.get(case.outcome.value, 0) + 1
    return build_m22_manifest(
        f"{study.study_id}-manifest",
        domain=study.domain,
        dataset_id=str(study.baseline_configuration.get("artifact", "internal-synthetic-fixture")),
        project_id="qualification",
        survey_id=study.study_id,
        configuration={
            **{str(key): value for key, value in study.baseline_configuration.items()},
            "case_ids": [case.case_id for case in study.cases],
            "case_values": [case.value if not isinstance(case.value, Mapping) else dict(case.value) for case in study.cases],
        },
        expected_outputs={"case_count": len(study.cases), "outcomes": counts},
    )


def outcome_coverage(contracts: Sequence[ConvergenceContract]) -> dict[str, int]:
    """Count each normalized solver outcome across the supplied records."""
    solver_outcomes = (
        QualificationOutcome.CONVERGED,
        QualificationOutcome.TERMINATED,
        QualificationOutcome.FAILED,
        QualificationOutcome.INVALID_INPUT,
        QualificationOutcome.CANCELLED,
    )
    return {outcome.value: sum(1 for item in contracts if item.outcome is outcome) for outcome in solver_outcomes}


def run_m22_qualification() -> M22QualificationReport:
    """Run every bounded M22 study once and assemble the qualification report."""
    records: list[M22QualificationRecord] = []
    contracts: list[ConvergenceContract] = []

    ves = ves_qualification()
    _, ves_bounded, ves_bounded_result = run_ves_contract(ves, _VES_BASELINE_INITIAL, max_nfev=20)
    _, ves_complete, ves_complete_result = run_ves_contract(ves, _VES_BASELINE_INITIAL, max_nfev=40)
    ves_metrics = (
        comparison_metrics([point.apparent_resistivity for point in ves.noisy_points], ves_bounded_result.predicted)
        if ves_bounded_result is not None else {}
    )
    for manifest_id, contract in (("m22-ves-bounded-20", ves_bounded), ("m22-ves-complete-40", ves_complete)):
        records.append(M22QualificationRecord(
            build_m22_manifest(
                manifest_id, domain="VES", dataset_id=ves.spec.name, project_id="qualification", survey_id="ves",
                configuration={
                    "initial_resistivities": list(_VES_BASELINE_INITIAL.resistivities),
                    "initial_thicknesses": list(_VES_BASELINE_INITIAL.thicknesses),
                    "max_nfev": contract.configured_maximum,
                    "convergence_criterion": contract.convergence_criterion,
                },
                expected_outputs={"status": "internal synthetic"},
            ),
            "VES", EvidenceClass.QUALITATIVELY_CONSISTENT, contract, ves_metrics,
        ))
    contracts.extend((ves_bounded, ves_complete))

    ert2d = ert2d_qualification()
    _, ert2d_contract, ert2d_result = run_ert2d_contract(ert2d, initial_model=1.0, damping=0.3, max_iterations=1)
    ert2d_metrics = (
        comparison_metrics([item.apparent_resistivity for item in ert2d.noisy_observations], ert2d_result.predicted)
        if ert2d_result is not None else {}
    )
    records.append(M22QualificationRecord(
        build_m22_manifest(
            "m22-ert2d-bounded-1", domain="2D ERT", dataset_id=ert2d.spec.name, project_id="qualification",
            survey_id="ert2d",
            configuration={
                "initial_resistivity": 1.0, "damping": 0.3, "max_iterations": 1,
                "mesh_cells": ert2d.mesh.cell_count, "convergence_criterion": ert2d_contract.convergence_criterion,
            },
            expected_outputs={"status": "internal synthetic"},
        ),
        "2D ERT", EvidenceClass.QUALITATIVELY_CONSISTENT, ert2d_contract, ert2d_metrics,
    ))
    contracts.append(ert2d_contract)

    ert3d = ert3d_qualification()
    _, ert3d_contract, ert3d_result = run_ert3d_contract(ert3d, initial_model=1.0, damping=0.5, max_iterations=1)
    ert3d_metrics = (
        comparison_metrics([item.apparent_resistivity for item in ert3d.noisy_observations], ert3d_result[1])
        if ert3d_result is not None else {}
    )
    records.append(M22QualificationRecord(
        build_m22_manifest(
            "m22-ert3d-bounded-1", domain="3D ERT", dataset_id=ert3d.spec.name, project_id="qualification",
            survey_id="ert3d",
            configuration={
                "initial_resistivity": 1.0, "damping": 0.5, "max_iterations": 1,
                "mesh_cells": ert3d.mesh.cell_count, "convergence_criterion": ert3d_contract.convergence_criterion,
            },
            expected_outputs={"status": "internal synthetic"},
        ),
        "3D ERT", EvidenceClass.QUALITATIVELY_CONSISTENT, ert3d_contract, ert3d_metrics,
    ))
    contracts.append(ert3d_contract)

    # Invalid input evidence: the VES engine must reject incompatible controls
    # before producing a scientific result.
    _, ves_invalid, _ = run_ves_contract(ves, _VES_BASELINE_INITIAL, max_nfev=0)
    records.append(M22QualificationRecord(
        build_m22_manifest(
            "m22-ves-invalid-controls", domain="VES", dataset_id=ves.spec.name, project_id="qualification",
            survey_id="ves", configuration={"max_nfev": 0},
            expected_outputs={"status": "invalid input rejected before evaluation"},
        ),
        "VES", EvidenceClass.QUALITATIVELY_CONSISTENT, ves_invalid, {},
    ))
    contracts.append(ves_invalid)

    cancellation, cancellation_evidence = run_cancellation_evidence()
    records.append(M22QualificationRecord(
        build_m22_manifest(
            "m22-cancellation-safety", domain="2D ERT", dataset_id="desktop-operation-executor",
            project_id="qualification", survey_id="cancellation",
            configuration={"cancellation": "requested before the guarded commit point"},
            expected_outputs={"status": "no partial scientific state committed"},
        ),
        "2D ERT", EvidenceClass.QUALITATIVELY_CONSISTENT, cancellation, {},
    ))
    contracts.append(cancellation)

    evidence = (
        run_ves_study_evidence(),
        run_ert2d_study_evidence(),
        run_ert3d_study_evidence(),
    )
    studies = tuple(study for item in evidence for study in item.studies)
    for item in evidence:
        contracts.extend(item.contracts)

    return M22QualificationReport(
        procedure_version=PROCEDURE_VERSION,
        evidence_class=EvidenceClass.QUALITATIVELY_CONSISTENT,
        environment=environment_snapshot(),
        records=tuple(records),
        studies=studies,
        study_manifests=tuple(_study_manifest(study) for study in studies),
        outcome_coverage=outcome_coverage(contracts),
        cancellation_evidence=cancellation_evidence,
        selection_rule=(
            "Every configured bounded case is reported. No case is dropped, retried, or selected after the fact, and "
            "no 'best' result is chosen. Baselines are the M21-documented configurations (VES max_nfev=20, 2D "
            "max_iterations=1 damping=0.3 initial 1.0 Ohm.m, 3D max_iterations=1 damping=0.5 initial 1.0 Ohm.m); "
            "study baselines are fixed before execution and are recorded in each study's baseline configuration."
        ),
        metric_definitions=metric_definitions(),
        unavailable_evidence=unavailable_evidence(),
        unvalidated_claims=unvalidated_claims(),
        external_benchmarks=(
            ExternalBenchmarkReadiness(
                "m22-external-reference-gate", "no-authorized-reference-dataset",
                reason=(
                    "No legally usable independent dataset with a trustworthy expected result is available in the "
                    "repository. M22 does not acquire or fabricate reference results to change this status."
                ),
                required_evidence=(
                    "licensed dataset bytes",
                    "known acquisition and geometry metadata",
                    "source hash and provenance",
                    "trustworthy reference result",
                    "frozen preprocessing, mesh, inversion, stopping, metric, and tolerance protocol",
                ),
            ),
        ),
        limitations=(
            "Internal synthetic evidence is not independent validation.",
            "The internal fixture is small; no medium, large, or stress-scale convergence behaviour is measured.",
            "Residual reduction, stability, and reproducibility do not establish geological correctness or uniqueness.",
            "No uncertainty, resolution, or topography-aware inversion result is produced.",
            "The engines separate invalid input from numerical failure by exception class (``ERT2DError`` / "
            "``ERT3DError`` / ``VESError`` for rejected input, ``ERT2DNumericalError`` / ``ERT3DNumericalError`` / "
            "``VESNumericalError`` for a mid-run forward-model or solver failure) and by the recorded failure phase. "
            "A numerical failure that is raised as a bare ``ValueError`` by a future library version would still be "
            "recorded as ``INVALID_INPUT``; no such case is reachable in the committed studies.",
            "Reaching a configured limit is retained as bounded-completion evidence and is never reported as a defect.",
            "M15 physical LS2 validation remains pending and the ABEM/Barugo importer remains NOT_READY.",
        ),
    )


__all__ = [
    "PROCEDURE_VERSION",
    "SUPERSEDED_ARTIFACTS",
    "HISTORY_RECORDED",
    "HISTORY_UNAVAILABLE",
    "MAXIMUM_UNITS_ITERATIONS",
    "MAXIMUM_UNITS_EVALUATIONS",
    "MAXIMUM_UNITS_NOT_APPLICABLE",
    "VES_NOISE_FACTORS_V1",
    "ERT2D_NOISE_FACTORS_V1",
    "ERT3D_NOISE_FACTORS_V1",
    "FinalModelStatus",
    "TrajectoryPoint",
    "ConvergenceContract",
    "classify_outcome",
    "invalid_input_contract",
    "failed_contract",
    "cancelled_contract",
    "model_log10_vector",
    "run_ves_contract",
    "run_ert2d_contract",
    "run_ert3d_contract",
    "mesh2d_discretization",
    "mesh3d_discretization",
    "ves_discretization",
    "model_comparison_omission_reason",
    "FAILURE_PHASES",
    "PHASE_INPUT_VALIDATION",
    "PHASE_FORWARD_MODEL",
    "PHASE_SOLVER",
    "PHASE_INITIAL_MODEL",
    "PHASE_NOT_APPLICABLE",
    "StudyEvidence",
    "run_ves_study_evidence",
    "run_ert2d_study_evidence",
    "run_ert3d_study_evidence",
    "run_m22_studies",
    "run_cancellation_evidence",
    "metric_definitions",
    "unavailable_evidence",
    "unvalidated_claims",
    "M22QualificationRecord",
    "M22QualificationReport",
    "build_m22_manifest",
    "outcome_coverage",
    "run_m22_qualification",
]
