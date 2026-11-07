"""Semantic qualification for the factual ABEM intermediate representation.

Qualification is deliberately separate from SQLite parsing and NiX persistence.
It applies only the evidence explicitly recorded for the supplied Barugo
fixtures; it never promotes an unknown database pattern to a vendor meaning.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from nix_ert.data.abem_intermediate import (
    ABEMIntermediateProject,
    FactStatus,
    RawField,
    SourceLocation,
)


class QualificationStatus(str, Enum):
    """Result of qualifying one semantic or factual import prerequisite."""

    VERIFIED = "verified"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"
    INVALID = "invalid"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class AuthorizedDatasetEvidence:
    """Explicit vendor evidence for exact known source combinations.

    This is intentionally an allow-list, not a classifier. A source is matched
    only by its documented hash, task name, and protocol file. No filename,
    table name, array code, or numeric pattern is used to infer its kind.
    """

    source_sha256: str
    dataset_kind: str
    task_name: str
    protocol_file: str
    citation: str


@dataclass(frozen=True)
class QualificationResult:
    """Qualification outcome with factual evidence and import impact."""

    name: str
    source: tuple[SourceLocation, ...]
    observed_fact: str
    interpretation: str | None
    status: QualificationStatus
    blocks_import: bool
    evidence: str
    required_vendor_evidence: str | None = None


@dataclass(frozen=True)
class ABEMQualificationReport:
    """Deterministic semantic qualification report for one intermediate parse."""

    source_path: Path
    source_sha256: str
    results: tuple[QualificationResult, ...]
    importer_readiness: str

    @property
    def importer_ready(self) -> bool:
        return self.importer_readiness == "READY"

    def result(self, name: str) -> QualificationResult:
        for result in self.results:
            if result.name == name:
                return result
        raise KeyError(name)

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic report suitable for inspection/tests."""
        return {
            "source_path": str(self.source_path),
            "source_sha256": self.source_sha256,
            "importer_readiness": self.importer_readiness,
            "importer_ready": self.importer_ready,
            "results": [
                {
                    "name": result.name,
                    "source": [location.describe() for location in result.source],
                    "observed_fact": result.observed_fact,
                    "interpretation": result.interpretation,
                    "status": result.status.value,
                    "blocks_import": result.blocks_import,
                    "evidence": result.evidence,
                    "required_vendor_evidence": result.required_vendor_evidence,
                }
                for result in self.results
            ],
        }


# These are the exact source facts already recorded in the Barugo contract and
# readiness assessment. They are not a general ABEM code table.
DOCUMENTED_BARUGO_EVIDENCE: tuple[AuthorizedDatasetEvidence, ...] = (
    AuthorizedDatasetEvidence(
        "057674127c923842510ee5e8af6082fed88ef152438f3752ca681d5f2f6d47af",
        "ERT",
        "Gradient_1",
        "/home/root/protocols/Gradient_2x21.xml",
        "docs/barugo_import_readiness.md: supplied Barugo ERT evidence",
    ),
    AuthorizedDatasetEvidence(
        "97eec29b3f9870092f9674e54b560df20f9df2130ac18778ff29161757d09e51",
        "VES",
        "VES Schlumberger_1",
        "/home/root/protocols/VES_Schlumberger.xml",
        "docs/barugo_import_readiness.md: supplied Barugo VES evidence",
    ),
)


def _table(project: ABEMIntermediateProject, name: str):
    return project.table(name)


def _first(project: ABEMIntermediateProject, table_name: str, field_name: str) -> RawField | None:
    table = _table(project, table_name)
    if table is None or not table.rows:
        return None
    return table.rows[0].field(field_name)


def _all_sources(project: ABEMIntermediateProject, table_name: str, field_name: str) -> tuple[SourceLocation, ...]:
    table = _table(project, table_name)
    if table is None:
        return ()
    return tuple(
        field.source
        for record in table.rows
        for field in (record.field(field_name),)
        if field is not None
    )


