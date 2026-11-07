# M22 — Inversion Robustness and Scientific Hardening

**Procedure:** `m22-inversion-hardening-v2`
**Status:** Complete for instrumented bounded convergence evidence, with explicit limits
**Evidence class:** `QUALITATIVELY CONSISTENT` (internal synthetic fixtures only)
**External benchmark status:** `NOT VALIDATED`
**Independently validated the inversion robustness?** `NOT_VALIDATED`

> **Correction notice (M23).** The v1 numbers recorded here were produced by the
> pre-correction forward physics. The independent M23 audit confirmed the A1 VES
> layered-earth kernel defect and the A2/A3 nonuniform-mesh transmissibility defects,
> and the corrections changed every affected objective, trajectory, and model. The v1
> artifact (`report_sha256 =
> df6847c8073f86bda8e6e8d6aef178780972795307ba5b4c95efd17c0be37367`) is therefore
> recorded as `SUPERSEDED` in the report's `superseded_artifacts` block rather than
> silently overwritten. The values below are from the corrected implementation
> (`m22-inversion-hardening-v2`); see
> [`m23_forward_physics_correction.md`](m23_forward_physics_correction.md) for the
> audit evidence and the pre-correction values.

M22 executes the direction approved in
[`m22_roadmap_proposal.md`](m22_roadmap_proposal.md): measure and characterize the
existing VES, 2D ERT, and 3D ERT engines rather than replace them.

Generated artifacts for the run documented here:

- [`m22_scientific_hardening.json`](m22_scientific_hardening.json) — machine-readable
  result, including every contract, trajectory point, and per-case model vector.
- [`m22_scientific_hardening_report.md`](m22_scientific_hardening_report.md) —
  human-readable report generated from the same object
  (`report_sha256 = c05d476c0cf74f5569756ae6466bb5b544829cea809df1ac9e6dc48c5547cf52`).

Regenerate both with:

```bash
python tools/generate_m22_qualification.py
```

## 1. What M22 measured and what it did not

M22 measured, on the existing small synthetic fixtures:

- initial, per-evaluation, and final objectives with an explicit provenance for each;
- per-step solver state for the engines that expose it;
- bounded-completion, convergence, invalid-input, and cancellation outcomes using one
  normalized vocabulary;
- starting-model, damping, mesh/domain, stopping-limit, and deterministic-noise
  dependence for every engine that exposes the corresponding control;
- repeated-run reproducibility of the full qualification report.

M22 did **not** establish geological correctness, field accuracy, uniqueness,
resolution, uncertainty, or agreement with an external reference. Numerical
evidence is reported separately from scientific validity throughout the artifacts,
and the report carries a machine-readable `unvalidated_claims` block.

## 2. Common convergence/outcome contract

`nix_ert.qualification.m22.ConvergenceContract` is the single result structure used
for VES, 2D ERT, and 3D ERT. It records:

| Field | Meaning |
|---|---|
| `domain` | `VES`, `2D ERT`, or `3D ERT` |
| `initial_objective` / `initial_objective_source` | objective at the declared initial model, and how it was obtained |
| `objective_history` | recorded per-evaluation objectives, or empty |
| `history_status` | `RECORDED` or `HISTORY_UNAVAILABLE` |
| `trajectory` | per-step `TrajectoryPoint(step, objective, origin, solver_state)` |
| `final_objective` | objective of the **returned** model |
| `iteration_count` / `evaluation_count` | solver steps and recorded objective evaluations |
| `configured_maximum` / `configured_maximum_units` | the configured bound and whether it counts iterations or function evaluations |
| `configured_maximum_reached` | whether that bound caused termination |
| `convergence_criterion` / `convergence_tolerance` | the engine's declared criterion and tolerance |
| `convergence_criterion_satisfied` | whether the engine reported that criterion satisfied |
| `termination_reason` | the engine's or layer's termination text |
| `cancellation_requested`, `invalid_input`, `numerical_failure` | explicit flags |
| `final_model_status` | `VALID`, `INVALID`, or `NOT_PRODUCED` |
| `error` / `error_class` | retained error text and exception class |

Invariants enforced in `__post_init__`:

- a recorded history must begin at the declared initial objective and end at the
  declared final objective, with consecutive 1-based steps;
- `HISTORY_UNAVAILABLE` records must keep both the history and the trajectory empty —
  M22 never fabricates a trajectory;
- `CONVERGED` requires `convergence_criterion_satisfied`; solver completion alone is
  never enough;
