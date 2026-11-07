"""Validation tests for VES geometry and layered-earth modeling."""

from __future__ import annotations

import math
import unittest

from nix_ert.ves.engine import (
    LayeredEarthModel,
    VESPoint,
    VESError,
    invert_ves,
    layered_apparent_resistivity,
    resistivity_transform,
    schlumberger_geometric_factor,
    ves_apparent_resistivity,
)


class VESTests(unittest.TestCase):
    def test_schlumberger_factor_and_resistance(self) -> None:
        # AB/2=1.5a and MN/2=0.5a is equivalent to a Wenner spacing a.
        self.assertAlmostEqual(schlumberger_geometric_factor(15, 5), 20 * math.pi)
        self.assertAlmostEqual(ves_apparent_resistivity(VESPoint(15, 5, resistance=2)), 40 * math.pi)

    def test_homogeneous_half_space_is_exact(self) -> None:
        model = LayeredEarthModel((100,), ())
        for ab2, mn2 in ((10, 1), (25, 5), (100, 10)):
            self.assertAlmostEqual(layered_apparent_resistivity(model, ab2, mn2), 100.0, places=10)
            self.assertAlmostEqual(resistivity_transform(0.1, model), 100.0, places=10)

    def test_layer_transform_has_expected_limits(self) -> None:
        model = LayeredEarthModel((100, 10), (5,))
        self.assertAlmostEqual(resistivity_transform(0, model), 10.0, places=10)
        self.assertAlmostEqual(resistivity_transform(100, model), 100.0, places=8)

    def test_two_layer_synthetic_inversion_is_reproducible(self) -> None:
        true_model = LayeredEarthModel((100, 10), (8,))
        points = tuple(
            VESPoint(ab2, mn2, apparent_resistivity=layered_apparent_resistivity(true_model, ab2, mn2))
            for ab2, mn2 in ((10, 1), (15, 1), (22, 2), (32, 2), (48, 3), (70, 4))
        )
        result = invert_ves(points, LayeredEarthModel((80, 20), (5,)), max_nfev=100)
        self.assertTrue(result.converged)
        self.assertLess(result.rms_log10, 1e-3)
        self.assertEqual(result.predicted, invert_ves(points, LayeredEarthModel((80, 20), (5,)), max_nfev=100).predicted)

    def test_invalid_geometry_and_model_are_rejected(self) -> None:
        with self.assertRaises(VESError):
            schlumberger_geometric_factor(5, 5)
        with self.assertRaises(VESError):
            LayeredEarthModel((100, 10), ())
        with self.assertRaises(VESError):
            ves_apparent_resistivity(VESPoint(10, 1))


if __name__ == "__main__":
    unittest.main()
