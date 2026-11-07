# M21 Scientific Qualification Result

**Procedure:** `m21-scientific-qualification-v1`  
**Status:** Complete for internal qualification and benchmark readiness  
**Evidence class:** `QUALITATIVELY CONSISTENT` for the internal synthetic VES,
2D ERT, and 3D ERT cases.  
**External benchmark status:** `NOT VALIDATED`

## Scope and methodology

M21 reuses the existing M19 deterministic manifest contract and existing VES,
2D ERT, and 3D ERT engines. It does not change scientific calculations.
Each run records:

- dataset identity and classification;
- software/environment metadata;
- starting model and solver configuration;
- mesh/domain information;
- damping and stopping limits;
- objective/residual history;
- final output metrics;
- termination outcome;
- sensitivity-study configuration and measured differences.

Qualification outcomes are explicit:

- `CONVERGED` — solver reported convergence under its configured criterion;
- `TERMINATED` — solver completed at a configured limit without convergence;
- `FAILED` — numerical/solver failure;
- `INVALID_INPUT` — input rejected before a scientific result;
- `CANCELLED` — operation cancelled before persistence;
- `NOT_VALIDATED` — evidence is unavailable, not a solver outcome.

A completed solver run is not automatically considered scientifically validated.

## Metrics

The M21 metrics are numerical comparison quantities only:

- RMSE of predicted versus observed apparent resistivity;
- relative RMSE;
- maximum absolute response difference;
- log10-response RMSE;
- model L2 difference when a comparable model vector exists.

These metrics describe numerical response and sensitivity. They do not measure
geological accuracy, uncertainty, resolution, or inversion uniqueness.

## Internal qualification results

Environment: Python 3.11.9, Windows 10, AMD64, NiX ERT 0.1.0.

| Domain | Dataset | Configuration | Outcome | Initial objective | Final objective | Evidence |
|---|---|---|---|---:|---:|---|
| VES | `ves-layered-internal-v1` | 3-layer model, `max_nfev=20` | `CONVERGED` | not exposed by engine | 0.0115011 | Qualitatively consistent |
| 2D ERT | `ert-2d-anomaly-internal-v1` | 18 cells, damping 0.3, 1 iteration | `TERMINATED` | 0.172645 | 0.0260411 | Qualitatively consistent |
| 3D ERT | `ert-3d-anomaly-internal-v1` | 16 cells, damping 0.5, 1 iteration | `TERMINATED` | 0.202134 | 0.149530 | Qualitatively consistent |

The 2D case reduced its objective during the controlled iteration. The 3D
case reduced its objective from `0.202134` to `0.149530` in the single
configured iteration and did not converge. These are evidence records, not
pass/fail claims.

**Corrections.** The values above are the current, re-measured records. Two
corrections were applied after the original run and are preserved in the
`corrections` block of
[`m21_scientific_qualification.json`](m21_scientific_qualification.json):

- the 3D `final_objective` was corrected by `m22-inversion-hardening-v1` when a
  demonstrated 3D reporting defect (pre-update versus returned model) was fixed;
- the VES `outcome`, `final_objective` and metrics were corrected by
  `m23-forward-physics-correction-v1` when the demonstrated A1 layered VES kernel
  defect was fixed (the pre-correction fit was mis-scaled and therefore truncated
  at `max_nfev`); the 2D/3D metric values moved at floating-point rounding level
  only when the A2/A3 transmissibility corrections were applied, because those
  fixtures use equal-width meshes. See
  [`m23_forward_physics_correction.md`](m23_forward_physics_correction.md).

## Sensitivity studies

Controlled deterministic studies were run on the internal 2D fixture:

- starting resistivity: `0.5` and `2.0` versus baseline `1.0`;
- mesh depth resolution: 2 and 4 layers versus baseline 3;
- damping: `0.1` and `0.8` versus baseline `0.3`;
- stopping limit: 1 and 2 iterations;
- deterministic multiplicative noise factors:
  `1.01, 0.99, 1.02, 0.98, 1.01, 0.99`.

