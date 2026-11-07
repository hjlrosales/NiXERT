"""Tests for VES input and curve export."""

from __future__ import annotations

import unittest

from nix_ert.ves.data import parse_ves, ves_curve_csv
from nix_ert.ves.engine import VESError


class VESDataTests(unittest.TestCase):
    def test_headered_csv_and_explicit_apparent_resistivity(self) -> None:
        points = parse_ves("AB/2,MN/2,resistance,rho\n10,2,3,150\n20,2,4,200\n")
        self.assertEqual(len(points), 2)
        self.assertEqual(points[0].apparent_resistivity, 150)
        self.assertIn("log10_apparent_resistivity", ves_curve_csv(points))

    def test_resistance_only_is_calculated_using_validated_geometry(self) -> None:
        points = parse_ves("10 2 3\n20 2 4\n")
        self.assertAlmostEqual(points[0].apparent_resistivity, 3 * 24 * 3.141592653589793)

    def test_malformed_and_invalid_geometry_are_rejected(self) -> None:
        with self.assertRaises(VESError):
            parse_ves("AB/2,MN/2,resistance\n5,5,1\n")
        with self.assertRaises(VESError):
            parse_ves("10,2,-1\n")


if __name__ == "__main__":
    unittest.main()