- `TERMINATED` must not claim a satisfied criterion and must expose a valid final model;
- `FAILED` requires `numerical_failure` **and** a recorded error, and cannot expose a
  valid model — so reaching a configured limit is never reported as a failure;
- `INVALID_INPUT` requires rejected input plus an error and `NOT_PRODUCED`;
- `CANCELLED` requires a cancellation request, forbids a valid final model, and
  forbids an error, because cancellation is a safe stop rather than a failure.

`classify_outcome(...)` is the only mapping from engine-independent signals to the
normalized vocabulary (`CONVERGED`, `TERMINATED`, `FAILED`, `INVALID_INPUT`,
`CANCELLED`). It refuses ambiguous combinations instead of silently preferring one
outcome.

## 3. Instrumentation rather than replacement

M22 changed no inversion algorithm, update rule, damping schedule, regularization,
Jacobian, mesh, or forward model — it wraps the existing engines. (The later M23
milestone did change the VES forward kernel and the 2D/3D face transmissibility;
see the correction notice above and
[`m23_forward_physics_correction.md`](m23_forward_physics_correction.md).)

The instrumentation layer is:

- `run_ves_contract`, `run_ert2d_contract`, `run_ert3d_contract` call the existing
  `invert_ves`, `invert_ert`, and `invert_ert3d` unchanged;
- initial objectives are obtained through each engine's own public forward model at
  the declared initial model, and the source is recorded
  (`qualification forward evaluation at the declared initial parameters`);
- the 2D trajectory uses `ERTInversionResult.iterations` (documented as the
  *pre-update* objective per step) plus one final point for the returned model;
- the VES record is marked `HISTORY_UNAVAILABLE`, because
  `scipy.optimize.least_squares` exposes no per-evaluation objective series.

### 3.1 One concrete defect was demonstrated and corrected

Evidence: `invert_ert3d(fixture.noisy_observations, fixture.mesh,
fixture.electrodes, 1.0, damping=0.5, max_iterations=1)` returned

```text
history   = (0.2021335923930331,)      # pre-update objective
converged = False                      # derived from the same pre-update value
returned-model objective = 0.14952966792891706   # measured from the returned prediction
```

The returned history and convergence flag therefore described a model that was no
longer returned: the final accepted update changed the model *after* the objective
was computed. M21 consumed `history[-1]` as the final objective, so its 3D record
wrongly reported `initial == final == 0.202134` and hid a measured objective
reduction. This is an inconsistent termination state and an inconsistent
initial/final objective report.

Minimum correction (reporting only, `nix_ert/ert/inversion3d.py`):

- the returned model is evaluated once at the end of the run, its objective is
  appended to the history, and the convergence flag is derived from that value, so
  `history[-1]` and the flag always describe the returned model;
- the configured tolerance `1e-3` is exposed as `ERT3D_CONVERGENCE_RMS` instead of
  being duplicated as a literal in the qualification layer.

Numerical outputs are unchanged: no model vector, predicted response, update, or
damping schedule differs. The returned history gains the returned-model evaluation.
Regression coverage: `tests/test_m22_hardening.py::M22EngineReportingRegressionTests`.
The affected M21 record was re-run and corrected — see
[`m21_scientific_qualification.md`](m21_scientific_qualification.md) and the
`corrections` block in the M21 JSON.

Result-semantics clarifications (documentation only) were added to
`ERTInversionResult`/`InversionIteration` (2D) and `VESInversionResult` (VES). In
particular the VES `iterations` field is the optimizer's **function-evaluation
count**; the name is retained for persisted-version compatibility and is recorded in
M22 as `evaluation_count` with `configured_maximum_units = function_evaluations`.

No other defect was demonstrated. Sensitivity, non-uniqueness, and bounded
termination are reported as observations, not defects.

## 4. Study protocols

All studies are bounded, deterministic, and run on the existing internal fixtures
(VES `ves-layered-internal-v1`, 2D `ert-2d-anomaly-internal-v1`, 3D
`ert-3d-anomaly-internal-v1`). Baselines are the M21 configurations; study baselines
are fixed before execution and recorded in each study.

