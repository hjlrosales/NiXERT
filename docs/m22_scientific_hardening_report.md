# M22 inversion robustness and scientific hardening result

**Procedure:** `m22-inversion-hardening-v2`  
**Evidence class:** `QUALITATIVELY CONSISTENT`  
**Report SHA-256:** `c05d476c0cf74f5569756ae6466bb5b544829cea809df1ac9e6dc48c5547cf52`

## Environment

- **python:** 3.11.9
- **platform:** Windows-10-10.0.26200-SP0
- **machine:** AMD64
- **software_version:** 0.1.0

## Convergence and outcome records

| Domain | Record | Outcome | History | Initial objective | Final objective | Iterations | Evaluations | Configured maximum | Criterion satisfied |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| VES | `m22-ves-bounded-20` | `CONVERGED` | HISTORY_UNAVAILABLE | 0.10354346 | 0.011501149 | - | 13 | 20 function_evaluations | True |
| VES | `m22-ves-complete-40` | `CONVERGED` | HISTORY_UNAVAILABLE | 0.10354346 | 0.011501149 | - | 13 | 40 function_evaluations | True |
| 2D ERT | `m22-ert2d-bounded-1` | `TERMINATED` | RECORDED | 0.17264465 | 0.026041052 | 1 | 2 | 1 iterations | False |
| 3D ERT | `m22-ert3d-bounded-1` | `TERMINATED` | RECORDED | 0.20213359 | 0.14952967 | 1 | 2 | 1 iterations | False |
| VES | `m22-ves-invalid-controls` | `INVALID_INPUT` | HISTORY_UNAVAILABLE | not exposed | not exposed | 0 | 0 | 0 function_evaluations | False |
| 2D ERT | `m22-cancellation-safety` | `CANCELLED` | HISTORY_UNAVAILABLE | not exposed | not exposed | - | - | - | False |

### Termination detail

- `m22-ves-bounded-20`: `ftol` termination condition is satisfied. (final model status `VALID`)
- `m22-ves-complete-40`: `ftol` termination condition is satisfied. (final model status `VALID`)
- `m22-ert2d-bounded-1`: maximum iterations reached (final model status `VALID`)
- `m22-ert3d-bounded-1`: maximum iterations reached (final model status `VALID`)
- `m22-ves-invalid-controls`: input rejected before a scientific result was produced (final model status `NOT_PRODUCED`, error class `VESError`)
- `m22-cancellation-safety`: operation cancelled before project state was changed (final model status `NOT_PRODUCED`)

Outcome coverage across every committed M22 record and study case:

- `CONVERGED`: 9
- `TERMINATED`: 27
- `FAILED`: 0
- `INVALID_INPUT`: 3
- `CANCELLED`: 1

## Sensitivity studies

### `m22-ves-starting-model-v1` (VES)

| Case | Changed parameter | Value | Outcome | Final objective | Response RMSE | Log10 RMSE | Model L2 |
|---|---|---|---|---:|---:|---:|---:|
| `ves-starting-low` | starting_model | {'resistivities': [50.0, 15.0, 120.0], 'thicknesses': [3.0, 8.0]} | `CONVERGED` | 0.011501149 | 1.528957e-05 | 1.1101326e-07 | 7.2299842e-06 |
| `ves-starting-high` | starting_model | {'resistivities': [150.0, 50.0, 300.0], 'thicknesses': [8.0, 16.0]} | `CONVERGED` | 0.011501149 | 7.2510102e-06 | 5.0285096e-08 | 3.1348637e-06 |
| `ves-starting-two-layer` | starting_model | {'resistivities': [100.0, 20.0], 'thicknesses': [5.0]} | `CONVERGED` | 0.072749876 | 8.3681051 | 0.070966637 | not exposed |

Measured differences are configuration sensitivity evidence only. No preferred setting is declared and no universal pass/fail threshold is asserted; a lower residual is not evidence of a more accurate model.

### `m22-ves-stopping-limit-v1` (VES)

