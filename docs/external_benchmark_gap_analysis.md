# External benchmark gate — qualification gap analysis

**Gate:** independent external reference comparison for the VES / 2D ERT / 3D ERT engines
**Gate identifiers:** `m21-external-reference-gate`, `m22-external-reference-gate`
**Status:** `NOT VALIDATED` (unchanged)
**Verdict of this analysis:** **evidence-blocked — not code-completable to completion with existing evidence**
**Analysis type:** read-only. No implementation, no data acquisition, no artifact regeneration, no status change.

This document is the required output for an evidence-blocked milestone: it records the
exact missing evidence, the acceptance criteria, and what must happen next. It does
**not** change any qualification result and does **not** mark the gate complete.

## 1. Why this gate is the next unfinished milestone/gate

The repository's remaining open items, taken from `ROADMAP.md`, the M22 proposal
ranking, and the checked-in qualification artifacts:

| # | Open item | Recorded status | Dependency | Why it is not the next target |
|---|---|---|---|---|
| — | Inversion robustness / scientific hardening | `COMPLETE` (M22) | — | Already delivered |
| 1 | **External independent reference comparison** | **`NOT VALIDATED`** | Licensed/authorized dataset + trustworthy reference result | **Not satisfiable from the repository alone → this analysis** |
| 2 | Uncertainty / resolution | Not implemented | A defensible method and its own validation plan | Requires a new roadmap decision plus a separate methodology; implementing it now would expand the roadmap |
| 3 | Medium/large/stress performance qualification | Unmeasured | Representative field-scale inputs and native-memory tooling | Blocked by the same class of missing external input as #1; no representative workload exists |
| 4 | Engineering reporting / deliverables | Deferred "behind robustness" | None (code-completable) | Code-completable, but the M22 proposal ranked it below the scientific and performance candidates and deferred it behind robustness; it improves deliverables rather than evidence |
| 5 | Topography-aware inversion | Not implemented | New mesh/forward/inversion qualification and a validation plan | New scientific capability, not a blocked gate; needs a separate approved milestone |
| 6 | ABEM/Barugo → NiX importer | `NOT READY` (`importer_ready = false`) | Authoritative ABEM schema/protocol evidence + authorized conformance fixtures | Blocked; see §7 |
| 7 | M15 Terrameter LS2 physical validation | `PENDING` / blocked | Official protocol/API documentation, legal authorization, device fixture | Blocked; see §7 |

**Nomination.** The next unfinished gate is the **external independent reference
comparison (benchmark) gate**, because:

1. It is the only remaining item that is *already contracted in code and artifacts* and
   whose "unfinished" state is recorded as a first-class gate status (`NOT VALIDATED`)
   in both `docs/m21_scientific_qualification.json` and
   `docs/m22_scientific_hardening.json`, and repeated in every recent `ROADMAP.md`
   milestone entry.
2. The approved `docs/m22_roadmap_proposal.md` ranks it **#2 of 8** ("Very high"
   scientific value, "High" engineering value) — the highest-ranked remaining candidate
   after M22 itself, under the project's established pattern of acting on the
   top-ranked candidate in each milestone.
3. Its acceptance criteria are already encoded in the repository (§3), so a precise and
   verifiable gap analysis is possible without inventing anything.

**Verdict.** Evidence-blocked. The gate cannot be completed by writing or changing code
in this milestone: it requires licensed external bytes and a trustworthy independent
reference result that do not exist in the repository. Item #1 is therefore not marked
complete, and no status was changed.

## 2. Verified current state (read-only checks)