| Study | VES | 2D ERT | 3D ERT |
|---|---|---|---|
| starting model | 3 cases (low, high, two-layer), converged limit | 2 cases (0.5, 2.0 Ω·m) | 2 cases (0.5, 2.0 Ω·m) |
| damping | not exposed by the engine | 2 cases (0.1, 0.8) | 2 cases (0.1, 0.9) |
| mesh / domain | not applicable (1D layered model) | 4 cases (nz 2, nz 4, depth 6 m, too-coarse domain) | 4 cases (nz 3, nz 4, x-refined 8 columns, too-coarse domain) |
| stopping limit | 3 limits (10, 20, 40 evaluations) | 3 limits (1, 2, 5 iterations) | 3 limits (1, 3, 10 iterations) |
| deterministic noise | 1 realization (8 factors) | 1 realization (6 factors) | 1 realization (2 factors) |

VES starting-model and noise cases use a limit the engine converges within, so
measured differences are attributable to the changed parameter rather than to a
shared truncation. The stopping-limit study then measures the truncation itself.
The deterministic-noise realizations are applied to the **clean** fixture responses
and are deliberately different from the M21 fixture noise.

The "too-coarse domain" cases are real bounded failure modes: a mesh that cannot
resolve four distinct electrode cells is rejected by the engine, and M22 preserves
that as `INVALID_INPUT` evidence rather than removing the case.

## 5. Measured results

### 5.1 Baseline records

| Domain | Configuration | Outcome | Initial objective | Final objective | History | Criterion satisfied |
|---|---|---|---:|---:|---|---|
| VES | `max_nfev=20` (converges at 13 evaluations) | `CONVERGED` | 0.10354346 | 0.011501149 | `HISTORY_UNAVAILABLE` | yes (`ftol`) |
| VES | `max_nfev=40` (converges at 13 evaluations) | `CONVERGED` | 0.10354346 | 0.011501149 | `HISTORY_UNAVAILABLE` | yes (`ftol`) |
| 2D ERT | 1 iteration, damping 0.3, initial 1.0 Ω·m | `TERMINATED` | 0.17264465 | 0.026041052 | `RECORDED` (2 points) | no |
| 3D ERT | 1 iteration, damping 0.5, initial 1.0 Ω·m | `TERMINATED` | 0.20213359 | 0.14952967 | `RECORDED` (2 points) | no |

Trajectories for the longer study baselines (all `TERMINATED`, criterion unmet):

- 2D ERT (3 iterations): `0.172645 → 0.0260411 → 0.00927311 → 0.00780249`.
- 3D ERT (5 iterations): `0.202134 → 0.149530 → 0.112258 → 0.0852931 → 0.0655284 → 0.0509530`.

The 3D sequence is the M22 correction in action: the same run previously reported
`0.202134` before and after.

### 5.2 VES

| Case | Outcome | Final objective | Response RMSE vs baseline | Model L2 vs baseline |
|---|---|---:|---:|---:|
| starting low `(50, 15, 120)/(3, 8)` | `CONVERGED` | 0.011501149 | 1.53e-05 | 7.23e-06 |
| starting high `(150, 50, 300)/(8, 16)` | `CONVERGED` | 0.011501149 | 7.25e-06 | 3.13e-06 |
| starting two-layer `(100, 20)/(5)` | `CONVERGED` | 0.072749876 | 8.368 | not comparable (different parameter count) |
| limit 10 evaluations | `TERMINATED` | 0.011501158 | 1.64e-03 | 8.90e-04 |
| limit 20 evaluations | `CONVERGED` | 0.011501149 | 0 (baseline) | 0 (baseline) |
| limit 40 evaluations | `CONVERGED` | 0.011501149 | 0 (baseline) | 0 (baseline) |
| deterministic noise realization | `CONVERGED` | 0.012453941 | 0.343 | 0.0212 |

Findings, stated as observations:

- **After the M23 kernel correction the two three-layer starting models converge to
  the same response *and* the same model.** Model L2 against the baseline falls to
  `7.2e-06` and `3.1e-06` in log10 units from starting models that differ by more
  than half a decade. The earlier M22 observation that the response stabilized while
  the model kept moving was a consequence of the mis-scaled A1 kernel and is
  **withdrawn**; see [`m23_forward_physics_correction.md`](m23_forward_physics_correction.md).
- **The three-layer structure is now resolved by the data.** A two-layer model fits
  markedly worse (`0.0727` versus `0.0115`; response RMSE 8.37) instead of matching
  the three-layer response. The earlier M22 observation that a two-layer model was
  response-equivalent is likewise **withdrawn**. No model-complexity selection is made
  either way: M22 reports the measured fit, not a preferred model.
