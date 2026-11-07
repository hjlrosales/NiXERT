"""Validated 3D resistivity volume representation and inspection operations."""

from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np


class VolumeError(ValueError):
    """Raised for invalid volume geometry or display operations."""


@dataclass(frozen=True)
class VolumeControls:
    minimum: float | None = None
    maximum: float | None = None
    threshold_minimum: float | None = None
    threshold_maximum: float | None = None
    opacity: float = 1.0


@dataclass(frozen=True)
class VolumeCell:
    ix: int
    iy: int
    iz: int
    x: float
    y: float
    depth: float
    resistivity: float


@dataclass(frozen=True)
class ResistivityVolume:
    x_edges: tuple[float, ...]
    y_edges: tuple[float, ...]
    depth_edges: tuple[float, ...]
    resistivity: np.ndarray
    controls: VolumeControls = VolumeControls()
    topography: np.ndarray | None = None

    def __post_init__(self) -> None:
        values = np.asarray(self.resistivity, dtype=float)
        expected = (len(self.depth_edges) - 1, len(self.y_edges) - 1, len(self.x_edges) - 1)
        if values.shape != expected:
            raise VolumeError(f"volume shape must be {expected}")
        if any(len(edges) < 2 for edges in (self.x_edges, self.y_edges, self.depth_edges)):
            raise VolumeError("volume must have at least one cell in each dimension")
        if any(not math.isfinite(value) for value in (*self.x_edges, *self.y_edges, *self.depth_edges)):
            raise VolumeError("volume edges must be finite")
        if any(right <= left for left, right in zip(self.x_edges, self.x_edges[1:])) or any(right <= left for left, right in zip(self.y_edges, self.y_edges[1:])):
            raise VolumeError("horizontal edges must increase")
        if self.depth_edges[0] != 0 or any(right <= left for left, right in zip(self.depth_edges, self.depth_edges[1:])):
            raise VolumeError("depth edges must start at zero and increase")
        if not np.all(np.isfinite(values)) or np.any(values <= 0):
            raise VolumeError("volume resistivities must be finite and positive")
        minimum, maximum = self.display_limits
        if minimum >= maximum:
            raise VolumeError("minimum display value must be less than maximum")
        if not 0 < self.controls.opacity <= 1:
            raise VolumeError("opacity must be in (0, 1]")
        for value in (self.controls.threshold_minimum, self.controls.threshold_maximum):
            if value is not None and (not math.isfinite(value) or value <= 0):
                raise VolumeError("threshold values must be finite and positive")
        if self.controls.threshold_minimum is not None and self.controls.threshold_maximum is not None and self.controls.threshold_minimum > self.controls.threshold_maximum:
            raise VolumeError("minimum threshold must not exceed maximum threshold")
        if self.topography is not None and (self.topography.shape != (len(self.y_edges) - 1, len(self.x_edges) - 1) or not np.all(np.isfinite(self.topography))):
            raise VolumeError("topography must match horizontal cell shape")
        object.__setattr__(self, "resistivity", values.copy())

    @property
    def display_limits(self) -> tuple[float, float]:
        return (self.controls.minimum if self.controls.minimum is not None else float(np.min(self.resistivity)), self.controls.maximum if self.controls.maximum is not None else float(np.max(self.resistivity)))

    @property
    def x_centres(self) -> np.ndarray:
        return (np.asarray(self.x_edges[:-1]) + np.asarray(self.x_edges[1:])) / 2

    @property
    def y_centres(self) -> np.ndarray:
        return (np.asarray(self.y_edges[:-1]) + np.asarray(self.y_edges[1:])) / 2

    @property
    def depth_centres(self) -> np.ndarray:
        return (np.asarray(self.depth_edges[:-1]) + np.asarray(self.depth_edges[1:])) / 2

    def with_controls(self, **changes: object) -> "ResistivityVolume":
        return replace(self, controls=replace(self.controls, **changes))

    def threshold_mask(self) -> np.ndarray:
        mask = np.ones(self.resistivity.shape, dtype=bool)
        if self.controls.threshold_minimum is not None:
            mask &= self.resistivity >= self.controls.threshold_minimum
        if self.controls.threshold_maximum is not None:
            mask &= self.resistivity <= self.controls.threshold_maximum
        return mask

    def horizontal_slice(self, iz: int) -> np.ndarray:
        if not 0 <= iz < self.resistivity.shape[0]:
            raise VolumeError("depth slice is out of range")
        return self.resistivity[iz].copy()

    def vertical_slice_x(self, ix: int) -> np.ndarray:
        if not 0 <= ix < self.resistivity.shape[2]:
            raise VolumeError("x slice is out of range")
        return self.resistivity[:, :, ix].copy()

    def vertical_slice_y(self, iy: int) -> np.ndarray:
        if not 0 <= iy < self.resistivity.shape[1]:
            raise VolumeError("y slice is out of range")
        return self.resistivity[:, iy, :].copy()

    def inspect_cell(self, ix: int, iy: int, iz: int) -> VolumeCell:
        if not (0 <= ix < self.resistivity.shape[2] and 0 <= iy < self.resistivity.shape[1] and 0 <= iz < self.resistivity.shape[0]):
            raise VolumeError("volume cell is out of range")
        return VolumeCell(ix, iy, iz, float(self.x_centres[ix]), float(self.y_centres[iy]), float(self.depth_centres[iz]), float(self.resistivity[iz, iy, ix]))

    def csv(self) -> str:
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(("ix", "iy", "iz", "x", "y", "depth", "resistivity", "visible"))
        mask = self.threshold_mask()
        for iz, depth in enumerate(self.depth_centres):
            for iy, y in enumerate(self.y_centres):
                for ix, x in enumerate(self.x_centres):
                    writer.writerow((ix, iy, iz, x, y, depth, self.resistivity[iz, iy, ix], mask[iz, iy, ix]))
        return output.getvalue()

    def render(self, path: Path | str) -> None:
        try:
            import matplotlib.pyplot as plt
        except ImportError as exc:  # pragma: no cover
            raise VolumeError("matplotlib is required for 3D rendering") from exc
        mask = self.threshold_mask()
        z, y, x = np.where(mask)
        if len(x) == 0:
            raise VolumeError("threshold excludes every volume cell")
        figure = plt.figure(figsize=(9, 7))
        axis = figure.add_subplot(111, projection="3d")
        values = self.resistivity[z, y, x]
        scatter = axis.scatter(self.x_centres[x], self.y_centres[y], -self.depth_centres[z], c=values, alpha=self.controls.opacity)
        figure.colorbar(scatter, ax=axis, label="Resistivity")
        axis.set_xlabel("X")
        axis.set_ylabel("Y")
        axis.set_zlabel("Elevation relative to surface")
        figure.savefig(path, dpi=150)
        plt.close(figure)


def export_volume_csv(volume: ResistivityVolume, path: Path | str) -> None:
    Path(path).write_text(volume.csv(), encoding="utf-8", newline="")
