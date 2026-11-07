# NiX ERT — Roadmap

> **Project:** NiX ERT
> **Purpose:** Modern electrical resistivity and geophysical interpretation software for ERT, VES, Terrameter LS2 data, 2D/3D visualization, data refinement, interpretation, and professional reporting.
>
> **Core principle:** Build a scientifically reliable geophysical platform first, then add advanced visualization, automation, AI assistance, and direct instrument integration.

---

## 1. Vision

NiX ERT is a modern alternative to traditional resistivity-processing software such as RES2DINV.

It should provide a complete workflow:

```text
Terrameter LS2
      ↓
Import
      ↓
Project / Survey Database
      ↓
Data QC & Editing
      ↓
Processing
      ↓
VES / ERT Inversion
      ↓
2D / 3D Visualization
      ↓
Interpretation
      ↓
Professional Report
```

NiX ERT should prioritize:

* scientific correctness
* transparent processing
* non-destructive data editing
* reproducible results
* fast visualization
* modern UX
* offline desktop operation
* extensibility
* professional reporting

---

# 2. Product Goals

### Primary goals

1. Import and process Terrameter LS2 survey data.
2. Support RES2DINV-compatible DAT files.
3. Support ERT workflows.
4. Support VES workflows.
5. Provide interactive data QC and editing.
6. Provide 2D resistivity inversion.
7. Provide 3D resistivity visualization and eventually 3D inversion.
8. Support electrode coordinates and topography.
9. Allow multiple survey lines to be combined into a 3D project.
10. Generate professional technical reports.
11. Preserve raw data and processing history.
12. Allow users to compare different processing/inversion versions.
13. Eventually support direct Terrameter LS2 communication.
14. Eventually provide AI-assisted QC and interpretation.

---

# 3. Non-Goals

NiX ERT should NOT initially attempt to:

* clone every feature of RES2DINV
* reproduce proprietary algorithms without understanding or validating them
* automatically make geological conclusions without user review
* modify raw survey data destructively
* build direct hardware communication before the data architecture is stable
* build advanced AI interpretation before the underlying scientific calculations are validated

---

# 4. Development Principles

## 4.1 Scientific correctness over visual features

A beautiful visualization is useless if the underlying resistivity calculation or inversion is incorrect.

Every scientific module should be testable independently.

## 4.2 Raw data is immutable

Never overwrite original Terrameter data.

Use:

```text
Raw Dataset
    ↓
Working Dataset
    ↓
Processed Dataset
    ↓
Inversion Dataset
```

Users must always be able to return to the original data.

## 4.3 Every processing operation should be reproducible

Store:

* processing parameters
* removed measurements
* filters
* inversion parameters
* model settings
* timestamps
* software version

## 4.4 Human approval for destructive decisions

Automatic QC should flag suspicious data.

It should not silently delete measurements.

---

# 5. Target Architecture

```text
NiX ERT
│
├── Application UI
│
├── Project Manager
│
├── Survey Manager
│
├── Data Import
│   ├── Terrameter LS2
│   ├── RES2DINV DAT
│   └── VES formats
│
├── Data Model
│
├── QC Engine
│
├── Processing Engine
│
├── Resistivity Calculator
│
├── VES Engine
│   └── 1D Inversion
│
├── ERT Engine
│   ├── Forward Modeling
│   ├── Jacobian
│   ├── Mesh
│   ├── Regularization
│   └── 2D Inversion
│
├── 3D Engine
│   ├── Coordinates
│   ├── Topography
│   ├── 3D Visualization
│   └── Future 3D Inversion
│
├── GIS Engine
│
├── Interpretation Engine
│
├── Report Generator
│
├── AI Assistant
│
└── Import / Export
```

---

# 6. Technology Direction

Initial target:

* Python
* PySide6 / Qt
* NumPy
* SciPy
* pandas
* SQLite
* PyVista / VTK
* matplotlib where appropriate

Performance-critical components may later be implemented using:

* Numba
* C++
* Rust
* CUDA/GPU acceleration

Do not prematurely optimize.

---

# 7. PHASE 0 — Project Foundation

### Objective

Create a clean, maintainable scientific desktop application foundation.

### Tasks

* Create repository.
* Establish project structure.
* Create Python environment.
* Configure PySide6.
* Establish application entry point.
* Establish logging.
* Establish configuration management.
* Establish test framework.
* Establish scientific calculation module structure.
* Establish project/documentation structure.

Suggested structure:

```text
NiX-ERT/
│
├── app/
├── core/
├── data/
├── processing/
├── ert/
├── ves/
├── inversion/
├── visualization/
├── gis/
├── reports/
├── tests/
├── docs/
│
├── ROADMAP.md
├── prompt.md
└── changelog.md
```

### Exit criteria

Application launches successfully with a clean main window.

---

# 8. PHASE 1 — Project & Survey Management

### Objective

Create the project database and survey organization system.

### Features

* New Project
* Open Project
* Save Project
* Recent Projects
* Project metadata
* Client
* Location
* Survey date
* Operator
* Instrument
* Notes

Survey types:

```text
ERT
VES
3D ERT
```

Project structure:

```text
Project
│
├── Survey 001
├── Survey 002
├── VES 001
├── VES 002
└── 3D Model
```

### Exit criteria

A user can create, save, reopen, and manage a complete project.

---

# 9. PHASE 2 — Terrameter LS2 Import

### Objective

Import Terrameter LS2 survey data reliably.

### Initial support

* RES2DINV-compatible DAT
* Terrameter LS2 exported data
* electrode information
* array type
* electrode spacing
* measurements
* resistance
* current
* voltage where available
* apparent resistivity where available
* quality information where available

