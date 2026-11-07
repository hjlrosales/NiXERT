"""Small, explicit 2D DC resistivity forward and inversion engine.

The solver discretizes ``div(sigma grad(u)) = q`` on a cell-centred
finite-volume mesh. All outer boundaries are zero-flux (Neumann); because a
current quadrupole has zero net injected current, the potential gauge is fixed
at one cell. Apparent resistivity is normalized by the same mesh's homogeneous
unit-resistivity response for each quadrupole. This makes homogeneous synthetic
validation exact while avoiding an undocumented half-space correction.

This is a research-grade baseline, not a claim of RES2DINV equivalence. The
finite domain, 2D approximation, cell-centred electrode treatment, and
zero-flux boundaries are explicit limitations. Topography is intentionally
rejected until a non-flat mesh is validated.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from scipy.sparse import csc_matrix, lil_matrix
from scipy.sparse.linalg import factorized

from nix_ert.core.numerics import percent_rms


FORWARD_FACTORIZATION_PHASE = "forward_factorization"
"""Failure phase for an accepted forward problem whose system cannot be factorized."""

FORWARD_EVALUATION_PHASE = "forward_model_evaluation"
"""Failure phase for any other forward-model numerical failure."""

SOLVER_UPDATE_PHASE = "solver_update"
"""Failure phase for a regularized model-update numerical failure."""


class ERT2DError(ValueError):
    """Raised for invalid meshes, observations, or inversion inputs."""


class ERT2DNumericalError(ERT2DError):
    """Raised when the forward solution or the solver update fails numerically.

    This is a *numerical* failure, not invalid input: the inputs were accepted
    and the failure happened while evaluating the forward response or the
    regularized model update. Qualification layers must classify it as
    ``FAILED`` rather than ``INVALID_INPUT``.

    ``phase`` records which stage failed so that the qualification layer labels
    the failure from the exception rather than from message text: one of
    :data:`FORWARD_FACTORIZATION_PHASE` (the forward system could not be
    factorized), :data:`FORWARD_EVALUATION_PHASE` (any other forward-model
    failure) or :data:`SOLVER_UPDATE_PHASE` (the regularized model update).
    """

    def __init__(self, message: str, *, phase: str = FORWARD_EVALUATION_PHASE) -> None:
        super().__init__(message)
        self.phase = phase


@dataclass(frozen=True)
class Mesh2D:
    """Cell-centred rectangular mesh; depth is positive below the surface."""

    x_edges: tuple[float, ...]
    depth_edges: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.x_edges) < 3 or len(self.depth_edges) < 2:
            raise ERT2DError("mesh needs at least two columns and one depth cell")
        if any(not math.isfinite(value) for value in (*self.x_edges, *self.depth_edges)):
            raise ERT2DError("mesh coordinates must be finite")
        if any(right <= left for left, right in zip(self.x_edges, self.x_edges[1:])):
            raise ERT2DError("x edges must be strictly increasing")
        if self.depth_edges[0] != 0 or any(right <= left for left, right in zip(self.depth_edges, self.depth_edges[1:])):
            raise ERT2DError("depth edges must start at zero and be strictly increasing")

    @property
    def nx(self) -> int:
        return len(self.x_edges) - 1

    @property
    def nz(self) -> int:
        return len(self.depth_edges) - 1

    @property
    def cell_count(self) -> int:
        return self.nx * self.nz

    @property
    def x_centres(self) -> np.ndarray:
        return (np.asarray(self.x_edges[:-1]) + np.asarray(self.x_edges[1:])) / 2

    @property
    def depth_centres(self) -> np.ndarray:
        return (np.asarray(self.depth_edges[:-1]) + np.asarray(self.depth_edges[1:])) / 2

    @classmethod
    def from_electrodes(
        cls, electrode_x: Sequence[float], *, nz: int = 6, depth: float | None = None,
    ) -> "Mesh2D":
        """Create a mesh whose top cells contain the supplied electrodes."""
        x = np.asarray(electrode_x, dtype=float)
        if x.ndim != 1 or len(x) < 2 or not np.all(np.isfinite(x)):
            raise ERT2DError("at least two finite electrode x coordinates are required")
        if np.any(np.diff(x) <= 0):
            raise ERT2DError("electrode x coordinates must be strictly increasing")
        if not isinstance(nz, int) or nz < 1:
            raise ERT2DError("nz must be a positive integer")
        spacing = float(np.median(np.diff(x)))
        if spacing <= 0:
            raise ERT2DError("electrode spacing must be positive")
        if depth is None:
            depth = max(spacing * max(3.0, nz / 2), spacing)
        if not math.isfinite(depth) or depth <= 0:
            raise ERT2DError("mesh depth must be finite and positive")
        # Extend one half-spacing beyond the outermost electrodes. This puts
        # electrode positions at cell centres while retaining side cells.
        x_edges = np.concatenate(([x[0] - spacing / 2], (x[:-1] + x[1:]) / 2, [x[-1] + spacing / 2]))
        depth_edges = np.linspace(0.0, depth, nz + 1)
        return cls(tuple(float(value) for value in x_edges), tuple(float(value) for value in depth_edges))

    def cell_index(self, column: int, layer: int) -> int:
        if not (0 <= column < self.nx and 0 <= layer < self.nz):
            raise ERT2DError("mesh cell index is out of range")
        return layer * self.nx + column


@dataclass(frozen=True)
class ERTObservation:
    """Four-electrode apparent-resistivity observation using 1-based electrodes."""

    a: int
    b: int
    m: int
    n: int
    apparent_resistivity: float
    excluded: bool = False

    def __post_init__(self) -> None:
        if len({self.a, self.b, self.m, self.n}) != 4:
            raise ERT2DError("A, B, M, and N must be distinct")
        if min(self.a, self.b, self.m, self.n) < 1:
            raise ERT2DError("electrode numbers are 1-based and must be positive")
        if not math.isfinite(self.apparent_resistivity) or self.apparent_resistivity <= 0:
            raise ERT2DError("observed apparent resistivity must be finite and positive")


@dataclass(frozen=True)
class InversionIteration:
    """One solver step, recording the objective *before* that step's update.

    ``rms_log10`` is therefore the residual of the model that entered the step.
    The objective of the returned model is :attr:`ERTInversionResult.rms_log10`,
    which is evaluated once more after the final update. Line-search trial
    evaluations are not exposed.
    """

    iteration: int
    rms_log10: float
    rms_percent: float
    damping: float
    accepted_step: float


@dataclass(frozen=True)
class ERTInversionResult:
    """Inversion output.

    ``iterations`` holds per-step pre-update objectives; ``rms_log10`` and
    ``predicted`` describe the returned model. ``converged`` is true only when
    the configured ``convergence_rms`` criterion was satisfied, never merely
    because the loop finished.
    """

    resistivity: np.ndarray
    predicted: tuple[float, ...]
    residuals_log10: tuple[float, ...]
    rms_log10: float
    rms_percent: float
    converged: bool
    iterations: tuple[InversionIteration, ...]
    message: str


def _validate_model(model: np.ndarray, mesh: Mesh2D) -> np.ndarray:
    array = np.asarray(model, dtype=float)
    if array.shape != (mesh.nz, mesh.nx):
        raise ERT2DError(f"model shape must be ({mesh.nz}, {mesh.nx})")
    if not np.all(np.isfinite(array)) or np.any(array <= 0):
        raise ERT2DError("model resistivities must be finite and positive")
    return array


def face_conductance(
    conductivity_self: float, conductivity_neighbor: float,
    width_self: float, width_neighbor: float, face_area: float,
) -> float:
    """Return the two-point flux transmissibility across a shared cell face.

    The two cells are resistors in series between their centres: half of each
    cell width belongs to each side, with its own conductivity. The exact
    transmissibility is therefore

        G = A / (w_self / (2 * sigma_self) + w_neighbor / (2 * sigma_neighbor))

    which reduces to ``A * harmonic(sigma_self, sigma_neighbor) / w`` only for
    equal widths. Using a harmonic mean of conductivities with an arithmetic
    mean of widths (the previous formulation) overestimates the conductance of
    every unequal-width face; for widths 1 and 2 with resistivities 1 and 4 it
    gave 0.2667 instead of the exact 0.2222.
    """
    return face_area / (
        width_self / (2.0 * conductivity_self)
        + width_neighbor / (2.0 * conductivity_neighbor)
    )


def _system_matrix(resistivity: np.ndarray, mesh: Mesh2D) -> csc_matrix:
    conductivity = 1.0 / resistivity
    matrix = lil_matrix((mesh.cell_count, mesh.cell_count), dtype=float)
    dx = np.diff(np.asarray(mesh.x_edges))
    dz = np.diff(np.asarray(mesh.depth_edges))
    for layer in range(mesh.nz):
        for column in range(mesh.nx):
            index = mesh.cell_index(column, layer)
            diagonal = 0.0
            if column > 0:
                conductance = face_conductance(
                    conductivity[layer, column], conductivity[layer, column - 1],
                    dx[column], dx[column - 1], dz[layer],
                )
                matrix[index, mesh.cell_index(column - 1, layer)] = -conductance
                diagonal += conductance
            if column + 1 < mesh.nx:
                conductance = face_conductance(
                    conductivity[layer, column], conductivity[layer, column + 1],
                    dx[column], dx[column + 1], dz[layer],
                )
                matrix[index, mesh.cell_index(column + 1, layer)] = -conductance
                diagonal += conductance
            if layer > 0:
                conductance = face_conductance(
                    conductivity[layer, column], conductivity[layer - 1, column],
                    dz[layer], dz[layer - 1], dx[column],
                )
                matrix[index, mesh.cell_index(column, layer - 1)] = -conductance
                diagonal += conductance
            if layer + 1 < mesh.nz:
                conductance = face_conductance(
                    conductivity[layer, column], conductivity[layer + 1, column],
                    dz[layer], dz[layer + 1], dx[column],
                )
                matrix[index, mesh.cell_index(column, layer + 1)] = -conductance
                diagonal += conductance
            matrix[index, index] = diagonal
    # Use a Lagrange multiplier for the additive-potential gauge. This keeps
    # the complete current source vector, including when an electrode occupies
    # cell zero, while imposing mean potential = 0 without altering the PDE.
    augmented = lil_matrix((mesh.cell_count + 1, mesh.cell_count + 1), dtype=float)
    augmented[:mesh.cell_count, :mesh.cell_count] = matrix
    for index in range(mesh.cell_count):
        augmented[index, mesh.cell_count] = 1.0
        augmented[mesh.cell_count, index] = 1.0
    return augmented.tocsc()


def _electrode_column(mesh: Mesh2D, electrode: int) -> int:
    if electrode < 1 or electrode > mesh.nx:
        raise ERT2DError(f"electrode {electrode} is outside the mesh")
    return electrode - 1


def _potential(
    resistivity: np.ndarray, mesh: Mesh2D, source: int, sink: int, factorization=None,
) -> np.ndarray:
    matrix = _system_matrix(resistivity, mesh) if factorization is None else None
    solve = factorized(matrix) if factorization is None else factorization
    rhs = np.zeros(mesh.cell_count + 1, dtype=float)
    source_cell = mesh.cell_index(_electrode_column(mesh, source), 0)
    sink_cell = mesh.cell_index(_electrode_column(mesh, sink), 0)
    rhs[source_cell] += 1.0
    rhs[sink_cell] -= 1.0
    return np.asarray(solve(rhs), dtype=float)[:mesh.cell_count]


def _voltage(potential: np.ndarray, mesh: Mesh2D, positive: int, negative: int) -> float:
    value = potential[mesh.cell_index(_electrode_column(mesh, positive), 0)] - potential[mesh.cell_index(_electrode_column(mesh, negative), 0)]
    if not math.isfinite(float(value)):
        raise ERT2DNumericalError("forward model produced a non-finite voltage")
    return float(value)


def forward_apparent_resistivity(
    model: np.ndarray, mesh: Mesh2D, observations: Sequence[ERTObservation],
) -> tuple[float, ...]:
    """Compute normalized numerical apparent resistivities for observations."""
    model = _validate_model(model, mesh)
    if not observations:
        raise ERT2DError("at least one ERT observation is required")
    homogeneous = np.ones_like(model)
    matrix = _system_matrix(model, mesh)
    homogeneous_matrix = _system_matrix(homogeneous, mesh)
    try:
        # scipy's SuperLU binding reports an exactly singular (or otherwise
        # unfactorizable) matrix as a bare RuntimeError while numpy reports
        # LinAlgError. The boundary is deliberately narrow: it wraps only the
        # factorization calls, so a RuntimeError raised anywhere else is never
        # relabelled as a numerical factorization failure.
        solve = factorized(matrix)
        homogeneous_solve = factorized(homogeneous_matrix)
    except (np.linalg.LinAlgError, RuntimeError) as exc:
        raise ERT2DNumericalError(
            "forward system factorization failed",
            phase=FORWARD_FACTORIZATION_PHASE,
        ) from exc
    output: list[float] = []
    for observation in observations:
        for electrode in (observation.a, observation.b, observation.m, observation.n):
            _electrode_column(mesh, electrode)
        potential = _potential(model, mesh, observation.a, observation.b, solve)
        homogeneous_potential = _potential(homogeneous, mesh, observation.a, observation.b, homogeneous_solve)
        measured_voltage = _voltage(potential, mesh, observation.m, observation.n)
        reference_voltage = _voltage(homogeneous_potential, mesh, observation.m, observation.n)
        if abs(reference_voltage) <= np.finfo(float).eps:
            raise ERT2DNumericalError("quadrupole has zero homogeneous numerical sensitivity")
        value = abs(measured_voltage / reference_voltage)
        if not math.isfinite(value) or value <= 0:
            raise ERT2DNumericalError("forward model produced an invalid apparent resistivity")
        output.append(value)
    return tuple(output)


def numerical_jacobian(
    model: np.ndarray, mesh: Mesh2D, observations: Sequence[ERTObservation], *, step: float = 1e-3,
) -> np.ndarray:
    """Central finite-difference Jacobian of log10 response vs log10 model."""
    model = _validate_model(model, mesh)
    if not math.isfinite(step) or step <= 0:
        raise ERT2DError("Jacobian step must be finite and positive")
    base = np.log10(model)
    columns: list[np.ndarray] = []
    for parameter in range(mesh.cell_count):
        plus = base.copy().reshape(-1)
        minus = base.copy().reshape(-1)
        plus[parameter] += step
        minus[parameter] -= step
        plus_response = np.log10(forward_apparent_resistivity(10.0 ** plus.reshape(model.shape), mesh, observations))
        minus_response = np.log10(forward_apparent_resistivity(10.0 ** minus.reshape(model.shape), mesh, observations))
        columns.append((plus_response - minus_response) / (2 * step))
    return np.column_stack(columns)


def invert_ert(
    observations: Sequence[ERTObservation], mesh: Mesh2D, initial_model: np.ndarray | float,
    *, max_iterations: int = 8, damping: float = 0.3, jacobian_step: float = 1e-3,
    convergence_rms: float = 1e-3,
) -> ERTInversionResult:
    """Run damped Gauss–Newton inversion in log10 resistivity space."""
    usable = tuple(observation for observation in observations if not observation.excluded)
    if not usable:
        raise ERT2DError("at least one active ERT observation is required")
    if not isinstance(max_iterations, int) or max_iterations < 1:
        raise ERT2DError("max_iterations must be a positive integer")
    if not math.isfinite(damping) or damping <= 0:
        raise ERT2DError("damping must be finite and positive")
    if not math.isfinite(jacobian_step) or jacobian_step <= 0:
        raise ERT2DError("jacobian_step must be finite and positive")
    # A non-finite or non-positive tolerance cannot be satisfied by any finite
    # residual: NaN silently disabled convergence, and infinity made every run
    # "converged" on its first evaluation. Both are invalid configuration.
    if not math.isfinite(convergence_rms) or convergence_rms <= 0:
        raise ERT2DError("convergence_rms must be finite and positive")
    if isinstance(initial_model, (int, float)):
        model = np.full((mesh.nz, mesh.nx), float(initial_model), dtype=float)
    else:
        model = np.asarray(initial_model, dtype=float).copy()
    model = _validate_model(model, mesh)
    observed_log = np.log10(np.asarray([item.apparent_resistivity for item in usable], dtype=float))
    history: list[InversionIteration] = []
    converged = False
    message = "maximum iterations reached"

    for iteration in range(max_iterations + 1):
        predicted = np.asarray(forward_apparent_resistivity(model, mesh, usable))
        predicted_log = np.log10(predicted)
        residual = observed_log - predicted_log
        rms = float(np.sqrt(np.mean(residual**2)))
        rms_percent = percent_rms(predicted, 10.0 ** observed_log)
        if rms <= convergence_rms:
            converged = True
            message = "converged"
            break
        if iteration == max_iterations:
            break
        jacobian = numerical_jacobian(model, mesh, usable, step=jacobian_step)
        normal = jacobian.T @ jacobian + (damping**2) * np.eye(mesh.cell_count)
        try:
            update = np.linalg.solve(normal, jacobian.T @ residual)
        except np.linalg.LinAlgError as exc:
            raise ERT2DNumericalError(
                "regularized model update is singular", phase=SOLVER_UPDATE_PHASE,
            ) from exc
        update = np.clip(update, -0.5, 0.5)
        base_log = np.log10(model).reshape(-1)
        accepted = 0.0
        for trial in (1.0, 0.5, 0.25, 0.125, 0.0):
            candidate = 10.0 ** (base_log + trial * update)
            candidate_prediction = np.asarray(forward_apparent_resistivity(candidate.reshape(model.shape), mesh, usable))
            candidate_rms = float(np.sqrt(np.mean((np.log10(candidate_prediction) - observed_log) ** 2)))
            if trial == 0.0 or candidate_rms < rms:
                model = candidate.reshape(model.shape)
                accepted = trial
                break
        history.append(InversionIteration(iteration + 1, rms, rms_percent, damping, accepted))
        if accepted == 0.0:
            damping *= 2.0
        else:
            damping = max(damping * 0.7, 1e-5)

    final_predicted = tuple(forward_apparent_resistivity(model, mesh, usable))
    final_residuals = tuple(float(observed - math.log10(predicted)) for observed, predicted in zip(observed_log, final_predicted))
    final_rms = float(np.sqrt(np.mean(np.asarray(final_residuals) ** 2)))
    final_percent = percent_rms(final_predicted, 10.0 ** observed_log)
    return ERTInversionResult(
        resistivity=model.copy(), predicted=final_predicted, residuals_log10=final_residuals,
        rms_log10=final_rms, rms_percent=final_percent, converged=converged,
        iterations=tuple(history), message=message,
    )
