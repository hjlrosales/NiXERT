"""M23 forward-physics correction and qualification-integrity regression tests.

Every expected value in this module is derived independently of the code under
test:

* the layered-earth reference is the classical two-layer image/reflection series,
  which shares no code path with the engine's numerical Hankel quadrature;
* the interface transmissibility reference is the exact series resistance of two
  half-cells between their centres;
* the mesh-assembly checks reconstruct the expected conductance from the mesh
  edges and the model rather than reading it back from the assembled matrix.

These tests encode demonstrated defects, so they must keep failing if the
corrections are reverted.
"""

from __future__ import annotations

import contextlib
import math
import tempfile
import unittest
import warnings
from dataclasses import replace
from decimal import Decimal, localcontext
from pathlib import Path
from unittest import mock

import numpy as np

from nix_ert.app.workflow import ERTWorkflow, WorkflowError
from nix_ert.core.numerics import percent_rms
from nix_ert.data.dat_import import DATParseError, parse_dat
from nix_ert.data.measurements import Electrode, ImportedDataset, Measurement
from nix_ert.data.models import ProjectMetadata, SurveyType
from nix_ert.data.project import ProjectStore
from nix_ert.ert.inversion2d import (
    FORWARD_EVALUATION_PHASE,
    FORWARD_FACTORIZATION_PHASE,
    SOLVER_UPDATE_PHASE,
    ERT2DError,
    ERT2DNumericalError,
    ERTObservation,
    Mesh2D,
    _system_matrix,
    face_conductance,
    forward_apparent_resistivity as forward_2d,
    invert_ert,
)
from nix_ert.ert.inversion3d import (
    ERT3DNumericalError,
    ERT3DObservation,
    Mesh3D,
    _matrix,
    forward_apparent_resistivity as forward_3d,
    invert_ert3d,
)
from nix_ert.qualification.datasets import (
    ert2d_qualification,
    ert3d_qualification,
    ves_qualification,
)
from nix_ert.qualification.m21 import comparison_metrics
from nix_ert.qualification.m22 import (
    FAILURE_PHASES,
    PHASE_FORWARD_FACTORIZATION,
    PHASE_FORWARD_MODEL,
    PHASE_INPUT_VALIDATION,
    PHASE_SOLVER,
    QualificationOutcome,
    failed_contract,
    mesh2d_discretization,
    mesh3d_discretization,
    model_comparison_omission_reason,
    run_ert2d_contract,
    run_ert3d_contract,
    run_ves_contract,
    ves_discretization,
)
from nix_ert.qualification.registry import (
    BenchmarkComparison,
    BenchmarkProtocol,
    ComparisonStatus,
    DatasetClassification,
    LicenseStatus,
    QualificationDataset,
    QualificationRegistry,
    freeze_mapping,
    thaw,
)
from nix_ert.ves.data import parse_ves
from nix_ert.ves.engine import (
    LayeredEarthModel,
    VESError,
    VESNumericalError,
    VESPoint,
    invert_ves,
    layered_apparent_resistivity,
)

# ---------------------------------------------------------------------------
# A1 — independent two-layer forward reference
# ---------------------------------------------------------------------------


def two_layer_schlumberger_reference(
    rho_1: float, rho_2: float, thickness: float, ab2: float, mn2: float,
) -> float:
    """Two-layer Schlumberger apparent resistivity from the image series.

    For a point source on a two-layer earth the surface potential is the exact
    reflection series ``V(r) = (I rho_1 / 2 pi r) [1 + 2 sum k^n / sqrt(1 + (2 n h / r)^2)]``
    with ``k = (rho_2 - rho_1) / (rho_2 + rho_1)``. Applying the Schlumberger
    geometric factor ``pi (ab2^2 - mn2^2) / (2 mn2)`` gives

        rho_a = rho_1 (ab2^2 - mn2^2) / (2 mn2) [f(ab2 - mn2) - f(ab2 + mn2)]

    where ``f`` is the bracketed kernel including the ``1/r`` prefactor. This
    shares no code with the engine's Hankel quadrature. 800 terms is far beyond
    convergence for ``|k| < 1`` (``|k|^800 < 1e-62``).
    """
    reflection = (rho_2 - rho_1) / (rho_2 + rho_1)

    def kernel(distance: float) -> float:
        series = sum(
            reflection**n / math.sqrt(1.0 + (2.0 * n * thickness / distance) ** 2)
            for n in range(1, 801)
        )
        return (1.0 + 2.0 * series) / distance

    return (
        rho_1
        * (ab2**2 - mn2**2)
        / (2.0 * mn2)
        * (kernel(ab2 - mn2) - kernel(ab2 + mn2))
    )


_TWO_LAYER_CASES = (
    (100.0, 10.0, 8.0, 10.0, 1.0),
    (100.0, 20.0, 5.0, 20.0, 2.0),
    (50.0, 500.0, 12.0, 45.0, 3.0),
    (200.0, 5.0, 3.0, 130.0, 6.0),
    (10.0, 100.0, 40.0, 15.0, 2.0),
    # Worst case measured over a 525-case two-layer sweep of contrasts (0.01x - 100x),
    # thicknesses (0.5 - 500 m) and Schlumberger geometries (AB/2 10 - 500 m).
    (100.0, 10000.0, 0.5, 60.0, 4.0),
)


class VESLayeredKernelTests(unittest.TestCase):
    """A1: the kernel must reproduce the independent image-series reference."""

    def test_audit_reference_case_matches_independent_series(self) -> None:
        # The audit case: rho1 = 100, rho2 = 10, h = 8 m, AB/2 = 10 m, MN/2 = 1 m.
        reference = two_layer_schlumberger_reference(100.0, 10.0, 8.0, 10.0, 1.0)
        self.assertAlmostEqual(reference, 78.76163158480, places=7)
        engine = layered_apparent_resistivity(
            LayeredEarthModel((100.0, 10.0), (8.0,)), 10.0, 1.0
        )
        # The pre-correction kernel returned 91.78282027 (16.5% high) here.
        self.assertLess(abs(engine - reference) / reference, 1e-9)

    def test_two_layer_cases_match_the_image_series(self) -> None:
        for rho_1, rho_2, thickness, ab2, mn2 in _TWO_LAYER_CASES:
            with self.subTest(case=(rho_1, rho_2, thickness, ab2, mn2)):
                reference = two_layer_schlumberger_reference(rho_1, rho_2, thickness, ab2, mn2)
                engine = layered_apparent_resistivity(
                    LayeredEarthModel((rho_1, rho_2), (thickness,)), ab2, mn2
                )
                self.assertLess(abs(engine - reference) / reference, 1e-9)

    def test_homogeneous_halfspace_is_exact(self) -> None:
        for rho, ab2, mn2 in ((100.0, 10.0, 1.0), (7.5, 200.0, 20.0), (0.5, 3.0, 0.25)):
            with self.subTest(case=(rho, ab2, mn2)):
                value = layered_apparent_resistivity(LayeredEarthModel((rho,), ()), ab2, mn2)
                self.assertLess(abs(value - rho) / rho, 1e-12)

    def test_layer_limits_approach_the_expected_halfspace(self) -> None:
        # A very thick second layer is invisible to a shallow sounding.
        thick = layered_apparent_resistivity(
            LayeredEarthModel((100.0, 10.0), (1e6,)), 10.0, 1.0
        )
        self.assertLess(abs(thick - 100.0) / 100.0, 1e-6)
        # A vanishingly thin top layer exposes the second layer.
        for thickness, tolerance in ((0.05, 1e-3), (0.01, 1e-4)):
            with self.subTest(thickness=thickness):
                thin = layered_apparent_resistivity(
                    LayeredEarthModel((100.0, 10.0), (thickness,)), 10.0, 1.0
                )
                self.assertLess(abs(thin - 10.0) / 10.0, tolerance)

    def test_geometric_scale_invariance(self) -> None:
        base_model = LayeredEarthModel((100.0, 10.0), (8.0,))
        base = layered_apparent_resistivity(base_model, 10.0, 1.0)
        for scale in (0.5, 2.0, 7.0, 100.0):
            with self.subTest(scale=scale):
                scaled = layered_apparent_resistivity(
                    LayeredEarthModel((100.0, 10.0), (8.0 * scale,)),
                    10.0 * scale,
                    1.0 * scale,
                )
                self.assertLess(abs(scaled - base) / base, 1e-9)

    def test_quadrature_convergence_is_certified_not_silently_wrong(self) -> None:
        # A layer far thinner than the documented certification floor must raise
        # the forward-model numerical error rather than return a wrong value.
        with self.assertRaises(VESNumericalError):
            layered_apparent_resistivity(LayeredEarthModel((100.0, 10.0), (1e-6,)), 10.0, 1.0)
        with self.assertRaises(VESNumericalError):
            layered_apparent_resistivity(LayeredEarthModel((100.0, 10.0), (1e-12,)), 10.0, 1.0)

    def test_refining_the_sounding_does_not_change_the_reference_agreement(self) -> None:
        # Convergence-accuracy check: agreement must not degrade as AB/2/MN/2 grow.
        for ab2, mn2 in ((10.0, 1.0), (20.0, 2.0), (60.0, 4.0), (130.0, 6.0)):
            with self.subTest(ab2=ab2, mn2=mn2):
                reference = two_layer_schlumberger_reference(100.0, 20.0, 5.0, ab2, mn2)
                engine = layered_apparent_resistivity(
                    LayeredEarthModel((100.0, 20.0), (5.0,)), ab2, mn2
                )
                self.assertLess(abs(engine - reference) / reference, 1e-9)