### Requirements

The importer must:

* validate the file
* report parsing errors
* preserve original file
* identify survey parameters
* identify electrode count
* identify measurement count
* identify array type
* identify invalid measurements

### UI

```text
Import Survey
    ↓
File Validation
    ↓
Survey Preview
    ↓
Import
```

### Exit criteria

Known LS2/RES2DINV datasets can be imported and displayed correctly.

---

# 10. PHASE 3 — Data QC & Editing

### Objective

Create a professional non-destructive data refinement system.

### Features

* measurement table
* search
* sorting
* filtering
* exclude measurement
* restore measurement
* edit metadata where appropriate
* mark suspicious data
* bulk selection
* undo/redo
* QC statistics

Flag conditions such as:

* invalid values
* negative/invalid resistance
* extreme values
* suspicious apparent resistivity
* abnormal measurements
* missing electrodes
* duplicate measurements
* potential noise

### Visualization

Provide:

* pseudosection
* measurement table
* electrode map
* statistics

Selecting a measurement in one view should highlight it in the others.

### Critical rule

Never delete raw measurements.

Use:

```text
ACTIVE
EXCLUDED
FLAGGED
```

### Exit criteria

User can refine a dataset safely and restore every excluded measurement.

---

# 11. PHASE 4 — Apparent Resistivity Processing

### Objective

Implement and validate resistivity calculations independently from inversion.

### Features

Support appropriate geometric factors for:

* Wenner
* Wenner-Schlumberger
* Dipole-Dipole
* Pole-Pole
* Pole-Dipole
* Schlumberger
* Multiple Gradient
* other supported arrays as architecture permits

Calculate:

```text
Resistance
+
Electrode Geometry
+
Geometric Factor
=
Apparent Resistivity
```

### Testing

Use known synthetic examples and published/reference calculations.

### Exit criteria

Calculated apparent resistivity matches validated reference calculations within defined tolerances.

---

# 12. PHASE 5 — ERT Pseudosection

### Objective

Create high-quality interactive ERT visualization.

### Features

* apparent resistivity pseudosection
* electrode positions
* depth approximation
* array display
* logarithmic scaling
* linear scaling
* value inspection
* zoom
* pan
* measurement selection
* excluded-data visualization

### Export

* PNG
* SVG/PDF where appropriate
* CSV

### Exit criteria

A user can inspect an entire ERT dataset visually before inversion.

---

# 13. PHASE 6 — VES Module

### Objective

Create a complete VES workflow.

### Features

Import/input:

* AB/2
* MN/2
* resistance
* apparent resistivity
* electrode configuration

Visualization:

```text
Apparent Resistivity
        │
        ▼
VES Curve
```

Support:

* log-log plotting
* curve editing
* data exclusion
* manual interpretation
* 1D layered-earth inversion

Output:

```text
Layer
Thickness
Resistivity
Depth
```

### Example model

```text
Layer 1
ρ = ...
Thickness = ...

Layer 2
ρ = ...
Thickness = ...

Layer 3
ρ = ...
Half-space
```

### Exit criteria

User can import/create VES data, refine it, perform 1D inversion, and visualize the resulting layered model.

---

# 14. PHASE 7 — 2D ERT Inversion Engine

### Objective

Develop a validated 2D inversion engine.

This is a major scientific milestone.

### Components

* mesh generation
* forward modeling
* sensitivity/Jacobian calculation
* regularization
* model update
* convergence control
* RMS calculation
* iteration history
* topography support

Workflow:

```text
Measured Data
      ↓
Initial Model
      ↓
Forward Model
      ↓
Synthetic Data
      ↓
Residual
      ↓
Jacobian
      ↓
Regularization
      ↓
Model Update
      ↓
Repeat
```

### Display

```text
Iteration 1   RMS ...
Iteration 2   RMS ...
Iteration 3   RMS ...
...
Converged
```

### Critical requirement

Do not claim equivalence to RES2DINV until benchmark validation has been completed.

### Exit criteria

Synthetic and reference datasets produce stable, reproducible inversion results.

---

# 15. PHASE 8 — 2D Resistivity Model Visualization

### Objective

Create a professional 2D subsurface interpretation view.

### Features

* resistivity section
* depth
* distance
* topography
* electrode positions
* contouring
* color scale controls
* logarithmic resistivity scale
* editable color limits
* data cursor
* model cell inspection
* export image
* export PDF/SVG
* export model/data

### User controls

```text
Min Resistivity
Max Resistivity
Contour Levels
Scale
Interpolation
Topography
Labels
```

### Exit criteria

2D inversion results are easy to inspect and publication/report ready.

---

# 16. PHASE 9 — Multi-Line / 3D Survey Management

### Objective

Allow multiple ERT lines to exist in a common coordinate system.

### Features

* GPS coordinates
* UTM
* local coordinates
* electrode coordinates
* line coordinates
* elevation
* line orientation
* line spacing
* topography

Example:

```text
Line 01 ────────────────
Line 02 ────────────────
Line 03 ────────────────
Line 04 ────────────────
```

Allow:

* rotate
* translate
* align
* reverse line direction
* inspect coordinates

### Exit criteria

Multiple surveys can be positioned accurately in 3D space.

---

# 17. PHASE 10 — 3D Visualization

### Objective

Create a modern interactive 3D subsurface visualization.

### Features

* 3D resistivity volume
* surface topography
* electrode locations
* survey lines
* 2D sections
* horizontal slices
* vertical slices
* clipping
* transparency
* threshold filtering
* volume rendering
* point/cell inspection
* camera controls

Example:

```text
        Ground Surface
   ─────────────────────

      Resistivity Volume

      ███████████████
     ████████████████
    █████████████████

          Depth
```

