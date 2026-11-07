"""Small performance qualification harness for existing inversion engines."""

from __future__ import annotations

import gc
import time
import tracemalloc
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Mapping


class PerformanceScale(str, Enum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    STRESS = "stress-scale"


@dataclass(frozen=True)
class PerformanceCase:
    """Declared qualification size, including cases not yet runnable locally."""

    name: str
    scale: PerformanceScale
    observations: int
    mesh_cells: int
    electrodes: int
    iterations: int
    status: str = "not measured"
    limitation: str = ""

    def __post_init__(self) -> None:
        if min(self.observations, self.mesh_cells, self.electrodes, self.iterations) <= 0:
            raise ValueError("performance case sizes must be positive")
        if not self.name.strip():
            raise ValueError("performance case name is required")


def declared_performance_cases() -> tuple[PerformanceCase, ...]:
    """Return the fixed scale vocabulary used for qualification planning."""
    return (
        PerformanceCase("small-baseline", PerformanceScale.SMALL, 6, 18, 6, 1, "measured"),
        PerformanceCase("medium-field-placeholder", PerformanceScale.MEDIUM, 100, 500, 32, 3),
        PerformanceCase("large-field-placeholder", PerformanceScale.LARGE, 1000, 5000, 128, 5),
        PerformanceCase("stress-field-placeholder", PerformanceScale.STRESS, 5000, 25000, 256, 8),
    )


@dataclass(frozen=True)
class PerformanceMeasurement:
    name: str
    seconds: float
    peak_python_bytes: int
    metadata: Mapping[str, object]


def measure(name: str, operation: Callable[[], object], **metadata: object) -> PerformanceMeasurement:
    """Measure one deterministic operation without modifying its inputs."""
    gc.collect()
    tracemalloc.start()
    start = time.perf_counter()
    operation()
    seconds = time.perf_counter() - start
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return PerformanceMeasurement(name, seconds, peak, dict(metadata))


def format_measurement(measurement: PerformanceMeasurement) -> str:
    return (
        f"{measurement.name}: {measurement.seconds:.6f} s, "
        f"{measurement.peak_python_bytes} peak Python bytes, "
        f"{dict(measurement.metadata)}"
    )
