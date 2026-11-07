# M20 evidence-based roadmap assessment

**Assessment date:** 2026-09-15  
**Assessment only:** no M20 implementation was started.  
**Recommendation confidence:** High for the primary direction; medium for exact scope until a desktop acceptance pass is performed.

## 1. Current qualified baseline

M0–M19 are recorded complete. M19 established:

`QUALIFIED_FOR_SUPPORTED_OFFLINE_WORKFLOW`

The qualified baseline includes deterministic DAT import, non-destructive QC,
apparent-resistivity processing, bounded VES/2D/3D numerical services,
visualization data services, project/model versioning, provenance-aware
reporting, advisory local AI, cancellation guards, and reproducibility tests.

This qualification is limited to the tested offline workflow. It does not
establish production-grade geological inversion, field-scale performance,
independent benchmark agreement, RES2DINV equivalence, or LS2 communication.

## 2. Area-by-area readiness assessment

| Area | Status | Repository-grounded assessment |
|---|---|---|
| Desktop workflow / UX completeness | **PARTIALLY READY** | The PySide6 shell exposes project/import, QC, processing, 2D inversion, model inspection, report, Assistant, and LS2 status. The headless ERT workflow is stronger than the UI. VES processing and visualization services are not exposed as a complete desktop path, and 3D/model/report visualization is not a complete interactive UI workflow. |
| Scientific benchmark and validation | **PARTIALLY READY** | Unit/reference mathematics, deterministic internal VES/2D/3D fixtures, reproducibility, and bounded residual tests exist. No independent field/published/commercial benchmark or production-scale validation exists. |
| Barugo/ABEM interoperability | **BLOCKED BY EXTERNAL EVIDENCE** | The forensic document narrows some exact-file semantics using official manuals/XML, but the current qualification code has not incorporated that evidence and critical QC/status/uncertainty/VES persistence gates remain unresolved. `importer_ready = false`; no importer is justified. |
| Terrameter LS2 physical integration | **BLOCKED BY EXTERNAL EVIDENCE** | The repository has fail-closed abstractions and mocks only. No official public acquisition API/protocol, validated device fixture, or physical validation is available. |
| Reporting / engineering deliverables | **PARTIALLY READY** | Structured HTML/PDF reports include project, source, QC, model/version, and state provenance. Report generation is tested, but complete figure embedding/export and a polished deliverable workflow are not demonstrated as a full desktop acceptance path. |
| Performance / scalability | **PARTIALLY READY** | Small workflow and scientific baselines are measured. Medium, large, stress-scale, native-memory, and field-workload limits remain unmeasured. No optimization is justified without representative profiling. |
| Scientific limitations affecting production use | **NOT YET JUSTIFIED** | Independent validation, uncertainty/resolution analysis, topography-aware inversion, field-scale behavior, and geological interpretation limits prevent a production-grade scientific claim. |

## 3. Remaining material gaps

1. The desktop UI does not yet expose the complete set of already-existing
   offline services coherently, especially VES and 3D inspection paths.
2. Desktop acceptance is mostly startup/headless integration evidence rather than
   a repeatable user-facing acceptance matrix.
3. Reports are provenance-aware but are not yet demonstrated as complete
   figure-rich engineering deliverables for every supported workflow.
4. Larger representative performance cases are not measured.
5. Scientific qualification remains internally synthetic and does not establish
   field accuracy or geological certainty.
6. Barugo exact-file evidence has advanced, but current qualification code and
   persistence targets have not been revised; the importer remains blocked.

## 4. External blockers

- Authoritative ABEM definitions for remaining status/QC, uncertainty, and
  vendor-specific fields; an approved neutral/unassessed state or mapping; and
  an additive VES persistence contract are still required before importer work.
- LS2 hardware, official interface/API documentation, legal authorization, and
  validated read-only fixtures are still required before physical integration.
- Licensed independent/reference datasets and expected results are required for
  external benchmark claims.
- Representative field-scale datasets are required for meaningful scalability
  limits.

## 5. Candidate directions

| Candidate | Evidence now | Value now | Risk/dependency | Decision |
|---|---|---|---|---|
| A. Production desktop workflow / UX | Strong existing services and shell; visible gaps | High user value and practical readiness value | Low/medium if limited to integration; risk of duplicating scientific logic | **Primary recommendation** |
| B. Scientific benchmark expansion | Strong internal fixtures; no external bytes/reference results | High scientific value, but limited immediate independent evidence | Medium/high external-data dependency | Defer except for acceptance-matrix design |
| C. Barugo interoperability | Partial exact-file official evidence; critical gates remain open | High eventual user value | High; importer would require unresolved semantics/schema | Defer; do not guess |
| D. LS2 physical integration | Fail-closed architecture only | High eventual value | Very high; hardware/protocol unavailable | Defer |
| E. Reporting / engineering deliverables | Existing structured report/provenance foundation | Medium/high user value | Low if scoped to existing state and figures | Include as a supporting M20 workstream |
| F. Performance / scalability | Small measurements only | Potentially high | Requires real larger cases and profiling first | Defer optimization; add measurement hooks only if needed |

