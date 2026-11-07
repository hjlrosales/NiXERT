# M23 — Forward-Physics Correction and Qualification Integrity

**Procedure:** `m23-forward-physics-correction-v1`
**Status:** COMPLETE — every assigned finding is closed with evidence or explicitly
classified as evidence-blocked
**External benchmark status:** `NOT VALIDATED` (unchanged; no reference evidence acquired)
**Independently validated?** `NOT_VALIDATED`
**`importer_ready`:** `false`

M23 corrects the demonstrated mathematical and software defects identified by the
independent scientific audit (A1–A5) and the qualification-integrity defects
(B1–B4). The existing inversion optimizers are preserved: no optimizer, objective
function, damping schedule, or stopping rule was replaced.

The milestone was then closed by a second increment that corrected the two
remaining open code defects found by the post-M23 independent audit — the
`rms_percent` overflow and the incorrect classification/failure-phase reporting
of forward-factorization failures — both of which fall inside M23's scope. No
qualification artifact changed, and nothing was superseded (see sections C5, C6,
E and F).

---

## A. Defects confirmed

| ID | Subject | Evidence | Classification |
|---|---|---|---|
| A1 | Layered VES forward kernel integrated `J0(lambda*r) / r` instead of `J0(lambda*r)`, mis-scaling every layered response | Independent two-layer image/reflection series reproduces the audit value 78.76163158480 while the pre-correction kernel returned 91.78282027 (16.5% high) for `rho1 = 100`, `rho2 = 10`, `h = 8 m`, `AB/2 = 10 m`, `MN/2 = 1 m` | **CLOSED** |
| A2 | 3D nonuniform-mesh assembly used `dx[ix if nx > ix else nx]`, i.e. the cell's **own** width twice whenever the neighbour index was larger | On `x = (0,1,3,6,10)`, `y = (0,1,3)`, `z = (0,1,3)` with heterogeneous resistivity, `max abs(A - A^T) = 1.6369` pre-correction | **CLOSED** |
| A3 | Unequal-width face transmissibility used a harmonic mean of conductivities with an arithmetic mean of widths | Two cells, widths `1` and `2`, resistivities `1` and `4`, unit face area: assembled conductance `0.2666667` versus the exact series-resistance value `0.2222222` | **CLOSED** |
| A4 | Imported electrode geometry was not bound to the scientific calculation: the mesh was reconstructed from survey-level `electrode_spacing` metadata that the most recent import overwrites, so one source could silently move another source's electrodes; topography and off-line geometry were flattened; stale-result detection carried no geometry identity | Demonstrated: survey metadata is overwritten by the latest import (regression test asserts `7.0` after importing a 7 m source), and `Mesh2D.from_electrodes` was fed a spacing derived from that metadata | **CLOSED** |
| A5 | Advertised RES2DINV-compatible DAT support with no defined supported subset and no vendor fixtures | No authentic RES2DINV or Terrameter LS2 export exists in the repository; the parser accepted files whose header order it had no evidence for | **CLOSED** (dialect definition + rejection behaviour) / **EVIDENCE-BLOCKED** (vendor conformance) |
| B1 | Qualification admission accepted `VALIDATED` from structurally valid cross-references alone | A comparison could be recorded as `VALIDATED` against an internal synthetic dataset with no reference result, no tolerance justification, and no complete metric set | **CLOSED** |
| B2 | Invalid solver controls were accepted and misclassified: `convergence_rms = inf` made every 2D run "converged" on its first evaluation, `NaN` silently disabled convergence, and a forward-model numerical failure was indistinguishable from invalid input | Reproduced through the public `invert_ert` API; the pre-correction engine returned `converged=True` for `convergence_rms=math.inf` | **CLOSED** |
| B3 | The model-comparison metric required only a matching vector length | Two meshes with the same cell count but different cell edges (different domain, cell centres and volumes) were treated as a shared parameter space | **CLOSED** |
| B4 | A malformed or non-numeric first VES row could be interpreted as a header, silently discarding the observation | `parse_ves("BAD 1 2\n...")` and `parse_ves("nan 1 2\n...")` | **CLOSED** |
| C1 | `rms_percent` overflowed to `inf` for representable percentages: the metric squares each relative residual, so an accepted finite initial model of `1e160`–`1e300` (or a VES sounding whose apparent resistivities are ~`1e-190`) reported `inf` with `RuntimeWarning: overflow encountered in square` while `rms_log10` stayed finite | Pre-correction `invert_ert(..., 1e160).rms_percent` and `invert_ert(..., 1e300).rms_percent` were `inf`; the corrected values are `2.1579671983284469e+161` and `2.1579671983287294e+301` against 60-digit independent references at relative errors `4.6e-14` and `8.6e-14` | **CLOSED** |
| C2 | A forward-factorization failure was misclassified and mis-phased: scipy's SuperLU binding reports an exactly singular matrix as a bare `RuntimeError`, which escaped the numpy-only forward-model boundary and was recorded as `FAILED` in the `solver_update` phase although no model update was attempted | `invert_ert(..., 1e-308)` and `invert_ert3d(..., 1e-308)` reproduced `RuntimeError: Factor is exactly singular`; the qualification record now reads `FAILED` / `forward_factorization` / `numerical_failure = true` / `invalid_input = false` for both engines | **CLOSED** |