| Check | Method | Result |
|---|---|---|
| Registered qualification datasets | `internal_qualification_registry()` | 3 entries: `ves-layered-internal-v1`, `ert-2d-anomaly-internal-v1`, `ert-3d-anomaly-internal-v1` |
| Datasets eligible as an independent benchmark | `QualificationDataset.independent_benchmark_eligible` | **none** (all three are `internal synthetic` / `internal`) |
| Registered benchmark protocols | registry | **0** |
| Recorded benchmark comparisons | registry | **0** |
| External dataset bytes in the repository | filename scan for `.dat` / `.db` / `.sqlite*` / `.csv` / `.zip`, excluding caches | **none** (only the three generated qualification JSON artifacts exist) |
| External gate status, M21 artifact | `docs/m21_scientific_qualification.json` | `"status": "NOT VALIDATED"` |
| External gate status, M22 artifact | `docs/m22_scientific_hardening.json` | `"status": "NOT VALIDATED"` with the fixed required-evidence list |
| Benchmark execution path in application code | search of `nix_ert/` for `BenchmarkProtocol` / `BenchmarkComparison` / `ComparisonStatus` | **only used inside `nix_ert/qualification/registry.py`** — no runner is wired into the application (§5, readiness gap R-1) |
| ABEM/Barugo importer readiness | `qualify_abem(...)` on the offline fixture | `importer_readiness = NOT_READY`, `importer_ready = False` |
| M15 LS2 boundary | `tests/test_ls2.py`, `tests/test_ls2_connection.py`, `tests/test_ls2_discovery.py` | 19 fail-closed tests pass; unsupported transports remain the default; no acquisition or mutation method exists |

## 3. Acceptance criteria that already exist

These are the criteria the gate is judged against today. They are implemented, and no
part of this analysis relaxes them.

### 3.1 Dataset admissibility — `nix_ert/qualification/registry.py`

- `QualificationDataset.__post_init__` rejects an external dataset whose
  `license_status` is `unknown` or `not applicable`: **external permission must be explicit**.
- An `internal synthetic` dataset must use `license_status = internal`.
- `independent_benchmark_eligible` is true only when the classification is **not**
  `internal synthetic` **and** the license status is `permission confirmed`.
- `QualificationRegistry.add_protocol` refuses a protocol that defines a non-empty
  `expected_reference_result` against a dataset that is not
  `independent_benchmark_eligible`: *internal or unpermitted datasets cannot define
  independent reference results*.

### 3.2 Frozen comparison protocol — `BenchmarkProtocol`

A protocol must supply `protocol_id`, `dataset_id`, a non-empty `comparison_metrics`
tuple, and non-empty `stopping_criteria`; it also carries `preprocessing_rules`,
`qc_rules`, `inversion_parameters`, `mesh_assumptions`, `expected_reference_result`,
`acceptable_tolerance`, and `known_differences`. The documented rule
(`docs/qualification.md`) is that these are **fixed before the comparison is run** and
must not be used to tune preprocessing or inversion settings retroactively.

### 3.3 Comparison outcome recording — `BenchmarkComparison`

- Outcomes use exactly three statuses: `VALIDATED`, `QUALITATIVELY CONSISTENT`,
  `NOT VALIDATED`.
- Every comparison requires non-empty notes, and records metrics, convergence context,
  and a creation identifier/timestamp.
- Nothing in the code promotes a comparison to `VALIDATED`; the status is a recorded
  judgement, and unsuccessful outcomes must be recorded too.
- `QualificationRegistry.validate()` rechecks dataset/protocol/comparison references, and
  `from_json` rejects malformed manifests.

### 3.4 Required evidence recorded in the M21/M22 artifacts

Both artifacts require all of the following before any external comparison may be
labelled validated:

1. licensed / authorized dataset bytes;
2. known acquisition and geometry metadata;
3. source hash and provenance;
4. a trustworthy reference result;
5. a frozen preprocessing, mesh, inversion, stopping, metric, and tolerance protocol.

## 4. Exact missing evidence