- **The generating fixture model is now approached, not recovered.** From the
  documented baseline configuration `(80, 30, 180) Ω·m / (4, 10) m` the fit reaches
  `(109.93, 20.97, 268.43) Ω·m / (4.716, 13.055) m` against the fixture's generating
  model `(100, 20, 250) Ω·m / (5, 12) m` at `2.64 %` response RMS, with a
  deterministic `-4 % … +5 %` multiplicative perturbation on the observations. Close
  agreement on one synthetic sounding is not a uniqueness, resolution or geological
  result, and no residual threshold is asserted.
- **`max_nfev=20` converges.** The bounded baseline now satisfies the engine's `ftol`
  criterion at 13 evaluations, so the pre-correction reading of that baseline as a
  truncation is **withdrawn**. The stopping-limit study still shows that only 10
  evaluations truncate the fit (`0.011501158`, above the converged `0.011501149`), and
  that allowing 40 instead of 20 changes nothing because both converge at 13.

### 5.3 2D ERT

| Case | Outcome | Final objective | Response RMSE vs baseline | Model L2 vs baseline |
|---|---|---:|---:|---:|
| starting 0.5 Ω·m | `TERMINATED` | 0.0047847367 | 0.01872 | 0.6758 |
| starting 2.0 Ω·m | `TERMINATED` | 0.011084888 | 0.01354 | 0.8136 |
| damping 0.1 | `TERMINATED` | 0.0043206527 | 0.01591 | 0.2362 |
| damping 0.8 | `TERMINATED` | 0.011748970 | 0.02605 | 0.07936 |
| mesh nz 2 (12 cells) | `TERMINATED` | 0.0074318884 | 0.002416 | not comparable (12 vs 18 cells) |
| mesh nz 4 (24 cells) | `TERMINATED` | 0.0081362256 | 0.001958 | not comparable (24 vs 18 cells) |
| mesh depth 6 m (18 cells) | `TERMINATED` | 0.0068810065 | 0.004585 | 0.1722 |
| mesh too coarse (15 cells) | `INVALID_INPUT` | not produced | — | — |
| limit 1 iteration | `TERMINATED` | 0.026041052 | 0.08561 | 0.1190 |
| limit 2 iterations | `TERMINATED` | 0.0092731122 | 0.01138 | 0.04510 |
| limit 5 iterations | `TERMINATED` | 0.0055580267 | 0.01003 | 0.1454 |
| deterministic noise realization | `TERMINATED` | 0.0059925697 | 0.06709 | 0.1469 |

Findings, stated as observations:

- **The residual decreases while the model does not converge to the baseline.**
  Across the stopping-limit cases the objective falls monotonically
  (`0.0260411 → 0.00927311 → 0.00555803`) but the distance from the 3-iteration
  baseline model does not `(0.1190 → 0.0451 → 0.1454)`. Lower residual is not a model
  claim and not a convergence claim: every case remains `TERMINATED`.
- **Every studied control changes the measured response, and the largest 2D effects
  come from the cases that change the data or the allowed work rather than only the
  solver path** (1-iteration limit 0.0856, deterministic noise 0.0671) versus the
  configuration-only cases (damping 0.0159-0.0260, starting model 0.0135-0.0187, mesh
  0.0020-0.0046). No damping value is preferred; the engine also adapts damping inside
  its loop, and that adaptation is documented rather than removed.
- **Mesh resolution changes the measured response**, and cell-wise model L2 is only
  reported between meshes of identical shape. Comparing different discretizations
  cell-by-cell would produce a number with no defensible meaning, so M22 omits it and
  records only response metrics plus the cell counts.

### 5.4 3D ERT

| Case | Outcome | Final objective | Response RMSE vs baseline | Model L2 vs baseline |
|---|---|---:|---:|---:|
| starting 0.5 Ω·m | `TERMINATED` | 0.14266386 | 0.27466 | 0.7950 |
| starting 2.0 Ω·m | `TERMINATED` | 0.024588921 | 0.24118 | 0.9042 |
| damping 0.1 | `TERMINATED` | 0.12277590 | 0.22053 | 0.2129 |
| damping 0.9 | `TERMINATED` | 0.062640612 | 0.039172 | 0.03623 |
| mesh nz 3 (24 cells) | `TERMINATED` | 0.058938741 | 0.026948 | not comparable |
| mesh nz 4 (32 cells) | `TERMINATED` | 0.060199924 | 0.031130 | not comparable |
| mesh x-refined 8 columns (32 cells) | `TERMINATED` | 0.047328306 | 0.012530 | not comparable |
| mesh too coarse (8 cells) | `INVALID_INPUT` | not produced | — | — |
| limit 1 iteration | `TERMINATED` | 0.14952967 | 0.29275 | 0.2880 |
| limit 3 iterations | `TERMINATED` | 0.085293147 | 0.11097 | 0.1044 |
| limit 10 iterations | `TERMINATED` | 0.019986959 | 0.12146 | 0.1082 |
| deterministic noise realization | `TERMINATED` | 0.052357874 | 0.000410 | 0.000376 |

