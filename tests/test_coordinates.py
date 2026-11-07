"""Tests for multi-line coordinate placement and WGS84 conversion."""

from __future__ import annotations

import math
import unittest

from nix_ert.gis.coordinates import (
    CoordinateError,
    CoordinateReference,
    CoordinateSystem,
    ElectrodeCoordinate,
    SurveyLine,
    aggregate_lines,
    gps_delta_to_enu,
    gps_to_ecef,
)


class CoordinateTests(unittest.TestCase):
    def test_line_transform_rotation_translation_and_reversal(self) -> None:
        line = SurveyLine(
            "Line 1",
            (ElectrodeCoordinate(1, 0, 0), ElectrodeCoordinate(2, 10, 0)),
        ).rotated(90).translated(100, 200, 5)
        self.assertEqual(line.coordinates[0], ElectrodeCoordinate(1, 100, 200, 5))
        self.assertAlmostEqual(line.coordinates[1].x, 100, places=10)
        self.assertAlmostEqual(line.coordinates[1].y, 210, places=10)
        reversed_line = line.reversed_line()
        self.assertEqual([e.number for e in reversed_line.coordinates], [2, 1])

    def test_gps_ecef_and_local_enu_are_metre_scale(self) -> None:
        origin = CoordinateReference(CoordinateSystem.GPS, latitude=0, longitude=0, altitude=0)
        ecef = gps_to_ecef(0, 0, 0)
        self.assertAlmostEqual(ecef[0], 6378137.0, places=3)
        east, north, up = gps_delta_to_enu(0, 0.00001, 0, origin)
        self.assertAlmostEqual(east, 1.1132, places=2)
        self.assertAlmostEqual(north, 0.0, places=5)
        self.assertAlmostEqual(up, 0.0, places=4)

    def test_utm_reference_and_aggregation(self) -> None:
        reference = CoordinateReference(CoordinateSystem.UTM, zone=36, northern_hemisphere=True)
        line = SurveyLine("UTM line", (ElectrodeCoordinate(1, 10, 20),), reference=reference)
        self.assertEqual(line.coordinates[0].x, 10)
        self.assertEqual(len(aggregate_lines([line])), 1)

    def test_invalid_coordinates_are_rejected(self) -> None:
        with self.assertRaises(CoordinateError):
            CoordinateReference(CoordinateSystem.UTM, zone=61, northern_hemisphere=True)
        with self.assertRaises(CoordinateError):
            CoordinateReference(CoordinateSystem.GPS, latitude=91, longitude=0)
        with self.assertRaises(CoordinateError):
            SurveyLine("", (ElectrodeCoordinate(1, 0, 0),))
        with self.assertRaises(CoordinateError):
            SurveyLine("x", (ElectrodeCoordinate(1, 0, 0), ElectrodeCoordinate(1, 1, 0)))


if __name__ == "__main__":
    unittest.main()