### Interaction

User should be able to:

* rotate
* zoom
* pan
* slice
* clip
* isolate resistivity ranges
* inspect coordinates
* inspect resistivity

### Exit criteria

A multi-line survey can be explored interactively in 3D.

---

# 18. PHASE 11 — 3D Inversion

### Objective

Develop a true 3D resistivity inversion engine after the 2D engine has been validated.

### Components

* 3D mesh
* forward solver
* Jacobian
* regularization
* model update
* topography
* convergence
* sensitivity analysis

### Performance

Investigate:

* multithreading
* Numba
* C++
* GPU acceleration

Only optimize after profiling.

### Exit criteria

Validated synthetic and real-world benchmark datasets can be inverted reliably.

---

# 19. PHASE 12 — GIS & DEM Integration

### Objective

Integrate NiX ERT with geographic information.

### Support

Potential formats:

* GeoTIFF
* DEM
* CSV coordinates
* GeoJSON
* shapefile where appropriate

### Features

* map view
* survey locations
* electrode locations
* DEM surface
* elevation extraction
* coordinate transformation
* topographic correction

### Exit criteria

ERT/VES surveys can be positioned accurately against real-world terrain.

---

# 20. PHASE 13 — Interpretation Tools

### Objective

Help users interpret resistivity results without pretending to replace professional geological judgment.

### Features

* resistivity range classification
* user-defined interpretation ranges
* interpretation annotations
* polygons
* lines
* points
* horizons
* interpreted layers
* potential target zones
* notes

Example:

```text
Possible Target Zone

Distance: 120–165 m
Depth: 8–20 m
Resistivity: 12–35 Ωm

Interpretation:
[User-defined]

Confidence:
[User-defined]
```

### Important

Automatic interpretations must be presented as **possible interpretations**, not definitive geology.

---

# 21. PHASE 14 — Professional Reporting

### Objective

Generate complete technical reports from project data.

### Report sections

1. Cover page
2. Project information
3. Survey location
4. Instrument
5. Survey methodology
6. Array configuration
7. Electrode configuration
8. Data statistics
9. QC summary
10. Pseudosection
11. Inversion parameters
12. RMS/convergence
13. 2D resistivity sections
14. VES curves/models
15. 3D visualization
16. Interpretation
17. Conclusions
18. Recommendations
19. Appendices

### Requirements

Reports should be generated from structured project data rather than manually assembled.

### Output

* PDF
* printable figures
* tables
* images

### Exit criteria

A complete survey can produce a professional technical report with minimal manual formatting.

---

# 22. PHASE 15 — Processing History & Model Versions

### Objective

Make processing reproducible.

Example:

```text
Survey 001

Raw
 │
 ├── Processing v1
 │
 ├── Processing v2
 │
 └── Processing v3
```

Inversion versions:

```text
Model A
RMS = 6.2%

Model B
RMS = 4.8%

Model C
RMS = 3.9%
```

Allow:

* duplicate processing state
* compare models
* restore previous version
* rename version
* add notes

### Exit criteria

Users can experiment without losing previous work.

---

# 23. PHASE 16 — Direct Terrameter LS2 Integration

### Objective

Investigate direct communication with the Terrameter LS2.

Possible workflow:

```text
Terrameter LS2
      │
      │ USB / supported communication
      ▼
NiX ERT
      ↓
Survey Import
      ↓
QC
      ↓
Processing
```

### Requirements

Before implementation:

* determine supported communication protocol
* determine legal/technical constraints
* identify officially supported interfaces
* test read-only acquisition first

### Important

Direct hardware integration must not compromise the stability of the import workflow.

The DAT/import pipeline remains supported independently.

---

# 24. PHASE 17 — AI Assistant

### Objective

Add AI assistance after the scientific engine is stable.

Possible commands:

```text
"Find suspicious measurements."

"Show me the highest resistivity anomalies."

"Compare Model A and Model B."

"Generate a preliminary interpretation."

"Explain why this area may be anomalous."

"Prepare the survey report."

"Summarize the QC results."
```

### AI must not silently:

* delete measurements
* change inversion parameters
* alter raw data
* declare geological conclusions as fact

AI actions should be:

```text
Suggest
    ↓
Show Reason
    ↓
User Approves
    ↓
Execute
```

---

# 25. PHASE 18 — Advanced Analysis

Future capabilities may include:

* induced polarization
* time-domain IP
* spectral IP
* borehole data
* crosshole tomography
* surface-to-borehole ERT
* automated anomaly detection
* geological model integration
* groundwater-target analysis
* uncertainty visualization
* sensitivity maps
* resolution analysis
* model comparison
* batch processing
* survey templates

These should remain future roadmap items until the core platform is mature.

---

# 26. Quality & Validation Strategy

Scientific software requires stronger testing than ordinary business applications.

### Unit tests

Test:

* geometric factors
* apparent resistivity
* electrode geometry
* coordinate calculations
* VES calculations
* mesh generation
* inversion mathematics
* statistics

### Integration tests

Test:

```text
LS2 file
→ import
→ QC
→ processing
→ inversion
→ visualization
→ report
```

### Regression tests

Maintain known datasets and expected results.

### Synthetic tests

Generate known underground models and verify whether inversion can recover expected structures.

### Benchmark tests

Compare against trusted/reference software and published examples.

Do not optimize for matching another program's output blindly; first establish the mathematical reason for differences.

---

# 27. UX Direction

NiX ERT should feel like modern professional engineering software rather than legacy scientific software.

Design principles:

* clean
* minimal
* professional
* information dense without being cluttered
* clear hierarchy
* fast navigation
* excellent charts
* excellent 2D/3D visualization
* keyboard shortcuts
* context menus
* undo/redo
* dark/light themes if appropriate