| ID | Required evidence (from §3.4) | What exists today | What is exactly missing | Why it blocks | Acceptance criterion (evidence is accepted only if…) |
|---|---|---|---|---|---|
| E-1 | Licensed / authorized dataset bytes | Nothing. No external, published, field, commercial, or user-supplied ERT/VES dataset is bundled or referenced | The dataset files themselves, or a documented, permission-confirmed means to obtain them | Without bytes there is no input to compare; synthetic fixtures are explicitly ineligible | The bytes exist locally; the dataset registers with classification ≠ `internal synthetic` and `license_status = permission confirmed`; redistribution/licensing terms are recorded |
| E-2 | Known acquisition and geometry metadata | For internal fixtures only | Array/survey type, electrode configuration and spacing, coordinates/topography context, instrument and software versions, and any processing already applied to the reference data | Geometry cannot be assumed from the inversion parameters; mismatch invalidates any comparison | Metadata is stated for the exact dataset version and is consistent with the registered `electrode_configuration` / `electrode_spacing` / `coordinate_context` |
| E-3 | Source hash and provenance | Hashing utilities and the M19 manifest contract exist | The actual SHA-256 of the licensed bytes plus their origin, version, and permission note | Without a hash, a comparison cannot be tied to a specific dataset revision, and reproducibility cannot be checked | The registered `data_path` hashes to a recorded SHA-256 and the provenance statement names the origin and permission basis |
| E-4 | Trustworthy reference result | Nothing external. Internal fixtures have expected qualitative behaviour only, and `expected_reference_result` is empty | The independent expected output for the same dataset: e.g. a published reference model or section, a reference apparent-resistivity/response set, or a documented reference-solver result with its own settings | The gate compares against an independent result; internal targets cannot serve as the reference | The reference result is independently produced (not by NiX ERT), its own provenance/settings are recorded, and its semantics (model space, resistivity units, depth convention) are stated |
| E-5 | Frozen preprocessing, mesh, inversion, stopping, metric, and tolerance protocol | The entire contract exists (`BenchmarkProtocol`), but no protocol instance is registered and no tolerance rule has ever been set for a real dataset | A registered, hash-recorded protocol instance for the specific E-1/E-4 pair, including the metric list, tolerances, and known differences | Tolerances chosen after seeing results would make any agreement meaningless | The protocol is registered *before* execution with non-empty metrics and stopping criteria; the tolerance rationale is defensible independently of the observed result; known differences are documented up front |

**No fabricated substitute satisfies any row above.** Internal synthetic fixtures,
internal `ρapp = R × K` arithmetic consistency, a visually plausible plot, and
convenience conventions from unrelated software are all explicitly insufficient.

## 5. Readiness gaps (engineering, not evidence)

> **Delivered (2026-10-27, follow-up increment).** R-1 … R-4 are now implemented in
> `nix_ert.qualification.benchmark` with `tests/test_benchmark_execution.py`; see
> [`benchmark_execution.md`](benchmark_execution.md). The gate status is unchanged and
> still `NOT VALIDATED`, because admission refuses every candidate reachable from the
> repository: no licensed dataset bytes and no independent reference result exist. This
> section is retained as the gap record it was written as.

These are *capability* gaps discovered while verifying the gate. They are recorded here
because they determine what must be built **after** the evidence arrives; none of them
is implemented in this analysis, and none is a defect in previously delivered behaviour.

| ID | Gap | Verified state | What a future approved increment must do |
|---|---|---|---|
| R-1 | No benchmark execution path | **Delivered:** `run_benchmark` executes a frozen protocol over the unmodified engines and records a `BenchmarkComparison` | Add a runner that loads a registered dataset, executes the frozen protocol over the existing engines **without modifying them**, and records a `BenchmarkComparison` |
| R-2 | Comparison records are not byte-reproducible | **Delivered:** every executed comparison carries `BenchmarkProvenance` (dataset SHA-256, protocol digest before/after execution, input and discretization digests, reference provenance, engine source digest, environment snapshot) | Record, alongside the comparison: the dataset SHA-256, a canonical protocol hash, the environment snapshot, and the engine versions, so a comparison is auditable even though its identifier is not deterministic |
| R-3 | No tolerance-justification artifact | **Delivered:** admission requires a written `justification` per metric, and a protocol digest change during execution aborts the record | Require a written tolerance rationale per metric before execution, and reject any protocol whose tolerances were set after the run |
| R-4 | No automated admission test for a candidate dataset | **Delivered:** `admit_benchmark_candidate` refuses internal-only data, unpermitted data, missing geometry or source digest, missing reference provenance, self-produced references, and missing frozen parameters | Add an explicit, fail-closed admission check that refuses: internal-only data, unpermitted data, missing geometry, missing reference provenance, or a reference result produced by NiX ERT itself |