| Case | Changed parameter | Value | Outcome | Final objective | Response RMSE | Log10 RMSE | Model L2 |
|---|---|---|---|---:|---:|---:|---:|
| `ves-max-nfev-10` | max_nfev | 10 | `TERMINATED` | 0.011501158 | 0.0016392468 | 1.3410063e-05 | 0.00088964681 |
| `ves-max-nfev-20` | max_nfev | 20 | `CONVERGED` | 0.011501149 | 0 | 0 | 0 |
| `ves-max-nfev-40` | max_nfev | 40 | `CONVERGED` | 0.011501149 | 0 | 0 | 0 |

The stopping-limit study measures how the recorded result changes with the configured function-evaluation limit. It does not declare the tightest limit preferable; it only shows whether the reported objective and model stabilize once more evaluations are allowed.

### `m22-ves-deterministic-noise-v1` (VES)

| Case | Changed parameter | Value | Outcome | Final objective | Response RMSE | Log10 RMSE | Model L2 |
|---|---|---|---|---:|---:|---:|---:|
| `ves-noise-deterministic-v1` | deterministic_noise | [1.02, 0.97, 1.03, 0.95, 1.01, 1.04, 0.98, 1.02] | `CONVERGED` | 0.012453941 | 0.34329575 | 0.0023775833 | 0.021182768 |

The deterministic noise case is a reproducible perturbation realization applied to the clean fixture, not a field-instrument noise model. Metric differences are numerical robustness observations only.

### `m22-ert2d-starting-model-v1` (2D ERT)

| Case | Changed parameter | Value | Outcome | Final objective | Response RMSE | Log10 RMSE | Model L2 |
|---|---|---|---|---:|---:|---:|---:|
| `ert2d-starting-0.5` | starting_resistivity | 0.5 | `TERMINATED` | 0.0047847367 | 0.018719163 | 0.0051930087 | 0.67580765 |
| `ert2d-starting-2.0` | starting_resistivity | 2 | `TERMINATED` | 0.011084888 | 0.013543398 | 0.0036995214 | 0.81364001 |

Measured differences are configuration sensitivity evidence only. No preferred setting is declared and no universal pass/fail threshold is asserted; a lower residual is not evidence of a more accurate model.

### `m22-ert2d-damping-v1` (2D ERT)

| Case | Changed parameter | Value | Outcome | Final objective | Response RMSE | Log10 RMSE | Model L2 |
|---|---|---|---|---:|---:|---:|---:|
| `ert2d-damping-0.1` | damping | 0.1 | `TERMINATED` | 0.0043206527 | 0.015906942 | 0.0043216067 | 0.23623375 |
| `ert2d-damping-0.8` | damping | 0.8 | `TERMINATED` | 0.01174897 | 0.026047824 | 0.0071367258 | 0.079359503 |

The 2D engine also adapts damping inside the loop, so these cases measure the configured starting damping under that documented adaptation. No damping value is declared preferable.

### `m22-ert2d-mesh-domain-v1` (2D ERT)

| Case | Changed parameter | Value | Outcome | Final objective | Response RMSE | Log10 RMSE | Model L2 |
|---|---|---|---|---:|---:|---:|---:|
| `ert2d-mesh-nz-2` | mesh_nz | 2 | `TERMINATED` | 0.0074318884 | 0.0024158551 | 0.00072299138 | not exposed |
| `ert2d-mesh-nz-4` | mesh_nz | 4 | `TERMINATED` | 0.0081362256 | 0.0019583134 | 0.00057365135 | not exposed |
| `ert2d-mesh-depth-6` | mesh_depth | 6 | `TERMINATED` | 0.0068810065 | 0.0045848464 | 0.001270569 | not exposed |
| `ert2d-mesh-too-coarse` | mesh_nx | 5 | `INVALID_INPUT` | not exposed | not exposed | not exposed | not exposed |

Mesh and domain variants are recorded as measured numerical differences. Cell-wise model L2 distance is only reported between meshes of identical shape; different discretizations are not compared model-to-model.