## 6. Recommended M20

### M20 — Supported Offline Desktop Workflow Completion

Complete the practical desktop workflow around the already-qualified offline
services, without changing scientific algorithms or importing unsupported vendor
semantics.

The target is:

```text
Create/Open Project
  → Import compatible data
  → Inspect/QC
  → Process
  → Invert or interpret supported VES/ERT data
  → Inspect 2D/3D outputs
  → Advisory interpretation/Assistant
  → Traceable report/export
```

### Why this is the highest-value next step

- It addresses the largest user-visible gap identified in the repository: the
  headless services are more complete than the desktop workflow.
- It can proceed entirely with existing compatible DAT and internal fixtures.
- It improves field usability and engineering readiness without pretending to
  improve scientific validity.
- It exercises existing boundaries rather than duplicating or replacing engines.
- It produces acceptance evidence that is useful whether or not ABEM/LS2
  evidence arrives later.
- It avoids speculative implementation of the two highest-risk blocked areas.

## 7. Proposed M20 scope

### In scope

1. Add explicit UI state for active project, survey type, source, QC state,
   processing/version state, selected model, interpretation status, and report
   provenance.
2. Expose existing VES import/processing/plot/inversion services through the
   desktop workflow where their current contracts support it.
3. Expose existing 2D model and 3D visualization inspection services through
   clear, labeled UI actions; retain depth/elevation and true-3D limitations.
4. Improve report/export workflow using current project/model state, including
   figures or structured figure artifacts only where existing services support
   them without stale-model risk.
5. Add a desktop acceptance matrix using internal fixtures and compatible DAT/
   VES inputs.
6. Preserve fail-closed errors, cancellation behavior, AI approval boundaries,
   raw immutability, and source/model provenance.

### Explicit non-goals

- No ABEM/Barugo importer or semantic qualification rewrite.
- No LS2 USB, serial, Wi-Fi, VNC, acquisition, or instrument-control code.
- No new inversion algorithm, topography-aware inversion, advanced 3D
  inversion, uncertainty/resolution analysis, IP inversion, or GPU work.
- No automatic geological classification or stronger AI claims.
- No production-scale performance claim or speculative optimization.
- No broad UI redesign or unrelated refactoring.
- No RES2DINV equivalence or production-grade geological claim.

## 8. Proposed qualification evidence

M20 should require a repeatable acceptance matrix for at least:

- project creation, open, close, and reopen;
- ERT DAT import → QC → processing → 2D inversion → model inspection → report;
- VES input/import → curve inspection → 1D inversion → interpretation/report,
  if the existing VES persistence contract permits the path;
- 2D model visualization and existing 3D visualization data inspection;
- Assistant read-only analysis against the active project context;
- cancellation, malformed input, stale model, missing source, and invalid
  transition behavior;
- LS2 panel default unsupported/disconnected behavior and explicit mock labeling;
- source hashes, version ownership, report state fingerprints, and raw-data
  immutability;
- report structured-data equivalence across repeated generation;
- screenshots or widget-state records only as UI evidence, never as scientific
  validation.

M20 acceptance should distinguish `tested`, `reproducible`, `measured`,
`unsupported`, `blocked`, and `not validated`. It should not introduce arbitrary
scientific pass/fail thresholds.

## 9. Deferred candidates

- **Scientific benchmark expansion:** defer external comparison until licensed
  reference data and trustworthy expected results are available. Internal
  qualification can remain a supporting acceptance fixture, not a benchmark.
- **Barugo interoperability:** defer until the narrowed official evidence is
  encoded in a separate qualification update and QC/VES persistence gates are
  closed. Do not implement based on the forensic report alone.
- **LS2 physical integration:** defer until official interface evidence and a
  validated device are available. Preserve M15 fail-closed.
- **Performance optimization:** defer until representative medium/large cases
  identify a concrete bottleneck; continue recording measurements without
  inventing operating limits.
- **Standalone reporting milestone:** incorporate only report gaps directly
  exposed by desktop acceptance; avoid duplicating the existing report contract.

## 10. Recommended roadmap wording

> **M20 — Supported Offline Desktop Workflow Completion (proposed).** Complete
> the user-facing Project → Import → QC → Process → Invert/Interpret →
> Visualize → Report workflow by integrating the existing compatible DAT, VES,
> ERT, visualization, Assistant, and provenance services. Add a repeatable
> desktop acceptance matrix and improve traceable engineering exports without
> changing scientific engines. M20 must not implement ABEM/Barugo conversion or
> LS2 communication. M15 physical validation remains pending, ABEM
> `importer_ready` remains `false`, and independent field/reference,
> production-scale, geological, uncertainty, topography-aware, and RES2DINV
> equivalence claims remain unvalidated.

## Final recommendation

Proceed with **M20 — Supported Offline Desktop Workflow Completion**. Confidence
is high because the recommendation is based on existing tested services and a
clear user-facing integration gap, not on unavailable vendor or hardware
assumptions.
