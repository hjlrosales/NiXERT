# M18 performance qualification

Measurements use `time.perf_counter()` and Python `tracemalloc`. Results are
environment-dependent and should be recorded with Python, NumPy/SciPy,
operating system, mesh, electrode, observation, and iteration metadata.

## Declared qualification scales

`PerformanceCase` provides explicit small, medium, large, and stress-scale
records. A case is not treated as measured unless a run records its timing,
peak memory, convergence, and cancellation outcome.

| Scale | Current representative case | Status |
|---|---|---|
| Small | 2D: 6 electrodes / 6 observations / 18 cells; 3D: 4 electrodes / 2 observations / 16 cells | Measured in internal tests and local baseline |
| Medium | To be defined from a representative field survey | Not measured |
| Large | To be defined from a representative field survey | Not measured |
| Stress-scale | To be defined from a representative field survey and resource budget | Not measured |

## Observed local small-case baseline

One qualification run on the development Windows/Python environment produced:

| Operation | Mesh/observations | Iterations | Wall time | Peak Python-traced memory |
|---|---|---:|---:|---:|
| VES noisy inversion | 8 points | SciPy `max_nfev=20` | 16.551942 s | 63,110 bytes |
| 2D noisy inversion | 18 cells / 6 observations | 1 | 0.247520 s | 139,640 bytes |
| 3D noisy inversion | 16 cells / 2 observations | 1 | 0.375646 s | 124,231 bytes |

These values are local reproducibility evidence, not guaranteed limits. ERT
cost is dominated by sparse solves and numerical Jacobian construction; VES
cost is dominated by repeated numerical Hankel integrals. No optimization is
claimed or performed merely from appearance. The correct next step for larger
cases is profiling, not speculative optimization.

## Cancellation and memory boundary

Desktop 2D inversion runs on a detached input in a single worker. Progress,
operation detail, iteration, elapsed time, and cancellation state are visible
to the UI. Cancellation is checked before any persistence commit; the worker
never writes SQLite. Python-traced memory excludes native allocations in
NumPy/SciPy, so resource limits cannot yet be inferred from these values.

## Practical limitations

No large or stress-scale field dataset is bundled. There is consequently no
scientifically defensible production workload limit, throughput claim, or
memory ceiling. Future measurements must include observation count, mesh/cell
count, iteration count, wall time, peak process/native memory, convergence,
and cancellation behavior.