# ---------------------------------------------------------------------------
# A2 / A3 — nonuniform-mesh assembly and interface transmissibility
# ---------------------------------------------------------------------------

_NONUNIFORM_3D = Mesh3D.regular((0, 1, 3, 6, 10), (0, 1, 3), (0, 1, 3))


def _heterogeneous_3d_model(mesh: Mesh3D) -> np.ndarray:
    """A deterministic heterogeneous model spread over three decades."""
    generator = np.random.default_rng(20230916)
    return np.exp(
        generator.uniform(math.log(5.0), math.log(200.0), size=(mesh.nz, mesh.ny, mesh.nx))
    )


def _expected_3d_conductances(mesh: Mesh3D, model: np.ndarray) -> dict[tuple[int, int], float]:
    """Recompute every shared-face conductance from the mesh edges alone."""
    conductivity = 1.0 / model
    dx, dy, dz = np.diff(mesh.x_edges), np.diff(mesh.y_edges), np.diff(mesh.depth_edges)
    expected: dict[tuple[int, int], float] = {}
    for iz in range(mesh.nz):
        for iy in range(mesh.ny):
            for ix in range(mesh.nx):
                index = mesh.cell_index(ix, iy, iz)
                faces: list[tuple[tuple[int, int, int], float, float, float]] = []
                if ix + 1 < mesh.nx:
                    faces.append(((ix + 1, iy, iz), dx[ix], dx[ix + 1], dy[iy] * dz[iz]))
                if iy + 1 < mesh.ny:
                    faces.append(((ix, iy + 1, iz), dy[iy], dy[iy + 1], dx[ix] * dz[iz]))
                if iz + 1 < mesh.nz:
                    faces.append(((ix, iy, iz + 1), dz[iz], dz[iz + 1], dx[ix] * dy[iy]))
                for neighbour, width_self, width_neighbour, area in faces:
                    other = mesh.cell_index(*neighbour)
                    expected[(index, other)] = face_conductance(
                        conductivity[iz, iy, ix],
                        conductivity[neighbour[2], neighbour[1], neighbour[0]],
                        width_self,
                        width_neighbour,
                        area,
                    )
    return expected


class InterfaceTransmissibilityTests(unittest.TestCase):
    """A3: conductance must be the exact series resistance between centres."""

    def test_audit_case_is_exact_series_resistance(self) -> None:
        # widths 1 and 2, resistivities 1 and 4, unit face area.
        conductance = face_conductance(1.0 / 1.0, 1.0 / 4.0, 1.0, 2.0, 1.0)
        self.assertAlmostEqual(conductance, 0.2222222222222222, places=15)
        # Exact two-material series resistance between the two cell centres.
        self.assertAlmostEqual(1.0 / conductance, 1.0 * 1.0 / 2.0 + 4.0 * 2.0 / 2.0, places=12)
        # The pre-correction harmonic/arithmetic form gave 0.2666667 here.
        self.assertNotAlmostEqual(conductance, 0.26666666666666666, places=6)

    def test_series_formula_matches_the_general_expression(self) -> None:
        for rho_self, rho_neighbour, width_self, width_neighbour, area in (
            (1.0, 4.0, 1.0, 2.0, 1.0),
            (10.0, 40.0, 1.0, 2.0, 1.0),
            (10.0, 40.0, 2.0, 3.0, 1.0),
            (200.0, 5.0, 3.0, 1.0, 7.5),
            (1e3, 1e-1, 0.5, 12.5, 0.25),
        ):
            with self.subTest(case=(rho_self, rho_neighbour, width_self, width_neighbour, area)):
                expected = area / (
                    rho_self * width_self / 2.0 + rho_neighbour * width_neighbour / 2.0
                )
                self.assertAlmostEqual(
                    face_conductance(
                        1.0 / rho_self, 1.0 / rho_neighbour, width_self, width_neighbour, area
                    ),
                    expected,
                    places=12,
                )

    def test_conductance_is_symmetric_under_cell_swap(self) -> None:
        forward = face_conductance(1.0 / 10.0, 1.0 / 40.0, 2.0, 3.0, 1.0)
        backward = face_conductance(1.0 / 40.0, 1.0 / 10.0, 3.0, 2.0, 1.0)
        self.assertAlmostEqual(forward, backward, places=15)

    def test_equal_widths_reduce_to_the_harmonic_form(self) -> None:
        # For equal widths w the series form is exactly A * harmonic(sigma) / w.
        sigma_self, sigma_neighbour, width, area = 0.1, 0.025, 2.0, 2.0
        harmonic = 2.0 / (1.0 / sigma_self + 1.0 / sigma_neighbour)
        self.assertAlmostEqual(
            face_conductance(sigma_self, sigma_neighbour, width, width, area),
            area * harmonic / width,
            places=15,
        )

    def test_2d_unequal_width_faces_use_the_exact_series_value(self) -> None:
        mesh = Mesh2D((0.0, 1.0, 3.0, 6.0), (0.0, 1.0, 3.0))
        model = np.asarray([[10.0, 40.0, 10.0], [10.0, 40.0, 10.0]])
        matrix = _system_matrix(model, mesh).toarray()[: mesh.cell_count, : mesh.cell_count]
        for column, (self_rho, neighbour_rho, self_width, neighbour_width) in enumerate(
            ((10.0, 40.0, 1.0, 2.0), (40.0, 10.0, 2.0, 3.0))
        ):
            with self.subTest(column=column):
                left = mesh.cell_index(column, 0)
                right = mesh.cell_index(column + 1, 0)
                expected = face_conductance(
                    1.0 / self_rho, 1.0 / neighbour_rho, self_width, neighbour_width, 1.0
                )
                self.assertAlmostEqual(-matrix[left, right], expected, places=12)
                self.assertAlmostEqual(-matrix[right, left], expected, places=12)
        # Column interfaces conserve flux and remain symmetric.
        np.testing.assert_allclose(matrix, matrix.T, rtol=0, atol=1e-15)
        np.testing.assert_allclose(matrix.sum(axis=1), 0.0, atol=1e-14)

    def test_2d_unequal_depth_faces_use_the_exact_series_value(self) -> None:
        mesh = Mesh2D((0.0, 2.0, 4.0), (0.0, 1.0, 3.0, 7.0))
        model = np.asarray([[10.0, 10.0], [40.0, 40.0], [10.0, 10.0]])
        matrix = _system_matrix(model, mesh).toarray()[: mesh.cell_count, : mesh.cell_count]
        for layer, (self_rho, neighbour_rho, self_height, neighbour_height) in enumerate(
            ((10.0, 40.0, 1.0, 2.0), (40.0, 10.0, 2.0, 4.0))
        ):
            with self.subTest(layer=layer):
                upper = mesh.cell_index(0, layer)
                lower = mesh.cell_index(0, layer + 1)
                expected = face_conductance(
                    1.0 / self_rho, 1.0 / neighbour_rho, self_height, neighbour_height, 2.0
                )
                self.assertAlmostEqual(-matrix[upper, lower], expected, places=12)
                self.assertAlmostEqual(-matrix[lower, upper], expected, places=12)
        np.testing.assert_allclose(matrix.sum(axis=1), 0.0, atol=1e-14)

    def test_3d_faces_agree_with_the_recomputed_conductance_on_every_axis(self) -> None:
        model = _heterogeneous_3d_model(_NONUNIFORM_3D)
        matrix = _matrix(model, _NONUNIFORM_3D).toarray()[
            : _NONUNIFORM_3D.cell_count, : _NONUNIFORM_3D.cell_count
        ]
        expected = _expected_3d_conductances(_NONUNIFORM_3D, model)
        self.assertTrue(expected)
        for (index, other), conductance in expected.items():
            with self.subTest(face=(index, other)):
                self.assertAlmostEqual(matrix[index, other], -conductance, places=12)