## B. Defects disproved

None. Every A1–A5/B1–B4 finding was reproduced. The audit's independent
two-layer reference value (`78.76163158`) was re-derived from the classical
image/reflection series and **confirmed**; the audit's reported pre-correction
values (`91.78282027`, `0.2666667`, non-symmetric 3D assembly) were reproduced
exactly.

## C. Mathematical corrections made

### C1 — Layered-earth Hankel kernel (A1, `nix_ert/ves/engine.py`)

For a point source on a layered earth the surface potential is

```
V(r) = (I / 2π) ∫₀^∞ T(λ) J0(λ r) dλ
```

and the four-electrode Schlumberger response uses
`K = π (AB/2² − MN/2²) / (2 MN/2)`. Because `T(λ) → ρ₁` as `λ → ∞`, the integral is
split into an exact homogeneous term plus a decaying correction:

```
dV/I = (1/2π) [ ρ₁ (1/AM − 1/AN − 1/BM + 1/BN)
              + ∫₀^∞ (T(λ) − ρ₁) (J0(λ·AM) − J0(λ·AN) − J0(λ·BM) + J0(λ·BN)) dλ ]
```

The identity `∫₀^∞ J0(λ r) dλ = 1/r` belongs to the **homogeneous** term. The
pre-correction code carried that `1/r` factor inside the correction integrand,
which mis-scaled every layered response. The `1/r` factor was removed from the
correction and the formulation, units and the identity are now documented in
`layered_apparent_resistivity`.

The correction integral was additionally replaced with a deterministic certified
scheme: the integration range is cut where `T(λ) − ρ₁` has decayed, covered by
panels half an oscillation period wide, each integrated with a fixed 8-point
Gauss–Legendre rule, with the node count checked against
`VES_QUADRATURE_NODE_BUDGET` **before** integrating. A model whose response
cannot be certified inside that budget raises `VESNumericalError`
(a numerical failure) instead of returning a silently wrong value or a scipy
`IntegrationWarning`. `certified_thickness_lower_bound` converts the node budget
into the shallowest interface depth the engine certifies, and `invert_ves`
bounds the search domain by it, replacing the previous arbitrary `1e-4 m` floor.
The optimizer, the objective, and the convergence criteria are unchanged.

**Measured accuracy:** against the independent image series, typical relative
error is `1e-13`; over a 525-case two-layer sweep (contrasts `0.01x`–`100x`,
thicknesses `0.5`–`500 m`, `AB/2` `10`–`500 m`) the worst case is `2.1e-10`.

**Measured consequence for the M22 evidence.** Correcting the kernel changed what
the M22 VES studies measure, and the affected M22 readings are withdrawn rather
than restated:

* the fixture's three-layer structure is now resolved by the data — from the
documented baseline initial model `(80, 30, 180) Ω·m / (4, 10) m` the fit reaches
`(109.93, 20.97, 268.43) Ω·m / (4.716, 13.055) m` against the generating model
`(100, 20, 250) Ω·m / (5, 12) m` at `2.64 %` response RMS, and a two-layer model
now fits markedly worse (`0.0727` versus `0.0115`, response RMSE `8.37`) instead
of being response-equivalent;
* the 20-evaluation baseline now satisfies the engine criterion at 13
evaluations, so the earlier reading of it as a truncation is withdrawn;
* the two three-layer starting models converge to the same response **and** the
same model (log10 model L2 `7.2e-06` and `3.1e-06`), so the earlier “response
stable, model unstable” observation is withdrawn.

These are numerical observations on one small synthetic sounding. They are **not**
a uniqueness, resolution, or geological result, and they do not establish that the
generating model is recoverable in general. The M22 evidence text was updated
accordingly (see the correction notice in
[`m22_scientific_hardening.md`](m22_scientific_hardening.md)).

### C2 — Face transmissibility (A2/A3, 2D and 3D)

Two adjacent cells are resistors in series between their centres: half of each
cell width belongs to each side, with its own conductivity. The exact
transmissibility is

```
G = A / ( w_self / (2 σ_self) + w_neighbour / (2 σ_neighbour) )
```

which reduces to `A · harmonic(σ) / w` only for equal widths. The previous
harmonic-mean/arithmetic-mean form overestimated every unequal-width face
(0.2666667 versus 0.2222222 for the audit case). `face_conductance` is now the
single implementation used by both the 2D and the 3D assemblies, which also
guarantees that the 3D off-diagonal entries are symmetric by construction.

### C3 — 3D assembly neighbour widths (A2, `nix_ert/ert/inversion3d.py`)

The neighbour width was selected with `dx[ix if nx > ix else nx]`, which returns
the **cell's own** width whenever the neighbour index is larger. The 3D assembly
now passes `(self_width, neighbour_width, shared_face_area)` per axis, and the
resulting matrix is symmetric and row-sum-conservative.

### C4 — 1D/2D/3D numerical-failure classes (B2)

`VESNumericalError`, `ERT2DNumericalError`, and `ERT3DNumericalError` were added
so that an accepted configuration that fails while computing the response or the
solver update is a **numerical failure**, never `INVALID_INPUT`. Solver controls
are validated: `convergence_rms`, `damping` and `jacobian_step` must be finite
and positive, and `max_iterations` positive.

### C5 — Representable percentage RMS (C1, `nix_ert/core/numerics.py`)

The reported percentage RMS is

```
100 * sqrt(mean(((predicted / observed) - 1) ** 2))
```

Evaluated directly it squares each relative residual, so the result overflows to
`inf` once one relative residual exceeds `sqrt(float_max) ~ 1.34e154` — even when
the exact percentage is perfectly representable. Resistance, apparent
resistivity, and initial-model inputs are validated only as finite and positive,
so that range is reachable through the public APIs.

The quantity is now computed by one shared helper. Everything in the range where
the conventional expression cannot overflow — every
`|predicted_i / observed_i - 1|` at most `sqrt(float_max / n) / 2` — is still
evaluated by exactly that expression, so ordinary and historical results stay
**bit-identical**. Outside that range the same quantity is evaluated from scaled
residual magnitudes:

```
r_i = |predicted_i / observed_i - 1|,        s = max_i r_i
100 * sqrt(mean(r_i ** 2))  =  100 * s * sqrt(mean((r_i / s) ** 2))
```

Every `r_i / s` lies in `[0, 1]`, so no squared term can overflow, and each
residual keeps its own magnitude: a minute residual contributes its true
`(r_i / s) ** 2` share rather than being annihilated by another residual's
scale. The residual magnitudes are formed directly — a division that underflows
to zero yields exactly the correct residual `1`, and one that overflows to `inf`
marks a magnitude beyond double precision, in which case alone a log10 form is
used because the scale itself is then unrepresentable.

