# M19 evidence-based roadmap proposal

**Assessment date:** 2026-09-15  
**Decision:** M18 is complete; no concrete unresolved M18 defect was identified.  
**Proposed milestone:** **M19 — Reproducibility and Release Qualification**  
**Implementation status:** implemented and qualified for the supported offline workflow; see `docs/m19_release_qualification.md`.

## 1. Current roadmap state

- **M0–M14:** complete.
- **M15 offline LS2 readiness:** complete.
- **M15 physical LS2 validation:** pending physical device access and authoritative protocol/interface evidence.
- **M16:** complete advisory AI increment.
- **M17:** complete application integration and scientific qualification increment.
- **M18:** complete field-qualification and production-workflow hardening increment.
- **Barugo ABEM → NiX importer:** blocked.
- **`importer_ready`:** `false`.

The Barugo read-only inspector, provenance-preserving intermediate parser,
semantic qualification layer, and vendor evidence request are complete. They do
not establish a safe importer and must not be treated as one.

## 2. M18 completion assessment

The repository contains evidence for the stated M18 work:

- metadata-only external/reference/field dataset contracts;
- frozen benchmark comparison records without fabricated external results;
- guarded long-running inversion execution and cooperative cancellation;
- preservation of the last valid model/version;
- source-aware measurement and model inspection;
- project lifecycle and report-provenance checks;
- explicit performance-scale declarations and measured small baseline;
- read-only Barugo inspection, intermediate parsing, and semantic qualification;
- explicit fail-closed LS2 boundary.

No concrete unresolved M18 defect was found in the reviewed implementation,
documentation, or regression tests. The unmeasured medium/large/stress cases,
absence of independent field/reference bytes, and pending LS2 evidence are
limitations and external dependencies, not defects to conceal by changing the
scientific engines.

## 3. Remaining blockers

### External blockers

1. **LS2 physical validation:** no instrument fixture or authorized public
   acquisition API/protocol has been supplied. M15 must remain fail-closed.
2. **ABEM importer:** the vendor evidence request remains unanswered. Array and
   protocol codes, electrode numbering, coordinate reference semantics,
   channel/sequence/polarity rules, QC/status and uncertainty definitions, VES
   persistence, auxiliary-row policy, supported versions, and conformance
   fixtures remain unresolved.
3. **Independent scientific qualification:** no authorized external/reference
   dataset with trustworthy expected results is currently available.

### Known qualification limitations

- Internal synthetic tests establish bounded behavior and invariants, not field
  accuracy or geological truth.
- Production-scale performance is not claimed from the small measured baseline.
- Topography-aware inversion, uncertainty/resolution analysis, true 3D
  inversion, commercial-solver equivalence, and RES2DINV equivalence remain
  unvalidated or out of scope.

## 4. Candidate M19 directions

| Rank | Candidate | Scientific value | User value | Evidence available now | Risk/dependency | Assessment |
|---:|---|---|---|---|---|---|
| 1 | **Reproducibility and release qualification** | High: turns existing tests and workflow claims into repeatable acceptance evidence | High: improves confidence in reopening, comparing, reporting, and sharing projects | High: existing lifecycle, provenance, synthetic qualification, report, and operation contracts | Low to medium; external benchmark results remain optional and must be labeled | **Recommended** |
| 2 | Production desktop workflow refinement | Medium to high: reduces workflow ambiguity and operational error | High: improves field usability and failure recovery | High: existing PySide6 workflow and lifecycle tests | Low to medium; must target measured usability defects rather than cosmetic redesign | Strong supporting work inside M19 |
| 3 | Scientific benchmark/qualification expansion | Potentially very high | Medium to high | Low for independent benchmarks because no authorized external/reference bytes are present; high for better internal protocols | Medium; cannot fabricate reference results | Conditional workstream only when licensed/reference evidence arrives |
| 4 | Reporting and engineering deliverables | Medium: strengthens traceability and reviewability | High: improves deliverables | High: project-bound reporting already exists | Low; risk of duplicating existing report contracts | Include only gaps found by acceptance review |
| 5 | Performance/scalability | Medium to high if a real bottleneck is demonstrated | Medium | Medium: small baseline exists, larger cases are declared but unmeasured | Medium to high; representative datasets and memory profiling are needed | Measure first; optimize only a proven bottleneck |
| 6 | Barugo interoperability | High if unblocked | High for ABEM users | Low: required vendor evidence is absent | High and currently blocked | Do not implement until the evidence gate changes |
| 7 | LS2 physical integration preparation/testing | Potentially high | High for instrument users | Low: hardware and protocol/API evidence are absent | Very high; unavailable hardware and unknown protocol | Keep as a readiness track, not implementation |

