"""Deterministic qualification dataset specifications and runners.

These datasets are internal synthetic qualification fixtures. They are not
published or commercial benchmark data and must not be presented as such.
Each fixture records expected qualitative behavior and explicit tolerances
rather than invented reference outputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from nix_ert.ert.inversion2d import ERTObservation, Mesh2D, forward_apparent_resistivity
from nix_ert.ert.inversion3d import ERT3DObservation, Mesh3D, forward_apparent_resistivity as forward_3d
from nix_ert.ves.engine import LayeredEarthModel, VESPoint, layered_apparent_resistivity


@dataclass(frozen=True)
class QualificationSpec:
    name: str
    domain: str
    source: str
    expected_behavior: str
    tolerance: str
    limitations: str


@dataclass(frozen=True)
class VESQualification:
    spec: QualificationSpec
    model: LayeredEarthModel
    clean_points: tuple[VESPoint, ...]
    noisy_points: tuple[VESPoint, ...]


@dataclass(frozen=True)
class ERT2DQualification:
    spec: QualificationSpec
    mesh: Mesh2D
    observations: tuple[ERTObservation, ...]
    noisy_observations: tuple[ERTObservation, ...]
    true_model: np.ndarray


@dataclass(frozen=True)
class ERT3DQualification:
    spec: QualificationSpec
    mesh: Mesh3D
    electrodes: tuple[tuple[float, float], ...]
    observations: tuple[ERT3DObservation, ...]
    noisy_observations: tuple[ERT3DObservation, ...]
    true_model: np.ndarray


def ves_qualification() -> VESQualification:
    spec = QualificationSpec(
        "ves-layered-internal-v1", "VES", "Internal deterministic synthetic model",
        "Forward data are finite and inversion can reduce log-space residuals.",
        "Forward reproducibility at machine-level for the same environment; inversion residual reduction > 0.",
        "No field noise model, non-uniqueness assessment, or published benchmark comparison.",
    )
    model = LayeredEarthModel((100.0, 20.0, 250.0), (5.0, 12.0))
    geometries = ((10, 2), (15, 2), (20, 2), (30, 3), (45, 3), (60, 4), (90, 5), (130, 6))
    clean = tuple(
        VESPoint(ab2, mn2, apparent_resistivity=layered_apparent_resistivity(model, ab2, mn2))
        for ab2, mn2 in geometries
    )
    noisy = tuple(
        VESPoint(point.ab2, point.mn2, apparent_resistivity=value * (1.0 + offset))
        for point, offset in zip(clean, (0.03, -0.02, 0.01, -0.04, 0.02, -0.03, 0.05, -0.01))
        for value in (point.apparent_resistivity,)
    )
    return VESQualification(spec, model, clean, noisy)


def ert2d_qualification() -> ERT2DQualification:
    spec = QualificationSpec(
        "ert-2d-anomaly-internal-v1", "2D ERT", "Internal deterministic synthetic finite-volume model",
        "Homogeneous normalization is unit-valued and inversion reduces residual from the initial model.",
        "Homogeneous response close to 1e-10 absolute; residual reduction is qualitative for the underdetermined fixture.",
        "Flat rectangular mesh, numerical normalization, no topography, no trusted external benchmark.",
    )
    mesh = Mesh2D.from_electrodes([0, 1, 2, 3, 4, 5], nz=3, depth=3)
    true_model = np.ones((3, 6))
    true_model[0, 2:4] = 3.0
    geometry = ((1, 6, 2, 3), (1, 6, 3, 4), (2, 5, 3, 4), (2, 6, 4, 5), (1, 5, 2, 4), (2, 6, 3, 5))
    clean_values = forward_apparent_resistivity(true_model, mesh, tuple(ERTObservation(*quad, 1.0) for quad in geometry))
    clean = tuple(ERTObservation(*quad, value) for quad, value in zip(geometry, clean_values))
    noisy = tuple(
        ERTObservation(item.a, item.b, item.m, item.n, item.apparent_resistivity * factor)
        for item, factor in zip(clean, (1.03, 0.98, 1.01, 0.96, 1.04, 0.99))
    )
    return ERT2DQualification(spec, mesh, clean, noisy, true_model)


def ert3d_qualification() -> ERT3DQualification:
    spec = QualificationSpec(
        "ert-3d-anomaly-internal-v1", "3D ERT", "Internal deterministic synthetic finite-volume model",
        "Homogeneous normalization is unit-valued and the small inversion fixture reduces residual.",
        "Homogeneous response close to 1e-10 absolute; residual reduction is qualitative.",
        "Small rectangular mesh, top-layer electrodes, numerical normalization, no topography or external benchmark.",
    )
    mesh = Mesh3D.regular((0, 1, 2, 3, 4), (0, 1, 2), (0, 1, 2))
    electrodes = ((0.5, 0.5), (1.5, 0.5), (2.5, 0.5), (3.5, 0.5))
    true_model = np.ones((2, 2, 4))
    true_model[0, 0, 1:3] = 4.0
    geometry = ((1, 4, 2, 3), (1, 4, 3, 2))
    clean_values = forward_3d(true_model, mesh, tuple(ERT3DObservation(*quad, 1.0) for quad in geometry), electrodes)
    clean = tuple(ERT3DObservation(*quad, value) for quad, value in zip(geometry, clean_values))
    noisy = tuple(
        ERT3DObservation(item.a, item.b, item.m, item.n, item.apparent_resistivity * factor)
        for item, factor in zip(clean, (1.04, 0.97))
    )
    return ERT3DQualification(spec, mesh, electrodes, clean, noisy, true_model)


def qualification_specs() -> tuple[QualificationSpec, ...]:
    return (ves_qualification().spec, ert2d_qualification().spec, ert3d_qualification().spec)
