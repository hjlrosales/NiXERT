"""Headless application workflow orchestration.

The workflow service coordinates existing domain services. It contains no
scientific formulas of its own; processing, QC, inversion, visualization, and
reporting remain delegated to their existing modules.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import numpy as np

from nix_ert.ai.assistant import AdvisoryAssistant, ProjectContext
from nix_ert.app.operations import CancellationToken, OperationExecutor, OperationHandle
from nix_ert.data.import_service import ImportResult, import_dat_into_project
from nix_ert.data.models import SurveyType
from nix_ert.data.project import ProjectStore
from nix_ert.data.measurements import MeasurementStatus
from nix_ert.ert.inversion2d import ERTInversionResult, ERTObservation, Mesh2D, invert_ert
from nix_ert.processing.qc import QCStatistics, QCEngine
from nix_ert.processing.versions import VersionRecord, VersionStore
from nix_ert.reports.generator import ReportData
from nix_ert.reports.project_report import write_project_report
from nix_ert.visualization.model2d import ResistivitySection
from nix_ert.visualization.pseudosection import PseudosectionPoint, build_pseudosection
from nix_ert.ves.data import parse_ves
from nix_ert.ves.engine import LayeredEarthModel, VESInversionResult, VESPoint, invert_ves


class WorkflowError(ValueError):
    """Raised when a desktop workflow transition is invalid."""


@dataclass(frozen=True)
class InversionWork:
    survey_id: str
    observations: tuple[ERTObservation, ...]
    mesh: Mesh2D
    initial_resistivity: float
    max_iterations: int
    source_hashes: tuple[str, ...]
    active_measurement_keys: tuple[tuple[str | None, int], ...]
    geometry_digest: str = ""
    """Digest of the source-bound electrode geometry used to build ``mesh``.

    Persisted with the work package so a result computed from one geometry can
    never be committed against a different geometry.
    """


@dataclass(frozen=True)
class MeasurementInspection:
    source_id: str | None
    row_number: int
    electrode_configuration: tuple[int, int, int, int]
    measured_resistance: float | None
    apparent_resistivity: float | None
    status: str
    exclusion_reason: str | None
    suspicious_reasons: tuple[str, ...]


@dataclass(frozen=True)
class ModelInspection:
    version_id: str
    name: str
    source_hashes: tuple[str, ...]
    cell_count: int
    resistivity_minimum: float
    resistivity_maximum: float
    iteration_count: int | None
    rms_percent: float | None
    converged: bool | None
    semantics: tuple[str, ...]


@dataclass(frozen=True)
class WorkflowSnapshot:
    project_name: str | None
    survey_id: str | None
    survey_name: str | None
    survey_type: str | None
    imported_sources: int
    measurements: int
    active: int
    flagged: int
    excluded: int
    invalid: int
    selected_version_id: str | None
    processing_state: str
    inversion_state: str
    semantics: tuple[str, ...]


class ERTWorkflow:
    """Coordinate the project-to-report workflow without duplicating engines."""

    SEMANTICS = (
        "Pseudosection depth is a display proxy, not inversion depth.",
        "Flat-coordinate model depth is not elevation or topography.",
        "The 3D view is not proof of a true 3D geological inversion.",
        "DEM/GIS metadata does not imply automatic reprojection or correction.",
        "Interpretations and AI findings are advisory, not geological certainty.",
    )

    def __init__(self, store: ProjectStore):
        if store.connection is None:
            raise RuntimeError("Project store must be open")
        self.store = store
        self.survey_id: str | None = None
        self.selected_version_id: str | None = None

    def select_survey(self, survey_id: str) -> None:
        survey = self.store.get_survey(survey_id)
        if survey is None:
            raise WorkflowError(f"Unknown survey: {survey_id}")
        self.survey_id = survey_id
        self.selected_version_id = None

    def import_dat(self, source_path: Path | str) -> ImportResult:
        survey = self._survey()
        if survey.survey_type not in (SurveyType.ERT, SurveyType.ERT_3D):
            raise WorkflowError("DAT import is available only for ERT and 3D ERT surveys")
        return import_dat_into_project(self.store, survey.id, source_path)

    def qc_statistics(self) -> QCStatistics:
        return QCEngine(self.store).statistics(self._survey().id)

    def qc_flags(self):
        return QCEngine(self.store).inspect(self._survey().id)

    def flag_detected(self) -> int:
        return len(QCEngine(self.store).flag_detected(self._survey().id))

    def build_pseudosection(self, *, include_excluded: bool = False) -> tuple[PseudosectionPoint, ...]:
        survey = self._survey()
        geometry = self.bound_electrode_geometry()
        measurements = self.store.list_measurements(survey.id)
        maximum = max((max(item.a, item.b, item.m, item.n) for item in measurements), default=0)
        electrodes = [geometry[number] for number in range(1, maximum + 1)]
        return build_pseudosection(measurements, electrodes, include_excluded=include_excluded)

    def bound_electrode_geometry(self) -> dict[int, float]:
        """Return the source-bound electrode geometry for the selected survey.

        Geometry comes from the per-source electrode rows recorded at import,
        never from survey-level spacing metadata. The method fails closed when
        the imported sources cannot be represented by the flat 2D finite-volume
        model:

        * every active electrode number must have exactly one position, so one
          source cannot silently move another source's electrodes;
        * electrode numbers must be contiguous from 1 and increase with ``x``,
          because the 2D engine maps electrode *n* to column *n-1*;
        * off-line (``y``) positions and non-zero elevations (topography) are
          rejected instead of being flattened;
        * measurements referencing an electrode with no recorded geometry are
          rejected.
        """
        survey = self._survey()
        records = self.store.list_electrodes(survey.id)
        if not records:
            raise WorkflowError("The selected survey has no imported electrode geometry")
        positions: dict[int, float] = {}
        owners: dict[int, str] = {}
        for source_id, number, x, y, elevation in records:
            if not np.isfinite(x) or not np.isfinite(y) or (elevation is not None and not np.isfinite(elevation)):
                raise WorkflowError(f"Electrode {number} has a non-finite coordinate in the project store")
            if number < 1:
                raise WorkflowError(f"Electrode numbers must be positive; found {number}")
            if y != 0.0:
                raise WorkflowError(
                    f"Electrode {number} is recorded {y:g} m off the survey line; "
                    "off-line geometry is not supported by the 2D model"
                )
            if elevation not in (None, 0.0):
                raise WorkflowError(
                    f"Electrode {number} has elevation {elevation:g} m; topography is not supported "
                    "and is rejected rather than flattened"
                )
            if number in positions:
                if positions[number] != x:
                    raise WorkflowError(
                        f"Imported sources disagree about electrode {number}: "
                        f"{positions[number]:g} m versus {x:g} m; import a consistent geometry"
                    )
                continue
            positions[number] = x
            owners[number] = source_id
        expected = set(range(1, max(positions) + 1))
        missing = sorted(expected - set(positions))
        if missing:
            raise WorkflowError(f"Electrode geometry is incomplete; electrode numbers {missing[:5]} are missing")
        numbers = sorted(positions)
        if any(positions[right] <= positions[left] for left, right in zip(numbers, numbers[1:])):
            raise WorkflowError("Electrode x coordinates must increase with electrode number")
        for item in self.store.list_measurements(survey.id):
            for electrode in (item.a, item.b, item.m, item.n):
                if electrode not in positions:
                    raise WorkflowError(
                        f"Measurement row {item.row_number} references electrode {electrode}, "
                        "which has no imported geometry"
                    )
        return positions

    @staticmethod
    def _geometry_digest(geometry: Mapping[int, float]) -> str:
        payload = json.dumps(
            [[number, format(geometry[number], ".12g")] for number in sorted(geometry)],
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def process_ert(self) -> VersionRecord:
        """Persist a reproducible processing snapshot of the active dataset."""
        survey = self._survey()
        measurements = self.store.list_measurements(survey.id)
        active = [
            item for item in measurements
            if item.status != MeasurementStatus.EXCLUDED
            and item.apparent_resistivity is not None
            and np.isfinite(item.apparent_resistivity)
            and item.apparent_resistivity > 0
        ]
        if not active:
            raise WorkflowError("No active positive apparent-resistivity measurements are available")
        source_hashes = tuple(item["sha256"] for item in self.store.list_imports(survey.id))
        active_keys = [
            [item.source_id, item.row_number]
            for item in active
        ]
        stats = self.qc_statistics()
        metadata = survey.metadata.get("import", {})
        version = VersionStore(self.store).create(
            survey.id,
            "processing",
            "Active apparent-resistivity dataset",
            {
                "active_measurements": len(active),
                "excluded_measurements": stats.excluded,
                "array_type": metadata.get("array_type", "unknown"),
            },
            {
                "active_rows": [item.row_number for item in active],
                "active_measurement_keys": active_keys,
                "source_hashes": list(source_hashes),
                "source_count": len(source_hashes),
            },
        )
        self.selected_version_id = version.id
        return version

    def _prepare_2d_inversion(self, *, max_iterations: int = 3) -> InversionWork:
        survey = self._survey()
        if survey.survey_type is not SurveyType.ERT:
            raise WorkflowError("The integrated 2D workflow requires an ERT survey")
        measurements = self.store.list_measurements(survey.id)
        usable = [
            item for item in measurements
            if item.status != MeasurementStatus.EXCLUDED
            and item.apparent_resistivity is not None
            and np.isfinite(item.apparent_resistivity)
            and item.apparent_resistivity > 0
            and len({item.a, item.b, item.m, item.n}) == 4
        ]
        if not usable:
            raise WorkflowError("No active valid quadrupoles are available for 2D inversion")
        maximum = max(max(item.a, item.b, item.m, item.n) for item in usable)
        if maximum < 4:
            raise WorkflowError("At least four electrodes are required for 2D inversion")
        geometry = self.bound_electrode_geometry()
        positions = [geometry[number] for number in range(1, maximum + 1)]
        spacing = float(np.median(np.diff(positions)))
        if not np.isfinite(spacing) or spacing <= 0:
            raise WorkflowError("Imported electrode geometry has no positive spacing")
        mesh = Mesh2D.from_electrodes(
            positions,
            nz=3,
            depth=max(spacing * 3.0, spacing),
        )
        observations = tuple(
            ERTObservation(item.a, item.b, item.m, item.n, float(item.apparent_resistivity))
            for item in usable
        )
        source_hashes = tuple(item["sha256"] for item in self.store.list_imports(survey.id))
        active_keys = tuple((item.source_id, item.row_number) for item in usable)
        return InversionWork(
            survey.id, observations, mesh,
            float(np.median([item.apparent_resistivity for item in usable])),
            max_iterations, source_hashes, active_keys,
            self._geometry_digest(geometry),
        )

    def start_invert_2d(
        self, executor: OperationExecutor, *, max_iterations: int = 3,
    ) -> tuple[OperationHandle[ERTInversionResult], InversionWork]:
        """Compute a detached inversion asynchronously; persistence is not automatic."""
        work = self._prepare_2d_inversion(max_iterations=max_iterations)

        def compute(token: CancellationToken) -> ERTInversionResult:
            token.update(progress=0.0, detail="Computing detached 2D inversion")
            result = invert_ert(
                work.observations, work.mesh, work.initial_resistivity,
                max_iterations=work.max_iterations,
            )
            token.update(progress=1.0, detail="2D inversion complete", iteration=len(result.iterations))
            return result

        return executor.submit("2D baseline inversion", compute), work

    def commit_inversion(self, result: ERTInversionResult, work: InversionWork) -> VersionRecord:
        """Persist a completed detached result after checking its input is still current."""
        if self.survey_id != work.survey_id:
            raise WorkflowError("The selected survey changed while inversion was running")
        current = self._prepare_2d_inversion(max_iterations=work.max_iterations)
        if current.source_hashes != work.source_hashes or current.active_measurement_keys != work.active_measurement_keys:
            raise WorkflowError("Working data changed while inversion was running; result was discarded")
        if current.geometry_digest != work.geometry_digest or current.mesh.x_edges != work.mesh.x_edges:
            raise WorkflowError("Electrode geometry changed while inversion was running; result was discarded")
        source_hashes = list(work.source_hashes)
        active_keys = [list(item) for item in work.active_measurement_keys]
        version = VersionStore(self.store).create(
            work.survey_id,
            "inversion",
            "2D baseline inversion",
            {
                "engine": "finite-volume-2d-baseline",
                "max_iterations": work.max_iterations,
                "initial_resistivity": work.initial_resistivity,
            },
            {
                "rms_log10": result.rms_log10,
                "rms_percent": result.rms_percent,
                "converged": result.converged,
                "message": result.message,
                "iterations": len(result.iterations),
                "x_edges": list(work.mesh.x_edges),
                "depth_edges": list(work.mesh.depth_edges),
                "resistivity": result.resistivity.tolist(),
                "active_measurement_keys": active_keys,
                "source_hashes": source_hashes,
                "geometry_digest": work.geometry_digest,
            },
        )
        self.selected_version_id = version.id
        return version

    def invert_2d(self, *, max_iterations: int = 3) -> ERTInversionResult:
        work = self._prepare_2d_inversion(max_iterations=max_iterations)
        result = invert_ert(
            work.observations, work.mesh, work.initial_resistivity,
            max_iterations=work.max_iterations,
        )
        self.commit_inversion(result, work)
        return result


    def inspect_3d_status(self) -> dict[str, object]:
        """Expose the 3D boundary without presenting a 2D model as 3D."""
        survey = self._survey()
        versions = self._versions_for_survey(survey.id)
        available = any(version.kind == "inversion-3d" for version in versions)
        return {"available": available, "reason": "No persisted 3D inversion model is selected" if not available else "Persisted 3D model available"}

    def selected_model_section(self) -> ResistivitySection:
        version = self._selected_version()
        if version.kind != "inversion":
            raise WorkflowError("The selected version does not contain an inversion model")
        try:
            snapshot = version.snapshot
            return ResistivitySection(
                tuple(float(value) for value in snapshot["x_edges"]),
                tuple(float(value) for value in snapshot["depth_edges"]),
                np.asarray(snapshot["resistivity"], dtype=float),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise WorkflowError("Selected inversion snapshot is incomplete") from exc

    def inspect_measurements(self) -> tuple[MeasurementInspection, ...]:
        """Return source-aware measurement facts without changing project state."""
        flags = {
            (flag.source_id, flag.row_number): flag.reasons
            for flag in self.qc_flags()
        }
        return tuple(
            MeasurementInspection(
                item.source_id,
                item.row_number,
                (item.a, item.b, item.m, item.n),
                item.resistance,
                item.apparent_resistivity,
                item.status.value,
                item.quality,
                tuple(flags.get((item.source_id, item.row_number), ())),
            )
            for item in self.store.list_measurements(self._survey().id)
        )

    def inspect_model(self) -> ModelInspection:
        """Summarize the selected persisted model and its display semantics."""
        version = self._selected_version()
        if version.kind != "inversion":
            raise WorkflowError("The selected version does not contain an inversion model")
        snapshot = version.snapshot
        try:
            values = np.asarray(snapshot["resistivity"], dtype=float)
            if values.size == 0 or not np.all(np.isfinite(values)) or np.any(values <= 0):
                raise ValueError("resistivity values are invalid")
            source_hashes = tuple(str(value) for value in snapshot["source_hashes"])
        except (KeyError, TypeError, ValueError) as exc:
            raise WorkflowError("Selected inversion snapshot is incomplete") from exc
        return ModelInspection(
            version.id,
            version.name,
            source_hashes,
            int(values.size),
            float(values.min()),
            float(values.max()),
            int(snapshot["iterations"]) if snapshot.get("iterations") is not None else None,
            float(snapshot["rms_percent"]) if snapshot.get("rms_percent") is not None else None,
            bool(snapshot["converged"]) if snapshot.get("converged") is not None else None,
            self.SEMANTICS,
        )

    def report(self, path: Path | str, *, interpretation: Mapping[str, object] | None = None) -> ReportData:
        return write_project_report(
            self.store,
            self._survey().id,
            path,
            version_id=self.selected_version_id,
            interpretation=interpretation,
        )

    def assistant(self) -> AdvisoryAssistant:
        """Return a thin local factory for the bounded advisory assistant."""
        return AdvisoryAssistant(ProjectContext.from_store(self.store), QCEngine(self.store))

    def snapshot(self) -> WorkflowSnapshot:
        metadata = self.store.load_metadata()
        survey = self.store.get_survey(self.survey_id) if self.survey_id else None
        if survey is None:
            return WorkflowSnapshot(
                metadata.name if metadata else None, None, None, None, 0, 0, 0, 0, 0, 0,
                self.selected_version_id, "not started", "not started", self.SEMANTICS,
            )
        stats = self.qc_statistics()
        versions = self._versions_for_survey(survey.id)
        has_processing = any(version.kind == "processing" for version in versions)
        has_inversion = any(version.kind == "inversion" for version in versions)
        return WorkflowSnapshot(
            metadata.name if metadata else None,
            survey.id,
            survey.name,
            survey.survey_type.value,
            len(self.store.list_imports(survey.id)),
            stats.total,
            stats.active,
            stats.flagged,
            stats.excluded,
            stats.invalid,
            self.selected_version_id,
            "complete" if has_processing else "available",
            "complete" if has_inversion else "available",
            self.SEMANTICS,
        )

    def _survey(self):
        if self.survey_id is None:
            raise WorkflowError("Select a survey before using this workflow")
        survey = self.store.get_survey(self.survey_id)
        if survey is None:
            raise WorkflowError("The selected survey is no longer available")
        return survey

    def _versions_for_survey(self, survey_id: str) -> list[VersionRecord]:
        assert self.store.connection is not None
        exists = self.store.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'versions'"
        ).fetchone()
        if exists is None:
            return []
        return VersionStore(self.store, create=False).list(survey_id)

    def _selected_version(self) -> VersionRecord:
        if self.selected_version_id is None:
            raise WorkflowError("Select or create an inversion model first")
        versions = _version_store_read_only(self.store)
        version = versions.get(self.selected_version_id) if versions else None
        if version is None or version.survey_id != self._survey().id:
            raise WorkflowError("Selected model/version is not available for this survey")
        return version


@dataclass(frozen=True)
class VESWorkflowSnapshot:
    project_name: str | None
    survey_id: str
    survey_name: str
    point_count: int
    selected_version_id: str | None
    processing_state: str
    inversion_state: str
    semantics: tuple[str, ...]


class VESWorkflow:
    """Coordinate the persisted VES curve and 1D interpretation workflow.

    VES observations do not fit the ERT A/B/M/N measurement table.  The
    existing immutable ``versions`` contract is therefore used as the single
    project-bound persistence mechanism: curve points and inversion results are
    stored in version snapshots, never in a parallel UI-only model.
    """

    SEMANTICS = (
        "VES uses AB/2 and MN/2 Schlumberger half-spacings.",
        "The layered-earth result is a mathematical 1D interpretation, not unique geology.",
        "Interpretation and Assistant output remain advisory.",
    )

    def __init__(self, store: ProjectStore):
        if store.connection is None:
            raise RuntimeError("Project store must be open")
        self.store = store
        self.survey_id: str | None = None
        self.selected_version_id: str | None = None
        self.points: tuple[VESPoint, ...] = ()

    def select_survey(self, survey_id: str) -> None:
        survey = self.store.get_survey(survey_id)
        if survey is None:
            raise WorkflowError(f"Unknown survey: {survey_id}")
        if survey.survey_type is not SurveyType.VES:
            raise WorkflowError("VES workflow requires a VES survey")
        self.survey_id = survey_id
        self.selected_version_id = None
        self.points = ()

    def _survey(self):
        if self.survey_id is None:
            raise WorkflowError("Select a VES survey before using this workflow")
        survey = self.store.get_survey(self.survey_id)
        if survey is None:
            raise WorkflowError("The selected VES survey is no longer available")
        return survey

    def import_text(self, text: str, source_name: str = "VES input") -> tuple[VESPoint, ...]:
        points = parse_ves(text, source_name)
        survey = self._survey()
        source_bytes = text.encode("utf-8")
        survey.metadata = {
            **survey.metadata,
            "ves_input": {
                "source_name": source_name,
                "sha256": hashlib.sha256(source_bytes).hexdigest(),
                "byte_count": len(source_bytes),
            },
        }
        self.store.update_survey(survey)
        self.points = points
        return points

    def process(self) -> VersionRecord:
        self._survey()
        if not self.points:
            raise WorkflowError("Import VES points before processing")
        snapshot = {
            "points": [
                {"ab2": point.ab2, "mn2": point.mn2, "resistance": point.resistance,
                 "apparent_resistivity": point.apparent_resistivity, "excluded": point.excluded}
                for point in self.points
            ],
            "source_name": "user-supplied VES input",
            "source_sha256": self._survey().metadata.get("ves_input", {}).get("sha256"),
            "semantics": list(self.SEMANTICS),
        }
        version = VersionStore(self.store).create(
            self.survey_id, "ves-processing", "VES curve processing", {}, snapshot
        )
        self.selected_version_id = version.id
        return version

    def invert(self, initial_model: LayeredEarthModel, *, max_nfev: int = 200) -> VESInversionResult:
        self._survey()
        if not self.points:
            raise WorkflowError("Import VES points before inversion")
        result = invert_ves(self.points, initial_model, max_nfev=max_nfev)
        version = VersionStore(self.store).create(
            self.survey_id, "ves-inversion", "VES 1D layered-earth inversion",
            {"max_nfev": max_nfev, "initial_resistivities": list(initial_model.resistivities),
             "initial_thicknesses": list(initial_model.thicknesses)},
            {"points": [point.__dict__ for point in self.points],
             "resistivities": list(result.model.resistivities),
             "thicknesses": list(result.model.thicknesses),
             "predicted": list(result.predicted),
             "residuals_log10": list(result.residuals_log10),
             "rms_log10": result.rms_log10, "rms_percent": result.rms_percent,
             "converged": result.converged, "iterations": result.iterations,
             "message": result.message, "semantics": list(self.SEMANTICS)},
        )
        self.selected_version_id = version.id
        return result

    def inspect_3d_status(self) -> dict[str, object]:
        """Report whether a true persisted 3D model is available for inspection."""
        self._survey()
        return {"available": False, "reason": "No true 3D model is produced by the VES workflow"}

    def inspect(self) -> dict[str, object]:
        self._survey()
        if not self.points:
            raise WorkflowError("No VES points have been imported")
        return {"point_count": len(self.points), "ab2_range": (min(p.ab2 for p in self.points), max(p.ab2 for p in self.points)),
                "rho_range": (min(p.apparent_resistivity or 0 for p in self.points), max(p.apparent_resistivity or 0 for p in self.points)),
                "semantics": self.SEMANTICS}

    def report(self, path: Path | str, *, interpretation: Mapping[str, object] | None = None) -> ReportData:
        return write_project_report(self.store, self._survey().id, path, version_id=self.selected_version_id, interpretation=interpretation)

    def snapshot(self) -> VESWorkflowSnapshot:
        survey = self._survey()
        metadata = self.store.load_metadata()
        versions = _version_store_read_only(self.store)
        records = versions.list(survey.id) if versions else []
        return VESWorkflowSnapshot(metadata.name if metadata else None, survey.id, survey.name,
            len(self.points), self.selected_version_id,
            "complete" if any(v.kind == "ves-processing" for v in records) else "available",
            "complete" if any(v.kind == "ves-inversion" for v in records) else "available", self.SEMANTICS)


def _version_store_read_only(store: ProjectStore) -> VersionStore | None:
    assert store.connection is not None
    exists = store.connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'versions'"
    ).fetchone()
    return VersionStore(store, create=False) if exists else None
