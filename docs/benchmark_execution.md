# Benchmark admission and execution readiness (R-1 … R-4)

**Gate:** external independent reference comparison (`m21-external-reference-gate`,
`m22-external-reference-gate`)
**Gate status after this increment:** **`NOT VALIDATED` — unchanged**
**Module:** `nix_ert.qualification.benchmark`
**Tests:** `tests/test_benchmark_execution.py`

This increment delivers the four *engineering* readiness gaps recorded in
[`external_benchmark_gap_analysis.md`](external_benchmark_gap_analysis.md) §5. It
does **not** supply evidence, does **not** bundle or download a dataset, and
does **not** change any qualification status or artifact.

## What was missing and what now exists

| Gap | Before | Now |
|---|---|---|
| **R-1** no execution path | The registry/protocol/comparison contracts existed but nothing executed a frozen protocol | `run_benchmark` executes one frozen protocol against one prepared case over the existing, unmodified `invert_ves`, `invert_ert`, or `invert_ert3d`, and records a `BenchmarkComparison` |
| **R-2** comparison records not auditable | `BenchmarkComparison.create` stamped a UUID and a timestamp only | Every executed comparison carries `BenchmarkProvenance`: dataset SHA-256, canonical protocol digest before *and* after execution, input and discretization digests, the reference producer/provenance, the engine source digest, and an environment snapshot (Python, platform, machine, NumPy, SciPy, software version) |
| **R-3** no tolerance justification | Tolerances were stored per protocol with no rule for deriving them | Admission refuses a declared metric whose tolerance has no finite non-negative `max_absolute` or no written `justification`; execution refuses to record if the protocol digest changes between admission and recording |
| **R-4** no automated dataset admission | Eligibility was a registration-time property only | `admit_benchmark_candidate` refuses internal-only data, unpermitted data, missing acquisition/geometry metadata, missing/unreadable bytes, an unrecorded or mismatched source digest, an absent reference result, a self-produced reference result, missing reference semantics, unsupported metrics, unsupported domains, and missing or contradictory frozen parameters |

## Admission rules (fail-closed)

A candidate is admitted only when **every** check below passes. Any single
finding refuses the candidate; there is no partial or conditional admission.

**Dataset** (`QualificationDataset`)

- `independent_benchmark_eligible`: classification is not `internal synthetic`
  **and** `license_status = permission confirmed`;
- `data_path` names a readable local file;
- `acquisition_information["sha256"]` records the file's SHA-256 and matches the
  bytes on disk — this is the documented intake location for the source hash;
- `acquisition_information` is non-empty, `electrode_configuration` is stated,
  `electrode_spacing` is set, and `coordinate_context` states the coordinate/CRS
  context.

**Reference result** (`BenchmarkProtocol.expected_reference_result`)

- non-empty;
- `producer` is present and does not name NiX ERT (a self-produced reference is
  refused);
- `provenance` states the reference's own origin and settings;
- `semantics` states `model_space`, `resistivity_unit`, and `depth_convention`;
- `response` lists finite positive reference values in observation order.

**Tolerances** — for every declared metric: a finite non-negative
`acceptable_tolerance[metric]["max_absolute"]` and a non-empty
`acceptable_tolerance[metric]["justification"]`.

**Frozen parameters** (`inversion_parameters`) — `domain` must be one of `VES`,
`2D ERT`, `3D ERT`, and every parameter that domain requires must be present and
valid. No engine default is ever substituted:

| Domain | Required parameters |
|---|---|
| `VES` | `max_nfev`, `initial_resistivities`, `initial_thicknesses` |
| `2D ERT` | `max_iterations`, `damping`, `jacobian_step`, `convergence_rms`, and exactly one of `initial_resistivity` / `initial_model` |
| `3D ERT` | `max_iterations`, `damping`, `initial_resistivity` |

A key present in both `stopping_criteria` and `inversion_parameters` must have
the same value, so the recorded stopping rule cannot contradict the executed
one.

## Execution rules

- The runner calls the public engine function exactly as documented. It does not
  add parameters, change a solver, or wrap an engine in new mathematics. The
  only pre-run check on the case is that the protocol's domain matches the case
  domain and that the reference response length equals the number of **active**
  observations.
- Every outcome is recorded: `CONVERGED`, `TERMINATED`, `FAILED`, and
  `INVALID_INPUT` all produce a comparison. A run that produces no response is
  recorded as `NOT VALIDATED` with empty metrics and a note naming the
  convergence outcome, so a failure can never be hidden by omission.
