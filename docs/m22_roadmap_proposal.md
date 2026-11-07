# M22 Post-M21 Evidence-Based Roadmap Assessment

**Assessment date:** 2026-09-15  
**Assessment only:** M22 is not implemented.  
**Recommendation confidence:** High for direction; medium for exact solver-hardening scope until a broader convergence study is frozen.

## 1. Current state

M19 established:

`QUALIFIED_FOR_SUPPORTED_OFFLINE_WORKFLOW`

M20 completed the supported offline desktop workflow. M21 added deterministic
qualification manifests, explicit outcome states, numerical comparison metrics,
controlled sensitivity studies, failure/cancellation records, and an external
benchmark gate.

Current status remains:

- `importer_ready = false`;
- M15 physical LS2 validation is pending;
- external independent benchmark status is `NOT VALIDATED`;
- internal VES/2D/3D evidence is `QUALITATIVELY CONSISTENT`.

## 2. What M21 actually demonstrates

### VES

The internal VES case completed with a finite result but was classified
`TERMINATED` because `max_nfev=20` was reached. The final log10 objective was
approximately `0.0115804`. The qualification layer currently records only a
single objective value for VES because the existing engine exposes final
function-evaluation count and result status, not a per-evaluation objective
history.

This demonstrates finite, repeatable bounded fitting for the selected synthetic
case. It does not demonstrate convergence robustness, uniqueness, or field
validity.

### 2D ERT

The one-iteration internal case was classified `TERMINATED`, with objective
reduction from approximately `0.172645` to `0.0260411`. Starting-model,
mesh-depth, damping, stopping-limit, and deterministic-noise cases were
reproducible and produced finite outputs.

The results demonstrate measurable configuration sensitivity. They do not show
which configuration is scientifically preferable, and they do not establish
geological accuracy. The current qualification history records the pre-update
objective per iteration; a comparable full objective trajectory is not yet
available for every step.

### 3D ERT

The one-iteration internal case was classified `TERMINATED`, with objective
approximately `0.202134` before and after the configured run. This is useful
failure-to-converge/limited-run evidence, not convergence evidence. The current
3D qualification path does not yet have the richer per-iteration result record
available in the 2D result type.

### Sensitivity

The strongest measured sensitivity was to starting model and damping in the
small 2D fixture. Mesh-depth and stopping-limit changes also altered numerical
outputs. VES starting-model sensitivity was measured. These differences are
numerical stability/dependence observations only; they do not imply that lower
sensitivity or lower residual means a more accurate geological model.

### Reproducibility and failure behavior

Repeated M21 reports and sensitivity studies are deterministic in the tested
environment. Invalid input is retained as `INVALID_INPUT`; cancellation is
represented as `CANCELLED`; external evidence remains `NOT VALIDATED`.

## 3. Limitation classification

| Limitation | Classification | Evidence |
|---|---|---|
| All recorded M21 domain runs terminate at configured limits | **KNOWN LIMITATION** | VES max evaluations, 2D one iteration, and 3D one iteration are recorded as `TERMINATED`. |
| Full objective history is not comparable across VES/2D/3D | **KNOWN LIMITATION** | Existing result structures expose different levels of iteration detail. |
| Starting-model dependence | **KNOWN LIMITATION** | Measured 2D and VES sensitivity differences. |
| Damping dependence | **KNOWN LIMITATION** | Measured 2D sensitivity differences. |
| Mesh/domain dependence | **KNOWN LIMITATION** | Measured 2D depth-resolution differences; only small flat meshes were studied. |
| Deterministic-noise response | **KNOWN LIMITATION** | One bounded deterministic noise case was measured; it is not a field-noise model. |
| Inversion robustness over realistic cases | **UNMEASURED** | Current studies are small and bounded. |
| Medium/large/stress performance | **UNMEASURED** | No representative workloads are qualified. |
| Uncertainty/resolution | **KNOWN LIMITATION** | Not implemented or calculated. |
| Topography-aware inversion | **KNOWN LIMITATION** | Flat finite meshes are used. |
| Independent/reference agreement | **BLOCKED BY EXTERNAL EVIDENCE** | No authorized reference dataset and trustworthy expected result are available. |
| Barugo interoperability | **BLOCKED BY EXTERNAL EVIDENCE** | `importer_ready = false`; vendor semantics and VES persistence evidence remain unresolved. |
| LS2 physical integration | **BLOCKED BY EXTERNAL EVIDENCE** | Hardware and authoritative protocol/API evidence remain unavailable. |

## 4. Candidate M22 directions

