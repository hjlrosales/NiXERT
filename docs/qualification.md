# M18–M23 qualification

## M23 forward-physics correction and qualification integrity

M23 corrects the defects demonstrated by the independent scientific audit
(A1–A5) and the qualification-integrity defects (B1–B4). No optimizer replaced:
the objective functions, damping schedules and stopping rules are unchanged.

- **A1** — the layered VES kernel integrated `J0(lambda*r)/r` instead of
  `J0(lambda*r)`. The audit case (`rho1 = 100`, `rho2 = 10`, `h = 8 m`,
  `AB/2 = 10 m`, `MN/2 = 1 m`) returned `91.78282027` against the independently
  derived two-layer image-series value `78.76163158480`. The `1/r` factor now
  belongs only to the exact homogeneous term, and the correction integral uses a
  deterministic certified Gauss–Legendre scheme that raises `VESNumericalError`
  rather than returning an uncertifiable value. Typical agreement with the
  independent series is `1e-13`, worst case `2.1e-10` over a 525-case two-layer
  sweep.
- **A2** — the 3D nonuniform-mesh assembly used each cell's own width twice for
  the higher-index neighbour (`max |A - A^T| = 1.6369`).
- **A3** — unequal-width face conductance used a harmonic mean of conductivities
  with an arithmetic mean of widths (`0.2666667` instead of the exact
  series-resistance value `0.2222222`); 2D and 3D now share one exact two-point
  transmissibility.
- **A4** — imported geometry is bound per source instead of from the most recent
  import's survey-level spacing, fails closed on mixed-source disagreement,
  incomplete numbering, off-line positions and topography, and carries a
  geometry digest into stale-result detection.
- **A5** — the unvalidated RES2DINV compatibility claim is withdrawn in favour of
  an explicitly documented NiX DAT dialect that rejects anything else. Vendor
  conformance remains evidence-blocked.
- **B1** — qualification `VALIDATED` requires an independent licence-eligible
  dataset, a recorded reference result, measured values for every protocol
  metric, a convergence record, and a written per-metric tolerance
  justification; records are recursively read-only.
- **B2** — non-finite and non-positive solver tolerances are rejected, so
  `convergence_rms = inf` can no longer report convergence, and forward-model or
  solver numerical failures use dedicated error classes and a recorded failure
  phase instead of being classified as invalid input.
- **B3** — model-comparison metrics require a shared discretization identity and
  are omitted with a recorded reason otherwise.
- **B4** — malformed and non-finite first VES rows fail explicitly with source
  and line locations instead of being parsed as headers.
- **C1** (closure increment) — `rms_percent` overflowed to `inf` for
  representable percentages, because the metric squares each relative residual:
  an accepted finite initial model of `1e160`–`1e300` in the public 2D API, and a
  VES sounding at the `1e-190` scale in the public VES API, reported `inf` while
  `rms_log10` stayed finite. One shared helper now keeps the conventional
  expression wherever it cannot overflow (ordinary and recorded results are
  bit-identical) and otherwise evaluates scaled residual magnitudes; `inf` is
  returned only when the exact value exceeds the double range, and non-finite or
  non-positive input raises `ValueError`.
- **C1** (final closure) — the scaled branch of that helper selected the largest
  `log10` ratio rather than the largest residual magnitude, so a minute relative
  residual underflowed the shared factor *and* the dominant term together: this
  made `percent_rms([1e160, 1e-200], [1.0, 1e200])` raise
  `ValueError: math domain error` for a finite, representable percentage, and made
  the public `invert_ert` case (initial `1e-60` ohm-m, observations alternating
  between `1e-230` and `1e308`) unable to report its ~`7.07e171` value. The branch
  now forms the residual magnitudes directly, scales by the largest of them, and
  accumulates `(r_i / s) ** 2`, using a log10 form only when that scale itself
  overflows; both cases now agree with an independent 60-digit reference to
  ~`2e-16`.
- **C2** (closure increment) — a forward-factorization failure was recorded as
  `FAILED` in the `solver_update` phase although no model update was attempted,
  because scipy's SuperLU binding reports an exactly singular system as a bare
  `RuntimeError` that escaped the numpy-only boundary. The boundary now wraps only
  the factorization calls of both ERT engines and reports
  `forward_factorization`, preserving the original cause without exposing
  binding-specific detail.

