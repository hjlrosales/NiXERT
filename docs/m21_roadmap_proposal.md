# M21 Evidence-Based Roadmap Assessment

**Assessment date:** 2026-09-15  
**Assessment only:** M21 is not implemented.  
**Recommendation confidence:** High for direction; medium for exact external benchmark scope because no licensed independent dataset is currently present.

## 1. Current qualified baseline

M19 established:

`QUALIFIED_FOR_SUPPORTED_OFFLINE_WORKFLOW`

M20 connected the existing offline services into a usable desktop workflow:

```text
Create/Open → Import/Inspect/QC → Process → Invert/Interpret
→ Model inspection → Assistant → Traceable report
```

The current baseline includes deterministic DAT import, non-destructive QC,
apparent-resistivity processing, bounded VES/2D/3D numerical engines,
visualization data services, project/model versioning, provenance-aware reports,
local advisory AI, cancellation guards, and fail-closed LS2 diagnostics.

This qualification is limited to supported offline workflows and small internal
fixtures. It does not establish field accuracy, production-grade geological
inversion, uncertainty/resolution estimates, topography-aware inversion,
RES2DINV equivalence, independent benchmark agreement, or physical LS2 access.

## 2. Area-by-area maturity assessment

| Area | Status | Repository evidence |
|---|---|---|
| Scientific validation | **PARTIALLY READY** | Mathematical reference checks, deterministic clean/noisy internal VES/2D/3D fixtures, finite-volume normalization, residual reduction, convergence fields, and reproducibility tests exist. No independent field/published/commercial comparison exists. |
| Engineering workflow | **READY FOR SUPPORTED OFFLINE SCOPE** | M20 acceptance tests cover project lifecycle, ERT workflow, VES workflow, reporting, invalid transitions, provenance, raw immutability, Assistant behavior, and LS2 fail-closed states. This is not a claim of field readiness. |
| Reporting | **PARTIALLY READY** | Structured HTML/PDF reports contain project, survey, QC, version/model, source, hashes, state fingerprints, limitations, and appendices. Figure-rich engineering deliverables and complete model/pseudosection figure embedding are not demonstrated. |
| Performance | **PARTIALLY READY** | Small ERT/VES/3D observations are measured. Medium, large, stress-scale, native-memory, and realistic desktop responsiveness limits remain unmeasured. VES small-case inversion is the most expensive recorded operation. |
| Barugo/ABEM interoperability | **BLOCKED BY EXTERNAL EVIDENCE** | The intermediate parser, qualification layer, and vendor evidence request exist, but `importer_ready = false`; unresolved vendor semantics and approved VES persistence evidence remain. |
| Terrameter LS2 integration | **BLOCKED BY EXTERNAL EVIDENCE** | Only fail-closed abstractions and mocks exist. No authoritative public acquisition API/protocol, validated device fixture, or physical LS2 test is available. |
| Scientific production readiness | **NOT YET JUSTIFIED** | Independent validation, topography treatment, uncertainty/resolution evidence, larger workloads, inversion robustness evidence, and field-scale geological qualification are absent. |

## 3. Material remaining gaps

1. Internal synthetic validation demonstrates numerical behavior but not
   independent agreement or field accuracy.
2. Convergence and residual reporting exist, but systematic mesh, damping,
   starting-model, noise, and geometry sensitivity evidence is limited.
3. No uncertainty/resolution analysis is calculated; residual fit must not be
   presented as confidence or uniqueness.
4. The 2D and 3D baselines use flat finite meshes and explicit boundary and
   electrode approximations. Topography-aware inversion is not implemented.
5. Medium/large/stress performance and native memory behavior are unmeasured.
6. Reports are traceable structured deliverables, but figure-rich engineering
   export is incomplete.
7. Barugo interoperability and physical LS2 integration depend on evidence not
   available in the repository.

## 4. Candidate M21 directions

| Rank | Candidate | Readiness | Scientific value | Engineering value | Evidence now | Dependencies/risk | Qualification value |
|---:|---|---|---|---|---|---|---|
| 1 | Scientific benchmark and validation expansion | Partially ready | Very high | High | Strong internal fixtures and benchmark contracts; no independent bytes | External reference data may remain unavailable; high risk of overstating results if not separated by status | High: improves reproducibility, convergence evidence, sensitivity evidence, and honest benchmark classification |
| 2 | Engineering reporting and deliverables | Partially ready | Medium | High | Existing report contract and provenance are strong | Low/medium; figure generation must avoid stale-model embedding | Medium/high: improves practical engineering outputs without changing inversion mathematics |
| 3 | Performance and large-dataset qualification | Partially ready | Medium/high | High | Measurement harness and small baselines exist | Requires representative larger cases and native-memory profiling; optimization is not yet justified | High if measured honestly, but field-scale inputs are currently absent |
| 4 | Advanced scientific capabilities | Not yet justified | Potentially very high | Medium | Existing limitations identify needs, but requirements are not qualified | High scientific risk; topography/uncertainty/advanced 3D changes require separate validation plans | Potentially high, but premature before baseline qualification is stronger |
| 5 | Barugo/ABEM interoperability | Blocked | High eventual value | High eventual value | Factual parser, qualification gate, and vendor request exist | `importer_ready = false`; authoritative field semantics and VES persistence contract are missing | No safe qualification value until evidence arrives |
| 6 | LS2 physical integration | Blocked | High eventual value | High eventual value | Fail-closed discovery architecture and mocks | Hardware, official interface/protocol evidence, authorization, and fixtures unavailable | No valid physical qualification can be produced now |

