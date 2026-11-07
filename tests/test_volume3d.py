"""Tests for 3D volume visualization operations."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from nix_ert.visualization.volume3d import ResistivityVolume, VolumeError


class Volume3DTests(unittest.TestCase):
    def setUp(self) -> None:
        self.volume = ResistivityVolume(
            x_edges=(0, 1, 2), y_edges=(0, 10, 20), depth_edges=(0, 2, 4),
            resistivity=np.asarray([[[10, 20], [30, 40]], [[50, 60], [70, 80]]], dtype=float),
        )

    def test_slices_and_threshold_mask(self) -> None:
        self.assertEqual(self.volume.horizontal_slice(0).shape, (2, 2))
        self.assertEqual(self.volume.vertical_slice_x(1).shape, (2, 2))
        masked = self.volume.with_controls(threshold_minimum=30, threshold_maximum=60).threshold_mask()
        self.assertEqual(int(masked.sum()), 4)
        self.assertEqual(self.volume.inspect_cell(1, 0, 1).resistivity, 60)

    def test_csv_contains_all_cells_and_visibility(self) -> None:
        output = self.volume.with_controls(threshold_minimum=50).csv()
        self.assertTrue(output.startswith("ix,iy,iz,x,y,depth,resistivity,visible\n"))
        self.assertEqual(output.count("\n"), 9)
        self.assertIn("60.0,True", output)
        self.assertIn("10.0,False", output)

    def test_invalid_geometry_and_controls_are_rejected(self) -> None:
        with self.assertRaises(VolumeError):
            ResistivityVolume((0, 1), (0, 1), (0, 1), np.asarray([[-1.0]]))
        with self.assertRaises(VolumeError):
            self.volume.with_controls(threshold_minimum=90, threshold_maximum=10)
        with self.assertRaises(VolumeError):
            self.volume.inspect_cell(2, 0, 0)

    def test_render_smoke_when_matplotlib_is_available(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "volume.png"
            try:
                self.volume.render(path)
            except VolumeError as exc:
                if "matplotlib is required" not in str(exc):
                    raise
            else:
                self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