## 6. What must happen next

Ordered, with the dependency that must be satisfied first.

1. **External (user/vendor side): obtain evidence E-1 … E-4.** This is outside the
   repository and cannot be produced by code. If a dataset cannot be licensed for local
   use, the gate stays blocked; it must not be approximated.
2. **Register the dataset.** Add an entry with the classification, explicit
   `permission confirmed` license status, acquisition/geometry metadata, provenance,
   and the recorded SHA-256. Until this row is valid, protocols against it are refused
   by `add_protocol` when they carry a reference result.
3. **Freeze the protocol (E-5) before any run.** Register the protocol instance with
   metrics, stopping criteria, tolerances, known differences, and the written tolerance
   rationale, and record its canonical hash. No setting may change afterwards.
4. **Then, and only then, implement R-1 … R-4** as a separate, approved increment
   (benchmark *execution*), reusing the existing engines unchanged.
5. **Execute read-only and record every outcome**, including failures and partial
   agreement. Record `NOT VALIDATED` or `QUALITATIVELY CONSISTENT` when that is what the
   frozen tolerances show; never select a better-looking result after the fact.
6. **Re-run the relevant qualification studies** and re-issue the qualification artifacts
   if any registered engine behaviour is affected. (No engine behaviour is expected to
   change: the runner is instrumentation only.)
7. **Only then consider the gate's status.** Even a `VALIDATED` comparison is scoped to
   the frozen dataset + protocol pair. It would not establish field accuracy, geological
   correctness, uncertainty, resolution, or RES2DINV equivalence.

### 6.1 Intake manifest (exact schema accepted today)

Evidence can be supplied without code changes by writing a registry manifest in this
shape (all collections required by `QualificationRegistry.from_json`):

```json
{
  "datasets": [
    {
      "dataset_id": "<stable id>",
      "classification": "published/reference | field | commercial/reference | user-supplied",
      "source": "<origin of the dataset>",
      "license_status": "permission confirmed",
      "permission_note": "<licence/permission basis>",
      "acquisition_information": {},
      "electrode_configuration": "<array/survey type>",
      "electrode_spacing": 5.0,
      "coordinate_context": {},
      "expected_reference_result": {},
      "known_limitations": [],
      "qualification_purpose": "<why this dataset is being compared>",
      "data_path": "<local path to the licensed bytes>"
    }
  ],
  "protocols": [
    {
      "protocol_id": "<stable id>",
      "dataset_id": "<must match a dataset above>",
      "preprocessing_rules": [],
      "qc_rules": [],
      "inversion_parameters": {},
      "mesh_assumptions": {},
      "stopping_criteria": {"max_iterations": 0},
      "expected_reference_result": {},
      "comparison_metrics": ["rmse", "log10_rmse"],
      "acceptable_tolerance": {},
      "known_differences": []
    }
  ],
  "comparisons": []
}
```

Notes that the schema enforces:

- `classification: "internal synthetic"` requires `license_status: "internal"` and can
  never be `independent_benchmark_eligible`.
- Any external classification requires an explicit license status; `unknown` and
  `not applicable` are rejected.
- A protocol carrying a non-empty `expected_reference_result` is refused unless its
  dataset is `independent_benchmark_eligible`.
- `comparison_metrics` and `stopping_criteria` must be non-empty.

## 7. Adjacent blocked gates — verified read-only, unchanged, not selected

Both of the other open external gates were re-verified in this analysis and are
**unchanged**. Neither is the next target under the approved ranking (rank 7 and rank 8
of the M22 proposal, both recorded as "Blocked"), and neither has new evidence.

