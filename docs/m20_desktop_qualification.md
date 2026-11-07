# M20 Supported Offline Desktop Workflow Qualification

**Status:** COMPLETE for the supported offline workflow

M20 integrates the existing project, DAT, QC, processing, inversion, VES,
visualization-status, Assistant, LS2 diagnostics, and report services without
changing the scientific engines or ABEM/LS2 boundaries.

## Implemented workflow

- Project creation/open/close/reopen and survey selection remain backed by the
  existing `ProjectManager` and `ProjectStore`.
- ERT exposes DAT import, QC, processing snapshots, detached 2D inversion,
  model inspection, pseudosection generation, and project-bound reporting.
- VES exposes text/CSV-compatible curve entry, validated curve inspection,
  Schlumberger semantics, 1D layered-earth inversion, and report generation.
  Curve and inversion results are stored as immutable `VersionStore` snapshots;
  no parallel UI-only persistence model was introduced.
- The UI exposes a clearly labeled 3D output-status action. It does not present
  a 2D model as a 3D geological inversion; no persisted 3D model is fabricated
  by this milestone.
- Assistant and LS2 panels remain local/advisory and fail-closed. Mock LS2
  status is explicitly labeled MOCK/TEST and never performs acquisition.
- Reports continue to originate from the active project/survey/version state,
  including source and stale-state provenance.

## Acceptance matrix

| Path or safety case | Result | Evidence |
|---|---|---|
| Create/open/select project and survey | Tested | Existing lifecycle tests and M20 workflow tests |
| ERT import → QC → process → 2D inversion | Tested/reproducible | `test_m20_workflow.py`, existing workflow tests |
| ERT model inspection and pseudosection | Tested | Existing workflow/model/pseudosection tests |
| VES curve → 1D inversion → report | Tested/reproducible | `test_m20_workflow.py` |
| 3D output semantics | Tested as fail-closed status | No true 3D result is claimed or fabricated |
| Traceable report and repeated state | Tested | Existing report and M19 reproducibility tests |
| Assistant read-only behavior | Tested | Existing AI assistant tests |
| Cancellation and invalid input | Tested | Existing operation/M19 tests |
| Stale model and missing source | Tested | Existing workflow/lifecycle tests |
| Invalid transitions | Tested | M20 and existing workflow tests |
| LS2 unavailable and mock labeling | Tested | Existing LS2 connection/discovery tests and Qt smoke |
| Source hashes/raw immutability | Tested | Import, lifecycle, Barugo hash checks |

## Qualification terms

This milestone is **tested** and **reproducible** for small offline fixtures.
It is not a field qualification, independent benchmark, production-scale
performance qualification, geological validation, or RES2DINV equivalence
claim.

## Known limitations

- The integrated VES input path is text/CSV-compatible; the ABEM/Barugo
  `project.db` importer remains `importer_ready = false`.
- The current desktop 3D action reports availability/boundary status rather
  than generating a new 3D inversion model.
- Figure-rich engineering report composition and larger-scale desktop
  performance remain limited/unqualified.
- M15 physical LS2 validation remains pending; no protocol or acquisition
  behavior was added.
- Topography-aware inversion, uncertainty/resolution analysis, advanced 3D
  inversion, IP inversion, automatic geological classification, and geological
  certainty remain unsupported.
