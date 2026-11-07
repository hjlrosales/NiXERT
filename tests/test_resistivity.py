"""Reference checks for apparent-resistivity mathematics."""

from __future__ import annotations

import math
import unittest

from nix_ert.data.measurements import Measurement
from nix_ert.ert.resistivity import (
    ArrayType,
    ResistivityError,
    apparent_resistivity,
    apparent_resistivity_from_measurement,
    array_geometric_factor,
    geometric_factor,
)


class ResistivityTests(unittest.TestCase):
    def test_general_wenner_geometry_matches_reference_factor(self) -> None:
        a = 10.0
        signed = geometric_factor((0, 0), (3 * a, 0), (a, 0), (2 * a, 0))
        self.assertAlmostEqual(abs(signed), 2 * math.pi * a, places=10)
        self.assertAlmostEqual(array_geometric_factor(ArrayType.WENNER, a), 2 * math.pi * a)

    def test_dipole_dipole_reference_factor(self) -> None:
        a = 5.0
        n = 2
        factor = geometric_factor((0, 0), (a, 0), ((n + 1) * a, 0), ((n + 2) * a, 0), absolute=True)
        reference = math.pi * a * n * (n + 1) * (n + 2)
        self.assertAlmostEqual(factor, reference, places=10)
        self.assertAlmostEqual(array_geometric_factor(ArrayType.DIPOLE_DIPOLE, a, n), reference)

    def test_resistivity_product_and_measurement_requirements(self) -> None:
        self.assertAlmostEqual(apparent_resistivity(2.5, 4.0), 10.0)
        measurement = Measurement(1, 1, 2, 3, 4, resistance=2.5)
        self.assertEqual(apparent_resistivity_from_measurement(measurement, 4), 10)
        with self.assertRaisesRegex(ResistivityError, "geometric factor is required"):
            apparent_resistivity_from_measurement(measurement)

    def test_invalid_inputs_are_rejected(self) -> None:
        with self.assertRaises(ResistivityError):
            array_geometric_factor(ArrayType.WENNER, 0)
        with self.assertRaises(ResistivityError):
            geometric_factor((0, 0), (1, 0), (0, 0), (3, 0))
        with self.assertRaises(ResistivityError):
            apparent_resistivity(float("nan"), 1)


if __name__ == "__main__":
    unittest.main()
