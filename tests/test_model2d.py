"""Tests for 2D model visualization data and export."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from nix_ert.visualization.model2d import ModelViewError, ResistivitySection


class Model2DTests(unittest.TestCase):
    def setUp(self) -> None:
        self.section = ResistivitySection(
            x_edges=(0, 1, 2), depth_edges=(0, 1, 3),
            resistivity=np.asarray([[10.0, 100.0], [1000.0, 10000.0]]),
            electrode_x=(0.5, 1.5),
        )

    def test_log_normalization_and_cell_inspection(self) -> None:
        np.testing.assert_allclose(self.section.normalized(), [[0, 1 / 3], [2 / 3, 1]])
        info = self.section.inspect_cell(1, 0)
        self.assertEqual((info.x, info.depth, info.resistivity), (1.5, 0.5, 100.0))

    def test_linear_controls_and_limits_are_applied(self) -> None:
        view = self.section.with_controls(logarithmic=False, minimum=10, maximum=1000)
        np.testing.assert_allclose(view.normalized(), [[0, 90 / 990], [1, 1]])
        self.assertEqual(view.display_limits, (10, 1000))

    def test_csv_is_stable_and_invalid_sections_are_rejected(self) -> None:
        output = self.section.csv()
        self.assertTrue(output.startswith("column,layer,x,depth,resistivity\n"))
        self.assertEqual(output.count("\n"), 5)
        with self.assertRaises(ModelViewError):
            ResistivitySection((0, 1), (0, 1), np.asarray([[0.0]]))
        with self.assertRaises(ModelViewError):
            self.section.inspect_cell(3, 0)

    def test_render_smoke_when_matplotlib_is_available(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "section.png"
            try:
                self.section.render(path)
            except ModelViewError as exc:
                if "matplotlib is required" not in str(exc):
                    raise
            else:
                self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