| Rank | Candidate | Scientific value | Engineering value | Current evidence | Dependency/risk | Scope | Decision |
|---:|---|---|---|---|---|---|---|
| 1 | Inversion robustness / scientific hardening | Very high | High | M21 directly shows termination and starting/damping dependence | Medium risk; must avoid silently changing solver behavior | Instrument convergence, broaden bounded studies, preserve failed outcomes, fix only demonstrated defects | **Recommend now** |
| 2 | External benchmark qualification | Very high | High | Benchmark registry and gate exist, but no eligible data | Blocked by licensed data/reference result | Execute only if evidence arrives; otherwise readiness preparation only | Defer execution |
| 3 | Uncertainty/resolution evidence | Very high | High | M21 explicitly has no such calculation | High scientific/design risk; requires a defensible method and validation | Needs a separate methodology before implementation | Defer |
| 4 | Performance / large dataset qualification | Medium/high | High | Small measurements and scale vocabulary exist | Representative medium/large inputs and native-memory tooling absent | Measure workloads before optimization | Defer or parallel evidence collection |
| 5 | Engineering reporting / deliverables | Medium | High | Reports are traceable but figure-rich output is incomplete | Low/medium; risk of stale figure/model mismatch | Improve exports after scientific result contracts are clearer | Defer behind robustness |
| 6 | Topography-aware inversion | Very high eventual value | High eventual value | Flat-domain limitation is known, but no requirement/validation plan is frozen | High algorithmic and validation risk | New mesh/forward/inversion qualification | Defer |
| 7 | Barugo/ABEM interoperability | High eventual value | High eventual value | Intermediate parser and evidence package exist; readiness unchanged | Vendor evidence blocker | No safe implementation scope currently | Blocked |
| 8 | LS2 physical integration | High eventual value | High eventual value | Fail-closed mocks only | Hardware/protocol blocker | No safe implementation scope currently | Blocked |

## 5. Recommended M22

### M22 — Inversion Robustness and Scientific Hardening

Address the concrete evidence weakness revealed by M21: the current qualification
runs are finite and reproducible but mostly terminate at deliberately small
limits, and the three engines expose unequal convergence evidence.

M22 should improve the qualification and result contracts first. It should not
replace the inversion algorithms merely because sensitivity exists.

## 6. Proposed scope

1. Freeze broader but still bounded convergence protocols for VES, 2D, and 3D,
   including multiple stopping limits and documented starting models.
2. Record comparable initial, per-step, and final objectives wherever the
   existing engines can provide them without changing mathematical behavior.
3. Explicitly distinguish solver completion, convergence, termination, numerical
   failure, invalid input, and cancellation in all qualification artifacts.
4. Repeat starting-model, damping, mesh, stopping, and deterministic-noise
   studies with enough controlled cases to characterize observed dependence,
   without declaring an arbitrary preferred configuration.
5. Add reproducible unsuccessful/non-convergent cases and verify that they remain
   useful evidence rather than disappearing from reports.
6. Investigate only concrete defects identified by the expanded evidence. Any
   solver correction must be minimal and regression-tested; no algorithm
   replacement is part of the milestone by default.
7. Maintain explicit domain metrics and report numerical stability separately
   from model truth, reference agreement, and geological validity.
8. Keep external benchmark execution gated at `NOT VALIDATED` unless authorized
   data and trustworthy reference results arrive.

## 7. Explicit non-goals

- No new inversion algorithm or commercial-solver emulation.
- No uncertainty/resolution implementation.
- No topography-aware inversion.
- No advanced 3D inversion, IP, GPU, or speculative optimization.
- No ABEM importer or undocumented vendor mappings.
- No LS2 communication, VNC, acquisition, or instrument control.
- No geological classification, field accuracy, geological certainty, or
  RES2DINV equivalence claim.
- No database schema change unless a separately justified persistence defect is
  demonstrated; qualification evidence should remain outside project state.

## 8. Prerequisites

- Existing M21 manifests, fixtures, and deterministic seeds.
- Fixed solver configurations and documented stopping criteria.
- A reproducible environment record.
- Optional external benchmark data only if licensing, provenance, reference
  semantics, and expected results are independently established.

## 9. Qualification evidence for M22

M22 should be accepted only when:

- repeated convergence studies produce equivalent structured records;
- VES, 2D, and 3D outcomes use the same explicit state vocabulary;
- per-step objective histories are either recorded or explicitly marked
  unavailable, never invented;
- starting-model, damping, mesh, stopping, and noise dependence is measured;
- unsuccessful, invalid, and cancelled cases are preserved;
- any solver defect fix has a specific reproducer and regression test;
- no configuration is called scientifically superior solely because it lowers a
  residual;
- external comparison remains `NOT VALIDATED` when evidence is absent;
- all existing tests and scientific limitations remain intact.

## 10. Final recommendation

Proceed with **M22 — Inversion Robustness and Scientific Hardening**. M21 has
already provided the evidence needed to prioritize this direction: the next
highest-value improvement is better convergence/robustness evidence around the
existing baselines, not a new scientific feature or blocked integration.
