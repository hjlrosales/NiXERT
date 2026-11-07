"""Validation tests for the baseline 2D ERT engine."""

from __future__ import annotations

import unittest

import numpy as np

from nix_ert.ert.inversion2d import (
    ERT2DError,
    ERTObservation,
    Mesh2D,
    forward_apparent_resistivity,
    invert_ert,
    numerical_jacobian,
)


class ERT2DTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mesh = Mesh2D.from_electrodes([0, 1, 2, 3, 4, 5], nz=3, depth=3)
        self.observations = (
            ERTObservation(1, 6, 2, 3, 1.0),
            ERTObservation(1, 6, 3, 4, 1.0),
            ERTObservation(2, 5, 3, 4, 1.0),
            ERTObservation(2, 6, 4, 5, 1.0),
            ERTObservation(1, 5, 2, 4, 1.0),
            ERTObservation(2, 6, 3, 5, 1.0),
        )

    def test_mesh_has_expected_cell_geometry(self) -> None:
        self.assertEqual((self.mesh.nx, self.mesh.nz, self.mesh.cell_count), (6, 3, 18))
        self.assertEqual(self.mesh.cell_index(2, 1), 8)

    def test_homogeneous_model_normalizes_to_unit_resistivity(self) -> None:
        response = forward_apparent_resistivity(np.ones((3, 6)), self.mesh, self.observations)
        np.testing.assert_allclose(response, np.ones(len(self.observations)), rtol=1e-10, atol=1e-10)

    def test_gauge_preserves_reciprocity_when_source_uses_first_cell(self) -> None:
        model = np.ones((3, 6))
        forward = forward_apparent_resistivity(
            model,
            self.mesh,
            (ERTObservation(1, 6, 2, 3, 1.0),),
        )[0]
        reciprocal = forward_apparent_resistivity(
            model,
            self.mesh,
            (ERTObservation(2, 3, 1, 6, 1.0),),
        )[0]
        self.assertAlmostEqual(forward, reciprocal, places=10)

        model = np.ones((3, 6))
        jacobian = numerical_jacobian(model, self.mesh, self.observations, step=1e-4)
        self.assertEqual(jacobian.shape, (len(self.observations), self.mesh.cell_count))
        self.assertTrue(np.all(np.isfinite(jacobian)))
        self.assertGreater(float(np.linalg.norm(jacobian)), 0.0)

    def test_synthetic_model_inversion_reduces_residual(self) -> None:
        true_model = np.ones((3, 6)) * 100
        true_model[0, 2:4] = 300
        synthetic = tuple(
            ERTObservation(item.a, item.b, item.m, item.n, value)
            for item, value in zip(self.observations, forward_apparent_resistivity(true_model / 100, self.mesh, self.observations))
        )
        initial = np.ones((3, 6))
        observed = np.asarray([item.apparent_resistivity for item in synthetic])
        before = np.sqrt(np.mean((np.log10(np.ones(len(synthetic))) - np.log10(observed)) ** 2))
        result = invert_ert(synthetic, self.mesh, initial, max_iterations=3)
        self.assertTrue(result.iterations)
        self.assertLess(result.rms_log10, before)
        self.assertTrue(np.all(np.isfinite(result.resistivity)))

    def test_excluded_observations_and_invalid_inputs(self) -> None:
        excluded = (*self.observations[:-1], ERTObservation(1, 5, 2, 4, 100, excluded=True))
        result = invert_ert(excluded, self.mesh, 1.0, max_iterations=1)
        self.assertEqual(len(result.predicted), len(self.observations) - 1)
        with self.assertRaises(ERT2DError):
            Mesh2D.from_electrodes([0, 0, 1])
        with self.assertRaises(ERT2DError):
            ERTObservation(1, 2, 1, 3, 10)


if __name__ == "__main__":
    unittest.main()