Affected M21/M22 artifacts were re-run and corrected with provenance rather than
silently overwritten: the M21 JSON preserves every previous value in a
`corrections` block (`last_corrected_by = m23-forward-physics-correction-v1`) and
the superseded M22 v1 artifact and its hash are retained in the v2 report's
`superseded_artifacts` block. Evidence notes are in `docs/m23_evidence/`.
Regression coverage is `tests/test_m23_forward_physics_correction.py` (83 tests,
99 subtests) with independently derived expected values. The C1/C2 closure, and
the final mixed-magnitude C1 closure, changed **no** qualification artifact: the
M22 artifact still regenerates byte-identically (`report_sha256 = c05d476c…52`),
every curated M21 field is unchanged, and the M19 record stores no
percentage-RMS quantity, so nothing was superseded at the qualification level.
The only superseded material is inside the closure evidence probe: six
`corrected_value`/`relative_error` fields and one `boundary_rule` string of
`docs/m23_evidence/probe_m23_closure.json` were measured with the superseded
algorithm and are now marked `PARTIALLY SUPERSEDED` (retained in place, with a
`superseded_by` pointer) and re-measured in
`docs/m23_evidence/probe_m23_c1_mixed_magnitude.json`. The supported mathematical
and workflow domain is documented in
[`m23_forward_physics_correction.md`](m23_forward_physics_correction.md).

The external benchmark gate remains `NOT VALIDATED`, `importer_ready = false`,
and M15 physical LS2 validation remains pending. No database schema changed.

## M22 inversion robustness and scientific hardening

M22 adds `nix_ert.qualification.m22`, which instruments the existing VES, 2D ERT,
and 3D ERT engines with one common convergence/outcome contract
(`ConvergenceContract`) and expands the bounded deterministic studies to starting
models, damping, mesh/domain resolution, stopping limits, and deterministic noise
for every engine that exposes the corresponding control.

Normalized outcomes are `CONVERGED`, `TERMINATED`, `FAILED`, `INVALID_INPUT`, and
`CANCELLED`. Solver completion alone is never reported as convergence, reaching a
configured limit is never reported as a failure, and an unavailable per-evaluation
objective history is recorded as `HISTORY_UNAVAILABLE` rather than invented. The
VES engine exposes no per-evaluation objective series, so its records carry no
trajectory; the 2D and 3D engines expose step objectives and the returned-model
evaluation.

M22 demonstrated and corrected one concrete reporting defect: the 3D ERT engine
returned an objective history and convergence flag that described the pre-update
model instead of the returned model, so the recorded final objective wrongly
equalled the initial objective and hid a measured objective reduction. The
correction changes reporting only - no model, predicted response, update, or
damping schedule changed - and the affected M21 record was re-run and corrected.
Regression coverage is in `tests/test_m22_hardening.py`.

Measured M22 findings on the internal synthetic fixtures only: the VES response
stabilizes between 20 and 40 allowed evaluations while the model parameters still
move, and a two-layer model fits the three-layer fixture as well as the three-layer
model; the 2D objective decreases monotonically with additional iterations while the
distance from the baseline model does not; every 3D case is bounded completion
because the configured tolerance is unreachable on that fixture, whose two clean
observations are a reciprocal pair and therefore supply one independent value for 16
model cells. These are numerical and non-uniqueness observations, not solver defects
and not geological claims.

Outcome coverage across the committed M22 evidence (v2) is `CONVERGED` 9,
`TERMINATED` 27, `FAILED` 0, `INVALID_INPUT` 3, and `CANCELLED` 1. No numerical failure occurred
in the committed bounded studies, so the `FAILED` category is implemented and
regression-tested but reported as zero rather than manufactured.

The checked-in artifacts are:

- [`m22_scientific_hardening.md`](m22_scientific_hardening.md)
- [`m22_scientific_hardening.json`](m22_scientific_hardening.json)
- [`m22_scientific_hardening_report.md`](m22_scientific_hardening_report.md)

They are regenerated deterministically with
`python tools/generate_m22_qualification.py`. The current run
(`m22-inversion-hardening-v2`, regenerated after the M23 corrections) has
`report_sha256 =
c05d476c0cf74f5569756ae6466bb5b544829cea809df1ac9e6dc48c5547cf52`.
The superseded v1 run
(`report_sha256 =
df6847c8073f86bda8e6e8d6aef178780972795307ba5b4c95efd17c0be37367`) is retained
as a `SUPERSEDED` entry in the report's `superseded_artifacts` block rather than
being silently overwritten.