Primary workflow should remain obvious:

```text
PROJECT
   ↓
IMPORT
   ↓
QC
   ↓
PROCESS
   ↓
INVERT
   ↓
VISUALIZE
   ↓
INTERPRET
   ↓
REPORT
```

---

# 28. Suggested Main Navigation

```text
┌─────────────────────────────┐
│ NiX ERT                     │
├─────────────────────────────┤
│ Project                     │
│                             │
│ Surveys                     │
│   ERT                       │
│   VES                       │
│   3D                        │
│                             │
│ Data                        │
│   Measurements              │
│   QC                        │
│   Electrodes                │
│                             │
│ Processing                  │
│   Apparent Resistivity      │
│   VES Inversion             │
│   2D Inversion              │
│   3D Inversion              │
│                             │
│ Visualization               │
│   Pseudosection             │
│   2D Model                  │
│   3D Model                  │
│   Map                       │
│                             │
│ Interpretation              │
│ Reports                     │
│                             │
│ Settings                    │
└─────────────────────────────┘
```

---

# 29. Milestone Strategy

Do not attempt the whole roadmap in one AI task.

Recommended milestones:

### M0

Foundation

### M1

Project management

### M2

Terrameter LS2 import

### M3

Data QC/editing

### M4

Apparent resistivity engine

### M5

ERT pseudosection

### M6

VES

### M7

2D inversion

### M8

2D visualization

### M9

Multi-line/coordinates

### M10

3D visualization

### M11

GIS/DEM

### M12

Professional reporting

### M13

Versioning/reproducibility

### M14

3D inversion

### M15

**Status: Blocked by external dependency; safe discovery design complete.** Official/public Guideline Geo material confirms product-level remote connectivity and vendor tools/resources, including Wi-Fi/Ethernet/mobile connectivity and USB-supported vendor workflows, but does not establish a public LS2 acquisition API, SDK, service-port contract, USB serial protocol, or validated read-only payload interface. NiX ERT therefore adds only observation-only, mockable diagnostics and preserves the fail-closed transport/DAT boundaries. Direct communication, acquisition, VNC, port probing, serial access, and instrument control remain blocked until official protocol/interface documentation, legal authorization, supported transport details, and validated device fixtures are available.

Direct LS2 integration

### M16

**Status: Complete for the initial advisory increment.** A local, provider-neutral assistant now supports project analysis, suspicious-measurement and anomaly review, QC explanations, model/inversion/VES/2D/3D summaries, report drafting, bounded natural-language queries, and approval-gated working-status proposals. It does not modify raw data, models, inversion parameters, or project state during analysis.

AI assistant

### M17

**Status: Complete for the controlled integration and qualification increment.** The desktop shell now exposes a delegated Project → Import → QC → Process → Invert → Visualize → Interpret → Report workflow, with explicit state/semantics and existing AI assistance. Project-bound reports validate current project/survey/version ownership, record source hashes and report provenance, and mark unlinked or stale models. Internal deterministic clean/noisy VES, 2D ERT, and 3D ERT qualification fixtures, migration/recovery tests, and performance measurement baselines are documented. External benchmark validation, production-scale performance qualification, topography-aware inversion, and RES2DINV equivalence remain unclaimed.

Application integration & scientific qualification

### M18

**Status: Complete for the controlled field-qualification and production-workflow hardening increment.** Added metadata-only external/published/field/commercial/user-supplied dataset classification, license/permission tracking, and frozen benchmark comparison records without bundling external data. Added detached cooperative inversion execution with guarded cancellation/persistence, source-aware measurement/model inspection, managed-source report provenance/path checks, lifecycle regressions, and explicit small-versus-unmeasured performance qualification records. External field/reference comparisons, stress-scale performance, topography-aware inversion, uncertainty/resolution analysis, production-grade geological claims, and RES2DINV equivalence remain unvalidated. M15 remains blocked by its external protocol and fixture dependency.

Field qualification & production workflow hardening

### Barugo sample-data validation increment

**Status: Complete for safe read-only inspection; NiX conversion blocked by schema incompatibility.** Inspected the two local **BARUGO SAMPLE DATA — REAL USER-PROVIDED DATA** SQLite files without modifying them. The ABEM project schema is valid SQLite but does not match NiX `ProjectStore`; no conversion, migration, import, inversion, visualization, report, or Assistant context was created from guessed mappings. Added a read-only ABEM inspector and desktop `Inspect Barugo ERT Sample` / `Inspect Barugo VES Sample` entry points that expose source hashes, vendor schema/task/software metadata, measurement links, named apparent-resistivity facts, geometry, and compatibility reasons. The files are not live LS2 acquisition data. The original files remain unchanged; LS2 hardware communication and validation remain blocked.

### Barugo sample-data validation and semantics increment

**Status: Specification complete; importer intentionally blocked.** The two local **BARUGO SAMPLE DATA — REAL USER-PROVIDED DATA** ABEM SQLite databases were inspected read-only at table/column, logical relationship, geometry, datatype/unit, status, timestamp, and ERT/VES representation levels. A versioned draft contract is documented in `docs/barugo_import_contract.md`, including source provenance, separate ERT/VES mappings, raw-value preservation, validation rules, failure conditions, and all unknown/unsupported fields. Independent arithmetic checks reproduce stored `ρapp` from `R × K` for 401/401 ERT and 25/25 VES linked observations to floating-point precision; this is internal consistency only, not an external benchmark. No importer, conversion, LS2 communication, or source mutation was performed. Implementation remains blocked pending an authorized ABEM schema/protocol reference covering array codes, channel/status meanings, coordinate units/numbering, and VES semantics.