| Gate | Verified state | Exact missing evidence | Existing acceptance criteria and next action |
|---|---|---|---|
| ABEM/Barugo → NiX importer | `importer_ready = False`, `NOT_READY` | Authoritative ABEM semantics for array/protocol/mode codes, electrode numbering and switch mapping, coordinate units/axis/origin/CRS, channel/sequence/polarity, QC/status bits, uncertainty/stacking/ADC fields, VES persistence, auxiliary-row policy, supported-version matrix, and an approved ABEM→NiX target contract; plus authorized conformance fixtures with row-level expected outputs | Already specified item-by-item as `E-01 … E-15` in `docs/barugo_vendor_evidence_request.md`, with acceptance criteria in its §6, the minimum ERT/VES packages in its §4, and the readiness states in its §7. Next action: obtain and accept that package; then implement a read-only parser/validator before any persistence adapter |
| M15 Terrameter LS2 physical validation | `PENDING`; fail-closed transports remain the default; 19 LS2 tests pass | Official protocol/interface documentation or a vendor-supported read-only SDK; legal/technical authorization; exact supported OS/driver/transport/authentication/compatibility details; a representative device/export fixture; validation evidence including malformed and unsupported responses | Already specified as the five "Required inputs to unblock M15" in `docs/ls2.md`. Next action: obtain those inputs; until then no USB/serial/network/VNC/command path may be enabled |

No Barugo source files are present in the repository, so their SHA-256 records cannot be
re-verified locally here; the qualification code's authorized-evidence allow-list still
contains exactly the two documented hashes
(`057674127c923842510ee5e8af6082fed88ef152438f3752ca681d5f2f6d47af` ERT,
`97eec29b3f9870092f9674e54b560df20f9df2130ac18778ff29161757d09e51` VES) and the
importer remains fail-closed regardless.

## 8. Prohibited shortcuts

The gate must not be moved by any of the following, now or later:

- presenting an internal synthetic fixture as an independent reference;
- relaxing, re-deriving, or widening a tolerance after seeing results;
- substituting `QUALITATIVELY CONSISTENT` for `VALIDATED`, or vice versa, without the
  frozen protocol's rule;
- selecting the best-looking comparison after the fact;
- using a screenshot, a column name, an array code, or a numeric pattern as evidence;
- reusing conventions from unrelated software or third-party reverse engineering;
- treating network reachability, VNC access, or vendor software availability as a data
  or protocol contract;
- inferring geology, field accuracy, or RES2DINV equivalence from residual agreement;
- changing an inversion algorithm to make a comparison look better.

## 9. How to re-verify this analysis (read-only)

Each §2 row is reproducible without touching project state or external systems:

```bash
# Gate contents: datasets, eligibility, protocols, comparisons
python -c "from nix_ert.qualification.registry import internal_qualification_registry as r; \
reg = r(); print(list(reg.datasets)); \
print([d.dataset_id for d in reg.datasets.values() if d.independent_benchmark_eligible]); \
print(len(reg.protocols), len(reg.comparisons))"

# Recorded gate status in the checked-in artifacts
python -c "import json; print(json.load(open('docs/m22_scientific_hardening.json'))['external_benchmarks'][0]['status'])"

# No external dataset bytes in the repository
find . -type f \\( -name '*.dat' -o -name '*.db' -o -name '*.sqlite*' -o -name '*.csv' -o -name '*.zip' \\) \
  -not -path '*/__pycache__/*' -not -path './.pytest_cache/*'

# Benchmark contracts are not wired into application code
grep -rn 'BenchmarkProtocol\|BenchmarkComparison\|ComparisonStatus' nix_ert --include='*.py'

# Adjacent gates: importer readiness and LS2 fail-closed coverage
python -m pytest tests/test_m18_contracts.py tests/test_ls2.py tests/test_ls2_connection.py \
  tests/test_ls2_discovery.py tests/test_qualification.py -q
```

## 10. Status statement

- Gate status: **`NOT VALIDATED`** — unchanged by this analysis.
- Milestone status: **NOT COMPLETE** (evidence-blocked).
- Code, tests, datasets, engines, database schema, qualification artifacts, and M15 /
  Barugo readiness were **not** changed by this analysis.
- Next action: obtain evidence E-1 … E-4 externally (§6 steps 1–3). The execution
  path (§5, R-1 … R-4) now exists and refuses every candidate until that evidence is
  supplied; see [`benchmark_execution.md`](benchmark_execution.md).
