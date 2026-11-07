"""Headless tests for pseudosection geometry and export."""

from __future__ import annotations

import unittest

from nix_ert.data.measurements import Measurement, MeasurementStatus
from nix_ert.visualization.pseudosection import build_pseudosection, pseudosection_csv


class PseudosectionTests(unittest.TestCase):
    def test_points_use_electrode_midpoint_and_documented_depth_proxy(self) -> None:
        points = build_pseudosection(
            [Measurement(10, 1, 4, 2, 3, apparent_resistivity=100)],
            [0, 10, 20, 30],
        )
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0].x, 15.0)
        self.assertEqual(points[0].pseudo_depth, 10.0)
        self.assertEqual(points[0].display_log10, 2.0)

    def test_invalid_and_excluded_values_are_not_plotted_by_default(self) -> None:
        measurements = [
            Measurement(1, 1, 2, 3, 4, apparent_resistivity=-1),
            Measurement(2, 1, 2, 3, 4, apparent_resistivity=10, status=MeasurementStatus.EXCLUDED),
            Measurement(3, 1, 2, 3, 4, apparent_resistivity=20),
        ]
        self.assertEqual([p.row_number for p in build_pseudosection(measurements, [0, 1, 2, 3])], [3])
        self.assertEqual([p.row_number for p in build_pseudosection(measurements, [0, 1, 2, 3], include_excluded=True)], [2, 3])

    def test_csv_has_stable_header_and_status(self) -> None:
        points = build_pseudosection([Measurement(1, 1, 2, 3, 4, apparent_resistivity=10)], [0, 1, 2, 3])
        output = pseudosection_csv(points)
        self.assertTrue(output.startswith("row_number,x,pseudo_depth,apparent_resistivity"))
        self.assertIn("ACTIVE", output)


if __name__ == "__main__":
    unittest.main()