### `m22-ert2d-stopping-limit-v1` (2D ERT)

| Case | Changed parameter | Value | Outcome | Final objective | Response RMSE | Log10 RMSE | Model L2 |
|---|---|---|---|---:|---:|---:|---:|
| `ert2d-max-iterations-1` | max_iterations | 1 | `TERMINATED` | 0.026041052 | 0.085605792 | 0.024109131 | 0.11899135 |
| `ert2d-max-iterations-2` | max_iterations | 2 | `TERMINATED` | 0.0092731122 | 0.011382279 | 0.0031958451 | 0.045103597 |
| `ert2d-max-iterations-5` | max_iterations | 5 | `TERMINATED` | 0.0055580267 | 0.010030064 | 0.0027831209 | 0.14537865 |

Additional iterations are allowed under the same controls. The study shows whether the recorded objective and model stabilize; it does not assume stabilization because the residual decreases.

### `m22-ert2d-deterministic-noise-v1` (2D ERT)

| Case | Changed parameter | Value | Outcome | Final objective | Response RMSE | Log10 RMSE | Model L2 |
|---|---|---|---|---:|---:|---:|---:|
| `ert2d-noise-deterministic-v1` | deterministic_noise | [0.95, 1.05, 0.97, 1.03, 0.99, 1.02] | `TERMINATED` | 0.0059925697 | 0.067092019 | 0.022018362 | 0.14692747 |

The deterministic noise case is applied to the clean fixture responses, so it is a distinct reproducible realization from the M21 fixture noise. It is not a field-instrument noise model.

### `m22-ert3d-starting-model-v1` (3D ERT)

| Case | Changed parameter | Value | Outcome | Final objective | Response RMSE | Log10 RMSE | Model L2 |
|---|---|---|---|---:|---:|---:|---:|
| `ert3d-starting-0.5` | starting_resistivity | 0.5 | `TERMINATED` | 0.14266386 | 0.2746605 | 0.093204691 | 0.79497137 |
| `ert3d-starting-2.0` | starting_resistivity | 2 | `TERMINATED` | 0.024588921 | 0.24117605 | 0.068036833 | 0.90415963 |

Measured differences are configuration sensitivity evidence only. No preferred setting is declared and no universal pass/fail threshold is asserted; a lower residual is not evidence of a more accurate model.

### `m22-ert3d-damping-v1` (3D ERT)

| Case | Changed parameter | Value | Outcome | Final objective | Response RMSE | Log10 RMSE | Model L2 |
|---|---|---|---|---:|---:|---:|---:|
| `ert3d-damping-0.1` | damping | 0.1 | `TERMINATED` | 0.1227759 | 0.22053292 | 0.073185452 | 0.21294485 |
| `ert3d-damping-0.9` | damping | 0.9 | `TERMINATED` | 0.062640612 | 0.039172395 | 0.012131206 | 0.03623331 |

The 3D engine uses the configured damping both in its normal equations and as a fixed step multiplier, so these cases measure that documented behavior. No damping value is declared preferable.

### `m22-ert3d-mesh-domain-v1` (3D ERT)

| Case | Changed parameter | Value | Outcome | Final objective | Response RMSE | Log10 RMSE | Model L2 |
|---|---|---|---|---:|---:|---:|---:|
| `ert3d-mesh-nz-3` | mesh_nz | 3 | `TERMINATED` | 0.058938741 | 0.026947865 | 0.0083089193 | not exposed |
| `ert3d-mesh-nz-4` | mesh_nz | 4 | `TERMINATED` | 0.060199924 | 0.031130299 | 0.0096128731 | not exposed |
| `ert3d-mesh-x-refined-8` | mesh_nx | 8 | `TERMINATED` | 0.047328306 | 0.01253038 | 0.0038100456 | not exposed |
| `ert3d-mesh-too-coarse` | mesh_nx | 2 | `INVALID_INPUT` | not exposed | not exposed | not exposed | not exposed |