Findings, stated as observations:

- **Every 3D case is bounded completion.** The 3D engine's configured tolerance
  (`1e-3` log10-RMS) is far tighter than this fixture can reach within the studied
  limits, so no 3D case converges. This is bounded-run evidence, not a defect and not
  convergence evidence.
- **Damping magnitude changes the 3D trajectory substantially** (0.1 → 0.123,
  0.9 → 0.0626 after 5 iterations), because the engine uses the configured damping
  both in its normal equations and as a fixed step multiplier. This is documented
  engine behaviour, not a discovered fault, and no damping value is preferred.
- **The 3D internal fixture is effectively rank-one.** Its two clean observations are
  a reciprocal pair (both `1.5836672968`), so the fixture supplies one independent
  apparent-resistivity value for 16 model cells. The measured 3D sensitivity is
  therefore dominated by underdetermination and cannot characterize 3D solver
  robustness in general. This is a limitation of the evidence, and M22 states it
  rather than treating the resulting model spread as a defect.
- **The deterministic-noise realization barely moves the model** (model L2 3.76e-04,
  the smallest measured effect) because the two observations are nearly degenerate.

## 6. Failure, bounded-run, and cancellation evidence

Committed outcome coverage across all M22 records and study cases:

| Outcome | Count | Note |
|---|---:|---|
| `CONVERGED` | 9 | VES cases whose `gtol`/`ftol` criterion was satisfied |
| `TERMINATED` | 27 | bounded completion at a configured iteration/evaluation limit |
| `FAILED` | 0 | no numerical failure occurred in the committed bounded studies |
| `INVALID_INPUT` | 3 | 2D too-coarse domain, 3D too-coarse domain, VES `max_nfev=0` |
| `CANCELLED` | 1 | desktop executor cancellation before the guarded commit point |

- Unsuccessful and bounded runs are retained with their configuration, objective,
  termination reason, and error class. No case is dropped, retried until a preferred
  result appears, or selected after the fact; the selection rule is recorded in the
  report.
- `FAILED` is implemented and regression-tested
  (`M22FailurePathTests::test_numerical_failures_are_classified_as_failed`, using an
  injected engine failure and a linear-algebra failure) but **zero** numerical
  failures occurred in the committed studies. M22 reports the zero rather than
  manufacturing a failure to fill the category.
- Cancellation uses the existing desktop operation executor: cancellation is
  requested inside the operation before the guarded commit point, the recorded state
  is `cancelled`, and `committed_state_entries` is 0. No partial model is committed.
- Classification boundary (after the M23 B2 correction): rejected input is raised as
  `ERT2DError` / `ERT3DError` / `VESError`, while a failure inside the forward model
  or the solver update is raised as the dedicated `ERT2DNumericalError` /
  `ERT3DNumericalError` / `VESNumericalError`, so the two are separated by class and
  by the recorded `failure_phase` rather than by message text. M22 additionally records
  `error_class` and treats `numpy.linalg.LinAlgError` as a numerical failure even
  though it subclasses `ValueError`. A numerical failure raised as a bare `ValueError`
  by a future library version would still be recorded as `INVALID_INPUT`; no such case
  is reachable in the committed studies.

## 7. Determinism and provenance

- The full report is reproducible: two independent `run_m22_qualification()` calls in
  one environment produce the same records, studies, coverage, manifests, and
  `report_sha256`, and the same byte-identical artifacts.
- `report_sha256` covers the complete report payload; each record and study manifest
  carries its own `manifest_sha256` over the M19 deterministic manifest contract with
  `procedure_version = m22-inversion-hardening-v2`.
- Artifacts are written with `newline="\n"` so artifact bytes do not depend on the
  platform newline convention.
- No timestamps, wall-clock values, or random seeds are recorded, so nothing varies
  between runs.