**Mixed magnitudes (final closure).** An earlier revision of this helper scaled
by the largest `log10` ratio instead of the largest residual magnitude. For
`[1e160, 1e-200] / [1.0, 1e200]` the minute ratio carried an exponent of about
`-400`, so the shared factor underflowed to zero *and* the dominant term
`(10 ** (160 - 400)) ** 2 = 1e-480` underflowed with it: the mean came out
exactly zero and `log10(0)` raised `ValueError: math domain error` for a finite,
float-representable percentage. Scaling by the largest residual magnitude
removes that failure mode.

Accuracy against a 60-digit independent decimal evaluation of the same
definition is `1.1e-16` for the audit's mixed-magnitude case, `1.5e-16` for the
public `1e160` case, `6.2e-17` for the `1e300` case, and `1.7e-16` for the VES
case. Representability is reported honestly and three cases are distinguished:

* a finite, representable result is returned;
* a mathematically finite result beyond `float_max` is returned as `inf` — no
  finite substitute is invented, and `rms_log10` remains usable in that regime;
* invalid input (non-finite, zero, negative, empty, or mismatched sequences)
  raises `ValueError` instead of silently producing `nan`.

`rms_log10`, the objective, the convergence criteria, and the optimizer are
unchanged. The defect was reachable in both the 2D ERT and the VES engines, and
both now use the helper.

### C6 — Forward-factorization failure boundary and phase (C2)

The forward-model boundary previously caught only `numpy.linalg.LinAlgError`,
but SuperLU reports an exactly singular matrix as a bare `RuntimeError`. The
boundary now wraps **only** the `factorized()` calls of the 2D and 3D engines and
converts `(LinAlgError, RuntimeError)` there into the engine's dedicated
numerical error, carrying an explicit failure phase. Two tests pin the boundary
in both directions: a `RuntimeError` from the factorization is converted, and a
`RuntimeError` raised by mesh/matrix assembly is not relabelled. No unrelated
`RuntimeError` is globally reclassified.

`ERT2DNumericalError` and `ERT3DNumericalError` now carry a `phase` attribute from
a shared vocabulary, and the qualification contract records it directly:

| Phase | Meaning |
|---|---|
| `forward_factorization` | the accepted forward system could not be factorized |
| `forward_model_evaluation` | any other forward-model numerical failure |
| `solver_update` | a regularized model-update numerical failure |
| `input_validation` | invalid input rejected before evaluation |

The original cause is preserved on `__cause__` for diagnostics, while the
reported message stays the documented generic text and exposes no unstable
binding detail. `FAILED` records now admit `forward_factorization`, so the
qualification layer labels the phase from the exception rather than from message
text.

## D. Tests added

`tests/test_m23_forward_physics_correction.py` — **83 tests, 99 subtests** across
eleven classes:

| Class | Covers |
|---|---|
| `VESLayeredKernelTests` | A1: audit case, five-case image-series agreement, homogeneous exactness, thick/thin layer limits, geometric scale invariance, certified-quadrature convergence and rejection |
| `InterfaceTransmissibilityTests` | A3: audit case versus exact series resistance, general series formula, cell-swap symmetry, equal-width harmonic limit, 2D x/z faces, 3D faces on all three axes |
| `NonuniformMeshAssemblyTests` | A2: symmetry, conservation, sign structure, reciprocity on a heterogeneous nonuniform fixture, homogeneous normalization |
| `GeometryBindingTests` | A4: per-source geometry storage, incompatible mixed-source rejection, topography rejection, off-line rejection, geometry-change commit guard |
| `DATDialectTests` | A5: dialect identity/units/array codes, malformed header/row rejection, row count, RES2DINV-style rejection, topography units |
| `QualificationAdmissionTests` | B1: synthetic-as-validation rejection, missing reference result/protocol/tolerance justification/metrics/convergence, unsupported status, recursive immutability |
| `SolverControlAndFailureTests` | B2: NaN/inf/negative/zero tolerances, invalid damping and iteration controls, real forward-model numerical failure, invalid configuration versus convergence, bounded runs |
| `ModelComparisonDiscretizationTests` | B3: discretization identity required, equal-cell-count/different-edges rejection, 3D and layered identities, missing-vector reporting |
| `VESInputParsingTests` | B4: non-numeric and non-finite first rows, row width, location reporting, no silent discarding, supported header, extra columns |
| `PercentRMSTests` | C1: ordinary-scale equivalence with the conventional expression, `1e160` and `1e300` through the public 2D API, a `1e-190`-scaled VES sounding through the public VES API, no arithmetic-overflow warning, the representable/unrepresentable boundary, rejection of NaN, ±inf, zero, negative, empty, and mismatched input, and the bit-identical ordinary-range guarantee, and the final-closure mixed-magnitude cases (the audit's `[1e160, 1e-200] / [1.0, 1e200]`, a dominant-plus-minute pair, a huge/ordinary/minute triple, two distinct large magnitudes, and the public `invert_ert` case with a `1e-60` initial model against alternating `1e-230` / `1e308` observations) |
| `ForwardFactorizationFailureTests` | C2: `1e-308` initial models through the public 2D and 3D APIs, both qualification records, the failure-phase vocabulary, the narrow conversion boundary in both directions, preserved cause, and the absence of implementation-specific detail in the reported message |

The expected values are independently derived: the layered reference is the
classical two-layer image series, and the transmissibility reference is the
analytic series resistance between two cell centres. Where a test must check the
*assembly* it recomputes the expected conductance from the mesh edges and the
model rather than reading it back from the assembled matrix.

The closure tests derive their references independently of the implementation:
the expected percentage is computed at 60 significant decimal digits with
`decimal` from the same result vectors, and the *conventional* expression is used
only as the defect reference (it is asserted to be `inf` where it overflows).
Efficacy was verified by reverting each correction in place: the 2D revert fails
seven closure tests and the VES revert fails its own finite-percentage test. For
the final C1 closure the previous `_scaled_percent_rms` body was restored in
place and the new mixed-magnitude tests re-run: five fail against it (`ValueError:
math domain error`) and all 83 pass against the corrected helper. The regression
tolerance was not widened.

Existing tests updated rather than removed: `tests/test_m21_qualification.py` and
`tests/test_m22_hardening.py` now assert the corrected values and the B3
discretization rule.

## E. Existing artifacts invalidated / superseded

* **`docs/m22_scientific_hardening.json` (v1, `report_sha256 = df6847c8…67`)** —
  `SUPERSEDED`. The A1/A2/A3 corrections changed every VES objective/trajectory,
  and the B1–B4 corrections changed the recorded failure phases, admission rules,
  model-comparison discretization requirement, and VES input-failure behaviour.
  The v1 artifact is **not** overwritten silently: it is recorded in the v2
  report's `superseded_artifacts` block with its hash, its procedure version, the
  reason, and where the historical values are retained.
* **`docs/m21_scientific_qualification.json`** — the affected records were
  re-run and corrected **in place with a `corrections` block** that preserves each
  previous value:
  * `m21-ves-internal-v1` — `outcome` `TERMINATED` → `CONVERGED`,
    `final_objective` `0.0115804…` → `0.0115011…`, and its metric set (A1);
  * `m21-ert2d-internal-v1` / `m21-ert3d-internal-v1` — metric changes at
    floating-point rounding level only (`< 1e-13` / `< 1e-15`), because those
    fixtures use equal-width meshes where the old and new transmissibility are
    algebraically identical (A2/A3);
  * `provenance.last_corrected_by = m23-forward-physics-correction-v1`.

**Closure increment (C1/C2): no additional artifact was invalidated.** The two
corrections were checked against the committed evidence rather than assumed
harmless:

* `docs/m22_scientific_hardening.json` was regenerated and is **byte-identical**,
  with the unchanged `report_sha256 = c05d476c…52`; the Markdown report is
  byte-identical too. The direct-form branch of `percent_rms` is retained exactly
  where the conventional expression cannot overflow, which is why no recorded
  trajectory value moves.
* `docs/m21_scientific_qualification.json` was compared field by field against a
  fresh run: `outcome`, `initial_objective`, `final_objective`, the metric sets
  and the manifest hashes are identical for all three records. The curated M21
  record stores log-space objectives, comparison metrics and manifest hashes
  only — it records no `rms_percent` and no failure phase, so neither correction
  reaches it.

**Final C1 closure (mixed magnitudes): still no qualification artifact changed.**
The mixed-magnitude correction was re-checked the same way rather than assumed
harmless. `docs/m22_scientific_hardening.json` regenerates **byte-identically**
(`report_sha256 = c05d476c…52`, Markdown report identical too), because the
direct-form branch still covers every recorded trajectory value;
`docs/m21_scientific_qualification.json` stores no `rms_percent`; and
`docs/m19_release_qualification.json` records no percentage-RMS quantity. No
historical evidence was overwritten. The only superseded material is **inside the
closure evidence probe**: six `corrected_value` / `relative_error` fields and one
`boundary_rule` string in `docs/m23_evidence/probe_m23_closure.json` were measured
with the superseded algorithm. That file gains a `superseded_by` block naming
those fields, retains them exactly as measured, and points to the re-measurements
in `docs/m23_evidence/probe_m23_c1_mixed_magnitude.json`; nothing else in it is
affected.

Measurements: `docs/m23_evidence/probe_m23_closure.json` and
`docs/m23_evidence/probe_m23_c1_mixed_magnitude.json`.

## F. Artifacts regenerated

* `docs/m22_scientific_hardening.json` (v2, `report_sha256 = c05d476c…52`) and
  `docs/m22_scientific_hardening_report.md`, regenerated from the corrected
  engines via `python tools/generate_m22_qualification.py`; the report is
  byte-identical across repeated runs.
* `docs/m21_scientific_qualification.json` records re-measured against the
  corrected implementation (see E).
* New evidence notes: `docs/m23_evidence/probe_a2_a3_before.json` (audited
  pre-correction measurements) and
  `docs/m23_evidence/probe_a1_a2_a3_after.json` (post-correction re-measurement
  with the pre-correction values retained alongside).
* `docs/m23_evidence/probe_m23_closure.json` — measured C1/C2 closure evidence:
  pre-correction and corrected values, independent 60-digit references, the
  representability semantics, the failure-phase classification before and after,
  the boundary behaviour, the artifact-impact verification, and the revert
  efficacy check. Its percentage-RMS `corrected_value` / `relative_error` fields
  and its `boundary_rule` string are marked `PARTIALLY SUPERSEDED` by the block
  below; the measured values are retained.
* `docs/m23_evidence/probe_m23_c1_mixed_magnitude.json` — final C1 closure
  evidence: the mixed-magnitude reproduction and its pre-fix `ValueError`, the
  corrected algorithm and why tiny residuals can no longer erase dominant ones,
  fresh helper and public-`invert_ert` measurements with 60-digit references, the
  re-measured values that supersede the affected fields of the previous probe, the
  three representability conditions, the artifact-impact re-verification, and the
  regression efficacy check.

## G. Remaining evidence blockers

| Blocker | State | What is missing |
|---|---|---|
| A5 vendor DAT conformance | `EVIDENCE-BLOCKED` | Authentic RES2DINV / Terrameter LS2 export fixtures; the parser claims only the documented NiX dialect and no equivalence |
| External independent benchmark | `NOT VALIDATED` | The five evidence items E-1…E-5 in `docs/external_benchmark_gap_analysis.md`: licensed dataset bytes, acquisition/geometry metadata, source hash and provenance, trustworthy independent reference result, frozen protocol with defensible tolerances |
| M15 physical LS2 validation | `PENDING` | Official protocol documentation and validated device fixtures |
| ABEM/Barugo importer | `NOT_READY` | Vendor semantic evidence; `importer_ready = false` |
| Barugo source hash verification | `UNAVAILABLE ON THIS HOST` | The `ERT Survey Data/` and `VES Survey Data/` fixture bytes are not present in this working tree, so the recorded hashes cannot be re-verified here. No M23 change touches any ABEM/Barugo or LS2 path, so no fixture change is possible from this milestone. |

## H. Remaining external blockers

Same as G: the external benchmark gate, vendor DAT conformance, Barugo vendor
evidence, and M15 physical LS2 validation all require evidence that does not
exist in the repository. M23 did not fabricate dataset bytes, reference results,
vendor mappings, field measurements, or geological conclusions, and did not
change the external benchmark status.

## I. Milestone status

**M23: COMPLETE.**

* A1, A2, A3, A4 **CLOSED** — demonstrated, corrected, independently tested.
* A5 **CLOSED** for the supported-dialect and rejection behaviour;
  vendor conformance **EVIDENCE-BLOCKED**.
* B1, B2, B3, B4 **CLOSED** — demonstrated, corrected, negatively tested.
* C1, C2 **CLOSED** (closure increment) — demonstrated through the public APIs,
  corrected, and independently referenced; no artifact changed.
* C1 **CLOSED again for mixed magnitudes** (final closure) — the release-gate
  audit's `percent_rms([1e160, 1e-200], [1.0, 1e200])` `ValueError: math domain
  error` and the public `invert_ert` case (initial `1e-60`, observations
  alternating `1e-230` / `1e308`) both return values within `2e-16` of an
  independent 60-digit reference; no artifact changed.
* Affected qualification artifacts superseded / corrected with provenance (E, F).
* Supported domain documented (below).
* Full regression suite passes; M19/M20/M21/M22 remain valid.

### Closure status of the previously recorded open finding

The earlier draft of this report recorded the `rms_percent` overflow as
newly observed, out of scope, and `ROADMAP DECISION REQUIRED`. That classification
is withdrawn: the defect was in M23's scope, and it is now fixed (C5). The second
remaining open defect from the post-M23 audit — the misclassification and
mis-phasing of forward-factorization failures as `solver_update` — is fixed too
(C6). The reason the earlier draft gave for not patching it (a changed M22 report
hash) turned out not to apply once the direct expression was preserved for every
range in which it cannot overflow: the regenerated artifact is byte-identical.

### Classification summary

| Finding | Classification |
|---|---|
| A1, A2, A3, A4 | `CLOSED` |
| A5 supported dialect and rejection behaviour | `CLOSED` |
| A5 vendor DAT conformance | `EVIDENCE-BLOCKED` |
| B1, B2, B3, B4 | `CLOSED` |
| C1 percentage RMS numeric domain | `CLOSED` (overflow domain; re-closed for mixed magnitudes) |
| C2 forward-factorization classification and phase | `CLOSED` |
| External independent benchmark | `EVIDENCE-BLOCKED` (`NOT VALIDATED`) |
| ABEM/Barugo importer semantics | `EVIDENCE-BLOCKED` (`importer_ready = false`) |
| M15 physical LS2 validation | `EVIDENCE-BLOCKED` (`PENDING`) |
| 2D physical applicability / 2.5D behaviour | **documented scientific limitation and evidence requirement** — not converted into a 2.5D support claim |
| Optimizer redesign | `NOT APPLICABLE` — no demonstrated necessity, none introduced |

---

## Supported mathematical and workflow domain (post-M23)

* **VES (1D layered):** flat horizontal layers, Schlumberger geometry with
  `AB/2 > MN/2`, resistivities `1e-6`–`1e12` ohm-m, thicknesses at or above
  `certified_thickness_lower_bound(max distance)`, all values finite and
  positive. Responses are certified to `<= 2.1e-10` relative error against
  independent two-layer image solutions. Below-floor layers and uncertifiable
  transforms raise `VESNumericalError`.
* **2D ERT:** rectangular cell-centred finite-volume mesh, `nz >= 1`, `nx >= 2`,
  strictly increasing edges, depth edges starting at zero, top-row electrodes
  mapped by 1-based electrode number to column `n-1`, zero-flux boundaries,
  Lagrange-multiplier potential gauge. Face transmissibility is the exact
  two-point series resistance; the matrix is symmetric with zero interior row
  sums. No topography, no off-line electrodes, no IP, no anisotropy. The model is
  a 2D slice with a finite zero-flux domain and a numerical homogeneous
  normalization; how far its response is physically applicable to a real 3D
  half-space is **unvalidated**. That applicability is a **documented limitation
  and evidence requirement** (it needs an independent 2D-versus-3D response
  comparison), and it is **not** a claim of 2.5D support.
* **3D ERT:** rectangular cell-centred finite-volume mesh with the same
  discretization rules extended to `(z, y, x)` ordering, top-cell electrodes
  addressed by `(x, y)`, numerical homogeneous normalization, and the same exact
  series-resistance transmissibility on all three axes.
* **Imported geometry:** electrode geometry is bound per imported source as
  recorded at import time. Binding fails closed for mixed-source disagreement,
  incomplete electrode numbering, non-increasing coordinates, off-line (`y != 0`)
  positions, non-zero elevations (topography, which is **rejected rather than
  flattened**), and measurements referencing electrodes with no geometry. The
  bound geometry digest is persisted with the work package and re-checked before
  any result is committed, so a result computed from one geometry can never be
  committed against another.
* **DAT input:** the documented NiX dialect only (data count, spacing, array
  code, optional topography count/rows, then exactly `data count` measurement
  rows of `A B M N rho` or `index A B M N rho` plus up to three electrical
  columns). Electrode geometry follows `x = (n-1) * spacing`, `y = 0`, no
  elevation. Anything else — including a RES2DINV-style header — is rejected
  rather than guessed. **Vendor conformance and RES2DINV equivalence are not
  claimed.** Note that ROADMAP product goal 2 (“Support RES2DINV-compatible DAT
  files”) is therefore **not satisfied**: M23 resolved A5 as option A (an
  explicitly documented NiX dialect), because no authentic vendor export exists
  in the repository to define a vendor subset against. Satisfying that goal is a
  future, evidence-blocked increment, not a claim this milestone makes.
* **VES input:** whitespace/comma/semicolon separated, exactly three or four
  columns (`AB/2, MN/2, resistance[, apparent_resistivity]`), with one optional
  recognized header row. Any other first row is data, so a malformed row is an
  error with source and line number, never a header.
* **Reported metrics:** `rms_log10` (the objective) is finite wherever the
  residual is finite. `rms_percent` is the mathematically exact
  `100 * sqrt(mean(((predicted / observed) - 1) ** 2))`; it is finite whenever
  that value is representable, is reported as `inf` only when the exact value
  exceeds the double range (where `rms_log10` must be reported instead), and
  rejects non-finite or non-positive input with `ValueError`. The evaluation is
  stable for arbitrarily mixed residual magnitudes — including ratios that
  underflow to zero and ratios that overflow — because it scales by the largest
  residual magnitude rather than by an extreme ratio exponent. Neither metric is
  a geological result.
* **Failure phases:** `input_validation`, `forward_factorization`,
  `forward_model_evaluation`, `solver_update`, and `not_applicable`. A forward
  system that cannot be factorized is `FAILED` / `forward_factorization`, never
  `INVALID_INPUT` and never `solver_update`.
* **Qualification records:** `VALIDATED` requires a licence-eligible independent
  dataset, a recorded reference result, measured values for every protocol
  metric, a recorded convergence outcome, and a written per-metric tolerance
  justification. Model-to-model metrics additionally require a shared
  discretization identity. Records are recursively read-only.
