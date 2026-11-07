"""Synthetic validation tests for the 3D ERT baseline."""

from __future__ import annotations

import unittest

import numpy as np

from nix_ert.ert.inversion3d import (
    ERT3DError,
    ERT3DObservation,
    Mesh3D,
    forward_apparent_resistivity,
    invert_ert3d,
    numerical_jacobian,
)


class ERT3DTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mesh = Mesh3D.regular((0, 1, 2, 3, 4), (0, 1, 2), (0, 1, 2))
        self.electrodes = ((0.5, 0.5), (1.5, 0.5), (2.5, 0.5), (3.5, 0.5))
        self.observations = (
            ERT3DObservation(1, 4, 2, 3, 1),
            ERT3DObservation(1, 4, 3, 2, 1),
        )

    def test_homogeneous_normalization(self) -> None:
        response = forward_apparent_resistivity(np.ones((2, 2, 4)), self.mesh, self.observations, self.electrodes)
        np.testing.assert_allclose(response, (1, 1), atol=1e-10)

    def test_gauge_preserves_reciprocity_when_source_uses_first_cell(self) -> None:
        model = np.ones((2, 2, 4))
        forward = forward_apparent_resistivity(
            model,
            self.mesh,
            (ERT3DObservation(1, 4, 2, 3, 1),),
            self.electrodes,
        )[0]
        reciprocal = forward_apparent_resistivity(
            model,
            self.mesh,
            (ERT3DObservation(2, 3, 1, 4, 1),),
            self.electrodes,
        )[0]
        self.assertAlmostEqual(forward, reciprocal, places=10)

        jacobian = numerical_jacobian(np.ones((2, 2, 4)), self.mesh, self.observations, self.electrodes)
        self.assertEqual(jacobian.shape, (2, 16))
        self.assertTrue(np.all(np.isfinite(jacobian)))

    def test_synthetic_anomaly_reduces_residual(self) -> None:
        true_model = np.ones((2, 2, 4))
        true_model[0, 0, 1:3] = 4
        synthetic_values = forward_apparent_resistivity(true_model, self.mesh, self.observations, self.electrodes)
        synthetic = tuple(ERT3DObservation(item.a, item.b, item.m, item.n, value) for item, value in zip(self.observations, synthetic_values))
        fitted, predicted, history, _ = invert_ert3d(synthetic, self.mesh, self.electrodes, 1.0, max_iterations=2)
        self.assertEqual(fitted.shape, (2, 2, 4))
        self.assertGreater(len(history), 0)
        self.assertLess(history[-1], history[0])
        self.assertTrue(np.all(np.isfinite(predicted)))

    def test_invalid_observation_is_rejected(self) -> None:
        with self.assertRaises(ERT3DError):
            ERT3DObservation(1, 2, 1, 3, 10)

    def test_out_of_domain_electrode_is_rejected(self) -> None:
        with self.assertRaises(ERT3DError):
            forward_apparent_resistivity(
                np.ones((2, 2, 4)),
                self.mesh,
                self.observations,
                ((0.5, 0.5), (1.5, 0.5), (2.5, 0.5), (99.0, 0.5)),
            )

    def test_collapsed_electrode_mapping_is_rejected(self) -> None:
        with self.assertRaises(ERT3DError):
            forward_apparent_resistivity(
                np.ones((2, 2, 4)),
                self.mesh,
                self.observations,
                ((0.5, 0.5), (0.6, 0.5), (2.5, 0.5), (3.5, 0.5)),
            )


if __name__ == "__main__":
    unittest.main()
