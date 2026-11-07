# Architecture Notes

## M17/M20 application integration

The desktop shell delegates ERT operations to `nix_ert.app.workflow.ERTWorkflow` and VES operations to `VESWorkflow`. The coordinators select persisted surveys, call the existing import/QC/processing/inversion/visualization/report/AI services, and expose workflow state for UI display. They do not duplicate scientific formulas.

VES curve and 1D inversion results use the existing immutable `VersionStore` snapshot contract because the ERT measurement table does not represent AB/2/MN/2 observations. This is project-bound persistence, not a second UI-only data model. The desktop 3D action reports whether a persisted 3D model is available and does not reinterpret a 2D model as 3D.

Project-bound reports are assembled by `nix_ert.reports.project_report` from the currently open `ProjectStore`. Selected versions must belong to the selected survey. Report runs record source hashes, selected version IDs, output paths, and generation time.

## Persistence boundary

A project is a SQLite database named `project.nixert.sqlite3` inside its project directory. The `ProjectStore` owns structured project metadata, survey records, imported source provenance, working statuses, and report-run records. Raw instrument files are preserved in a separate managed raw-data area and are never overwritten by processing.

Schema version 4 adds report-run state fingerprints after the additive v2-to-v3 report provenance migration. Unsupported, newer, incomplete, malformed, or invalid project databases fail closed.

## Scientific boundary

Scientific calculations belong in independently testable modules under `ert`, `ves`, `processing`, and `qualification`. The 2D and 3D inversion engines remain bounded numerical baselines with explicit limitations; no equivalence to RES2DINV is claimed.

## Configuration and logging

User preferences live under `~/.nix-ert` by default. A malformed config is treated as empty preferences so startup remains reliable. Application logs are written to `~/.nix-ert/logs` by the desktop entry point.
