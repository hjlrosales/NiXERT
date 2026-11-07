"""Survey-line coordinates and deterministic 3D placement transforms."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import Enum
from typing import Iterable, Sequence

import numpy as np


class CoordinateError(ValueError):
    """Raised for invalid coordinate systems or line transforms."""


class CoordinateSystem(str, Enum):
    LOCAL = "local"
    UTM = "utm"
    GPS = "gps"


@dataclass(frozen=True)
class CoordinateReference:
    system: CoordinateSystem
    zone: int | None = None
    northern_hemisphere: bool | None = None
    latitude: float | None = None
    longitude: float | None = None
    altitude: float = 0.0

    def __post_init__(self) -> None:
        if self.system is CoordinateSystem.UTM and (self.zone is None or not 1 <= self.zone <= 60 or self.northern_hemisphere is None):
            raise CoordinateError("UTM reference requires zone 1-60 and hemisphere")
        if self.system is CoordinateSystem.GPS:
            if self.latitude is None or self.longitude is None or not (-90 <= self.latitude <= 90) or not (-180 <= self.longitude <= 180):
                raise CoordinateError("GPS reference requires valid latitude and longitude")
        for value in (self.latitude, self.longitude, self.altitude):
            if value is not None and not math.isfinite(value):
                raise CoordinateError("coordinate reference values must be finite")


@dataclass(frozen=True)
class ElectrodeCoordinate:
    number: int
    x: float
    y: float
    z: float = 0.0


@dataclass(frozen=True)
class SurveyLine:
    name: str
    electrodes: tuple[ElectrodeCoordinate, ...]
    reference: CoordinateReference = CoordinateReference(CoordinateSystem.LOCAL)
    azimuth_degrees: float = 0.0
    origin_x: float = 0.0
    origin_y: float = 0.0
    origin_z: float = 0.0
    reversed: bool = False

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise CoordinateError("line name cannot be empty")
        if not self.electrodes:
            raise CoordinateError("line requires electrodes")
        if any(e.number <= 0 for e in self.electrodes):
            raise CoordinateError("electrode numbers must be positive")
        if len({e.number for e in self.electrodes}) != len(self.electrodes):
            raise CoordinateError("electrode numbers must be unique")
        values = [value for electrode in self.electrodes for value in (electrode.x, electrode.y, electrode.z)]
        if any(not math.isfinite(value) for value in (*values, self.azimuth_degrees, self.origin_x, self.origin_y, self.origin_z)):
            raise CoordinateError("line coordinates and transforms must be finite")

    @property
    def coordinates(self) -> tuple[ElectrodeCoordinate, ...]:
        """Return transformed line coordinates in its declared reference system."""
        angle = math.radians(self.azimuth_degrees % 360)
        cosine, sine = math.cos(angle), math.sin(angle)
        ordered = tuple(reversed(self.electrodes)) if self.reversed else self.electrodes
        return tuple(
            ElectrodeCoordinate(
                number=electrode.number,
                x=self.origin_x + cosine * electrode.x - sine * electrode.y,
                y=self.origin_y + sine * electrode.x + cosine * electrode.y,
                z=self.origin_z + electrode.z,
            )
            for electrode in ordered
        )

    def translated(self, x: float, y: float, z: float = 0.0) -> "SurveyLine":
        return replace(self, origin_x=self.origin_x + x, origin_y=self.origin_y + y, origin_z=self.origin_z + z)

    def rotated(self, degrees: float) -> "SurveyLine":
        if not math.isfinite(degrees):
            raise CoordinateError("rotation must be finite")
        return replace(self, azimuth_degrees=self.azimuth_degrees + degrees)

    def reversed_line(self) -> "SurveyLine":
        return replace(self, reversed=not self.reversed)


def gps_to_ecef(latitude: float, longitude: float, altitude: float = 0.0) -> tuple[float, float, float]:
    """Convert WGS84 geodetic coordinates to ECEF metres."""
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180) or not all(math.isfinite(value) for value in (latitude, longitude, altitude)):
        raise CoordinateError("invalid GPS coordinate")
    semi_major = 6378137.0
    eccentricity_squared = 6.6943799901413165e-3
    lat, lon = math.radians(latitude), math.radians(longitude)
    radius = semi_major / math.sqrt(1 - eccentricity_squared * math.sin(lat) ** 2)
    return ((radius + altitude) * math.cos(lat) * math.cos(lon), (radius + altitude) * math.cos(lat) * math.sin(lon), (radius * (1 - eccentricity_squared) + altitude) * math.sin(lat))


def gps_delta_to_enu(latitude: float, longitude: float, altitude: float, origin: CoordinateReference) -> tuple[float, float, float]:
    """Convert a WGS84 point into local ENU metres relative to a GPS origin."""
    if origin.system is not CoordinateSystem.GPS or origin.latitude is None or origin.longitude is None:
        raise CoordinateError("ENU conversion requires a GPS origin")
    point = np.asarray(gps_to_ecef(latitude, longitude, altitude))
    base = np.asarray(gps_to_ecef(origin.latitude, origin.longitude, origin.altitude))
    delta = point - base
    lat, lon = math.radians(origin.latitude), math.radians(origin.longitude)
    east = -math.sin(lon) * delta[0] + math.cos(lon) * delta[1]
    north = -math.sin(lat) * math.cos(lon) * delta[0] - math.sin(lat) * math.sin(lon) * delta[1] + math.cos(lat) * delta[2]
    up = math.cos(lat) * math.cos(lon) * delta[0] + math.cos(lat) * math.sin(lon) * delta[1] + math.sin(lat) * delta[2]
    return float(east), float(north), float(up)


def aggregate_lines(lines: Iterable[SurveyLine]) -> tuple[ElectrodeCoordinate, ...]:
    """Flatten transformed line coordinates for 3D visualization/export."""
    result: list[ElectrodeCoordinate] = []
    for line in lines:
        result.extend(line.coordinates)
    return tuple(result)