def _result(
    name: str,
    source: tuple[SourceLocation, ...],
    observed_fact: str,
    interpretation: str | None,
    status: QualificationStatus,
    blocks_import: bool,
    evidence: str,
    required_vendor_evidence: str | None = None,
) -> QualificationResult:
    return QualificationResult(
        name, source, observed_fact, interpretation, status, blocks_import,
        evidence, required_vendor_evidence,
    )


def _authorized_kind(
    project: ABEMIntermediateProject,
    evidence: tuple[AuthorizedDatasetEvidence, ...],
) -> tuple[str, AuthorizedDatasetEvidence] | None:
    task = _first(project, "Tasks", "Name")
    protocol = next(
        (
            field
            for record in (_table(project, "TaskSettings").rows if _table(project, "TaskSettings") else ())
            if (setting := record.field("Setting")) is not None
            and setting.value == "ProtocolFile"
            for field in (record.field("Value"),)
            if field is not None
        ),
        None,
    )
    if task is None or protocol is None:
        return None
    for candidate in evidence:
        if (
            project.source_sha256 == candidate.source_sha256
            and task.value == candidate.task_name
            and protocol.value == candidate.protocol_file
        ):
            return candidate.dataset_kind, candidate
    return None


def _relationship_results(project: ABEMIntermediateProject) -> tuple[QualificationResult, ...]:
    sources = tuple(link.source for link in project.observation_links)
    if not project.observation_links:
        result = _result(
            "measurement_relationships",
            (_first(project, "DP_MEASURE", "ID").source,) if _first(project, "DP_MEASURE", "ID") else (),
            "No DP_MEASURE relationships were extracted",
            None,
            QualificationStatus.INVALID,
            True,
            "The intermediate representation contains no observation links.",
            "Provide a non-empty, valid DP_MEASURE observation boundary.",
        )
        return (result,)
    invalid = [link for link in project.observation_links if link.status is FactStatus.INVALID]
    if invalid:
        return (
            _result(
                "measurement_relationships",
                sources,
                f"{len(invalid)} invalid logical DP_MEASURE relationship(s)",
                None,
                QualificationStatus.INVALID,
                True,
                "Intermediate link checks identified missing, duplicate, or invalid linked records.",
                "Repair the vendor relationship or supply an authorized relationship definition.",
            ),
        )
    return (
        _result(
            "measurement_relationships",
            sources,
            f"{len(project.observation_links)} logical DP_MEASURE links are structurally valid",
            "The links may be retained as source identity and relationship facts.",
            QualificationStatus.VERIFIED,
            False,
            "The intermediate parser checked DP_MEASURE → DP_ABMN, Measures, and DPV values.",
        ),
    )