## 5. Recommended M19

### M19 — Reproducibility and Release Qualification

M19 should consolidate the existing tested capabilities into a measurable,
repeatable release-readiness qualification rather than add another scientific
engine or speculative integration. It should focus on the complete supported
offline workflow:

```text
compatible DAT/fixture
→ project
→ QC
→ processing
→ inversion
→ model/version inspection
→ report
→ close/reopen/reproduce
```

The milestone should identify and fix only defects found by the qualification
matrix. It should not replace working scientific engines or tune parameters to
match an untrusted reference.

Recommended work packages:

1. Freeze a versioned internal qualification manifest containing input hashes,
   software/runtime information, parameters, expected structural outputs,
   numerical tolerances, and known limitations.
2. Repeat the lifecycle on clean/noisy VES, 2D ERT, and 3D visualization/
   inversion fixtures, including close/reopen and report regeneration.
3. Verify deterministic project/model/report provenance and explicit handling of
   excluded measurements, stale sources, failed operations, and cancellation.
4. Perform a usability acceptance pass on the major desktop workflow and record
   only workflow-blocking defects.
5. Measure representative performance cases before any optimization; report
   actual runtime, Python-traced memory, convergence, and practical limits.
6. Produce an engineering qualification report suitable for internal release
   review, without calling the product production-grade geological software.

## 6. Explicitly out of scope

M19 must not implement or imply:

- ABEM-to-NiX conversion before the vendor evidence gate is satisfied;
- direct LS2 USB, Wi-Fi, serial, VNC, acquisition, or instrument control;
- topography-aware inversion, advanced/true 3D inversion, IP inversion,
  uncertainty/resolution analysis, GPU acceleration, or automatic geological
  classification;
- RES2DINV or commercial-solver equivalence;
- geological certainty or production-grade geological inversion;
- fabricated external datasets, benchmark results, or reference tolerances;
- broad stylistic refactoring or feature expansion without an acceptance need.

## 7. Proposed M19 acceptance criteria

M19 should be considered complete only when all applicable criteria are
supported by recorded evidence:

- A versioned qualification manifest identifies every fixture, source hash,
  parameter set, runtime/software version, expected result, tolerance, and
  limitation.
- The supported offline workflow passes clean/noisy VES and 2D ERT cases and
  the bounded 3D workflow without mutating raw data.
- Reopening a project reproduces the selected processing/model/report context;
  stale, missing, modified, or out-of-scope sources fail clearly.
- Cancellation and failed operations leave no partial scientific persistence
  and preserve the last valid model/version.
- Reports identify the actual project, survey, source, processing/model version,
  exclusions, parameters, statistics, and software context.
- A usability review records the workflow state and fixes only genuine
  transition/error-message defects.
- Performance measurements distinguish measured cases from placeholders and
  record observations, mesh/cell counts, iterations, wall time, memory method,
  convergence, and cancellation behavior.
- All results are reproducible from the manifest and no claim exceeds the
  validation evidence.
- Full regression tests, compilation, and PySide6 startup smoke pass.
- M15 remains fail-closed and `importer_ready` remains `false` unless new
  authoritative evidence changes that status.

## 8. Required evidence/data before implementation

Before starting M19, the repository needs no new external vendor evidence for
the recommended offline work. It does require:

- agreement on the supported offline workflow and qualification manifest
  version;
- stable internal fixture hashes and documented expected outputs;
- a defined runtime/platform for repeatability claims;
- representative larger datasets if medium/large performance claims are to be
  made;
- an authorized independent/reference dataset only if M19 is expanded to
  external benchmarking;
- a measured usability defect if a UI change is proposed.

New ABEM vendor documentation or an LS2 fixture is required only for their
separate blocked milestones, not for the recommended M19 baseline.

## 9. Minimal documentation changes

If approved, add the M19 qualification manifest/procedure and a dated results
record, then update `ROADMAP.md` and `changelog.md` with actual completed work
only. Do not mark M19 complete when merely the proposal is accepted. Keep the
existing Barugo contract, vendor request, `importer_ready = false`, and M15
blocked language unchanged until evidence genuinely changes them.

**Result:** M19 was implemented as a controlled reproducibility and release-
qualification milestone. The supported offline workflow is qualified within the
recorded limits; this does not qualify field-scale performance, geological
certainty, the Barugo importer, or LS2 communication. Do not begin the Barugo
importer or LS2 communication work without the explicitly requested external
evidence.