Internal M22 evidence is `QUALITATIVELY CONSISTENT`; the external benchmark gate
remains `NOT VALIDATED`. M22 itself changed no inversion algorithm, solver
mathematics, database schema, ABEM importer, or LS2 behavior; the later M23
correction did change the VES forward kernel and the 2D/3D face transmissibility
(see the M23 section above), and the affected M21/M22 numbers were re-run and
recorded with provenance. `importer_ready = false` still holds.

## M21 scientific qualification and benchmark readiness

M21 adds a separate evidence layer in `nix_ert.qualification.m21` that reuses
existing scientific engines and M19 manifests. It records explicit convergence
outcomes (`CONVERGED`, `TERMINATED`, `FAILED`, `INVALID_INPUT`, `CANCELLED`,
and `NOT_VALIDATED`), deterministic response/model comparison metrics,
controlled sensitivity studies, and machine-readable/human-readable results.

The current M21 result is **QUALITATIVELY CONSISTENT** for the internal
synthetic VES, 2D ERT, and 3D ERT cases. This means the configured runs and
sensitivity studies are reproducible numerical evidence; it is not independent
field validation or geological qualification. The external benchmark gate is
**NOT VALIDATED** because no legally usable independent dataset with a
trustworthy reference result is available in the repository.

The checked-in artifacts are:

- [`m21_scientific_qualification.md`](m21_scientific_qualification.md)
- [`m21_scientific_qualification.json`](m21_scientific_qualification.json)

M21 measured 2D sensitivity to starting resistivity, mesh depth resolution,
damping, stopping iterations, and deterministic multiplicative noise, plus VES
starting-model sensitivity. Differences are reported as numerical response
metrics only; no arbitrary pass/fail threshold or geological accuracy metric
was introduced.

No scientific engine, ABEM importer, database schema, or LS2 behavior changed.

One M21 field, the 3D `final_objective`, was later corrected by M22 after a
demonstrated 3D reporting defect; the M21 manifest hashes, comparison metrics,
sensitivity studies, and VES/2D records are unchanged. See the M22 section above
and the `corrections` block in the M21 JSON.


## M20 desktop workflow qualification

M20 is complete for the supported offline desktop workflow. The PySide6 shell
now exposes the existing ERT and VES workflow services, project-bound reports,
advisory Assistant, and fail-closed LS2 diagnostics. The acceptance matrix is in
`docs/m20_desktop_qualification.md`.

This is workflow qualification, not independent scientific or field
qualification. The numerical engines remain bounded baselines; no production-
grade geological, RES2DINV-equivalence, uncertainty, topography-aware, or
physical LS2 claim is made.

## M18 field qualification and production-workflow hardening

## Dataset framework

`nix_ert.qualification.registry` provides metadata-only records for:

- internal synthetic;
- published/reference;
- field;
- commercial/reference; and
- user-supplied datasets.

A record captures source, license/permission status, acquisition information,
electrode configuration and spacing, coordinate/topography context, expected
reference result, known limitations, purpose, and an optional local data path.
The registry validates cross-references and round-trips JSON manifests. It does
not download or bundle external data. Internal synthetic data cannot be marked
as an independent benchmark, and external data with unknown permission status
cannot be presented as eligible.

The repository currently contains no external, published, commercial, or field
bytes. The internal registry therefore remains qualification metadata only and
makes no independent benchmark claim.

## Benchmark protocol

`BenchmarkProtocol` freezes the dataset, preprocessing rules, QC rules,
inversion parameters, mesh assumptions, stopping criteria, expected/reference
result, comparison metrics, tolerances, and known differences. A
`BenchmarkComparison` records successful and unsuccessful outcomes using one of
`VALIDATED`, `QUALITATIVELY CONSISTENT`, or `NOT VALIDATED`, together with
metrics, convergence details, and explanatory notes.

Recording a status is gated on evidence, not on cross-references. Since M23,
`QualificationRegistry` enforces what each status requires: `VALIDATED` needs a
licence-eligible independent dataset, a recorded reference result, measured
values for every protocol metric, a convergence record, and a written
`justification` for every declared metric tolerance. `QUALITATIVELY CONSISTENT`
needs complete metrics and a convergence record but no independent dataset.
`NOT VALIDATED` stays recorded without metrics so unsuccessful and unexecuted
comparisons remain representable. Internal or unpermitted datasets can never
define an independent reference result, and every mapping stored in a record is
recursively read-only so a later edit cannot invalidate a validated record.