Barugo vendor evidence acquisition package

**Status: Complete as a vendor-facing readiness request; ABEM → NiX importer remains NOT READY.** Added `docs/barugo_vendor_evidence_request.md`, mapping every current qualification blocker to its ABEM fields, current evidence, exact minimum authoritative evidence, validation method, applicable ERT/VES path, and state-unlock criteria. Linked the detailed request from the existing checklist. No importer, NiX persistence, scientific calculation, acquisition, or LS2 communication was added.

### M19 evidence-based roadmap proposal

**Status: Complete for the supported offline workflow, with explicit limits.** Added deterministic machine-readable qualification manifests and release results, reproducibility/lifecycle regression coverage, source/model/report provenance checks, cancellation and invalid-input safety coverage, desktop startup/LS2 fail-closed acceptance smoke, and measured small-fixture workflow/scientific baselines. The result is `QUALIFIED_FOR_SUPPORTED_OFFLINE_WORKFLOW`, not production-grade geological qualification. Independent field/reference validation, medium/large/stress performance, Barugo importer semantics, and physical LS2 validation remain blocked or unvalidated. See `docs/m19_release_qualification.md` and `docs/m19_release_qualification.json`.

### M20 Supported Offline Desktop Workflow Completion

**Status: Complete for the supported offline workflow, with explicit limits.** Integrated the existing ProjectManager/ProjectStore, compatible DAT import, QC, processing, detached 2D inversion, model/pseudosection inspection, VES curve and 1D inversion workflow, advisory Assistant, LS2 fail-closed panel, and project-bound reporting into the PySide6 shell. VES results use the existing immutable version-snapshot contract; no parallel UI persistence model or scientific engine rewrite was introduced. Added the repeatable M20 acceptance tests and documented the 3D boundary, provenance, cancellation, raw-data immutability, and scientific limitations in `docs/m20_desktop_qualification.md`. ABEM/Barugo conversion, LS2 physical integration, topography-aware/uncertainty/advanced-3D algorithms, and stronger scientific claims remain out of scope; `importer_ready = false` and M15 physical validation remains pending.


### M21 Scientific Qualification and Benchmark Readiness

**Status: Complete for internal qualification and benchmark readiness, with explicit limits.** Added the reusable `nix_ert.qualification.m21` evidence layer, deterministic VES/2D/3D manifests, explicit convergence outcomes, numerical comparison metrics, controlled starting-model/mesh/damping/stopping/noise studies, failure/cancellation evidence, and machine-readable/human-readable qualification artifacts in `docs/m21_scientific_qualification.md` and `.json`. Internal cases remain `QUALITATIVELY CONSISTENT`; the external benchmark gate remains `NOT VALIDATED` because no authorized independent reference dataset is available. No solver, importer, database schema, or LS2 behavior changed; `importer_ready = false` and M15 physical validation remains pending.

### External benchmark gate — qualification gap analysis (blocked; `NOT VALIDATED`)

**Status: Assessment complete; gate NOT COMPLETE (evidence-blocked).** The next unfinished roadmap gate is the external independent reference-comparison gate. A read-only gap analysis in `docs/external_benchmark_gap_analysis.md` verifies that no benchmark-eligible dataset, protocol, or comparison is registered, that no external dataset bytes exist in the repository, and that the benchmark registry/protocol/comparison contracts are not wired to any execution path in the application. It records the acceptance criteria already encoded in `nix_ert.qualification.registry`, the five exactly-missing evidence items (licensed dataset bytes, acquisition/geometry metadata, source hash and provenance, trustworthy independent reference result, frozen protocol with defensible tolerances), the readiness gaps that must be closed only after that evidence arrives, the ordered next actions, the intake manifest schema, and the prohibited shortcuts. No data, benchmark, vendor evidence, or field result was fabricated, no algorithm or schema changed, and the gate remains `NOT VALIDATED`. The adjacent ABEM/Barugo importer gate (`importer_ready = false`) and M15 physical LS2 validation remain blocked and unchanged.

### M22 Inversion Robustness and Scientific Hardening

**Status: Complete for instrumented bounded convergence evidence, with explicit limits.** Added the reusable `nix_ert.qualification.m22` evidence layer: a single `ConvergenceContract` result structure for VES, 2D ERT, and 3D ERT with strict `CONVERGED` / `TERMINATED` / `FAILED` / `INVALID_INPUT` / `CANCELLED` semantics (solver completion is never treated as convergence, a configured limit is never treated as failure, and an unavailable objective trajectory is recorded as `HISTORY_UNAVAILABLE` instead of being invented), plus expanded bounded deterministic starting-model, damping, mesh/domain, stopping-limit, and deterministic-noise studies for every engine that exposes the corresponding control. Bounded, invalid-input, and cancellation cases are retained rather than hidden. One concrete defect was demonstrated and fixed: the 3D ERT engine returned an objective history and convergence flag describing the pre-update model rather than the returned model, so the recorded final objective wrongly equalled the initial objective; the correction changes reporting only, and the affected M21 record was re-run and corrected. Internal cases remain `QUALITATIVELY CONSISTENT`; the external benchmark gate remains `NOT VALIDATED` because no authorized independent reference dataset is available. No inversion algorithm, solver mathematics, database schema, ABEM importer, or LS2 behavior changed; `importer_ready = false` and M15 physical validation remain pending. See `docs/m22_scientific_hardening.md`, `docs/m22_scientific_hardening.json`, and `docs/m22_scientific_hardening_report.md`.

### M22 post-M21 evidence-based roadmap assessment