class NonuniformMeshAssemblyTests(unittest.TestCase):
    """A2: the nonuniform 3D assembly must be symmetric and conservative."""

    def test_3d_matrix_is_symmetric(self) -> None:
        model = _heterogeneous_3d_model(_NONUNIFORM_3D)
        dense = _matrix(model, _NONUNIFORM_3D).toarray()[
            : _NONUNIFORM_3D.cell_count, : _NONUNIFORM_3D.cell_count
        ]
        # The pre-correction assembly was asymmetric here: a face used its own
        # cell width twice whenever the neighbour index was larger.
        np.testing.assert_allclose(dense, dense.T, rtol=0, atol=1e-12)

    def test_3d_assembly_conserves_flux_and_signs(self) -> None:
        model = _heterogeneous_3d_model(_NONUNIFORM_3D)
        dense = _matrix(model, _NONUNIFORM_3D).toarray()[
            : _NONUNIFORM_3D.cell_count, : _NONUNIFORM_3D.cell_count
        ]
        np.testing.assert_allclose(dense.sum(axis=1), 0.0, atol=1e-12)
        self.assertTrue(np.all(np.diag(dense) > 0))
        off_diagonal = dense - np.diag(np.diag(dense))
        self.assertTrue(np.all(off_diagonal <= 1e-14))

    def test_3d_reciprocity_on_the_nonuniform_heterogeneous_fixture(self) -> None:
        model = _heterogeneous_3d_model(_NONUNIFORM_3D)
        electrodes = ((0.5, 0.5), (2.0, 0.5), (4.0, 0.5), (8.0, 0.5))
        forward = forward_3d(
            model, _NONUNIFORM_3D, (ERT3DObservation(1, 4, 2, 3, 1.0),), electrodes
        )[0]
        reciprocal = forward_3d(
            model, _NONUNIFORM_3D, (ERT3DObservation(2, 3, 1, 4, 1.0),), electrodes
        )[0]
        self.assertGreater(forward, 0.0)
        self.assertLess(abs(forward - reciprocal) / forward, 1e-12)

    def test_3d_homogeneous_nonuniform_mesh_still_normalises(self) -> None:
        model = np.full((_NONUNIFORM_3D.nz, _NONUNIFORM_3D.ny, _NONUNIFORM_3D.nx), 37.0)
        electrodes = ((0.5, 0.5), (2.0, 0.5), (4.0, 0.5), (8.0, 0.5))
        response = forward_3d(
            model, _NONUNIFORM_3D, (ERT3DObservation(1, 4, 2, 3, 1.0),), electrodes
        )[0]
        self.assertAlmostEqual(response / 37.0, 1.0, places=9)


# ---------------------------------------------------------------------------
# A4 — imported geometry binding and fail-closed behaviour
# ---------------------------------------------------------------------------


def _dataset(
    name: str, spacing: float, electrodes: tuple[Electrode, ...],
    measurements: tuple[Measurement, ...],
) -> ImportedDataset:
    return ImportedDataset(
        source_name=name,
        data_count=len(measurements),
        electrode_spacing=spacing,
        array_type="Wenner",
        measurements=measurements,
        electrodes=electrodes,
    )