No protocol in this repository has trustworthy external reference results yet. The
exact missing evidence, the acceptance criteria already encoded in
`nix_ert.qualification.registry`, and the ordered next actions for this gate are
recorded in
[`external_benchmark_gap_analysis.md`](external_benchmark_gap_analysis.md).

The admission and execution path now exists (`nix_ert.qualification.benchmark`):
a candidate is admitted only when it carries licensed bytes with a recorded
SHA-256, acquisition/geometry metadata, an independent reference result with its
own provenance and stated semantics, a written tolerance justification for every
declared metric, and complete frozen engine parameters. An executed comparison
records the dataset digest, the protocol digest before and after the run, the
executed input and discretization digests, the engine source digest, and the
environment snapshot, and its status is computed from the frozen tolerance rule
rather than chosen. Because no such dataset exists in the repository, admission
refuses every candidate and the gate stays `NOT VALIDATED`; see
[`benchmark_execution.md`](benchmark_execution.md).
The current scientific status is:

- **VALIDATED:** unit/reference checks and deterministic internal invariants
  already covered by the scientific test suite;
- **QUALITATIVELY CONSISTENT:** clean/noisy internal VES, 2D ERT, and 3D ERT
  behavior on small synthetic fixtures;
- **NOT VALIDATED:** independent field/reference comparisons, commercial-solver
  agreement, RES2DINV equivalence, and production-scale geological behavior.

Parameters must be fixed before a future comparison is run. Results must not be
used to tune preprocessing or inversion settings retroactively.

## Included qualification cases

The existing deterministic fixtures remain internal synthetic data:

- layered VES, clean and deterministic noisy variants;
- small 2D ERT anomaly, clean and deterministic noisy variants; and
- small 3D ERT anomaly, clean and deterministic noisy variants.

Noise exercises numerical robustness only; it is not a field-instrument noise
model. No reference result was fabricated to make an inversion pass.

## Workflow hardening evidence

The application uses a detached in-memory inversion input and a single guarded
persistence step. Cancellation is cooperative: a cancelled or failed operation
cannot write a partial model/version, and commit rechecks the selected survey,
source hashes, and active source-scoped measurement keys. The prior valid model
therefore remains intact.

The headless lifecycle test covers create → import → process → invert → close →
reopen → source-aware measurement inspection → model inspection → report.
Reports reject missing or modified managed sources and paths outside the
project's managed `raw` directory.

Measurement inspection exposes source ID, row, A/B/M/N configuration, resistance,
apparent resistivity, status, exclusion note, and QC reasons. Model inspection
exposes version identity, cell count, resistivity range, iterations, RMS,
convergence, and the documented depth/topography/interpretation semantics.

## Barugo sample-data inspection

The local user-provided files were inspected in SQLite read-only mode on
2026-09-14 and were not copied, migrated, imported, or modified:

- **BARUGO SAMPLE DATA — REAL USER-PROVIDED DATA — ERT:**
  `ERT Survey Data/Project7/project.db`; ABEM project schema 4/common schema 3;
  task `Gradient_1`; 401 `DP_MEASURE` links; 6,007 `DPV` rows; 401 explicit
  geometry rows; 37 unique electrode positions; 401 named `ρapp` rows; X-only
  coordinates; instrument software `2.2.5b(3179)` and transmitter software
  `3.7.2` recorded in the file.
- **BARUGO SAMPLE DATA — REAL USER-PROVIDED DATA — VES:**
  `VES Survey Data/Project8/project.db`; ABEM project schema 4/common schema 3;
  task `VES Schlumberger_1`; 25 `DP_MEASURE` links; 450 `DPV` rows; 25
  explicit geometry rows; 40 unique electrode positions; 25 named `ρapp` rows;
  X-only coordinates; the same recorded instrument/transmitter software
  versions.

The files are valid SQLite databases (`integrity_check=ok`) but are **not
compatible with `ProjectStore`**. They do not contain NiX
`schema_info/project_metadata/surveys/imported_sources/measurements` tables;
the ABEM `DP_MEASURE`/`DPV` linkage and coordinate semantics require a
separately specified import contract. The VES points also have no direct
persistence representation in the current NiX project schema. The ERT task's
vendor array code/protocol semantics are not silently mapped to a NiX DAT array
name. Consequently no conversion was attempted and no NiX inversion,
visualization, report, or Assistant context was created from these files.