## 8. Metric definitions

M22 reuses the M21 metrics and adds none. Each metric's meaning, inputs, and
limitations are recorded in the report's `metric_definitions` block: `rmse`,
`relative_rmse`, `max_absolute_difference`, `log10_rmse`, `model_l2_difference`, and
`model_relative_l2_difference`. Model metrics are defined on **log10** parameter
vectors, the space the engines fit. After the M23 B3 correction they are produced only
when the two models additionally share a **discretization identity** — the same mesh
geometry, cell locations, cell parameter identity/order, and (where relevant) cell
volumes. A matching vector length alone is no longer sufficient; when the
discretizations differ the metric is omitted with a recorded
`model_comparison_omission_reason` instead of being computed on unrelated vectors.

## 9. Unavailable evidence

| Domain | Evidence | Status | Reason |
|---|---|---|---|
| VES | damping study | `UNAVAILABLE` | the VES engine exposes no damping control |
| VES | mesh/domain study | `UNAVAILABLE` | a 1D layered model has no mesh to refine |
| VES | per-evaluation trajectory | `HISTORY_UNAVAILABLE` | scipy exposes no per-evaluation objective series |
| 2D / 3D ERT | line-search and Jacobian evaluation sequence | `PARTIAL` | only step objective(s) and the returned-model evaluation are exposed |
| all | uncertainty, resolution, uniqueness | `UNAVAILABLE` | not implemented; out of M22 scope |
| all | external reference or field agreement | `NOT_VALIDATED` | no authorized independent dataset with a trustworthy reference result |

## 10. Unvalidated claims

- A lower residual, a decreasing trajectory, or a nominal convergence criterion does
  not establish a more accurate geological model.
- Stable, repeatable results do not establish field accuracy or instrument validity.
- Reproducibility does not establish correctness or external agreement.
- Bounded completion at a configured limit is not evidence of an implementation
  defect.
- No RES2DINV, commercial-solver, or published-dataset equivalence is claimed.
- No uncertainty, resolution, or inversion-uniqueness result is provided.

## 11. External benchmark status

`NOT VALIDATED`.

No legally usable independent dataset with a trustworthy expected result exists in
the repository, and M22 neither acquired nor fabricated reference results to change
this status. The external gate requires licensed dataset bytes, known acquisition and
geometry metadata, a source hash and provenance, a trustworthy reference result, and
a frozen preprocessing/mesh/inversion/stopping/metric/tolerance protocol.

## 12. Scope boundaries preserved

- No new inversion algorithm, optimizer, automatic damping selection, automatic model
  selection, uncertainty/resolution algorithm, topography-aware inversion, advanced
  3D inversion, IP inversion, GPU path, geological classification, or AI conclusion.
- No ABEM importer, undocumented vendor mapping, LS2 communication, acquisition, VNC,
  or instrument control. `importer_ready = false` is unchanged, and no M22 change
  touches an ABEM/Barugo or LS2 path, so the recorded Barugo sample source hashes
  could not be affected by this milestone. Note that the `ERT Survey Data/` and
  `VES Survey Data/` fixture bytes are not present in every working tree, so the
  hashes cannot always be re-verified locally; see
  [`m23_forward_physics_correction.md`](m23_forward_physics_correction.md).
- No database or schema change. Qualification evidence remains outside project state.
- M15 physical LS2 validation remains pending.

## 13. Summary of what changed

| Area | Change |
|---|---|
| `nix_ert/qualification/m22.py` | new contract, classification, runners, 13 studies, report artifacts (new file) |
| `nix_ert/ert/inversion3d.py` | 3D history/flag now describe the returned model; `ERT3D_CONVERGENCE_RMS` exposed |
| `nix_ert/ert/inversion2d.py`, `nix_ert/ves/engine.py` | result semantics documented (no behaviour change) |
| `nix_ert/qualification/__init__.py`, `m21.py` | export the M22 entry points and `environment_snapshot` |
| `tools/generate_m22_qualification.py` | deterministic artifact generator (new file) |
| `tests/test_m22_hardening.py` | 33 M22 tests, including regression coverage for the corrected defect (new file) |
| `docs/m21_scientific_qualification.*` | corrected 3D `final_objective` plus a `corrections` record |
| `docs/qualification.md`, `ROADMAP.md`, `changelog.md` | M22 status, evidence, and limits |

No scientific algorithm, numerical method, database schema, or persisted-state
semantics changed.
