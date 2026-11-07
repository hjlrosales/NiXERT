"""Baseline 3D DC resistivity forward modeling and inversion.

This is the 3D extension of the explicit finite-volume baseline: rectangular
cell-centred mesh, zero-flux boundaries, top-cell electrodes, numerical
homogeneous normalization, central-difference Jacobian, and damped Gauss–
Newton updates in log10 resistivity. It is intentionally not a claim of
production-grade or RES2DINV-equivalent behavior.

Result semantics: the objective history returned by :func:`invert_ert3d` is the
sequence of log10-RMS solver evaluations and it always terminates at the
objective of the returned model, so ``history[-1]`` and the returned
convergence flag describe the model that is actually returned. ``nfev``-style
internal work (Jacobian evaluations and trial steps) is not exposed as history.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from scipy.sparse import lil_matrix
from scipy.sparse.linalg import factorized


from nix_ert.ert.inversion2d import (
    FORWARD_EVALUATION_PHASE,
    FORWARD_FACTORIZATION_PHASE,
    SOLVER_UPDATE_PHASE,
    face_conductance,
)


class ERT3DError(ValueError):
    """Raised for invalid 3D meshes, observations, or inversion inputs."""


class ERT3DNumericalError(ERT3DError):
    """Raised when the 3D forward solution or solver update fails numerically.

    Inputs were accepted; the failure happened while solving. Qualification
    layers must classify it as ``FAILED`` rather than ``INVALID_INPUT``.
    ``phase`` names the stage that failed, matching the 2D engine's vocabulary:
    :data:`FORWARD_FACTORIZATION_PHASE`, :data:`FORWARD_EVALUATION_PHASE`, or
    :data:`SOLVER_UPDATE_PHASE`.
    """

    def __init__(self, message: str, *, phase: str = FORWARD_EVALUATION_PHASE) -> None:
        super().__init__(message)
        self.phase = phase


ERT3D_CONVERGENCE_RMS = 1e-3
"""Configured log10-RMS convergence tolerance used by :func:`invert_ert3d`."""


@dataclass(frozen=True)
class Mesh3D:
    x_edges: tuple[float, ...]
    y_edges: tuple[float, ...]
    depth_edges: tuple[float, ...]

    def __post_init__(self) -> None:
        if any(len(edges) < 2 for edges in (self.x_edges, self.y_edges, self.depth_edges)):
            raise ERT3DError("mesh needs at least one cell in each dimension")
        if any(not math.isfinite(value) for edges in (self.x_edges, self.y_edges, self.depth_edges) for value in edges):
            raise ERT3DError("mesh coordinates must be finite")
        if any(right <= left for edges in (self.x_edges, self.y_edges, self.depth_edges) for left, right in zip(edges, edges[1:])):
            raise ERT3DError("mesh edges must increase")
        if self.depth_edges[0] != 0:
            raise ERT3DError("depth edges must start at zero")

    @property
    def nx(self) -> int:
        return len(self.x_edges) - 1

    @property
    def ny(self) -> int:
        return len(self.y_edges) - 1

    @property
    def nz(self) -> int:
        return len(self.depth_edges) - 1

    @property
    def cell_count(self) -> int:
        return self.nx * self.ny * self.nz

    @property
    def x_centres(self) -> np.ndarray:
        return (np.asarray(self.x_edges[:-1]) + np.asarray(self.x_edges[1:])) / 2

    @property
    def y_centres(self) -> np.ndarray:
        return (np.asarray(self.y_edges[:-1]) + np.asarray(self.y_edges[1:])) / 2

    @property
    def depth_centres(self) -> np.ndarray:
        return (np.asarray(self.depth_edges[:-1]) + np.asarray(self.depth_edges[1:])) / 2

    def cell_index(self, ix: int, iy: int, iz: int) -> int:
        if not (0 <= ix < self.nx and 0 <= iy < self.ny and 0 <= iz < self.nz):
            raise ERT3DError("mesh cell index is out of range")
        return (iz * self.ny + iy) * self.nx + ix

    @classmethod
    def regular(cls, x_edges: Sequence[float], y_edges: Sequence[float], depth_edges: Sequence[float]) -> "Mesh3D":
        return cls(tuple(float(value) for value in x_edges), tuple(float(value) for value in y_edges), tuple(float(value) for value in depth_edges))


@dataclass(frozen=True)
class ERT3DObservation:
    a: int
    b: int
    m: int
    n: int
    apparent_resistivity: float
    excluded: bool = False

    def __post_init__(self) -> None:
        if len({self.a, self.b, self.m, self.n}) != 4 or min(self.a, self.b, self.m, self.n) < 1:
            raise ERT3DError("A, B, M, and N must be distinct positive electrode numbers")
        if not math.isfinite(self.apparent_resistivity) or self.apparent_resistivity <= 0:
            raise ERT3DError("apparent resistivity must be finite and positive")


def _matrix(model: np.ndarray, mesh: Mesh3D):
    conductivity = 1 / model
    matrix = lil_matrix((mesh.cell_count, mesh.cell_count), dtype=float)
    dx, dy, dz = np.diff(mesh.x_edges), np.diff(mesh.y_edges), np.diff(mesh.depth_edges)
    for iz in range(mesh.nz):
        for iy in range(mesh.ny):
            for ix in range(mesh.nx):
                index = mesh.cell_index(ix, iy, iz)
                diagonal = 0.0
                # (neighbour index, neighbour conductivity, self width,
                #  neighbour width, shared face area)
                neighbours = (
                    ((ix - 1, iy, iz), conductivity[iz, iy, ix - 1], dx[ix], dx[ix - 1], dy[iy] * dz[iz]) if ix > 0 else None,
                    ((ix + 1, iy, iz), conductivity[iz, iy, ix + 1], dx[ix], dx[ix + 1], dy[iy] * dz[iz]) if ix + 1 < mesh.nx else None,
                    ((ix, iy - 1, iz), conductivity[iz, iy - 1, ix], dy[iy], dy[iy - 1], dx[ix] * dz[iz]) if iy > 0 else None,
                    ((ix, iy + 1, iz), conductivity[iz, iy + 1, ix], dy[iy], dy[iy + 1], dx[ix] * dz[iz]) if iy + 1 < mesh.ny else None,
                    ((ix, iy, iz - 1), conductivity[iz - 1, iy, ix], dz[iz], dz[iz - 1], dx[ix] * dy[iy]) if iz > 0 else None,
                    ((ix, iy, iz + 1), conductivity[iz + 1, iy, ix], dz[iz], dz[iz + 1], dx[ix] * dy[iy]) if iz + 1 < mesh.nz else None,
                )
                for neighbour in neighbours:
                    if neighbour is None:
                        continue
                    location, neighbour_conductivity, self_width, neighbour_width, area = neighbour
                    conductance = face_conductance(
                        conductivity[iz, iy, ix], neighbour_conductivity,
                        self_width, neighbour_width, area,
                    )
                    matrix[index, mesh.cell_index(*location)] = -conductance
                    diagonal += conductance
                matrix[index, index] = diagonal
    # Impose a zero-mean potential with a Lagrange multiplier so source/sink
    # terms are never lost when an electrode maps to cell zero.
    augmented = lil_matrix((mesh.cell_count + 1, mesh.cell_count + 1), dtype=float)
    augmented[:mesh.cell_count, :mesh.cell_count] = matrix
    for index in range(mesh.cell_count):
        augmented[index, mesh.cell_count] = 1.0
        augmented[mesh.cell_count, index] = 1.0
    return augmented.tocsc()


def _validate_model(model: np.ndarray, mesh: Mesh3D) -> np.ndarray:
    array = np.asarray(model, dtype=float)
    expected = (mesh.nz, mesh.ny, mesh.nx)
    if array.shape != expected or not np.all(np.isfinite(array)) or np.any(array <= 0):
        raise ERT3DError(f"model must have finite positive shape {expected}")
    return array


def _electrode_cell(mesh: Mesh3D, electrode: int, electrode_xy: Sequence[tuple[float, float]]) -> int:
    if electrode < 1 or electrode > len(electrode_xy):
        raise ERT3DError(f"electrode {electrode} has no coordinate")
    x, y = (float(value) for value in electrode_xy[electrode - 1])
    if not math.isfinite(x) or not math.isfinite(y):
        raise ERT3DError(f"electrode {electrode} coordinate must be finite")
    if x < mesh.x_edges[0] or x > mesh.x_edges[-1] or y < mesh.y_edges[0] or y > mesh.y_edges[-1]:
        raise ERT3DError(f"electrode {electrode} lies outside the mesh")
    ix = int(np.argmin(abs(mesh.x_centres - x)))
    iy = int(np.argmin(abs(mesh.y_centres - y)))
    return mesh.cell_index(ix, iy, 0)


def _response(model: np.ndarray, mesh: Mesh3D, observation: ERT3DObservation, electrodes: Sequence[tuple[float, float]], solve, homogeneous_solve) -> float:
    rhs = np.zeros(mesh.cell_count + 1)
    rhs[_electrode_cell(mesh, observation.a, electrodes)] += 1
    rhs[_electrode_cell(mesh, observation.b, electrodes)] -= 1
    potential = np.asarray(solve(rhs))[:mesh.cell_count]
    homogeneous_potential = np.asarray(homogeneous_solve(rhs))[:mesh.cell_count]
    m_cell = _electrode_cell(mesh, observation.m, electrodes)
    n_cell = _electrode_cell(mesh, observation.n, electrodes)
    measured = potential[m_cell] - potential[n_cell]
    reference = homogeneous_potential[m_cell] - homogeneous_potential[n_cell]
    if abs(reference) <= np.finfo(float).eps:
        raise ERT3DNumericalError("quadrupole has zero homogeneous numerical sensitivity")
    value = abs(measured / reference)
    if not math.isfinite(float(value)) or value <= 0:
        raise ERT3DNumericalError("forward model produced invalid apparent resistivity")
    return float(value)


def forward_apparent_resistivity(model: np.ndarray, mesh: Mesh3D, observations: Sequence[ERT3DObservation], electrodes: Sequence[tuple[float, float]]) -> tuple[float, ...]:
    model = _validate_model(model, mesh)
    if not observations:
        raise ERT3DError("at least one observation is required")
    if not electrodes:
        raise ERT3DError("at least one electrode coordinate is required")
    for observation in observations:
        mapped_cells = tuple(
            _electrode_cell(mesh, electrode, electrodes)
            for electrode in (observation.a, observation.b, observation.m, observation.n)
        )
        if len(set(mapped_cells)) != 4:
            raise ERT3DError(
                "quadrupole electrodes must map to four distinct mesh cells"
            )
    matrices = (_matrix(model, mesh), _matrix(np.ones_like(model), mesh))
    try:
        # See the 2D engine: SuperLU reports an exactly singular system as a
        # bare RuntimeError. The boundary wraps only the factorization calls.
        solve, homogeneous_solve = factorized(matrices[0]), factorized(matrices[1])
    except (np.linalg.LinAlgError, RuntimeError) as exc:
        raise ERT3DNumericalError(
            "forward system factorization failed",
            phase=FORWARD_FACTORIZATION_PHASE,
        ) from exc
    return tuple(_response(model, mesh, observation, electrodes, solve, homogeneous_solve) for observation in observations)


def numerical_jacobian(model: np.ndarray, mesh: Mesh3D, observations: Sequence[ERT3DObservation], electrodes: Sequence[tuple[float, float]], step: float = 1e-3) -> np.ndarray:
    model = _validate_model(model, mesh)
    if not math.isfinite(step) or step <= 0:
        raise ERT3DError("Jacobian step must be positive and finite")
    base = np.log10(model).reshape(-1)
    columns = []
    for index in range(mesh.cell_count):
        plus, minus = base.copy(), base.copy()
        plus[index] += step
        minus[index] -= step
        plus_response = np.log10(forward_apparent_resistivity((10**plus).reshape(model.shape), mesh, observations, electrodes))
        minus_response = np.log10(forward_apparent_resistivity((10**minus).reshape(model.shape), mesh, observations, electrodes))
        columns.append((plus_response - minus_response) / (2 * step))
    return np.column_stack(columns)


def invert_ert3d(observations: Sequence[ERT3DObservation], mesh: Mesh3D, electrodes: Sequence[tuple[float, float]], initial_model: np.ndarray | float, *, max_iterations: int = 5, damping: float = 0.5) -> tuple[np.ndarray, tuple[float, ...], tuple[float, ...], bool]:
    usable = tuple(item for item in observations if not item.excluded)
    if not usable:
        raise ERT3DError("at least one active observation is required")
    if not isinstance(max_iterations, int) or max_iterations < 1 or not math.isfinite(damping) or damping <= 0:
        raise ERT3DError("invalid inversion controls")
    model = np.full((mesh.nz, mesh.ny, mesh.nx), float(initial_model)) if isinstance(initial_model, (float, int)) else np.asarray(initial_model, dtype=float).copy()
    model = _validate_model(model, mesh)
    observed = np.log10([item.apparent_resistivity for item in usable])
    history: list[float] = []
    for _ in range(max_iterations):
        predicted = np.log10(forward_apparent_resistivity(model, mesh, usable, electrodes))
        residual = observed - predicted
        rms = float(np.sqrt(np.mean(residual**2)))
        history.append(rms)
        if rms <= ERT3D_CONVERGENCE_RMS:
            return model, tuple(10**predicted), tuple(history), True
        jacobian = numerical_jacobian(model, mesh, usable, electrodes)
        try:
            update = np.linalg.solve(jacobian.T @ jacobian + damping**2 * np.eye(mesh.cell_count), jacobian.T @ residual)
        except np.linalg.LinAlgError as exc:
            raise ERT3DNumericalError(
                "regularized model update is singular", phase=SOLVER_UPDATE_PHASE,
            ) from exc
        update = np.clip(update, -0.5, 0.5)
        model = 10 ** (np.log10(model).reshape(-1) + damping * update).reshape(model.shape)
    final = forward_apparent_resistivity(model, mesh, usable, electrodes)
    final_rms = float(np.sqrt(np.mean((observed - np.log10(final)) ** 2)))
    # The last accepted update changed the model after the objective above was
    # computed. Record the returned model's own evaluation so that the history
    # and the convergence flag describe the model that is actually returned.
    history.append(final_rms)
    return model, final, tuple(history), final_rms <= ERT3D_CONVERGENCE_RMS