`nix_ert.data.abem_sample.inspect_abem_project` and the desktop **Inspect
Barugo ERT/VES Sample** actions expose stored metadata, counts, coordinate
ranges, named values, software metadata, file size, and SHA-256 provenance
without changing source bytes. The displayed apparent-resistivity ranges are
raw stored vendor values, including the Barugo ERT negative-to-positive range;
NiX did not recalculate or reinterpret them. The inspector is not an LS2
connection and the sample is not live acquisition data.

## Barugo semantic analysis and import-contract status

`docs/barugo_import_contract.md` records the versioned draft contract
`abem-project-db-to-nix-v0.1-draft`. It is based on a read-only table/column
inventory, logical relationship checks, coordinate inspection, datatype/unit
inspection, and independent arithmetic checks against the supplied files.

The strongest established result is internal electrical consistency: for all
401 ERT and 25 VES linked observations, the stored primary `ρapp` equals
`R × K` using the general four-electrode half-space factor and the observed
coordinate spacing. Maximum absolute differences were `1.46e-11 Ωm` (ERT) and
`2.84e-14 Ωm` (VES), with maximum relative differences below `3e-16`. For
228 ERT and 25 VES rows where the corresponding channel-14 current is present,
`ΔU / I` also equals the selected resistance to the available floating-point
precision. This is an internal consistency result, not an independent
benchmark, instrument validation, inversion validation, or geological result.

The proposed contract keeps ERT and VES separate. It permits only provenance,
raw-value preservation, linked-row identity, and conditionally validated
geometry/electrical candidates. It does not decode vendor array/protocol codes,
status bitmasks, channel semantics, electrode numbering, coordinate units, CRS,
`FocusZ`, or VES persistence semantics. The future importer must fail closed on
those unresolved items and must preserve all unmapped DPV/status/auxiliary
records rather than silently discard them.

Accordingly, no importer has been implemented. The next implementation step is
to obtain an authorized ABEM schema/protocol reference and then build a
read-only, versioned intermediate parser/validator against copied fixtures
before adding any user-approved `ProjectStore` persistence adapter.

The maximum compatible Barugo workflow remains read-only inspection. NiX's
existing internal synthetic fixtures remain the fallback for DAT import, QC,
inversion, plots, reports, and Assistant workflow tests until a
licensed/authorized conversion specification or compatible export is supplied.

External data acquisition and permission verification are still blocked on
appropriate datasets and fixtures. Large/stress performance cases are declared
by the performance harness but are not claimed measured until representative
field-scale input is available. Native allocations are not captured by
`tracemalloc`; full profiling remains future work.

## M19 reproducibility and release qualification

M19 adds a deterministic qualification-manifest and release-result contract in
`nix_ert.qualification.release`. Manifests preserve software/procedure version,
dataset identity and SHA-256 when available, project/survey identity, processing
and model/version parameters, configuration metadata, and expected outputs.
Canonical JSON and manifest hashes provide machine-readable reproducibility;
human-readable results are recorded in:

- [`m19_release_qualification.md`](m19_release_qualification.md)
- [`m19_release_qualification.json`](m19_release_qualification.json)

The supported offline DAT workflow was exercised through project creation,
import, QC, processing, one-iteration 2D inversion, model/version selection,
HTML report, and repeated structured report comparison. Source hashes, model
provenance, stale-state detection, cancellation safety, invalid-input
rejection, close/reopen lifecycle, and managed-source path rejection passed.

Measured on the recorded Windows/Python environment, the small workflow baseline
was 0.005806 s import, 0.000575 s QC, 0.002614 s processing, 0.228566 s one-
iteration 2D inversion, and 0.005072 s HTML report generation. These are
observations rather than arbitrary performance thresholds. A small VES inversion
with 20 evaluations measured 14.911569 s and is the most expensive recorded
small fixture operation. Medium, large, and stress-scale cases remain
unmeasured; native allocations remain outside `tracemalloc`.

M19 status is **QUALIFIED_FOR_SUPPORTED_OFFLINE_WORKFLOW**, not production-grade
geological qualification. Independent field/reference comparisons, commercial
solver agreement, RES2DINV equivalence, geological certainty, Barugo importer
semantics, and physical LS2 validation remain unvalidated or blocked.