Mesh and domain variants are recorded as measured numerical differences. Cell-wise model L2 distance is only reported between meshes of identical shape; different discretizations are not compared model-to-model.

### `m22-ert3d-stopping-limit-v1` (3D ERT)

| Case | Changed parameter | Value | Outcome | Final objective | Response RMSE | Log10 RMSE | Model L2 |
|---|---|---|---|---:|---:|---:|---:|
| `ert3d-max-iterations-1` | max_iterations | 1 | `TERMINATED` | 0.14952967 | 0.29275349 | 0.10010764 | 0.28799326 |
| `ert3d-max-iterations-3` | max_iterations | 3 | `TERMINATED` | 0.085293147 | 0.11096966 | 0.035285809 | 0.10435538 |
| `ert3d-max-iterations-10` | max_iterations | 10 | `TERMINATED` | 0.019986959 | 0.12146256 | 0.03559553 | 0.10822663 |

Additional iterations are allowed under the same controls. The 3D engine's configured tolerance is much tighter than the fixture can reach, so bounded completion remains the recorded outcome.

### `m22-ert3d-deterministic-noise-v1` (3D ERT)

| Case | Changed parameter | Value | Outcome | Final objective | Response RMSE | Log10 RMSE | Model L2 |
|---|---|---|---|---:|---:|---:|---:|
| `ert3d-noise-deterministic-v1` | deterministic_noise | [0.96, 1.05] | `TERMINATED` | 0.052357874 | 0.00041017373 | 0.00012528608 | 0.000376024 |

The deterministic noise case is applied to the clean fixture responses, so it is a distinct reproducible realization from the M21 fixture noise. It is not a field-instrument noise model.

## Result-selection rule

Every configured bounded case is reported. No case is dropped, retried, or selected after the fact, and no 'best' result is chosen. Baselines are the M21-documented configurations (VES max_nfev=20, 2D max_iterations=1 damping=0.3 initial 1.0 Ohm.m, 3D max_iterations=1 damping=0.5 initial 1.0 Ohm.m); study baselines are fixed before execution and are recorded in each study's baseline configuration.

## Cancellation evidence

- **executor_state:** cancelled
- **cancellation_exception:** OperationCancelled
- **committed_state_entries:** 0

## Metric definitions

- **`rmse`** — measures: Root-mean-square difference between a compared response and the baseline response. Requires: Two equal-length finite response sequences with identical observation order. Does not establish: Geological accuracy, uniqueness, resolution, or field validity.
- **`relative_rmse`** — measures: Root-mean-square of the response difference normalized by the baseline magnitude. Requires: Two equal-length finite response sequences with non-zero baseline values. Does not establish: Any statement about which configuration is scientifically preferable.
- **`max_absolute_difference`** — measures: Largest absolute response difference in the compared sequences. Requires: Two equal-length finite response sequences. Does not establish: Where or why a difference matters geologically.
- **`log10_rmse`** — measures: Root-mean-square difference in log10 response, the space the engines fit. Requires: Two equal-length finite positive response sequences. Does not establish: That a smaller log10 residual means a more accurate model.
- **`model_l2_difference`** — measures: Euclidean distance between two log10 model parameter vectors. Requires: Two equal-length finite model vectors *and* an identical declared discretization (mesh edges, so cell locations and volumes match, plus the same parameter order). Cases whose discretizations differ are omitted instead of compared. Does not establish: Model correctness; different discretizations are not comparable this way.
- **`model_relative_l2_difference`** — measures: Model L2 difference normalized by the baseline model-vector norm. Requires: Two equal-length finite non-zero model vectors and the same discretization/parameter identity as ``model_l2_difference``. Does not establish: Uniqueness or resolution of the inverted model.

## Unavailable evidence