## 5. Recommended M21

### M21 — Scientific Qualification and Benchmark Readiness

Strengthen the evidence around the existing VES, 2D ERT, and 3D ERT numerical
baselines without replacing their algorithms or claiming field validity.

The milestone should produce a fixed, auditable qualification procedure that
separates:

- **VALIDATED** — mathematical checks and reproducible internal invariants;
- **QUALITATIVELY CONSISTENT** — behavior on internal synthetic cases;
- **NOT VALIDATED** — independent/reference/field claims with no trustworthy
  comparison evidence.

If an authorized independent/reference dataset becomes available during M21, it
may be run through the frozen protocol. If not, M21 must still complete its
internal qualification and explicitly record the external comparison as blocked,
not fabricate a result.

## 6. Proposed scope

### In scope

1. Freeze versioned qualification manifests for representative VES, 2D, and 3D
   cases, including source identity, geometry, mesh, starting model, damping,
   stopping criteria, noise, and software environment.
2. Add reproducible convergence/residual evidence across fixed internal cases,
   including clean/noisy behavior and unsuccessful/non-convergent outcomes.
3. Add controlled sensitivity studies for starting model, mesh size, damping,
   iteration/stopping criteria, and deterministic noise level. Report measured
   differences rather than selecting parameters to obtain a desired result.
4. Define comparison metrics appropriate to each domain: apparent-resistivity
   response error, residual behavior, model-parameter difference where a known
   synthetic truth exists, anomaly-location agreement where meaningful, and
   convergence behavior.
5. Add a frozen external benchmark protocol and an evidence gate that prevents
   internal synthetic data from being presented as independent validation.
6. Record a human-readable and machine-readable qualification result with
   environment, datasets, parameters, metrics, limitations, and blocked claims.
7. Re-measure small baselines where needed and document that medium/large/stress
   performance remains unqualified unless representative cases are available.

### Explicit non-goals

- No new inversion algorithm or solver replacement.
- No uncertainty/resolution implementation.
- No topography-aware inversion.
- No advanced or true geological 3D inversion.
- No IP inversion, GPU acceleration, or speculative optimization.
- No ABEM/Barugo importer or undocumented mappings.
- No LS2 USB, serial, Wi-Fi, VNC, acquisition, or instrument-control code.
- No geological classification, geological certainty, or stronger AI claims.
- No RES2DINV or commercial-solver equivalence claim.
- No fabricated external dataset, reference result, tolerance, or benchmark.

## 7. Prerequisites and evidence inputs

- Existing internal qualification fixtures and M19 manifests.
- Fixed software/environment capture and deterministic random/noise seeds.
- Explicitly documented mesh and inversion parameter sets.
- For independent comparison: legally usable dataset bytes, acquisition and
  geometry metadata, trustworthy reference result, permission status, and a
  protocol frozen before execution.
- If no external dataset is available, the external benchmark portion remains
  `NOT VALIDATED` and does not block completion of the internal qualification
  portion.

## 8. Proposed qualification evidence

M21 acceptance should demonstrate:

- repeated execution produces equivalent structured results;
- clean synthetic forward calculations reproduce the declared internal truth;
- noisy cases preserve finite outputs and report residual/convergence behavior;
- parameter sensitivity results are recorded without being converted into
  universal accuracy claims;
- failed or non-convergent cases are retained as qualification evidence;
- external comparisons, if available, include numerical differences,
  convergence, residuals, spatial agreement, known differences, and fixed
  tolerances;
- no result is labeled independent unless its dataset classification and
  permission status allow it;
- M15 and Barugo gates remain unchanged.

## 9. Expected deliverables

- Versioned qualification protocol/manifests for VES, 2D ERT, and 3D ERT.
- Machine-readable qualification result and human-readable report.
- Convergence and sensitivity result tables for internal fixtures.
- Optional reproducible external comparison records, or an explicit blocked
  record when no authorized reference data exists.
- Updated qualification documentation and limitations matrix.
- No changes to scientific engines unless a specific qualification defect is
  demonstrated and independently regression-tested.

## 10. Risks and dependencies

- Internal synthetic evidence can be mistaken for field validation; every result
  must retain its dataset classification.
- Inversion non-uniqueness means model-parameter agreement alone is insufficient.
- External references may use different mesh, boundary, preprocessing, or
  stopping conventions; disagreement must be investigated, not tuned away.
- Native memory and field-scale performance remain outside scope unless suitable
  workloads are supplied.
- Barugo and LS2 remain independent external dependencies and must not be
  smuggled into M21 through assumptions.

## 11. Definition of done

M21 would be complete when:

- fixed qualification protocols/manifests exist for VES, 2D, and 3D;
- internal clean/noisy, convergence, and sensitivity results are reproducible;
- successful and unsuccessful outcomes are recorded;
- any external comparison is legally authorized, frozen before execution, and
  labeled with the correct validation status;
- no fabricated reference result or tolerance is introduced;
- machine-readable and human-readable qualification results agree;
- scientific limitations remain visible in reports and documentation;
- all existing tests remain regression-free;
- Barugo `importer_ready = false` remains unchanged;
- M15 physical LS2 validation remains pending;
- no production-grade geological or RES2DINV-equivalence claim is made.

## Final recommendation

Proceed with **M21 — Scientific Qualification and Benchmark Readiness**. It has
the highest scientific value among directions that can proceed without
undocumented vendor behavior, builds directly on M19/M20, and converts the
current limitations into measurable, auditable evidence rather than adding
speculative capability.