- The status is **computed from the frozen rule**, not chosen: `VALIDATED` only
  when every declared metric is measured *and* inside its frozen absolute bound;
  otherwise `NOT VALIDATED`. `QUALITATIVELY CONSISTENT` is not produced here
  because a numeric reference response is required for a measurable comparison.
- Metrics are the existing deterministic `comparison_metrics` values restricted
  to the protocol's declared metrics. No model-space metric is computed, because
  that requires a shared discretization identity (M23 B3).
- The protocol digest is recomputed after execution; a change aborts the record,
  so a tolerance cannot be adjusted while a result is being produced.

## Scope boundary

This is instrumentation, not evidence. It establishes that *if* licensed bytes
and an independent reference result are supplied in the documented registry
manifest, they can be admitted, executed without engine modification, and
recorded with auditable provenance. It does not establish:

- field accuracy, geological correctness, or RES2DINV equivalence;
- uncertainty, resolution, or uniqueness;
- production-scale performance;
- any status for the external gate, which remains `NOT VALIDATED` because no
  admissible dataset exists in the repository.

The supplied Barugo files are still not benchmark-eligible (they are an ABEM
project database without an independent reference result), the ABEM → NiX
importer remains `NOT_READY`, and M15 physical LS2 validation remains pending.

## Headless CLI

`tools/run_external_benchmark.py` (logic in
`nix_ert.qualification.benchmark_cli`) runs the same admission and execution path
without the desktop application.

```bash
# Admission only: never executes and never writes
python tools/run_external_benchmark.py --manifest registry.json --admit-only

# Admit, execute, and record into the manifest it read
python tools/run_external_benchmark.py --manifest registry.json \
    --case candidate-protocol=VES.json --json result.json

# Build a 2D case directly from a NiX dialect DAT file (no hand-written JSON)
python tools/run_external_benchmark.py --manifest registry.json \
    --case-from-dat ert-protocol=line.dat --emit-case ert-protocol=case.json

# Build a VES case directly from a text/CSV sounding (no hand-written JSON)
python tools/run_external_benchmark.py --manifest registry.json \
    --case-from-ves ves-protocol=sounding.csv --emit-case ves-protocol=case.json

# Select one protocol and record into a copy of the manifest
python tools/run_external_benchmark.py --manifest registry.json \
    --protocol candidate-protocol --case candidate-protocol=VES.json \
    --record-to recorded-registry.json
```

`--manifest` is required. `--protocol` (repeatable) selects protocols and
defaults to every registered protocol. `--case PROTOCOL_ID=PATH` supplies the
engine inputs and is required for every protocol that is actually executed; a
case file for an unselected protocol is a usage error rather than a silent
no-op. Recorded comparisons are written back to the manifest named by
`--record-to`, defaulting to the input manifest; `--admit-only` never writes, so a
refusal cannot modify the operator's evidence file.

### Case file format (`benchmark-case-v1`)

The manifest describes evidence; it does not carry engine inputs, because the
vendor dataset format is not part of any accepted contract. The operator
supplies the prepared engine inputs separately, bound to one protocol:

```json
{
  "protocol_id": "candidate-protocol",
  "domain": "VES",
  "case_format_version": "benchmark-case-v1",
  "points": [{"ab2": 10.0, "mn2": 2.0, "apparent_resistivity": 95.2}]
}
```

`2D ERT` cases carry `x_edges`, `depth_edges`, and `observations`; `3D ERT` cases
add `y_edges` and `electrodes`. Observations are
`{a, b, m, n, apparent_resistivity, excluded}`. Unknown fields, unknown format
versions, non-finite numbers, non-numeric strings, duplicate or unselected
protocol IDs, and a `protocol_id` that disagrees with the selected protocol are
all refused before execution. The runner additionally refuses a case whose domain
or active-observation count disagrees with the frozen protocol.

### Converting a NiX DAT file (`--case-from-dat`)

A 2D ERT case does not need a hand-written case file: `--case-from-dat
PROTOCOL_ID=DAT_PATH` builds it from the DAT dialect documented in
`docs/dat-import.md` (`nix_ert.qualification.dat_benchmark_case`). Electrode
geometry and quadrupole observations are read from the file;
`--emit-case PROTOCOL_ID=PATH` writes the derived `benchmark-case-v1` payload for
review before execution.