A VES starting-model study compared low and high initial layer models with a
fixed `max_nfev=20` limit.

Measured examples from the 2D studies:

| Study | Case | Final objective | Response RMSE vs baseline |
|---|---|---:|---:|
| Starting model | 0.5 | 0.146844 | 0.352258 |
| Starting model | 2.0 | 0.0373123 | 0.142479 |
| Mesh depth | 2 layers | 0.0194241 | 0.0261605 |
| Mesh depth | 4 layers | 0.0313473 | 0.0190084 |
| Damping | 0.1 | 0.0136754 | 0.0504923 |
| Damping | 0.8 | 0.0837860 | 0.184726 |
| Stopping | 1 iteration | 0.0260411 | 0 |
| Stopping | 2 iterations | 0.00927311 | 0.0768999 |
| Deterministic noise | fixed factors above | 0.0257670 | 0.0137886 |

The values quantify configuration sensitivity only. No universal tolerance was
created and no setting was selected because it produced a preferred geological
result.

## Failure and cancellation evidence

The qualification layer preserves invalid-input records and explicit
cancellation records. A negative 2D starting resistivity is classified as
`INVALID_INPUT` with the solver error retained. Cancellation is represented as
`CANCELLED` before persistence; no partial scientific state is written.

## External benchmark readiness

The external benchmark gate is:

`NOT VALIDATED`

No legally usable independent dataset with trustworthy expected results is
available in the repository. M21 therefore does not claim comparison against a
published dataset, commercial solver, RES2DINV, or field result.

Required evidence before an external comparison can be labeled validated:

- licensed/authorized dataset bytes;
- known acquisition and geometry metadata;
- source hash and provenance;
- trustworthy reference result;
- frozen preprocessing, mesh, inversion, stopping, metric, and tolerance
  protocol.

## Remaining limitations

- Internal synthetic evidence is not independent validation.
- No field accuracy or production-grade geological claim is established.
- Residuals do not establish uncertainty, resolution, or uniqueness.
- Topography-aware inversion is not implemented.
- Advanced/true 3D geological inversion is not established.
- M15 physical LS2 validation remains pending.
- ABEM/Barugo `importer_ready = false` remains unchanged.
- No RES2DINV equivalence or geological certainty is claimed.

## Corrections applied by M22

Fields were corrected twice, each time with the previous value preserved in the
`corrections` block of
[`m21_scientific_qualification.json`](m21_scientific_qualification.json).

**M22 — 3D ERT reporting defect.** The 3D engine returned an objective history
and convergence flag that described the pre-update model rather than the
returned model, so the recorded 3D `final_objective` wrongly equalled the
`initial_objective` and hid a measured objective reduction. M22 corrected the
engine reporting (not the algorithm) and re-ran the affected study. Regression
coverage: `tests/test_m22_hardening.py::M22EngineReportingRegressionTests`.

**M23 — forward-physics corrections.** The demonstrated A1 layered VES kernel
defect changed every VES response, so the VES record was re-measured; the A2/A3
face-transmissibility corrections moved the 2D and 3D metric values at
floating-point rounding level only, because both fixtures use equal-width meshes
where the old and new forms are algebraically identical. Regression coverage:
`tests/test_m23_forward_physics_correction.py`.

| Field | Previous value | Corrected value | Corrected by |
|---|---:|---:|---|
| `m21-ert3d-internal-v1` `final_objective` | 0.2021335923930331 | 0.14952966792891706 | M22 (reporting), then M23 (rounding level) |
| `m21-ves-internal-v1` `outcome` | `TERMINATED` | `CONVERGED` | M23 (A1 kernel) |
| `m21-ves-internal-v1` `final_objective` | 0.011580412898065794 | 0.011501149486299902 | M23 (A1 kernel) |

Manifest hashes and sensitivity studies are unchanged. The evidence is
documented in [`m22_scientific_hardening.md`](m22_scientific_hardening.md) and
[`m23_forward_physics_correction.md`](m23_forward_physics_correction.md), and
`provenance.last_corrected_by = m23-forward-physics-correction-v1`.