**Status: Proposal only; M22 not implemented.** M21 results show finite, reproducible but mostly `TERMINATED` VES/2D/3D runs, measurable starting-model/damping/mesh/stopping/noise dependence, and unequal convergence-history detail across engines. The recommended next direction is **M22 — Inversion Robustness and Scientific Hardening**: broaden bounded convergence evidence, align outcome/history reporting, preserve unsuccessful cases, and fix only demonstrated defects. Uncertainty/resolution, topography, external benchmark execution, Barugo interoperability, and LS2 integration remain deferred or externally blocked. See `docs/m22_roadmap_proposal.md`.

### M23 Forward-Physics Correction and Qualification Integrity

**Status: COMPLETE.** Corrected the demonstrated defects identified by the independent scientific audit without replacing any optimizer, and then closed the two remaining open code defects found by the post-M23 audit. **A1:** the layered VES kernel integrated `J0(λr)/r` instead of `J0(λr)`, mis-scaling every layered response (audit case: 91.78282027 versus the independently derived image-series value 78.76163158480); the `1/r` factor now belongs only to the exact homogeneous term, and the correction integral uses a deterministic certified Gauss–Legendre scheme that raises `VESNumericalError` instead of returning an uncertifiable value. **A2:** the 3D nonuniform-mesh assembly used each cell's *own* width twice for the higher-index neighbour, producing an asymmetric matrix (max `|A − Aᵀ| = 1.6369`). **A3:** unequal-width interface conductance used a harmonic mean of conductivities with an arithmetic mean of widths (`0.2666667` instead of the exact series-resistance value `0.2222222`), now one shared exact implementation for 2D and 3D. **A4:** imported electrode geometry was reconstructed from overwritable survey-level spacing metadata instead of per-source rows, so one source could silently move another's electrodes, topography was flattened, and stale detection carried no geometry identity; binding is now source-bound, fail-closed, and geometry-digest-checked at commit. **A5:** the advertised RES2DINV DAT compatibility is withdrawn in favour of an explicitly documented NiX dialect that rejects anything else — vendor conformance remains evidence-blocked. **B1–B4:** qualification `VALIDATED` now requires an independent eligible dataset, a reference result, complete metrics, a convergence record and a written tolerance justification (with recursively immutable records); non-finite or non-positive solver tolerances are rejected so `convergence_rms = inf` can no longer report convergence; a forward-model numerical failure is a distinct failure class with a recorded failure phase rather than `INVALID_INPUT`; model-comparison metrics require a shared discretization identity; and malformed VES rows fail explicitly with source/line locations instead of being parsed as headers. The affected M21/M22 artifacts were re-run and corrected with provenance, and the superseded M22 v1 artifact is retained rather than overwritten. **Closure increment (C1/C2).** The two remaining open code defects were fixed. **C1:** `rms_percent` overflowed to `inf` for representable percentages because the metric squares each relative residual, so an accepted finite initial model of `1e160`–`1e300` (or a VES sounding at the `1e-190` scale) reported `inf` while `rms_log10` stayed finite; the quantity is now evaluated by one shared helper that keeps the conventional expression wherever it cannot overflow — so ordinary and recorded results are bit-identical — and otherwise evaluates scaled residual magnitudes, reporting `inf` only when the exact value genuinely exceeds the double range and rejecting non-finite or non-positive input. **C2:** scipy's SuperLU binding reports an exactly singular forward system as a bare `RuntimeError`, which escaped the numpy-only boundary and was recorded as `FAILED` in the `solver_update` phase although no model update was attempted; the boundary now wraps only the factorization calls of both ERT engines and converts that condition into the engine's dedicated numerical error with an explicit `forward_factorization` phase, preserving the original cause while exposing no binding-specific detail. Neither correction changed any qualification artifact: `docs/m22_scientific_hardening.json` regenerates byte-identically (`report_sha256 = c05d476c…52`) and every curated M21 field is unchanged. Measurements are in `docs/m23_evidence/probe_m23_closure.json`; tests are the `PercentRMSTests` and `ForwardFactorizationFailureTests` classes. **Final C1 closure (mixed magnitudes).** The release-gate audit found that the scaled branch had selected the largest `log10` ratio instead of the largest residual magnitude, so `percent_rms([1e160, 1e-200], [1.0, 1e200])` raised `ValueError: math domain error` and the public `invert_ert` case (initial `1e-60` ohm-m against observations alternating between `1e-230` and `1e308`) could not report its ~`7.07e171` percentage; the branch now forms the residual magnitudes directly, scales by the largest of them and accumulates `(r_i / s) ** 2`, using log space only when the scale itself overflows, and both cases agree with an independent 60-digit reference to ~`2e-16`. No qualification artifact changed — the M22 artifact still regenerates byte-identically and the curated M21/M19 records store no percentage-RMS quantity — and the affected fields of `docs/m23_evidence/probe_m23_closure.json` are marked partially superseded and re-measured in `docs/m23_evidence/probe_m23_c1_mixed_magnitude.json`. No database schema, ABEM importer, or LS2 behavior changed; the external benchmark gate remains `NOT VALIDATED`, `importer_ready = false`, and M15 physical validation remains pending. See `docs/m23_forward_physics_correction.md`.

### M24 Benchmark Admission and Execution Readiness

