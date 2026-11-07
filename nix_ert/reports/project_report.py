"""Project-bound report assembly from current persisted state."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from nix_ert import __version__
from nix_ert.data.models import SurveyType
from nix_ert.data.project import ProjectStore
from nix_ert.processing.qc import QCEngine
from nix_ert.processing.versions import VersionRecord, VersionStore
from nix_ert.reports.generator import ReportData, write_report


class ReportAssemblyError(ValueError):
    """Raised when a report cannot establish current project provenance."""


def _version_store(store: ProjectStore) -> VersionStore | None:
    """Return a non-creating version reader for legacy projects."""
    assert store.connection is not None
    exists = store.connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'versions'"
    ).fetchone()
    return VersionStore(store, create=False) if exists else None


def _current_measurement_keys(store: ProjectStore, survey_id: str) -> list[list[object]]:
    return [
        [item.source_id, item.row_number]
        for item in store.list_measurements(survey_id)
        if item.status.value != "EXCLUDED"
        and item.apparent_resistivity is not None
        and isinstance(item.apparent_resistivity, (int, float))
        and math.isfinite(item.apparent_resistivity)
        and item.apparent_resistivity > 0
    ]


def _version_provenance(
    store: ProjectStore,
    survey_id: str,
    version: VersionRecord | None,
) -> str:
    if version is None:
        return "No persisted processing/model version selected"
    snapshot = version.snapshot
    stored_hashes = snapshot.get("source_hashes")
    stored_keys = snapshot.get("active_measurement_keys")
    if not isinstance(stored_hashes, list) or not isinstance(stored_keys, list):
        return "Manual/unlinked version; current dataset match cannot be established"
    current_hashes = [item["sha256"] for item in store.list_imports(survey_id)]
    current_keys = _current_measurement_keys(store, survey_id)
    if stored_hashes != current_hashes or stored_keys != current_keys:
        return "Stale version; source or active measurement state differs from the selected model"
    return "Current selected version matches persisted source hashes and active measurement keys"


def _state_fingerprint(
    store: ProjectStore,
    survey_id: str,
    version: VersionRecord | None,
) -> str:
    """Hash the exact persisted state represented by a generated report."""
    survey = store.get_survey(survey_id)
    if survey is None:
        raise ReportAssemblyError(f"Unknown survey: {survey_id}")
    measurements = [
        {
            "source_id": item.source_id,
            "row_number": item.row_number,
            "a": item.a,
            "b": item.b,
            "m": item.m,
            "n": item.n,
            "apparent_resistivity": item.apparent_resistivity,
            "resistance": item.resistance,
            "current": item.current,
            "voltage": item.voltage,
            "status": item.status.value,
            "quality": item.quality,
            "extra": item.extra,
        }
        for item in store.list_measurements(survey_id)
    ]
    payload = {
        "project": store.load_metadata().__dict__,
        "survey": {
            "id": survey.id,
            "name": survey.name,
            "type": survey.survey_type.value,
            "metadata": survey.metadata,
        },
        "imports": store.list_imports(survey_id),
        "measurements": measurements,
        "version": ({
            "id": version.id,
            "kind": version.kind,
            "parameters": version.parameters,
            "snapshot": version.snapshot,
        } if version is not None else None),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
def _record_to_inversion(record: VersionRecord, provenance: str) -> dict[str, object]:
    values: dict[str, object] = {
        "Selected version": record.name,
        "Version ID": record.id,
        "Version kind": record.kind,
        "Parameter hash": record.parameter_hash,
        "Parent version": record.parent_id or "—",
        "Notes": record.notes or "—",
        "Provenance status": provenance,
    }
    values.update({str(key): value for key, value in record.parameters.items()})
    values.update({str(key): value for key, value in record.snapshot.items()})
    return values


def build_project_report(
    store: ProjectStore,
    survey_id: str,
    *,
    version_id: str | None = None,
    interpretation: Mapping[str, object] | None = None,
) -> ReportData:
    """Build report data from the currently open project database.

    This function deliberately does not accept arbitrary project metadata or
    manually supplied survey rows. Every project/survey/source/QC/version value
    is read from the supplied live store. A selected version must belong to the
    selected survey.
    """
    metadata = store.load_metadata()
    survey = store.get_survey(survey_id)
    if survey is None:
        raise ReportAssemblyError(f"Unknown survey: {survey_id}")
    if metadata is None:
        raise ReportAssemblyError("Project metadata is missing; report provenance is incomplete")

    imports = store.list_imports(survey_id)
    source_problems = store.verify_import_sources(survey_id)
    if source_problems:
        raise ReportAssemblyError(
            "Report provenance cannot be verified: " + "; ".join(source_problems)
        )
    measurements = store.list_measurements(survey_id)
    qc = QCEngine(store).statistics(survey_id)
    version: VersionRecord | None = None
    versions = _version_store(store)
    if version_id is not None:
        if versions is None:
            raise ReportAssemblyError("Selected model/version is unavailable in this project")
        version = versions.get(version_id)
        if version is None or version.survey_id != survey_id:
            raise ReportAssemblyError("Selected model/version does not belong to this survey")

    source_rows = [
        {
            "Source": item["original_name"],
            "SHA-256": item["sha256"],
            "Bytes": item["byte_count"],
            "Stored path": item["stored_path"],
        }
        for item in imports
    ]
    ves_input = survey.metadata.get("ves_input")
    if isinstance(ves_input, dict) and ves_input.get("sha256"):
        source_rows.append({
            "Source": ves_input.get("source_name", "VES input"),
            "SHA-256": ves_input["sha256"],
            "Bytes": ves_input.get("byte_count", "—"),
            "Provenance": "Manually supplied VES input; no LS2 acquisition claimed",
        })
    project = {
        "Project": metadata.name,
        "Client": metadata.client,
        "Location": metadata.location,
        "Survey date": metadata.survey_date.isoformat() if metadata.survey_date else "—",
        "Operator": metadata.operator,
        "Instrument": metadata.instrument,
        "Software version": __version__,
        "Provenance": "Current persisted project state",
    }
    survey_rows = [{
        "Survey": survey.name,
        "Type": survey.survey_type.value,
        "Survey ID": survey.id,
        "Measurements": len(measurements),            "Sources": len(imports),
            "Source datasets": source_rows or "No imported source recorded",
            "Coordinate/topography context": survey.metadata.get("coordinate_context", "Not supplied"),
    }]
    qc_summary = {
        "Total measurements": qc.total,
        "Active": qc.active,
        "Flagged": qc.flagged,
        "Excluded": qc.excluded,
        "Invalid apparent resistivity": qc.invalid,
        "Duplicate tuples": qc.duplicate,
        "Minimum apparent resistivity": qc.minimum_apparent_resistivity,
        "Maximum apparent resistivity": qc.maximum_apparent_resistivity,
        "Median apparent resistivity": qc.median_apparent_resistivity,
        "Excluded data handling": "Excluded working statuses are retained and counted; raw rows are immutable",
        "Qualification status": "Baseline workflow report; external benchmark status is not validated",
    }
    provenance_status = _version_provenance(store, survey_id, version)
    inversion = _record_to_inversion(version, provenance_status) if version else {
        "Selected version": "None",
        "Provenance": provenance_status,
    }
    appendices = [
        json.dumps(
            {"source_datasets": source_rows, "generated_from_survey": survey.id},
            sort_keys=True,
            default=str,
        ),
    ]
    if interpretation:
        interpretation_rows = (dict(interpretation),)
    else:
        interpretation_rows = ({
            "Status": "No interpretation supplied",
            "Meaning": "This report does not invent geological conclusions.",
        },)
    state_fingerprint = _state_fingerprint(store, survey_id, version)
    inversion["State fingerprint"] = state_fingerprint
    limitations = (
        "Pseudosection depth is a display proxy, not inversion depth.",
        "2D/3D models are baseline numerical products; they do not establish geological certainty.",
        "DEM/GIS metadata does not imply automatic reprojection or topographic correction.",
        "Direct Terrameter LS2 hardware communication remains blocked pending official protocol documentation and validated fixtures.",
        "External benchmark comparison remains NOT VALIDATED; RES2DINV equivalence is not claimed.",
        "This report does not invent geological conclusions or recommendations; interpretation must be supplied by the user.",
    )
    provenance = {
        "Software": f"NiX ERT {__version__}",
        "Project": metadata.name,
        "Survey ID": survey.id,
        "Survey": survey.name,
        "Survey type": survey.survey_type.value,
        "Selected version": version.name if version is not None else "None",
        "Selected version ID": version.id if version is not None else "—",
        "Version parameter hash": version.parameter_hash if version is not None else "—",
        "Source SHA-256": [item["sha256"] for item in imports]
        if imports
        else "No imported source recorded",
        "State fingerprint": state_fingerprint,
        "Dataset match": provenance_status,
        "Qualification scope": (
            "Supported offline workflow; external benchmark NOT VALIDATED; "
            "RES2DINV equivalence not claimed"
        ),
        "Raw data handling": "Raw source bytes are preserved; report generation never modifies them",
    }
    return ReportData(
        title=f"NiX ERT Report — {metadata.name} — {survey.name}",
        project=project,
        surveys=tuple(survey_rows),
        qc_summary=qc_summary,
        inversion=inversion,
        interpretation=interpretation_rows,
        appendices=tuple(appendices),
        generated_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        provenance=provenance,
        limitations=limitations,
    )


def write_project_report(
    store: ProjectStore,
    survey_id: str,
    path: Path | str,
    *,
    version_id: str | None = None,
    interpretation: Mapping[str, object] | None = None,
) -> ReportData:
    """Write a current-state report and record its provenance in SQLite."""
    data = build_project_report(store, survey_id, version_id=version_id, interpretation=interpretation)
    destination = Path(path)
    write_report(data, destination)
    imports = store.list_imports(survey_id)
    versions = _version_store(store)
    selected_version = versions.get(version_id) if versions is not None and version_id is not None else None
    store.record_report_run(
        survey_id=survey_id,
        version_id=version_id,
        source_hashes=tuple(item["sha256"] for item in imports),
        output_path=destination,
        state_fingerprint=_state_fingerprint(store, survey_id, selected_version),
    )
    return data
