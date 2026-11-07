"""Dependency-light DEM sampling, GeoJSON export, and WGS84/UTM conversion."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from nix_ert.gis.coordinates import CoordinateError, CoordinateReference, CoordinateSystem, ElectrodeCoordinate, SurveyLine


class GISError(ValueError):
    """Raised for invalid GIS/DEM data."""


@dataclass(frozen=True)
class DEMGrid:
    x: tuple[float, ...]
    y: tuple[float, ...]
    elevation: np.ndarray
    crs: str = "local"

    def __post_init__(self) -> None:
        values = np.asarray(self.elevation, dtype=float)
        if values.shape != (len(self.y), len(self.x)):
            raise GISError("DEM elevation shape must be (len(y), len(x))")
        if len(self.x) < 2 or len(self.y) < 2 or any(not math.isfinite(v) for v in (*self.x, *self.y)):
            raise GISError("DEM requires at least two finite coordinates per axis")
        if any(right <= left for left, right in zip(self.x, self.x[1:])) or any(right <= left for left, right in zip(self.y, self.y[1:])):
            raise GISError("DEM coordinates must be strictly increasing")
        if not np.all(np.isfinite(values)):
            raise GISError("DEM elevations must be finite")
        object.__setattr__(self, "elevation", values.copy())

    @classmethod
    def from_csv(cls, path: Path | str, *, crs: str = "local") -> "DEMGrid":
        rows: list[tuple[float, float, float]] = []
        with Path(path).open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.reader(stream)
            for number, row in enumerate(reader, 1):
                if not row or row[0].strip().startswith(("#", ";", "!")):
                    continue
                if len(row) < 3:
                    raise GISError(f"Line {number}: DEM CSV requires x,y,elevation")
                try:
                    rows.append((float(row[0]), float(row[1]), float(row[2])))
                except ValueError as exc:
                    if not rows and any(token.lower() in row[0].lower() for token in ("x", "east", "lon")):
                        continue
                    raise GISError(f"Line {number}: DEM values must be numeric") from exc
        if not rows:
            raise GISError("DEM CSV contains no points")
        xs, ys = sorted({row[0] for row in rows}), sorted({row[1] for row in rows})
        if len(rows) != len(xs) * len(ys):
            raise GISError("DEM CSV must contain a complete rectangular grid")
        lookup = {(x, y): z for x, y, z in rows}
        return cls(tuple(xs), tuple(ys), np.asarray([[lookup[x, y] for x in xs] for y in ys]), crs)

    def sample(self, x: float, y: float) -> float:
        """Bilinearly interpolate an in-bounds DEM point."""
        if not (self.x[0] <= x <= self.x[-1] and self.y[0] <= y <= self.y[-1]):
            raise GISError("DEM sample lies outside the grid")
        ix = min(len(self.x) - 2, max(0, int(np.searchsorted(self.x, x) - 1)))
        iy = min(len(self.y) - 2, max(0, int(np.searchsorted(self.y, y) - 1)))
        x0, x1, y0, y1 = self.x[ix], self.x[ix + 1], self.y[iy], self.y[iy + 1]
        tx = 0.0 if x1 == x0 else (x - x0) / (x1 - x0)
        ty = 0.0 if y1 == y0 else (y - y0) / (y1 - y0)
        z00, z10, z01, z11 = self.elevation[iy, ix], self.elevation[iy, ix + 1], self.elevation[iy + 1, ix], self.elevation[iy + 1, ix + 1]
        return float((1 - tx) * (1 - ty) * z00 + tx * (1 - ty) * z10 + (1 - tx) * ty * z01 + tx * ty * z11)


def add_dem_elevations(points: Iterable[ElectrodeCoordinate], dem: DEMGrid) -> tuple[ElectrodeCoordinate, ...]:
    return tuple(ElectrodeCoordinate(point.number, point.x, point.y, dem.sample(point.x, point.y)) for point in points)


def lines_to_geojson(lines: Iterable[SurveyLine]) -> dict[str, object]:
    features = []
    for line in lines:
        coordinates = [[point.x, point.y, point.z] for point in line.coordinates]
        features.append({"type": "Feature", "properties": {"name": line.name, "crs": line.reference.system.value}, "geometry": {"type": "LineString", "coordinates": coordinates}})
    return {"type": "FeatureCollection", "features": features}


def write_geojson(lines: Iterable[SurveyLine], path: Path | str) -> None:
    Path(path).write_text(json.dumps(lines_to_geojson(lines), indent=2), encoding="utf-8")


def wgs84_to_utm(latitude: float, longitude: float) -> tuple[int, bool, float, float]:
    """Convert WGS84 latitude/longitude to UTM easting/northing in metres."""
    if not (-90 < latitude < 90 and -180 <= longitude <= 180) or not all(math.isfinite(v) for v in (latitude, longitude)):
        raise GISError("latitude/longitude must be finite and within WGS84 bounds")
    zone = min(60, max(1, int((longitude + 180) / 6) + 1))
    northern = latitude >= 0
    a, eccentricity_squared, scale = 6378137.0, 0.0066943799901413165, 0.9996
    eccentricity_prime_squared = eccentricity_squared / (1 - eccentricity_squared)
    lat, lon = math.radians(latitude), math.radians(longitude)
    central_meridian = math.radians((zone - 1) * 6 - 180 + 3)
    sin_lat, cos_lat, tan_lat = math.sin(lat), math.cos(lat), math.tan(lat)
    N = a / math.sqrt(1 - eccentricity_squared * sin_lat**2)
    T, C, A = tan_lat**2, eccentricity_prime_squared * cos_lat**2, cos_lat * (lon - central_meridian)
    M = a * ((1 - eccentricity_squared / 4 - 3 * eccentricity_squared**2 / 64 - 5 * eccentricity_squared**3 / 256) * lat - (3 * eccentricity_squared / 8 + 3 * eccentricity_squared**2 / 32 + 45 * eccentricity_squared**3 / 1024) * math.sin(2 * lat) + (15 * eccentricity_squared**2 / 256 + 45 * eccentricity_squared**3 / 1024) * math.sin(4 * lat) - (35 * eccentricity_squared**3 / 3072) * math.sin(6 * lat))
    easting = scale * N * (A + (1 - T + C) * A**3 / 6 + (5 - 18 * T + T**2 + 72 * C - 58 * eccentricity_prime_squared) * A**5 / 120) + 500000
    northing = scale * (M + N * tan_lat * (A**2 / 2 + (5 - T + 9 * C + 4 * C**2) * A**4 / 24 + (61 - 58 * T + T**2 + 600 * C - 330 * eccentricity_prime_squared) * A**6 / 720))
    if not northern:
        northing += 10000000
    return zone, northern, easting, northing