The converter refuses rather than guesses:

- the mesh resolution and depth come from the protocol's frozen
  `mesh_assumptions` (`nz` required, `depth` optional) — no engine or mesh default
  is supplied, and a manifest without `nz` cannot be converted;
- a dataset with topography, no electrodes, or a non-positive/non-finite
  apparent resistivity is refused, because flattening terrain, dropping, or
  including an invalid row would change which observations the reference response
  must match;
- malformed DAT input is rejected with the parser's own line-numbered reason.

The DAT's declared array name is reported for operator review by
`describe_dat_case` and is not treated as scientific evidence. A protocol may not
receive both a case file and a DAT conversion, and `--emit-case` for a protocol
without a conversion is a usage error.

### Converting a VES sounding (`--case-from-ves`)

A VES case does not need a hand-written case file either: `--case-from-ves
PROTOCOL_ID=VES_PATH` builds it from the text/CSV dialect documented in
`nix_ert.ves.data` (`nix_ert.qualification.ves_benchmark_case`). Each row supplies
`AB/2, MN/2, resistance[, apparent_resistivity]`; the Schlumberger half-spacings,
the measured resistance and the apparent resistivity are written to the payload for
every point. `--emit-case PROTOCOL_ID=PATH` writes the derived
`benchmark-case-v1` payload for review before execution.

The converter refuses rather than guesses:

- a supplied fourth-column apparent resistivity is carried through unchanged; it
  is never recomputed, and when the column is absent the value is derived from the
  measured resistance by the documented Schlumberger geometric factor;
- a row with invalid geometry (`AB/2 <= MN/2`), a non-positive resistance, a
  non-finite or non-positive apparent resistivity, or more than four columns is
  refused with the source name and line number, because dropping or repairing a
  row would change which observations the reference response must match;
- malformed input is rejected with the parser's own line-numbered reason.

The dialect records no exclusions, so every converted point is active; the
converter does not mark points excluded on the operator's behalf. A
`--case-from-ves` conversion is only accepted for a protocol whose frozen
`inversion_parameters.domain` is `VES`; a VES sounding cannot build a 2D or 3D
case. `describe_ves_case` reports the source, point counts, and spacing and
resistivity ranges for operator review, and states that this description is not
scientific evidence.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Every selected protocol was admitted (and, when executing, stayed inside its frozen tolerance) |
| `1` | The manifest, a case file, or case coverage is invalid, or an admitted protocol could not be executed; nothing was recorded for that protocol |
| `2` | At least one selected protocol was refused admission |
| `3` | Every selected protocol executed, but at least one stayed outside tolerance |

`--json PATH` writes the full machine-readable result (admission findings, run,
metrics, provenance, recorded comparison).

## Refusal codes

`protocol_not_registered`, `dataset_not_registered`, `dataset_not_independent`,
`dataset_bytes_missing`, `dataset_hash_unrecorded`, `dataset_hash_mismatch`,
`dataset_geometry_missing`, `reference_result_missing`,
`reference_provenance_missing`, `reference_produced_by_nix_ert`,
`reference_semantics_missing`, `reference_response_missing`, `tolerance_missing`,
`tolerance_justification_missing`, `metric_unsupported`, `domain_unsupported`,
`protocol_parameter_missing`, `protocol_parameter_invalid`,
`stopping_criteria_mismatch`.

## Re-verification

```bash
python -m pytest tests/test_benchmark_execution.py tests/test_benchmark_cli.py \
  tests/test_benchmark_manifest_audit.py tests/test_dat_benchmark_case.py -q
python -c "from nix_ert.qualification.registry import internal_qualification_registry as r; \
reg = r(); print(len(reg.protocols), len(reg.comparisons))"
```

## What admission cannot detect

Admission is a structural, fail-closed gate: it proves that the required
evidence is present, well-typed, internally consistent, and not produced by NiX
ERT. It cannot authenticate an operator's claim. A manifest that asserts a
licence, provenance, and reference values which were fabricated is structurally
admissible, and no code can decide otherwise without a signed vendor artifact,
which does not exist here. The negative-path audit
(`tests/test_benchmark_manifest_audit.py`) therefore proves that no finding can be
*bypassed* by crafting, re-spelling, duplicating, or padding other fields — not
that a dishonest operator can be detected.