- **VES / damping study** — `UNAVAILABLE`: The VES engine exposes no damping control; no variant is simulated.
- **VES / mesh/domain-resolution study** — `UNAVAILABLE`: A 1D layered-earth model has no mesh or domain resolution to vary.
- **VES / per-evaluation objective trajectory** — `HISTORY_UNAVAILABLE`: scipy.optimize.least_squares exposes no per-evaluation objective series; M22 records the initial and final objective but refuses to invent a trajectory.
- **2D ERT / line-search trial objective sequence** — `PARTIAL`: Only accepted/attempted step objectives and the returned model evaluation are exposed; internal line-search and Jacobian evaluations are not recorded.
- **3D ERT / line-search trial objective sequence** — `PARTIAL`: Only solver step objectives and the returned model evaluation are exposed; internal Jacobian evaluations are not recorded.
- **all / uncertainty, resolution, and uniqueness analysis** — `UNAVAILABLE`: Not implemented; out of M22 scope.
- **all / external reference or field agreement** — `NOT_VALIDATED`: No authorized independent dataset with a trustworthy reference result is available.

## Unvalidated claims

- A lower residual, a decreasing trajectory, or a nominal convergence criterion does not establish a more accurate geological model.
- Stable repeat results do not establish field accuracy or instrument validity.
- Reproducibility does not establish correctness or agreement with an external reference.
- Bounded completion at a configured limit is not evidence of an implementation defect.
- No RES2DINV, commercial-solver, or published-dataset equivalence is claimed.
- No uncertainty, resolution, or inversion-uniqueness result is provided.

## External benchmark readiness

- `m22-external-reference-gate` (no-authorized-reference-dataset): **NOT VALIDATED** — No legally usable independent dataset with a trustworthy expected result is available in the repository. M22 does not acquire or fabricate reference results to change this status.
  - Required evidence: licensed dataset bytes, known acquisition and geometry metadata, source hash and provenance, trustworthy reference result, frozen preprocessing, mesh, inversion, stopping, metric, and tolerance protocol

## Limitations

- Internal synthetic evidence is not independent validation.
- The internal fixture is small; no medium, large, or stress-scale convergence behaviour is measured.
- Residual reduction, stability, and reproducibility do not establish geological correctness or uniqueness.
- No uncertainty, resolution, or topography-aware inversion result is produced.
- The engines separate invalid input from numerical failure by exception class (``ERT2DError`` / ``ERT3DError`` / ``VESError`` for rejected input, ``ERT2DNumericalError`` / ``ERT3DNumericalError`` / ``VESNumericalError`` for a mid-run forward-model or solver failure) and by the recorded failure phase. A numerical failure that is raised as a bare ``ValueError`` by a future library version would still be recorded as ``INVALID_INPUT``; no such case is reachable in the committed studies.
- Reaching a configured limit is retained as bounded-completion evidence and is never reported as a defect.
- M15 physical LS2 validation remains pending and the ABEM/Barugo importer remains NOT_READY.

## Superseded artifacts

- **`docs/m22_scientific_hardening.json`** — `SUPERSEDED` (was `m22-inversion-hardening-v1`, sha256 `df6847c8073f86bda8e6e8d6aef178780972795307ba5b4c95efd17c0be37367`)
  - Superseded by: docs/m22_scientific_hardening.json (m22-inversion-hardening-v2)
  - Reason: The M23 audit-corrected forward physics changed the numbers this artifact records. The A1 VES layered-earth kernel correction changes every VES objective, trajectory, and model; the A2/A3 nonuniform-mesh transmissibility corrections change every 2D and 3D nonuniform-mesh forward response; and the B1-B4 integrity corrections change the recorded failure phases, the admission rules, the model-comparison discretization requirement, and the VES input-failure behaviour. The v1 records were produced by the pre-correction implementation.
  - Historical evidence retained: The superseded v1 values are not overwritten silently: the pre-correction 3D reporting values are retained in the `corrections` block of docs/m21_scientific_qualification.json, the pre-correction VES and nonuniform-mesh values are recorded in docs/m23_forward_physics_correction.md and the M23 evidence notes, and the changelog records the transition.