class GeometryBindingTests(unittest.TestCase):
    """A4: one imported source must never redefine another source's geometry."""

    def _store(self, root: Path) -> tuple[ProjectStore, str]:
        store = ProjectStore(root / "project.sqlite3")
        store.open()
        store.save_metadata(ProjectMetadata("M23 geometry"))
        survey = store.add_survey("Line 1", SurveyType.ERT)
        return store, survey.id

    def _record(self, store: ProjectStore, survey_id: str, dataset: ImportedDataset, name: str) -> None:
        path = store.path.parent / name
        path.write_text(name, encoding="utf-8")
        store.record_import(survey_id, name, path, name, len(name), dataset)

    def test_geometry_is_stored_per_source_and_not_moved_by_a_later_import(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, survey_id = self._store(Path(directory))
            try:
                first = _dataset(
                    "a.dat", 5.0,
                    tuple(Electrode(number=n, x=(n - 1) * 5.0) for n in range(1, 5)),
                    (Measurement(1, 1, 4, 2, 3, apparent_resistivity=100.0),),
                )
                second = _dataset(
                    "b.dat", 7.0,
                    tuple(Electrode(number=n, x=(n - 1) * 7.0) for n in range(1, 5)),
                    (Measurement(1, 1, 4, 2, 3, apparent_resistivity=120.0),),
                )
                self._record(store, survey_id, first, "a.dat")
                self._record(store, survey_id, second, "b.dat")
                rows = store.list_electrodes(survey_id)
                by_source: dict[str, list[float]] = {}
                for source_id, number, x, _y, _elevation in rows:
                    by_source.setdefault(source_id, []).append(x)
                self.assertEqual(len(by_source), 2)
                geometries = sorted(tuple(values) for values in by_source.values())
                self.assertEqual(geometries, [(0.0, 5.0, 10.0, 15.0), (0.0, 7.0, 14.0, 21.0)])
                # The survey-level spacing metadata was overwritten by the most
                # recent import, which is exactly why it must not be used.
                survey = store.get_survey(survey_id)
                self.assertEqual(survey.metadata["import"]["electrode_spacing"], 7.0)
            finally:
                store.close()

    def test_incompatible_mixed_source_geometry_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, survey_id = self._store(Path(directory))
            try:
                self._record(
                    store, survey_id,
                    _dataset(
                        "a.dat", 5.0,
                        tuple(Electrode(number=n, x=(n - 1) * 5.0) for n in range(1, 5)),
                        (Measurement(1, 1, 4, 2, 3, apparent_resistivity=100.0),),
                    ),
                    "a.dat",
                )
                self._record(
                    store, survey_id,
                    _dataset(
                        "b.dat", 7.0,
                        tuple(Electrode(number=n, x=(n - 1) * 7.0) for n in range(1, 5)),
                        (Measurement(1, 1, 4, 2, 3, apparent_resistivity=120.0),),
                    ),
                    "b.dat",
                )
                workflow = ERTWorkflow(store)
                workflow.select_survey(survey_id)
                with self.assertRaisesRegex(WorkflowError, "disagree about electrode"):
                    workflow.bound_electrode_geometry()
            finally:
                store.close()

    def test_topography_is_rejected_rather_than_flattened(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, survey_id = self._store(Path(directory))
            try:
                self._record(
                    store, survey_id,
                    _dataset(
                        "sloped.dat", 5.0,
                        tuple(
                            Electrode(number=n, x=(n - 1) * 5.0, elevation=0.5 * (n - 1))
                            for n in range(1, 5)
                        ),
                        (Measurement(1, 1, 4, 2, 3, apparent_resistivity=100.0),),
                    ),
                    "sloped.dat",
                )
                workflow = ERTWorkflow(store)
                workflow.select_survey(survey_id)
                with self.assertRaisesRegex(WorkflowError, "topography is not supported"):
                    workflow.bound_electrode_geometry()
            finally:
                store.close()

    def test_off_line_electrodes_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, survey_id = self._store(Path(directory))
            try:
                self._record(
                    store, survey_id,
                    _dataset(
                        "offset.dat", 5.0,
                        tuple(
                            Electrode(number=n, x=(n - 1) * 5.0, y=1.0 if n > 2 else 0.0)
                            for n in range(1, 5)
                        ),
                        (Measurement(1, 1, 4, 2, 3, apparent_resistivity=100.0),),
                    ),
                    "offset.dat",
                )
                workflow = ERTWorkflow(store)
                workflow.select_survey(survey_id)
                with self.assertRaisesRegex(WorkflowError, "off the survey line"):
                    workflow.bound_electrode_geometry()
            finally:
                store.close()

    def test_geometry_change_during_inversion_blocks_the_commit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, survey_id = self._store(Path(directory))
            try:
                self._record(
                    store, survey_id,
                    _dataset(
                        "a.dat", 5.0,
                        tuple(Electrode(number=n, x=(n - 1) * 5.0) for n in range(1, 5)),
                        (Measurement(1, 1, 4, 2, 3, apparent_resistivity=100.0),),
                    ),
                    "a.dat",
                )
                workflow = ERTWorkflow(store)
                workflow.select_survey(survey_id)
                work = workflow._prepare_2d_inversion(max_iterations=1)
                # A second source extends the line with the same spacing.
                self._record(
                    store, survey_id,
                    _dataset(
                        "b.dat", 5.0,
                        tuple(Electrode(number=n, x=(n - 1) * 5.0) for n in range(1, 7)),
                        (Measurement(1, 3, 6, 4, 5, apparent_resistivity=130.0),),
                    ),
                    "b.dat",
                )
                result = invert_ert(
                    work.observations, work.mesh, work.initial_resistivity, max_iterations=1
                )
                with self.assertRaises(WorkflowError):
                    workflow.commit_inversion(result, work)
                self.assertIsNone(workflow.selected_version_id)
            finally:
                store.close()


# ---------------------------------------------------------------------------
# A5 — the DAT format claim
# ---------------------------------------------------------------------------

_VALID_DAT = """4
5.0
1
0
1 2 3 4 100.0
2 3 4 5 120.0
1 3 4 6 90.0
2 4 5 6 110.0
"""


class DATDialectTests(unittest.TestCase):
    """A5: only the documented NiX dialect is accepted; nothing is guessed."""

    def test_documented_dialect_is_parsed_with_units_and_array_identity(self) -> None:
        dataset = parse_dat(_VALID_DAT, "line.dat")
        self.assertEqual(dataset.data_count, 4)
        self.assertEqual(dataset.electrode_spacing, 5.0)
        self.assertEqual(dataset.array_type, "Wenner")
        self.assertEqual(len(dataset.measurements), 4)
        # Electrode geometry is derived by the documented convention x = (n - 1) * spacing.
        self.assertEqual(
            [electrode.x for electrode in dataset.electrodes],
            [0.0, 5.0, 10.0, 15.0, 20.0, 25.0],
        )
        self.assertEqual(dataset.measurements[0].apparent_resistivity, 100.0)

    def test_malformed_header_is_rejected(self) -> None:
        for text in (
            "not-a-count\n5.0\n1\n0\n1 2 3 4 100\n",
            "4\nnot-a-spacing\n1\n0\n1 2 3 4 100\n",
            "4\n5.0\nnot-an-array\n0\n1 2 3 4 100\n",
            "-1\n5.0\n1\n0\n",
        ):
            with self.subTest(text=text.splitlines()[0]):
                with self.assertRaises(DATParseError):
                    parse_dat(text, "bad.dat")

    def test_malformed_rows_are_rejected(self) -> None:
        for text in (
            "1\n5.0\n1\n0\n1 2 3 4\n",  # too few columns
            "1\n5.0\n1\n0\n1 2 3 4 1 2 3 4 5 6\n",  # more columns than the dialect documents
            "1\n5.0\n1\n0\n0 2 3 4 100\n",  # electrode numbers are 1-based
            "1\n5.0\n1\n0\n1 2 3 4 abc\n",  # non-numeric
        ):
            with self.subTest(text=text.splitlines()[-1]):
                with self.assertRaises(DATParseError):
                    parse_dat(text, "bad.dat")

    def test_row_count_and_array_code_must_match(self) -> None:
        with self.assertRaisesRegex(DATParseError, "Expected 2 measurement rows"):
            parse_dat("2\n5.0\n1\n0\n1 2 3 4 100\n", "short.dat")
        with self.assertRaisesRegex(DATParseError, "unsupported array type"):
            parse_dat("0\n5.0\n42\n", "array.dat")

    def test_res2dinv_style_header_is_not_silently_accepted(self) -> None:
        # A vendor export whose header order we have no fixture for must be
        # rejected rather than guessed. This is a claim-boundary test: the
        # parser documents a NiX dialect, not RES2DINV equivalence.
        res2dinv = (
            "Survey line\n"
            "5.0\n"
            "1\n"
            "0\n"
            "1 2 3 4 100.0\n"
        )
        with self.assertRaises(DATParseError):
            parse_dat(res2dinv, "vendor.dat")

    def test_topography_rows_keep_their_documented_units(self) -> None:
        dataset = parse_dat("1\n10.0\n1\n2\n0 100\n10 101.5\n1 2 3 4 50\n", "topo.dat")
        self.assertEqual(dataset.topography, ((0.0, 100.0), (10.0, 101.5)))


# ---------------------------------------------------------------------------
# B1 — qualification admission integrity
# ---------------------------------------------------------------------------


def _internal_dataset() -> QualificationDataset:
    return QualificationDataset(
        dataset_id="internal-synthetic-v1",
        classification=DatasetClassification.INTERNAL_SYNTHETIC,
        source="in-repo deterministic fixture",
        license_status=LicenseStatus.INTERNAL,
        qualification_purpose="synthetic sanity checks only",
    )


def _eligible_fixture_dataset() -> QualificationDataset:
    """A licence-eligible dataset *descriptor* used only to test the guards.

    No dataset bytes, no reference values, and no validation claim exist here:
    this only lets the admission rules be exercised past the independence gate
    so that the remaining requirements (reference result, tolerance
    justification, metrics, convergence) can be shown to be enforced.
    """
    return QualificationDataset(
        dataset_id="admission-test-fixture",
        classification=DatasetClassification.PUBLISHED_REFERENCE,
        source="admission-test fixture descriptor (no bytes in this repository)",
        license_status=LicenseStatus.PERMISSION_CONFIRMED,
        permission_note="fixture descriptor for admission tests only",
        qualification_purpose="exercise the admission rules",
    )


def _protocol(
    protocol_id: str = "protocol-1",
    dataset_id: str = "internal-synthetic-v1",
    metrics: tuple[str, ...] = ("log10_rmse",),
    tolerance: dict[str, object] | None = None,
    reference_result: dict[str, object] | None = None,
    stopping_criteria: dict[str, object] | None = None,
) -> BenchmarkProtocol:
    return BenchmarkProtocol(
        protocol_id=protocol_id,
        dataset_id=dataset_id,
        preprocessing_rules=(),
        qc_rules=(),
        inversion_parameters={"max_iterations": 3},
        mesh_assumptions={"cells": 24},
        stopping_criteria=stopping_criteria or {"max_iterations": 3},
        expected_reference_result=reference_result or {},
        comparison_metrics=metrics,
        acceptable_tolerance=tolerance
        or {metric: {"value": 0.1, "justification": "documented discretization error"} for metric in metrics},
    )


class QualificationAdmissionTests(unittest.TestCase):
    """B1: structural cross-references alone must never admit a status."""

    def test_internal_synthetic_data_cannot_masquerade_as_independent_validation(self) -> None:
        registry = QualificationRegistry()
        registry.add_dataset(_internal_dataset())
        protocol = _protocol()
        registry.add_protocol(protocol)
        comparison = BenchmarkComparison.create(
            protocol, ComparisonStatus.VALIDATED,
            {"log10_rmse": 0.01}, {"outcome": "CONVERGED"}, "attempt",
        )
        errors = registry.admission_errors(protocol, comparison)
        self.assertTrue(any("independent" in error for error in errors))
        with self.assertRaisesRegex(ValueError, "VALIDATED"):
            registry.add_comparison(comparison)

    def test_internal_dataset_cannot_declare_an_independent_reference_result(self) -> None:
        registry = QualificationRegistry()
        registry.add_dataset(_internal_dataset())
        with self.assertRaisesRegex(ValueError, "cannot define independent reference results"):
            registry.add_protocol(_protocol(reference_result={"log10_rmse": 0.02}))

    def test_missing_reference_result_is_rejected(self) -> None:
        registry = QualificationRegistry()
        registry.add_dataset(_eligible_fixture_dataset())
        protocol = _protocol(dataset_id="admission-test-fixture", reference_result={})
        registry.add_protocol(protocol)
        comparison = BenchmarkComparison.create(
            protocol, ComparisonStatus.VALIDATED,
            {"log10_rmse": 0.01}, {"outcome": "CONVERGED"}, "attempt",
        )
        self.assertTrue(
            any("reference result" in error for error in registry.admission_errors(protocol, comparison))
        )

    def test_missing_protocol_identity_is_rejected(self) -> None:
        registry = QualificationRegistry()
        registry.add_dataset(_internal_dataset())
        protocol = _protocol()
        comparison = BenchmarkComparison.create(
            protocol, ComparisonStatus.QUALITATIVELY_CONSISTENT,
            {"log10_rmse": 0.01}, {"outcome": "CONVERGED"}, "attempt",
        )
        with self.assertRaisesRegex(KeyError, "registered protocol"):
            registry.add_comparison(comparison)

    def test_missing_tolerance_justification_is_rejected(self) -> None:
        registry = QualificationRegistry()
        registry.add_dataset(_eligible_fixture_dataset())
        protocol = _protocol(
            dataset_id="admission-test-fixture",
            tolerance={"log10_rmse": {"value": 0.1}},
            reference_result={"log10_rmse": 0.02},
        )
        registry.add_protocol(protocol)
        comparison = BenchmarkComparison.create(
            protocol, ComparisonStatus.VALIDATED,
            {"log10_rmse": 0.01}, {"outcome": "CONVERGED"}, "attempt",
        )
        self.assertTrue(
            any("justification" in error for error in registry.admission_errors(protocol, comparison))
        )

    def test_incomplete_metrics_are_rejected(self) -> None:
        registry = QualificationRegistry()
        registry.add_dataset(_internal_dataset())
        protocol = _protocol(metrics=("log10_rmse", "rmse"))
        registry.add_protocol(protocol)
        comparison = BenchmarkComparison.create(
            protocol, ComparisonStatus.QUALITATIVELY_CONSISTENT,
            {"log10_rmse": 0.01}, {"outcome": "CONVERGED"}, "attempt",
        )
        errors = registry.admission_errors(protocol, comparison)
        self.assertTrue(any("missing measured metrics" in error for error in errors))

    def test_missing_convergence_record_is_rejected(self) -> None:
        registry = QualificationRegistry()
        registry.add_dataset(_internal_dataset())
        protocol = _protocol()
        registry.add_protocol(protocol)
        comparison = BenchmarkComparison.create(
            protocol, ComparisonStatus.QUALITATIVELY_CONSISTENT,
            {"log10_rmse": 0.01}, {}, "attempt",
        )
        self.assertTrue(
            any("convergence" in error for error in registry.admission_errors(protocol, comparison))
        )

    def test_not_validated_stays_representable_without_evidence(self) -> None:
        registry = QualificationRegistry()
        registry.add_dataset(_internal_dataset())
        protocol = _protocol()
        registry.add_protocol(protocol)
        comparison = BenchmarkComparison.create(
            protocol, ComparisonStatus.NOT_VALIDATED, {}, {}, "no reference data available",
        )
        self.assertEqual(registry.admission_errors(protocol, comparison), ())
        registry.add_comparison(comparison)
        self.assertEqual(len(registry.comparisons), 1)

    def test_unsupported_status_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            BenchmarkComparison.from_dict(
                {
                    "comparison_id": "c1",
                    "protocol_id": "protocol-1",
                    "dataset_id": "internal-synthetic-v1",
                    "status": "PROBABLY_FINE",
                    "metrics": {},
                    "convergence": {},
                    "notes": "attempt",
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            )

    def test_registered_records_cannot_be_mutated_after_validation(self) -> None:
        registry = QualificationRegistry()
        registry.add_dataset(_internal_dataset())
        protocol = _protocol()
        registry.add_protocol(protocol)
        comparison = BenchmarkComparison.create(
            protocol, ComparisonStatus.QUALITATIVELY_CONSISTENT,
            {"log10_rmse": 0.01}, {"outcome": "CONVERGED"}, "attempt",
        )
        registry.add_comparison(comparison)
        registry.validate()

        with self.assertRaises(TypeError):
            comparison.metrics["log10_rmse"] = 99.0  # type: ignore[index]
        with self.assertRaises(TypeError):
            protocol.acceptable_tolerance["log10_rmse"]["value"] = 99.0  # type: ignore[index]
        # Mutating the caller's original object must not reach the frozen record.
        registry.validate()
        self.assertEqual(thaw(comparison.metrics)["log10_rmse"], 0.01)

    def test_freeze_mapping_is_recursively_read_only(self) -> None:
        frozen = freeze_mapping({"outer": {"inner": [1, 2, {"deep": 3}]}})
        with self.assertRaises(TypeError):
            frozen["outer"] = {}  # type: ignore[index]
        with self.assertRaises(TypeError):
            frozen["outer"]["inner"] = ()  # type: ignore[index]
        with self.assertRaises(TypeError):
            frozen["outer"]["inner"][2]["deep"] = 4  # type: ignore[index]
        self.assertEqual(thaw(frozen), {"outer": {"inner": [1, 2, {"deep": 3}]}})


# ---------------------------------------------------------------------------
# B2 — solver control and failure semantics
# ---------------------------------------------------------------------------


class SolverControlAndFailureTests(unittest.TestCase):
    """B2: invalid controls are rejected, and failure phases are preserved."""

    def setUp(self) -> None:
        self.fixture = ert2d_qualification()

    def test_non_finite_or_non_positive_tolerances_are_rejected(self) -> None:
        for tolerance in (float("nan"), float("inf"), -float("inf"), -1e-3, 0.0):
            with self.subTest(tolerance=tolerance):
                with self.assertRaises(ERT2DError):
                    invert_ert(
                        self.fixture.observations, self.fixture.mesh, 1.0,
                        max_iterations=1, convergence_rms=tolerance,
                    )

    def test_infinite_tolerance_can_no_longer_report_convergence(self) -> None:
        # Reported audit case: convergence_rms=inf made every run "converged"
        # on its first evaluation.
        outcome, contract, result = run_ert2d_contract(
            self.fixture, max_iterations=1, convergence_rms=float("inf")
        )
        self.assertIsNone(result)
        self.assertIs(outcome, QualificationOutcome.INVALID_INPUT)
        self.assertEqual(contract.failure_phase, PHASE_INPUT_VALIDATION)
        self.assertFalse(contract.convergence_criterion_satisfied)
        self.assertEqual(contract.error_class, "ERT2DError")

    def test_invalid_damping_and_iteration_controls_are_rejected(self) -> None:
        for damping in (float("nan"), float("inf"), 0.0, -0.5):
            with self.subTest(damping=damping):
                with self.assertRaises(ERT2DError):
                    invert_ert(
                        self.fixture.observations, self.fixture.mesh, 1.0,
                        max_iterations=1, damping=damping,
                    )
        with self.assertRaises(ERT2DError):
            invert_ert(self.fixture.observations, self.fixture.mesh, 1.0, max_iterations=0)

    def test_real_forward_model_numerical_failure_raises_its_own_error(self) -> None:
        # A layer below the documented certification floor makes the actual
        # forward model fail numerically; this is not a mocked outer call.
        with self.assertRaises(VESNumericalError):
            layered_apparent_resistivity(LayeredEarthModel((100.0, 10.0), (1e-6,)), 10.0, 1.0)
        # VESNumericalError is a VESError subclass, so the qualification layer
        # must map it by class rather than falling into the invalid-input branch.
        self.assertTrue(issubclass(VESNumericalError, VESError))

    def test_invalid_configuration_is_not_reported_as_convergence(self) -> None:
        fixture = ves_qualification()
        # A thickness below the certified domain is invalid configuration, not
        # convergence and not a numerical failure.
        outcome, contract, result = run_ves_contract(
            fixture, LayeredEarthModel((100.0, 10.0), (1e-6,)), max_nfev=5
        )
        self.assertIsNone(result)
        self.assertIs(outcome, QualificationOutcome.INVALID_INPUT)
        self.assertEqual(contract.failure_phase, PHASE_INPUT_VALIDATION)
        self.assertFalse(contract.numerical_failure)

    def test_bounded_run_is_never_failed_and_never_converged(self) -> None:
        outcome, contract, result = run_ert2d_contract(self.fixture, max_iterations=1)
        self.assertIsNotNone(result)
        self.assertIs(outcome, QualificationOutcome.TERMINATED)
        self.assertFalse(contract.convergence_criterion_satisfied)
        self.assertFalse(contract.invalid_input)
        self.assertFalse(contract.numerical_failure)
        self.assertEqual(contract.failure_phase, "not_applicable")

    def test_failure_phase_is_recorded_on_the_contract(self) -> None:
        outcome, contract, _ = run_ves_contract(
            ves_qualification(), LayeredEarthModel((100.0, 20.0, 250.0), (5.0, 1e-6)), max_nfev=5
        )
        self.assertIs(outcome, QualificationOutcome.INVALID_INPUT)
        self.assertEqual(contract.failure_phase, PHASE_INPUT_VALIDATION)
        self.assertIn(contract.failure_phase, contract.to_dict()["failure_phase"])


# ---------------------------------------------------------------------------
# B3 — model-comparison validity
# ---------------------------------------------------------------------------


class ModelComparisonDiscretizationTests(unittest.TestCase):
    """B3: a matching vector length is not a shared parameter space."""

    def test_model_metric_requires_a_discretization_identity(self) -> None:
        with self.assertRaisesRegex(ValueError, "discretization"):
            comparison_metrics([1.0, 2.0], [1.1, 2.1], reference_model=[1.0, 1.0], result_model=[1.0, 1.2])

    def test_model_metric_is_computed_when_the_identity_is_supplied(self) -> None:
        metrics = comparison_metrics(
            [1.0, 2.0], [1.0, 2.0],
            reference_model=[1.0, 1.0], result_model=[1.0, 2.0],
            model_discretization=mesh2d_discretization(Mesh2D((0.0, 1.0, 2.0), (0.0, 1.0))),
        )
        self.assertAlmostEqual(metrics["model_l2_difference"], 1.0)

    def test_equal_cell_counts_with_different_edges_are_not_comparable(self) -> None:
        reference_mesh = Mesh2D((0.0, 1.0, 3.0), (0.0, 1.0))
        case_mesh = Mesh2D((0.0, 2.0, 3.0), (0.0, 1.0))
        self.assertEqual(reference_mesh.cell_count, case_mesh.cell_count)
        self.assertNotEqual(mesh2d_discretization(reference_mesh), mesh2d_discretization(case_mesh))
        reason = model_comparison_omission_reason(
            mesh2d_discretization(reference_mesh), mesh2d_discretization(case_mesh)
        )
        self.assertIsNotNone(reason)
        self.assertIn("different discretizations", reason or "")

    def test_same_mesh_identity_is_comparable(self) -> None:
        mesh = Mesh2D((0.0, 1.0, 3.0), (0.0, 1.0))
        self.assertIsNone(
            model_comparison_omission_reason(mesh2d_discretization(mesh), mesh2d_discretization(mesh))
        )

    def test_3d_and_layered_identities_encode_geometry_and_parameter_order(self) -> None:
        a = Mesh3D.regular((0, 1, 2), (0, 1), (0, 1))
        b = Mesh3D.regular((0, 1, 3), (0, 1), (0, 1))
        self.assertNotEqual(mesh3d_discretization(a), mesh3d_discretization(b))
        self.assertIsNotNone(
            model_comparison_omission_reason(mesh3d_discretization(a), mesh3d_discretization(b))
        )
        self.assertNotEqual(
            ves_discretization(LayeredEarthModel((100.0, 20.0), (5.0,))),
            ves_discretization(LayeredEarthModel((100.0, 20.0, 250.0), (5.0, 12.0))),
        )

    def test_missing_model_vector_is_reported_rather_than_assumed(self) -> None:
        self.assertIsNotNone(model_comparison_omission_reason(None, None))


# ---------------------------------------------------------------------------
# B4 — VES input parsing
# ---------------------------------------------------------------------------


class VESInputParsingTests(unittest.TestCase):
    """B4: malformed rows must fail explicitly, never become a header."""

    def test_non_numeric_first_row_is_not_treated_as_a_header(self) -> None:
        with self.assertRaisesRegex(VESError, "line 1"):
            parse_ves("BAD 1 2\n1 2 3\n", "sound.dat")

    def test_non_finite_first_row_is_not_treated_as_a_header(self) -> None:
        for token in ("nan", "inf", "NaN"):
            with self.subTest(token=token):
                with self.assertRaisesRegex(VESError, "line 1"):
                    parse_ves(f"{token} 1 2\n1 2 3\n", "sound.dat")

    def test_functionally_malformed_rows_are_rejected_with_location(self) -> None:
        with self.assertRaisesRegex(VESError, "requires AB/2, MN/2, and resistance"):
            parse_ves("1 2\n", "sound.dat")
        with self.assertRaisesRegex(VESError, "sound.dat line 2"):
            parse_ves("10 2 3\nnot-a-number 2 3\n", "sound.dat")
        with self.assertRaisesRegex(VESError, "at most 4 columns"):
            parse_ves("10 2 3 150 99\n", "sound.dat")

    def test_observations_are_never_silently_discarded(self) -> None:
        points = parse_ves("10 2 3\n20 2 4\n30 2 5\n", "sound.dat")
        self.assertEqual(len(points), 3)
        with self.assertRaises(VESError):
            parse_ves("10 2 3\n20 2 4\n30 2\n", "sound.dat")

    def test_supported_header_is_recognized_and_values_are_preserved(self) -> None:
        points = parse_ves(
            "AB/2,MN/2,resistance,apparent_resistivity\n10,2,3,150\n20,2,4,200\n", "sound.dat"
        )
        self.assertEqual(len(points), 2)
        self.assertEqual(points[0].apparent_resistivity, 150.0)
        self.assertEqual(points[0].resistance, 3.0)
        self.assertEqual(points[1].apparent_resistivity, 200.0)

    def test_extra_columns_are_rejected_explicitly(self) -> None:
        with self.assertRaises(VESError):
            parse_ves("10 2 3 150 1 extra\n", "sound.dat")

    def test_invalid_geometry_is_rejected_at_import(self) -> None:
        with self.assertRaises(VESError):
            parse_ves("5 5 1\n", "sound.dat")
        with self.assertRaises(VESError):
            parse_ves("10 2 0\n", "sound.dat")


# ---------------------------------------------------------------------------
# M23 closure 1 — percentage-RMS numeric domain
# ---------------------------------------------------------------------------


def percent_rms_reference(predicted, observed) -> Decimal:
    """High-precision percentage RMS from its mathematical definition.

    Evaluated with 60 significant decimal digits from the same inputs, so it is
    independent of the double-precision evaluation under test rather than a
    restatement of it.
    """
    with localcontext() as context:
        context.prec = 60
        total = Decimal(0)
        for predicted_value, observed_value in zip(predicted, observed):
            ratio = Decimal(repr(float(predicted_value))) / Decimal(repr(float(observed_value)))
            total += (ratio - 1) ** 2
        return (total / len(predicted)).sqrt() * 100


def conventional_percent_rms(predicted, observed) -> float:
    """The direct expression that overflowed, kept as the defect reference."""
    with np.errstate(over="ignore", invalid="ignore"):
        squared = (np.asarray(predicted, dtype=float) / np.asarray(observed, dtype=float) - 1.0) ** 2
        return float(np.sqrt(np.mean(squared)) * 100.0)


class PercentRMSTests(unittest.TestCase):
    """``percent_rms`` reports a finite value whenever one is representable.

    The demonstrated defect: with an accepted finite initial model the
    conventional expression overflowed inside the square and reported ``inf``
    for a mathematically representable percentage, while ``rms_log10`` stayed
    finite.
    """

    def setUp(self) -> None:
        self.fixture_2d = ert2d_qualification()
        self.usable = tuple(
            item for item in self.fixture_2d.observations if not item.excluded
        )
        self.observed = [item.apparent_resistivity for item in self.usable]

    def test_ordinary_values_match_the_conventional_formula(self) -> None:
        cases = (
            ([1.0], [1.0]),
            ([1.05, 0.95], [1.0, 1.0]),
            ([100.0, 20.0, 250.0], [100.0, 19.0, 260.0]),
            ([1.0], [1000.0]),
            ([1e-6], [1e6]),
            ([1e50], [1e-50]),
        )
        for predicted, observed in cases:
            with self.subTest(predicted=predicted, observed=observed):
                expected = conventional_percent_rms(predicted, observed)
                self.assertTrue(math.isfinite(expected))
                actual = percent_rms(predicted, observed)
                scale = abs(expected) if expected else 1.0
                self.assertLessEqual(abs(actual - expected), scale * 1e-12)

    def test_ordinary_range_is_bit_identical_to_the_conventional_expression(self) -> None:
        # The direct branch *is* the conventional expression, so values in the
        # safe range are unchanged rather than merely close. The comparison here
        # evaluates the conventional form through numpy, an independent path.
        cases = (
            ([1.0], [1.0]),
            ([1.05, 0.95], [1.0, 1.0]),
            ([100.0, 20.0, 250.0], [100.0, 19.0, 260.0]),
            ([1.0], [1000.0]),
            ([1e-6], [1e6]),
            ([1e50], [1e-50]),
        )
        for predicted, observed in cases:
            with self.subTest(predicted=predicted, observed=observed):
                self.assertEqual(
                    percent_rms(predicted, observed),
                    conventional_percent_rms(predicted, observed),
                )

    def test_mixed_magnitude_residuals_do_not_erase_the_dominant_contribution(self) -> None:
        """Regression for the C1 mixed-magnitude defect.

        The previous scaled form factored out the largest *ratio exponent*, so
        a minute ratio underflowed the shared factor and every contribution
        vanished, raising ``ValueError: math domain error`` for a
        mathematically finite, representable percentage. Scaling by the largest
        residual magnitude must keep the dominant contributions intact.
        """
        cases = (
            # The release-gate audit's exact reproduction.
            ([1e160, 1e-200], [1.0, 1e200]),
            # One dominant residual plus one ~500 orders of magnitude smaller.
            ([1e150, 1e-200], [1.0, 1e150]),
            # Huge, ordinary and minute residuals in one study.
            ([1e200, 1e-100, 1e-250], [1.0, 1e100, 1e150]),
            # Two distinct large magnitudes: the smaller must not erase the
            # larger, and neither may be lost to the shared scale.
            ([1e200, 1e120], [1.0, 1.0]),
        )
        for predicted, observed in cases:
            with self.subTest(predicted=predicted, observed=observed):
                actual = percent_rms(predicted, observed)
                self.assertTrue(math.isfinite(actual))
                self.assertGreater(actual, 0.0)
                reference = percent_rms_reference(predicted, observed)
                relative_error = abs(Decimal(repr(actual)) - reference) / reference
                self.assertLess(relative_error, Decimal("1e-12"))

    def test_audit_mixed_magnitude_case_matches_its_expected_value(self) -> None:
        # The audit's stated expectation for this case.
        actual = percent_rms([1e160, 1e-200], [1.0, 1e200])
        self.assertAlmostEqual(actual / 7.071067811865475e161, 1.0, places=12)

    def test_mixed_magnitude_reports_no_arithmetic_warning(self) -> None:
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            percent_rms([1e160, 1e-200], [1.0, 1e200])
        self.assertEqual([str(item.message) for item in captured], [])

    def test_mixed_magnitude_public_invert_ert_reports_a_correct_percentage(self) -> None:
        # Public 2D API path from the audit: an accepted finite initial model of
        # 1e-60 ohm-m against alternating 1e-230 / 1e308 observations. The
        # forward response of a homogeneous model is exactly the model value, so
        # the initial evaluation has the closed form 100 * (1e170 - 1) / sqrt(2),
        # and the final objective is checked against the high-precision
        # reference derived from the reported predictions.
        usable = tuple(
            item for item in self.fixture_2d.observations if not item.excluded
        )[:2]
        observations = tuple(
            replace(item, apparent_resistivity=value)
            for item, value in zip(usable, (1e-230, 1e308))
        )
        result = invert_ert(observations, self.fixture_2d.mesh, 1e-60, max_iterations=1)
        observed = [item.apparent_resistivity for item in observations]
        # 1. forward predictions stay finite and positive.
        self.assertTrue(
            all(math.isfinite(value) and value > 0.0 for value in result.predicted)
        )
        # 2-3. percentage reporting succeeds with a finite value.
        self.assertTrue(math.isfinite(result.rms_percent))
        self.assertGreater(result.rms_percent, 0.0)
        # 4. agreement with an independent high-precision reference.
        reference = percent_rms_reference(result.predicted, observed)
        relative_error = abs(Decimal(repr(result.rms_percent)) - reference) / reference
        self.assertLess(relative_error, Decimal("1e-12"))
        initial = result.iterations[0]
        self.assertEqual(len(result.iterations), 1)
        self.assertAlmostEqual(
            initial.rms_percent / 7.071067811865475e171, 1.0, places=10,
        )
        initial_reference = percent_rms_reference([1e-60, 1e-60], observed)
        self.assertLess(
            abs(Decimal(repr(initial.rms_percent)) - initial_reference)
            / initial_reference,
            Decimal("1e-12"),
        )

    def test_extreme_finite_initial_models_report_a_representable_percentage(self) -> None:
        # Public 2D API path, accepted finite initial resistivities.
        for initial in (1e160, 1e300):
            with self.subTest(initial=initial):
                result = invert_ert(
                    self.fixture_2d.observations, self.fixture_2d.mesh, initial,
                    max_iterations=1,
                )
                self.assertTrue(math.isfinite(result.rms_log10))
                self.assertTrue(math.isfinite(result.rms_percent))
                self.assertGreater(result.rms_percent, 0.0)
                # The conventional expression is the defect being corrected, not
                # the reference: independent evidence is the high-precision value.
                self.assertTrue(math.isinf(conventional_percent_rms(result.predicted, self.observed)))
                reference = percent_rms_reference(result.predicted, self.observed)
                relative_error = abs(Decimal(repr(result.rms_percent)) - reference) / reference
                self.assertLess(relative_error, Decimal("1e-12"))

    def test_extreme_scale_makes_no_arithmetic_overflow_warning(self) -> None:
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            invert_ert(
                self.fixture_2d.observations, self.fixture_2d.mesh, 1e300, max_iterations=1,
            )
        overflow = [
            str(item.message) for item in captured if "overflow" in str(item.message)
        ]
        self.assertEqual(overflow, [])

    def test_very_small_observed_values_stay_representable(self) -> None:
        # Public VES API path with a sounding whose resistivities are far below
        # the model scale; the percentage must stay finite, not overflow.
        fixture = ves_qualification()
        points = tuple(
            VESPoint(point.ab2, point.mn2, point.apparent_resistivity * 1e-190)
            for point in fixture.noisy_points
            if not point.excluded
        )
        observed = [point.apparent_resistivity for point in points]
        result = invert_ves(
            points, LayeredEarthModel((80.0, 30.0, 180.0), (4.0, 10.0)), max_nfev=20,
        )
        self.assertTrue(math.isfinite(result.rms_percent))
        self.assertTrue(math.isinf(conventional_percent_rms(result.predicted, observed)))
        reference = percent_rms_reference(result.predicted, observed)
        relative_error = abs(Decimal(repr(result.rms_percent)) - reference) / reference
        self.assertLess(relative_error, Decimal("1e-12"))

    def test_mathematically_finite_but_unrepresentable_is_inf(self) -> None:
        # ratio 10 ** 600: the exact percentage RMS is ~1e602, far beyond the
        # double range, so inf is the honest result and not a defect.
        self.assertTrue(math.isinf(percent_rms([1e300], [1e-300])))

    def test_representability_boundary_follows_the_exact_value(self) -> None:
        # ratio 1e303: the exact percentage (~1e305) is representable.
        self.assertTrue(math.isfinite(percent_rms([1e303], [1.0])))
        self.assertAlmostEqual(percent_rms([1e303], [1.0]) / 1e305, 1.0, places=9)
        # ratio 1e308: the exact percentage (~1e310) exceeds the double range.
        self.assertTrue(math.isinf(percent_rms([1e308], [1.0])))
        # The log10 residual stays usable in both regimes, and the independent
        # high-precision reference agrees where a value exists.
        self.assertAlmostEqual(math.log10(percent_rms([1e303], [1.0])), 305.0, places=6)
        reference = percent_rms_reference([1e303], [1.0])
        self.assertLess(
            abs(Decimal(repr(percent_rms([1e303], [1.0]))) - reference) / reference,
            Decimal("1e-15"),
        )

    def test_non_finite_input_is_rejected_not_silently_nan(self) -> None:
        for bad in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    percent_rms([bad], [1.0])
                with self.assertRaises(ValueError):
                    percent_rms([1.0], [bad])

    def test_non_positive_and_zero_denominators_are_rejected(self) -> None:
        for bad in (0.0, -1.0):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    percent_rms([1.0], [bad])
                with self.assertRaises(ValueError):
                    percent_rms([bad], [1.0])

    def test_empty_or_mismatched_input_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            percent_rms([], [])
        with self.assertRaises(ValueError):
            percent_rms([1.0], [1.0, 2.0])

    def test_2d_result_agrees_with_the_conventional_expression_at_ordinary_scale(self) -> None:
        result = invert_ert(
            self.fixture_2d.observations, self.fixture_2d.mesh, 1.0, max_iterations=2,
        )
        self.assertAlmostEqual(
            result.rms_percent, conventional_percent_rms(result.predicted, self.observed),
            places=12,
        )
        for item in result.iterations:
            self.assertTrue(math.isfinite(item.rms_percent))


# ---------------------------------------------------------------------------
# M23 closure 2 — forward factorization failure classification
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def extreme_model_warnings_expected():
    """Swallow the IEEE overflow warnings of an out-of-double-range conductivity.

    The accepted ``1e-308`` initial model has a conductivity above
    ``float_max``, so the transmissibility overflows to ``inf`` and the resulting
    system is genuinely unfactorizable. The classification of that failure is what
    the tests assert; the warnings are the honest IEEE outcome and would only
    clutter the run.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        yield


class ForwardFactorizationFailureTests(unittest.TestCase):
    """A singular forward system is a numerical failure with its own phase.

    The demonstrated defect: scipy's SuperLU binding reports an exactly singular
    matrix as a bare RuntimeError, which escaped the numpy-only except clause and
    was recorded as ``solver_update`` even though no model update was attempted.
    """

    def setUp(self) -> None:
        self.fixture_2d = ert2d_qualification()
        self.fixture_3d = ert3d_qualification()

    def test_2d_factorization_failure_raises_the_dedicated_numerical_error(self) -> None:
        with self.assertRaises(ERT2DNumericalError) as context, extreme_model_warnings_expected():
            invert_ert(
                self.fixture_2d.observations, self.fixture_2d.mesh, 1e-308, max_iterations=1,
            )
        self.assertEqual(context.exception.phase, FORWARD_FACTORIZATION_PHASE)
        # The original cause is retained for diagnostics.
        self.assertIsInstance(context.exception.__cause__, RuntimeError)
        self.assertIn("singular", str(context.exception.__cause__))

    def test_3d_factorization_failure_raises_the_dedicated_numerical_error(self) -> None:
        with self.assertRaises(ERT3DNumericalError) as context, extreme_model_warnings_expected():
            invert_ert3d(
                self.fixture_3d.observations, self.fixture_3d.mesh, self.fixture_3d.electrodes,
                1e-308, max_iterations=1,
            )
        self.assertEqual(context.exception.phase, FORWARD_FACTORIZATION_PHASE)
        self.assertIsInstance(context.exception.__cause__, RuntimeError)

    def test_2d_qualification_record_is_failed_not_invalid_input_nor_solver_update(self) -> None:
        with extreme_model_warnings_expected():
            outcome, contract, result = run_ert2d_contract(
                self.fixture_2d, initial_model=1e-308, max_iterations=1,
            )
        self.assertIsNone(result)
        self.assertIs(outcome, QualificationOutcome.FAILED)
        self.assertEqual(contract.failure_phase, PHASE_FORWARD_FACTORIZATION)
        self.assertEqual(contract.failure_phase, "forward_factorization")
        self.assertNotEqual(contract.failure_phase, PHASE_SOLVER)
        self.assertNotEqual(contract.failure_phase, PHASE_FORWARD_MODEL)
        self.assertNotEqual(contract.failure_phase, PHASE_INPUT_VALIDATION)
        self.assertTrue(contract.numerical_failure)
        self.assertFalse(contract.invalid_input)
        self.assertEqual(contract.error_class, "ERT2DNumericalError")
        self.assertEqual(contract.to_dict()["failure_phase"], "forward_factorization")

    def test_3d_qualification_record_is_failed_not_invalid_input_nor_solver_update(self) -> None:
        with extreme_model_warnings_expected():
            outcome, contract, result = run_ert3d_contract(
                self.fixture_3d, initial_model=1e-308, max_iterations=1,
            )
        self.assertIsNone(result)
        self.assertIs(outcome, QualificationOutcome.FAILED)
        self.assertEqual(contract.failure_phase, PHASE_FORWARD_FACTORIZATION)
        self.assertNotEqual(contract.failure_phase, PHASE_SOLVER)
        self.assertTrue(contract.numerical_failure)
        self.assertFalse(contract.invalid_input)
        self.assertEqual(contract.error_class, "ERT3DNumericalError")

    def test_factorization_phase_is_part_of_the_supported_vocabulary(self) -> None:
        self.assertIn(PHASE_FORWARD_FACTORIZATION, FAILURE_PHASES)
        contract = failed_contract(
            "2D ERT", "forward system factorization failed",
            failure_phase=PHASE_FORWARD_FACTORIZATION,
        )
        self.assertIs(contract.outcome, QualificationOutcome.FAILED)
        self.assertEqual(contract.failure_phase, "forward_factorization")
        with self.assertRaises(ValueError):
            failed_contract("2D ERT", "x", failure_phase="not_a_phase")

    def test_only_the_factorization_call_is_converted(self) -> None:
        # A RuntimeError from the factorization itself is a numerical failure...
        model = np.ones((self.fixture_2d.mesh.nz, self.fixture_2d.mesh.nx))
        with mock.patch(
            "nix_ert.ert.inversion2d.factorized",
            side_effect=RuntimeError("Factor is exactly singular"),
        ):
            with self.assertRaises(ERT2DNumericalError) as context:
                forward_2d(model, self.fixture_2d.mesh, self.fixture_2d.observations)
        self.assertEqual(context.exception.phase, FORWARD_FACTORIZATION_PHASE)
        # ... while an unrelated RuntimeError outside that boundary is not
        # relabelled as a numerical factorization failure.
        with mock.patch(
            "nix_ert.ert.inversion2d._system_matrix",
            side_effect=RuntimeError("unrelated failure"),
        ):
            with self.assertRaises(RuntimeError) as unrelated:
                forward_2d(model, self.fixture_2d.mesh, self.fixture_2d.observations)
        self.assertNotIsInstance(unrelated.exception, ERT2DNumericalError)

    def test_no_unstable_implementation_detail_is_exposed(self) -> None:
        with self.assertRaises(ERT2DNumericalError) as context, extreme_model_warnings_expected():
            invert_ert(
                self.fixture_2d.observations, self.fixture_2d.mesh, 1e-308, max_iterations=1,
            )
        message = str(context.exception)
        self.assertEqual(message, "forward system factorization failed")
        for detail in ("SuperLU", "splu", "Factor is exactly singular"):
            self.assertNotIn(detail, message)

    def test_failure_phases_stay_distinguishable(self) -> None:
        # The vocabulary keeps forward evaluation, factorization, and the model
        # update separate, so a later classification change is a visible break.
        self.assertEqual(FORWARD_EVALUATION_PHASE, PHASE_FORWARD_MODEL)
        self.assertEqual(SOLVER_UPDATE_PHASE, PHASE_SOLVER)
        self.assertEqual(
            ERT2DNumericalError("forward model produced a non-finite voltage").phase,
            FORWARD_EVALUATION_PHASE,
        )
        self.assertEqual(
            ERT2DNumericalError("x", phase=SOLVER_UPDATE_PHASE).phase, "solver_update",
        )
        self.assertEqual(
            ERT3DNumericalError("quadrupole has zero homogeneous numerical sensitivity").phase,
            FORWARD_EVALUATION_PHASE,
        )


if __name__ == "__main__":
    unittest.main()
