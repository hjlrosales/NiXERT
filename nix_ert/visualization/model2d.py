"""Report-ready 2D resistivity model representation and rendering."""

from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

import numpy as np


class ModelViewError(ValueError):
    """Raised when a model view contains invalid display parameters."""


@dataclass(frozen=True)
class ModelViewControls:
    minimum: float | None = None
    maximum: float | None = None
    contour_levels: int = 12
    logarithmic: bool = True
    show_electrodes: bool = True
    show_topography: bool = False


@dataclass(frozen=True)
class CellInfo:
    column: int
    layer: int
    x: float
    depth: float
    resistivity: float


@dataclass(frozen=True)
class ResistivitySection:
    x_edges: tuple[float, ...]
    depth_edges: tuple[float, ...]
    resistivity: np.ndarray
    electrode_x: tuple[float, ...] = ()
    topography: tuple[tuple[float, float], ...] = ()
    controls: ModelViewControls = ModelViewControls()

    def __post_init__(self) -> None:
        values = np.asarray(self.resistivity, dtype=float)
        if values.shape != (len(self.depth_edges) - 1, len(self.x_edges) - 1):
            raise ModelViewError("resistivity shape does not match section edges")
        if len(self.x_edges) < 2 or len(self.depth_edges) < 2:
            raise ModelViewError("section must contain at least one cell")
        if any(not math.isfinite(value) for value in (*self.x_edges, *self.depth_edges)):
            raise ModelViewError("section coordinates must be finite")
        if any(right <= left for left, right in zip(self.x_edges, self.x_edges[1:])):
            raise ModelViewError("x edges must increase")
        if self.depth_edges[0] != 0 or any(right <= left for left, right in zip(self.depth_edges, self.depth_edges[1:])):
            raise ModelViewError("depth edges must start at zero and increase")
        if not np.all(np.isfinite(values)) or np.any(values <= 0):
            raise ModelViewError("resistivity cells must be finite and positive")
        if self.controls.contour_levels < 2:
            raise ModelViewError("at least two contour levels are required")
        if self.controls.minimum is not None and (not math.isfinite(self.controls.minimum) or self.controls.minimum <= 0):
            raise ModelViewError("minimum resistivity must be finite and positive")
        if self.controls.maximum is not None and (not math.isfinite(self.controls.maximum) or self.controls.maximum <= 0):
            raise ModelViewError("maximum resistivity must be finite and positive")
        minimum, maximum = self.display_limits
        if minimum >= maximum:
            raise ModelViewError("minimum display resistivity must be less than maximum")
        object.__setattr__(self, "resistivity", values.copy())

    @property
    def display_limits(self) -> tuple[float, float]:
        values = self.resistivity
        minimum = self.controls.minimum if self.controls.minimum is not None else float(np.min(values))
        maximum = self.controls.maximum if self.controls.maximum is not None else float(np.max(values))
        return minimum, maximum

    @property
    def x_centres(self) -> np.ndarray:
        return (np.asarray(self.x_edges[:-1]) + np.asarray(self.x_edges[1:])) / 2

    @property
    def depth_centres(self) -> np.ndarray:
        return (np.asarray(self.depth_edges[:-1]) + np.asarray(self.depth_edges[1:])) / 2

    def with_controls(self, **changes: object) -> "ResistivitySection":
        return replace(self, controls=replace(self.controls, **changes))

    def normalized(self) -> np.ndarray:
        """Return values clipped and normalized for a color scale."""
        minimum, maximum = self.display_limits
        if self.controls.logarithmic:
            source = np.log10(self.resistivity)
            low, high = math.log10(minimum), math.log10(maximum)
        else:
            source, low, high = self.resistivity, minimum, maximum
        return np.clip((source - low) / (high - low), 0.0, 1.0)

    def inspect_cell(self, column: int, layer: int) -> CellInfo:
        if not (0 <= column < self.resistivity.shape[1] and 0 <= layer < self.resistivity.shape[0]):
            raise ModelViewError("model cell is out of range")
        return CellInfo(column, layer, float(self.x_centres[column]), float(self.depth_centres[layer]), float(self.resistivity[layer, column]))

    def csv(self) -> str:
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(("column", "layer", "x", "depth", "resistivity"))
        for layer, depth in enumerate(self.depth_centres):
            for column, x in enumerate(self.x_centres):
                writer.writerow((column, layer, x, depth, self.resistivity[layer, column]))
        return output.getvalue()

    def render(self, path: Path | str, *, dpi: int = 150) -> None:
        """Render PNG/PDF/SVG through matplotlib when that optional dependency exists."""
        try:
            import matplotlib.pyplot as plt
            from matplotlib.colors import LogNorm, Normalize
        except ImportError as exc:  # pragma: no cover
            raise ModelViewError("matplotlib is required for image rendering") from exc
        minimum, maximum = self.display_limits
        norm = LogNorm(minimum, maximum) if self.controls.logarithmic else Normalize(minimum, maximum)
        figure, axis = plt.subplots(figsize=(10, 5), constrained_layout=True)
        mesh = axis.pcolormesh(self.x_edges, self.depth_edges, self.resistivity, shading="flat", norm=norm, cmap="viridis")
        figure.colorbar(mesh, ax=axis, label="Resistivity")
        if self.controls.show_electrodes and self.electrode_x:
            axis.scatter(self.electrode_x, [0] * len(self.electrode_x), marker="^", color="white", edgecolor="black", zorder=3)
        if self.controls.show_topography and self.topography:
            axis.plot([point[0] for point in self.topography], [point[1] for point in self.topography], color="black", linewidth=1.5)
        axis.set_xlabel("Distance")
        axis.set_ylabel("Depth")
        axis.invert_yaxis()
        axis.set_title("2D Resistivity Section")
        figure.savefig(path, dpi=dpi)
        plt.close(figure)


def export_section_csv(section: ResistivitySection, path: Path | str) -> None:
    Path(path).write_text(section.csv(), encoding="utf-8", newline="")