def qualify_abem(
    project: ABEMIntermediateProject,
    *,
    evidence: tuple[AuthorizedDatasetEvidence, ...] = DOCUMENTED_BARUGO_EVIDENCE,
) -> ABEMQualificationReport:
    """Qualify an intermediate parse without creating or changing NiX records."""
    task = _first(project, "Tasks", "Name")
    array_code = _first(project, "Tasks", "ArrayCode")
    spacing = _first(project, "Tasks", "SpacingX")
    protocol = next(
        (
            record.field("Value")
            for record in (_table(project, "TaskSettings").rows if _table(project, "TaskSettings") else ())
            if (setting := record.field("Setting")) is not None
            and setting.value == "ProtocolFile"
            and record.field("Value") is not None
        ),
        None,
    )
    task_sources = tuple(field.source for field in (task, array_code, spacing, protocol) if field is not None)
    authorized = _authorized_kind(project, evidence)
    if authorized is None:
        kind_result = _result(
            "dataset_kind",
            task_sources,
            f"Task={task.value if task else None!r}; protocol={protocol.value if protocol else None!r}",
            None,
            QualificationStatus.BLOCKED,
            True,
            "The parser preserved task/protocol text, but no exact authorized evidence entry matched source hash, task, and protocol.",
            "Provide an authorized source-specific ERT/VES classification for this exact file/task/protocol combination.",
        )
        kind = None
    else:
        kind, candidate = authorized
        kind_result = _result(
            "dataset_kind",
            task_sources,
            f"Authorized source is classified as {kind}",
            kind,
            QualificationStatus.VERIFIED,
            False,
            candidate.citation,
        )

    results: list[QualificationResult] = [kind_result]
    source_location = (SourceLocation(str(project.source_path)),)
    if len(project.source_sha256) == 64 and project.byte_count >= 0:
        results.append(_result(
            "source_provenance",
            source_location,
            f"SHA-256={project.source_sha256}; byte_count={project.byte_count}",
            "The source identity can be retained as immutable provenance.",
            QualificationStatus.VERIFIED,
            False,
            "The intermediate parser read the source read-only and recorded hash and size.",
        ))
    else:
        results.append(_result(
            "source_provenance", source_location, "Source hash or byte count is invalid", None,
            QualificationStatus.INVALID, True, "Provenance is required before qualification.",
            "Provide a stable source hash and byte count.",
        ))

    if project.status is FactStatus.INVALID:
        results.append(_result(
            "intermediate_integrity",
            source_location,
            "; ".join(project.issues) or "Intermediate parse is invalid",
            None,
            QualificationStatus.INVALID,
            True,
            "The factual representation reports structural or source errors.",
            "Repair or replace the source; do not reinterpret an invalid parse.",
        ))
    else:
        results.append(_result(
            "intermediate_integrity", source_location, "Intermediate parse status is observed",
            "The factual representation is available for semantic qualification only.",
            QualificationStatus.VERIFIED, False,
            "SQLite and intermediate structural checks did not report an issue.",
        ))

    if task is not None:
        results.append(_result(
            "project_identity",
            tuple(field.source for field in (_first(project, "ProjectSchemaVersion", "Version"), _first(project, "CommonSchemaVersion", "Version"), _first(project, "Sessions", "InstrumentSerial")) if field is not None),
            "ABEM schema/version and available instrument/session identity fields are present",
            "Source/project identity can be retained as vendor metadata and provenance.",
            QualificationStatus.VERIFIED,
            False,
            "The intermediate representation preserves schema rows and session metadata without normalizing them into a NiX project.",
        ))
        results.append(_result(
            "survey_identity",
            (task.source,),
            f"Tasks.Name={task.value!r}",
            "The vendor task identity can be retained verbatim.",
            QualificationStatus.VERIFIED,
            False,
            "Tasks.Name is directly observed in the intermediate representation.",
        ))
        results.append(_result(
            "measurement_identity",
            tuple(link.source for link in project.observation_links),
            f"{len(project.observation_links)} DP_MEASURE source identities are present",
            "The source link identity can be retained without assigning NiX measurement semantics.",
            QualificationStatus.VERIFIED if project.observation_links else QualificationStatus.INVALID,
            not bool(project.observation_links),
            "DP_MEASURE row provenance and its DPID/MeasureID values are preserved by the intermediate parser.",
            "Provide a non-empty DP_MEASURE observation boundary." if not project.observation_links else None,
        ))
    else:
        results.append(_result(
            "project_identity", (), "Tasks and source identity records are absent", None,
            QualificationStatus.INVALID, True,
            "A project identity cannot be established without the required source records.",
            "Supply valid schema, task, and session identity records.",
        ))
        results.append(_result(
            "survey_identity", (), "Tasks.Name is absent", None,
            QualificationStatus.INVALID, True,
            "A survey identity cannot be established without the task record.",
            "Supply a valid task record.",
        ))
        results.append(_result(
            "measurement_identity", (), "No DP_MEASURE source identities are present", None,
            QualificationStatus.INVALID, True,
            "A measurement identity cannot be established without DP_MEASURE records.",
            "Provide a non-empty DP_MEASURE observation boundary.",
        ))
    results.extend(_relationship_results(project))
    results.append(_result(
        "dp_abmn_geometry_relationship",
        tuple(link.target for link in project.observation_links if link.target is not None),
        "DP_MEASURE targets are linked to DP_ABMN geometry where relationships are valid",
        "Role-labelled raw geometry may be retained without assigning NiX electrode numbers.",
        QualificationStatus.VERIFIED if project.observation_links and not any(link.status is FactStatus.INVALID for link in project.observation_links) else QualificationStatus.INVALID,
        bool(not project.observation_links or any(link.status is FactStatus.INVALID for link in project.observation_links)),
        "Logical relationship evidence only; no electrode semantics are inferred.",
        "Repair missing/invalid geometry links." if project.status is FactStatus.INVALID else None,
    ))
    results.append(_result(
        "dpv_relationship",
        tuple(link.source for link in project.observation_links),
        "DPV rows are retained through the logical DP_MEASURE relationship",
        "Raw DPV rows can be preserved as vendor values; channel/sequence meaning remains unresolved.",
        QualificationStatus.VERIFIED if project.observation_links and not any(link.status is FactStatus.INVALID for link in project.observation_links) else QualificationStatus.INVALID,
        bool(not project.observation_links or any(link.status is FactStatus.INVALID for link in project.observation_links)),
        "The intermediate parser checks presence of DPV values for each link.",
        "Repair missing/invalid DPV relationships." if project.status is FactStatus.INVALID else None,
    ))

    datatypes = _table(project, "Datatype")
    datatype_sources = tuple(
        field.source
        for record in (datatypes.rows if datatypes else ())
        for field in (record.field("Name"), record.field("Unit"))
        if field is not None
    )
    if datatypes and datatypes.rows:
        results.append(_result(
            "vendor_declared_units",
            datatype_sources,
            f"{len(datatypes.rows)} Datatype records with raw labels/units are present",
            "The displayed vendor labels and units may be preserved verbatim.",
            QualificationStatus.VERIFIED, False,
            "Datatype.Name/Unit are directly observed; this does not qualify channel or polarity mappings.",
        ))
    else:
        results.append(_result(
            "vendor_declared_units", datatype_sources, "Datatype records are absent", None,
            QualificationStatus.INVALID, True,
            "No vendor unit records are available.",
            "Supply the Datatype table or an authorized equivalent.",
        ))

    results.extend((
        _result(
            "electrode_positions",
            _all_sources(project, "DP_ABMN", "APosX") + _all_sources(project, "DP_ABMN", "BPosX"),
            "Raw DP_ABMN coordinate fields are present in the intermediate representation",
            "Coordinates may be preserved as vendor facts only.",
            QualificationStatus.VERIFIED if _table(project, "DP_ABMN") else QualificationStatus.INVALID,
            not bool(_table(project, "DP_ABMN")),
            "DP_ABMN coordinate values are observed with table/row/column provenance.",
            "Supply valid DP_ABMN geometry records." if not _table(project, "DP_ABMN") else None,
        ),
        _result(
            "electrode_roles",
            _all_sources(project, "DP_ABMN", "DPKEY"),
            "A/B/M/N role columns exist as raw vendor fields",
            None,
            QualificationStatus.BLOCKED,
            True,
            "Column structure does not establish NiX electrode numbering or switch semantics.",
            "Provide the authoritative role, numbering, and switch-address mapping.",
        ),
        _result(
            "array_and_protocol_semantics",
            task_sources,
            f"Raw ArrayCode={array_code.value if array_code else None!r} and protocol setting are present",
            None,
            QualificationStatus.BLOCKED,
            True,
            "No authoritative numeric array/protocol code table is currently available.",
            "Provide versioned definitions for ArrayCode, ProtocolMode, Mode, ModeValue, and the applicable protocol files.",
        ),
        _result(
            "coordinate_reference_system",
            _all_sources(project, "DP_ABMN", "APosX") + _all_sources(project, "Tasks", "SpacingX"),
            "Raw coordinates and spacing are present where available",
            None,
            QualificationStatus.BLOCKED,
            True,
            "Observed scale or repeated coordinate patterns do not establish units, CRS, datum, or axis rules.",
            "Provide coordinate units/scale, axis/origin, CRS/datum, and GPS semantics, or an explicit local-only policy.",
        ),
        _result(
            "timestamp_records",
            _all_sources(project, "Tasks", "Time") + _all_sources(project, "Sessions", "Time") + _all_sources(project, "Measures", "Time"),
            "Vendor timestamp fields are preserved as raw records",
            "Original timestamp text can be retained without normalization.",
            QualificationStatus.VERIFIED,
            False,
            "Presence and source locations are factual; event/timezone interpretation is not asserted.",
        ),
        _result(
            "timestamp_normalization",
            _all_sources(project, "Tasks", "Time") + _all_sources(project, "Sessions", "Time"),
            "Timestamp event and timezone precedence are not established",
            None,
            QualificationStatus.UNKNOWN,
            False,
            "This is non-blocking when timestamps remain raw metadata.",
            "Provide timezone, clock-source, and event-precedence rules if normalization is required.",
        ),
        _result(
            "qc_and_quality_semantics",
            _all_sources(project, "DPV", "Status") + _all_sources(project, "DP_MEASURE", "Ready") + _all_sources(project, "DP_ABMN", "Ready"),
            "Raw status/readiness fields are present but their meanings are unresolved",
            None,
            QualificationStatus.BLOCKED,
            True,
            "Numeric status patterns cannot establish QC or exclusion semantics.",
            "Provide complete status/readiness bit definitions and exclusion rules.",
        ),
        _result(
            "uncertainty_semantics",
            _all_sources(project, "DPV", "DataSDev") + _all_sources(project, "DPV", "N") + _all_sources(project, "DPV", "MCycles"),
            "Raw deviation/count fields may be preserved",
            None,
            QualificationStatus.BLOCKED,
            True,
            "Field names and numeric values do not establish an uncertainty model.",
            "Provide formulas, units, statistical definitions, and ADC scaling.",
        ),
        _result(
            "observed_vendor_values",
            _all_sources(project, "DPV", "DataValue"),
            "DPV.DataValue records are retained without calculation or reinterpretation",
            "Raw vendor values may be preserved as source facts.",
            QualificationStatus.VERIFIED,
            False,
            "Complete raw table snapshots retain values and provenance.",
        ),
        _result(
            "calculated_scientific_values",
            _all_sources(project, "DPV", "DataValue"),
            "This layer performs no geometric-factor, apparent-resistivity, or inversion calculation",
            None,
            QualificationStatus.UNSUPPORTED,
            False,
            "Scientific calculations belong to separately qualified services, not this layer.",
        ),
        _result(
            "ves_persistence",
            _all_sources(project, "DP_ABMN", "FocusZ"),
            "The current qualification layer creates no NiX VES representation",
            None,
            QualificationStatus.UNSUPPORTED,
            kind == "VES",
            "The current NiX ProjectStore has no approved dedicated VES persistence target.",
            "Approve a dedicated VES point/sidecar persistence contract." if kind == "VES" else None,
        ),
        _result(
            "auxiliary_raw_preservation",
            tuple(SourceLocation(str(project.source_path), table.name) for table in project.tables),
            f"All {len(project.tables)} extracted tables remain in the intermediate representation",
            "Auxiliary records can remain raw and source-addressable.",
            QualificationStatus.VERIFIED,
            False,
            "The parser snapshots complete tables and does not silently discard rows.",
        ),
        _result(
            "auxiliary_semantics",
            tuple(SourceLocation(str(project.source_path), table.name) for table in project.tables),
            "Operational/log/test/auxiliary meanings are not interpreted",
            None,
            QualificationStatus.UNKNOWN,
            False,
            "Unknown auxiliary semantics are non-blocking when retained losslessly and not mapped to NiX science/QC.",
            "Provide inclusion/exclusion rules if auxiliary records must be semantically imported.",
        ),
        _result(
            "nix_compatibility",
            source_location,
            "No NiX records are created and no approved ABEM-to-NiX mapping is available",
            None,
            QualificationStatus.BLOCKED,
            True,
            "Intermediate qualification is not an importer and cannot establish NiX persistence compatibility.",
            "Complete vendor semantic evidence and approve the separate NiX persistence contract.",
        ),
    ))

    readiness = "NOT_READY" if any(result.blocks_import for result in results) else "READY"
    return ABEMQualificationReport(project.source_path, project.source_sha256, tuple(results), readiness)


__all__ = [
    "ABEMQualificationReport",
    "AuthorizedDatasetEvidence",
    "DOCUMENTED_BARUGO_EVIDENCE",
    "QualificationResult",
    "QualificationStatus",
    "qualify_abem",
]