**Status: Complete for the engineering readiness gaps; the external gate remains `NOT VALIDATED`.** Delivered R‑1 … R‑4 of `docs/external_benchmark_gap_analysis.md` §5 in `nix_ert.qualification.benchmark`, without adding evidence or changing any qualification artifact. `admit_benchmark_candidate` is a fail-closed admission decision that refuses internal-only or unpermitted data, missing/unreadable bytes, an unrecorded or mismatched source digest, missing acquisition/geometry metadata, an absent reference result, a reference result produced by NiX ERT itself, missing reference semantics, unsupported metrics or domains, tolerances without a written per-metric justification, and missing or contradictory frozen parameters. `run_benchmark` executes one frozen protocol over the existing unmodified VES, 2D ERT, or 3D ERT engines, records every outcome including `FAILED`/`INVALID_INPUT` as `NOT VALIDATED` rather than omitting it, and derives its status only from the frozen tolerance rule. Executed comparisons carry `BenchmarkProvenance`: dataset SHA‑256, canonical protocol digest before and after execution (a change aborts the record, so a tolerance cannot be fitted to a result), executed input and discretization digests, reference producer/provenance, engine source digest, and an environment snapshot. No licensed external dataset or independent reference result exists, so admission refuses every candidate, the registry still holds 0 protocols/0 comparisons, and the gate stays `NOT VALIDATED`; ABEM/Barugo `importer_ready = false` and M15 physical LS2 validation remain unchanged. See `docs/benchmark_execution.md`.

### M25 Benchmark Tooling and Report Deliverables

**Status: Complete for the engineering tooling and deliverables increment; the external gate remains `NOT VALIDATED`.** Added a headless admission/execution tool (`tools/run_external_benchmark.py`, `nix_ert.qualification.benchmark_cli`) that admits each selected protocol in a registry manifest, executes only admitted protocols over the unmodified engines, records results into an explicitly named manifest (`--admit-only` never writes), and reports distinct exit codes for validated, refused, outside-tolerance, and usage outcomes; engine inputs are supplied as a versioned `benchmark-case-v1` case file because no vendor dataset format is contractually accepted. Added a 61-case negative-path audit (`tests/test_benchmark_manifest_audit.py`) proving that no admission finding can be bypassed by removing, weakening, re-spelling, duplicating, or padding evidence in a crafted manifest, while documenting that admission enforces presence/type/consistency/non-self-production and cannot authenticate an asserted licence. Hardened the report deliverables: fixed numbered section structure with a table of contents and anchors, explicit non-invention notes for unsupplied sections, a provenance section carrying the state fingerprint, source hashes, selected version identity and qualification scope, a format-independent content digest, a machine-readable manifest, and HTML/JSON/CSV/PDF export dispatch with unknown suffixes rejected; project-bound `.json`/`.csv` report runs are now recorded like HTML ones. No solver, optimizer, database schema, ABEM importer, or LS2 behavior changed; `importer_ready = false`, M15 physical validation remains pending, and the registry still holds 0 protocols and 0 comparisons. See `docs/benchmark_execution.md` and `docs/reports.md`.

### M26 Report Export UI, Frozen Report Output, and DAT Case Conversion

**Status: Complete for the desktop export wiring and the two supporting increments; no scientific or gate status changed.** The desktop shell's *Interpret / Report* tab now exposes an **Export format** selector (HTML, PDF, CSV, JSON) backed by `nix_ert.app.report_export`, so the operator chooses a format in the UI instead of relying on a raw save-dialog filter; the dialog uses the same format list, suggests a matching extension, a typed supported extension determines the written format, an unsupported extension is refused, and the output panel reports the written path, the format's role (PDF is a text rendering; HTML/JSON are authoritative) and the report content digest. Added a golden-file regression that freezes the exact HTML and CSV bytes and the content digest for a fixed fixture (`tests/golden/`, `tests/test_report_golden.py`), with an explicit regeneration tool (`tools/regenerate_report_goldens.py`), so any change to structure, escaping, row order, or line endings is reviewed rather than absorbed silently. An offscreen end-to-end smoke test (`tests/test_report_export_smoke.py`) now clicks the real export button on a persisted project and imported DAT: every suggested format is written and reported with its digest, the dialog's suggested filename and filter list follow the selection, a typed supported suffix wins over the selection, an unsupported suffix is refused with nothing written, and PDF either exports or names the missing dependency. Added `--case-from-dat`/`--emit-case` to the headless benchmark tool via `nix_ert.qualification.dat_benchmark_case`, which converts a documented NiX DAT file into a `benchmark-case-v1` payload using the protocol's frozen `mesh_assumptions` (no mesh default is invented) and refuses topography, missing electrodes, invalid apparent resistivity, malformed input, and a protocol that receives both a case file and a DAT conversion. No solver, optimizer, report structure, database schema, ABEM importer, or LS2 behavior changed; the external gate remains `NOT VALIDATED`, `importer_ready = false`, and M15 physical validation remains pending. See `docs/reports.md` and `docs/benchmark_execution.md`.

### M27 VES Case Conversion

**Status: Complete for the VES conversion increment; no scientific or gate status changed.** Added `nix_ert.qualification.ves_benchmark_case`, which converts a sounding in the documented VES text/CSV dialect into a `benchmark-case-v1` payload, so a VES case also no longer requires hand-written JSON. Every converted point carries both the measured resistance and the apparent resistivity: a supplied fourth column is preserved rather than recomputed, and an absent one is derived through the documented Schlumberger geometric factor, so the payload never hides which quantity was measured. Invalid geometry, non-positive resistance, non-finite or non-positive apparent resistivity, over-wide rows, malformed input, and a blank protocol ID are refused with the source name and line number; `--case-from-ves` is accepted only for a protocol whose frozen domain is `VES`, and a protocol may not receive both a case file and a VES conversion. The dialect records no exclusions, so no point is marked excluded on the operator's behalf. `tests/test_ves_benchmark_case.py` adds 24 tests, including an end-to-end conversion → execution → recorded comparison run. No solver, optimizer, dataset, database schema, ABEM importer, or LS2 behavior changed; the registry still holds 0 protocols and 0 comparisons, the external gate remains `NOT VALIDATED`, `importer_ready = false`, and M15 physical validation remains pending. See `docs/benchmark_execution.md`.

