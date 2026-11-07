"""Tests for dependency-light DEM and GIS operations."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from nix_ert.gis.coordinates import ElectrodeCoordinate, SurveyLine
from nix_ert.gis.dem import DEMGrid, GISError, add_dem_elevations, lines_to_geojson, wgs84_to_utm


class DEMGISTests(unittest.TestCase):
    def test_bilinear_sampling_and_elevation_transfer(self) -> None:
        dem = DEMGrid((0, 10), (0, 10), np.asarray([[0, 10], [20, 30]], dtype=float))
        self.assertEqual(dem.sample(5, 5), 15.0)
        points = add_dem_elevations((ElectrodeCoordinate(1, 5, 5),), dem)
        self.assertEqual(points[0].z, 15.0)
        with self.assertRaises(GISError):
            dem.sample(11, 5)

    def test_csv_grid_round_trip_and_incomplete_grid_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dem.csv"
            path.write_text("x,y,elevation\n0,0,1\n1,0,2\n0,1,3\n1,1,4\n", encoding="utf-8")
            dem = DEMGrid.from_csv(path, crs="EPSG:4326")
            self.assertEqual((dem.x, dem.y, dem.crs), ((0.0, 1.0), (0.0, 1.0), "EPSG:4326"))
            bad = Path(directory) / "bad.csv"
            bad.write_text("0,0,1\n1,1,4\n", encoding="utf-8")
            with self.assertRaises(GISError):
                DEMGrid.from_csv(bad)

    def test_wgs84_to_utm_known_reference_and_geojson(self) -> None:
        zone, north, easting, northing = wgs84_to_utm(0.0, 3.0)
        self.assertEqual((zone, north), (31, True))
        self.assertAlmostEqual(easting, 500000, delta=1)
        self.assertAlmostEqual(northing, 0, delta=1)
        line = SurveyLine("line", (ElectrodeCoordinate(1, 0, 0), ElectrodeCoordinate(2, 1, 0)))
        geojson = lines_to_geojson([line])
        self.assertEqual(geojson["features"][0]["geometry"]["type"], "LineString")
        self.assertEqual(len(geojson["features"][0]["geometry"]["coordinates"]), 2)

    def test_invalid_dem_is_rejected(self) -> None:
        with self.assertRaises(GISError):
            DEMGrid((0, 1), (0, 1), np.asarray([[1, np.nan], [2, 3]]))
        with self.assertRaises(GISError):
            wgs84_to_utm(90, 0)


if __name__ == "__main__":
    unittest.main()