### M28 Windows Standalone Installer Packaging

**Status: Complete for the packaging increment; no scientific or gate status changed.** Added a Windows packaging pipeline that turns the desktop shell into a normal program: `packaging/windows/nix_ert.spec` freezes `nix_ert.app.main` into a one-folder PyInstaller bundle and `packaging/windows/nix_ert.iss` compiles that bundle into a single per-user Inno Setup installer (`PrivilegesRequired=lowest`, so the target is `%LOCALAPPDATA%\Programs\NiX ERT` with an uninstall entry under `HKCU` and no administrator prompt). `tools/build_windows_installer.py` orchestrates both steps, creates a `.venv-build` environment from the project's own declared dependencies so a contaminated developer interpreter cannot inflate the installer, and passes one application version taken from `nix_ert.__version__` to both tools rather than duplicating it in a second place; `--bundle-only`, `--installer-only`, `--no-venv`, and `--clean` cover the narrower steps. The spec excludes everything the desktop shell does not import: `pkg_resources`/`setuptools` (whose collected runtime hook previously aborted startup), tkinter, pytest, the unused Qt modules, and the ML/NLP stacks a developer machine usually carries (torch, transformers, spacy, nltk, numba, llvmlite, librosa, MKL). A first build from a contaminated interpreter produced 1.9 GB containing that payload; the delivered bundle is 304 MB with none of it present. The build fails closed on a missing PyInstaller or `ISCC.exe`, an empty version, a non-Windows platform, a failed step, or a missing artifact. Verified end to end: `dist/installer/NiX-ERT-0.1.0-win64-setup.exe` (88,023,957 bytes, SHA-256 `45610a00745a2b23c998768e72c012703a37f52d86332c8d628256d06d3abd3d`) was installed silently for the current user, and both the frozen and the installed executables start and create the window titled `NiX ERT 0.1.0`; the install tree, Start menu shortcuts, and uninstaller are present. Remaining packaging limitations are recorded rather than claimed solved: the artifact is unsigned (SmartScreen may warn), no lock file freezes the library versions the installer ships, the pipeline is exercised on Windows x64 only, and packaging changes no qualification status — the external benchmark gate remains `NOT VALIDATED`, `importer_ready = false`, and physical LS2 communication remains blocked. See `docs/installer.md`.

## 30. Definition of Done

A phase is not complete merely because the UI exists.

A phase is complete when:

* implementation works
* tests exist
* existing tests still pass
* data is preserved correctly
* errors are handled
* UI is usable
* documentation is updated
* processing is reproducible
* scientific calculations have appropriate validation
* no unrelated functionality is broken

---

# 31. Development Rule for AI Agents

AI coding agents must:

1. Read `ROADMAP.md`.
2. Read `prompt.md`.
3. Inspect the existing implementation before changing it.
4. Implement only the current milestone/task.
5. Avoid unnecessary architecture changes.
6. Avoid adding speculative features.
7. Write tests alongside scientific functionality.
8. Run relevant tests.
9. Fix regressions before completion.
10. Update `changelog.md`.
11. Report exactly what was implemented.
12. Do not mark a milestone complete unless its exit criteria are satisfied.

Do not continuously expand the roadmap while implementing a milestone.

---

# 32. Git Milestones

After each stable milestone:

```text
git status
git diff
git add ...
git commit
git tag
```

Git commits/tags should remain under the user's control.

Suggested tags:

```text
v0.1.0-foundation
v0.2.0-ls2-import
v0.3.0-data-qc
v0.4.0-resistivity
v0.5.0-ert-pseudosection
v0.6.0-ves
v0.7.0-2d-inversion
v0.8.0-2d-model
v0.9.0-3d
v1.0.0-professional-release
```

---

# 33. First Release Target

The first serious usable release should target:

```text
NiX ERT v1.0

✓ Project management
✓ Terrameter LS2 import
✓ RES2DINV DAT compatibility
✓ ERT data QC
✓ Non-destructive editing
✓ Apparent resistivity calculation
✓ ERT pseudosection
✓ VES processing
✓ VES 1D inversion
✓ Validated 2D ERT inversion
✓ 2D resistivity visualization
✓ Electrode coordinates
✓ Basic 3D visualization
✓ Professional report generation
✓ Processing history
✓ Export
✓ Comprehensive tests
```

Advanced 3D inversion, direct LS2 communication, GIS expansion, IP, and AI assistance may follow after the core release is scientifically validated.

---

# 34. Long-Term Vision

NiX ERT should eventually become a complete geophysical interpretation platform:

```text
                ┌───────────────┐
                │ Terrameter LS2│
                └───────┬───────┘
                        │
                        ▼
               ┌─────────────────┐
               │    NiX ERT      │
               │                 │
               │ Data Management │
               └────────┬────────┘
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
        ERT            VES            IP
          │             │             │
          ▼             ▼             ▼
       2D Model       1D Model      IP Model
          │             │             │
          └─────────────┼─────────────┘
                        ▼
                  ┌───────────┐
                  │ 3D Model  │
                  └─────┬─────┘
                        │
              ┌─────────┼─────────┐
              ▼         ▼         ▼
             GIS   Interpretation AI
              │         │         │
              └─────────┼─────────┘
                        ▼
                Technical Report
```

The goal is not merely to build another resistivity plotting program.

The goal is to build a **modern, scientifically transparent, extensible geophysical platform** that can take raw field measurements all the way to an interpretable 2D/3D subsurface model and professional technical report.
