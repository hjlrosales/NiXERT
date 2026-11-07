"""Read-only, provenance-preserving ABEM intermediate representation.

This module deliberately stops between vendor storage and semantic qualification.
It records facts from an ABEM SQLite database, but does not convert them into
NiX measurements, decode vendor enumerations, calculate scientific values, or
open an instrument transport.
"""

from __future__ import annotations

import hashlib
import math
import sqlite3
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


class ABEMIntermediateError(ValueError):
    """Raised when a source cannot be inspected as SQLite in read-only mode."""


class FactStatus(str, Enum):
    """Evidence state for an intermediate fact or semantic assertion."""

    OBSERVED = "observed"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"
    INVALID = "invalid"


@dataclass(frozen=True)
class SourceLocation:
    """Exact source location for one extracted fact."""

    path: str
    table: str | None = None
    row: str | int | None = None
    column: str | None = None

    def describe(self) -> str:
        location = self.path
        if self.table is not None:
            location += f"::{self.table}"
        if self.row is not None:
            location += f"[{self.row}]"
        if self.column is not None:
            location += f".{self.column}"
        return location


@dataclass(frozen=True)
class RawField:
    """A vendor value retained without semantic reinterpretation."""

    name: str
    value: Any
    status: FactStatus
    source: SourceLocation
    note: str | None = None


@dataclass(frozen=True)
class RawRecord:
    """One vendor table row with a deterministic source row identity."""

    table: str
    row_key: str | int
    fields: tuple[RawField, ...]

    def field(self, name: str) -> RawField | None:
        return next((field for field in self.fields if field.name == name), None)

    def values(self) -> dict[str, Any]:
        return {field.name: field.value for field in self.fields}


@dataclass(frozen=True)
class TableSnapshot:
    """Schema and complete raw rows for one vendor table."""

    name: str
    columns: tuple[tuple[str, str], ...]
    rows: tuple[RawRecord, ...]


@dataclass(frozen=True)
class RelationshipCheck:
    """A logical relationship check, never a declared SQLite foreign key."""

    name: str
    status: FactStatus
    source: SourceLocation
    target: SourceLocation | None
    note: str


@dataclass(frozen=True)
class SemanticFact:
    """An explicit semantic boundary that is not silently inferred."""

    name: str
    status: FactStatus
    value: Any
    evidence: tuple[SourceLocation, ...]
    note: str


@dataclass(frozen=True)
class ABEMIntermediateProject:
    """Factual ABEM representation; it is not a NiX import payload."""

    source_path: Path
    source_sha256: str
    byte_count: int
    integrity_status: FactStatus
    tables: tuple[TableSnapshot, ...]
    observation_links: tuple[RelationshipCheck, ...]
    semantic_facts: tuple[SemanticFact, ...]
    issues: tuple[str, ...]
    status: FactStatus

    @property
    def importer_ready(self) -> bool:
        """Always false: semantic qualification and NiX import are separate stages."""
        return False

    @property
    def has_invalid_facts(self) -> bool:
        return self.status is FactStatus.INVALID or any(
            field.status is FactStatus.INVALID
            for table in self.tables
            for record in table.rows
            for field in record.fields
        )

    def table(self, name: str) -> TableSnapshot | None:
        return next((table for table in self.tables if table.name == name), None)

    def semantic(self, name: str) -> SemanticFact:
        for fact in self.semantic_facts:
            if fact.name == name:
                return fact
        raise KeyError(name)

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic, JSON-compatible factual view.

        This helper is for diagnostics/tests only. It does not create a NiX
        project and intentionally leaves bytes represented by a stable marker.
        """

        def json_value(value: Any) -> Any:
            if isinstance(value, bytes):
                return {"bytes_hex": value.hex()}
            return value

        return {
            "source_path": str(self.source_path),
            "source_sha256": self.source_sha256,
            "byte_count": self.byte_count,
            "integrity_status": self.integrity_status.value,
            "status": self.status.value,
            "importer_ready": self.importer_ready,
            "issues": list(self.issues),
            "tables": [
                {
                    "name": table.name,
                    "columns": list(table.columns),
                    "rows": [
                        {
                            "row_key": record.row_key,
                            "fields": [
                                {
                                    "name": field.name,
                                    "value": json_value(field.value),
                                    "status": field.status.value,
                                    "source": field.source.describe(),
                                    "note": field.note,
                                }
                                for field in record.fields
                            ],
                        }
                        for record in table.rows
                    ],
                }
                for table in self.tables
            ],
            "observation_links": [
                {
                    "name": link.name,
                    "status": link.status.value,
                    "source": link.source.describe(),
                    "target": link.target.describe() if link.target else None,
                    "note": link.note,
                }
                for link in self.observation_links
            ],
            "semantic_facts": [
                {
                    "name": fact.name,
                    "status": fact.status.value,
                    "value": json_value(fact.value),
                    "evidence": [location.describe() for location in fact.evidence],
                    "note": fact.note,
                }
                for fact in self.semantic_facts
            ],
        }


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _field_status(value: Any, declared_type: str) -> tuple[FactStatus, str | None]:
    declared = declared_type.upper()
    numeric = any(token in declared for token in ("INT", "REAL", "FLOA", "DOUB", "NUM", "DEC"))
    if numeric and value is not None and not isinstance(value, (int, float)):
        return FactStatus.INVALID, f"declared numeric field contains {type(value).__name__}"
    if isinstance(value, float) and not math.isfinite(value):
        return FactStatus.INVALID, "numeric value is non-finite"
    return FactStatus.OBSERVED, None


def _table_columns(db: sqlite3.Connection, table: str) -> tuple[tuple[str, str], ...]:
    return tuple(
        (str(row[1]), str(row[2] or ""))
        for row in db.execute(f"PRAGMA table_info({_quote(table)})")
    )


def _row_key(columns: tuple[tuple[str, str], ...], values: tuple[Any, ...], occurrence: int) -> str | int:
    primary_keys: list[tuple[int, str]] = []
    # PRAGMA table_info's fifth field is the 1-based PK order; this helper is
    # passed only names/types, so deterministic occurrence keys are used for
    # raw tables and logical IDs are recovered from the raw field values below.
    del primary_keys
    for name, value in zip((column[0] for column in columns), values):
        if name.upper() == "ID" and isinstance(value, (int, str)):
            return f"ID={value}"
    return occurrence


def _snapshot_table(db: sqlite3.Connection, path: Path, table: str) -> TableSnapshot:
    columns = _table_columns(db, table)
    try:
        cursor = db.execute(f"SELECT * FROM {_quote(table)} ORDER BY rowid")
    except sqlite3.DatabaseError:
        cursor = db.execute(f"SELECT * FROM {_quote(table)}")
    records: list[RawRecord] = []
    for occurrence, row in enumerate(cursor.fetchall(), start=1):
        values = tuple(row)
        row_key = _row_key(columns, values, occurrence)
        fields = tuple(
            RawField(
                name=name,
                value=value,
                status=_field_status(value, declared_type)[0],
                source=SourceLocation(str(path), table, row_key, name),
                note=_field_status(value, declared_type)[1],
            )
            for (name, declared_type), value in zip(columns, values)
        )
        records.append(RawRecord(table, row_key, fields))
    return TableSnapshot(table, columns, tuple(records))


def _records_by_value(table: TableSnapshot, field: str) -> dict[Any, list[RawRecord]]:
    result: dict[Any, list[RawRecord]] = {}
    for record in table.rows:
        raw = record.field(field)
        if raw is not None:
            result.setdefault(raw.value, []).append(record)
    return result


def _first_field(record: RawRecord | None, name: str) -> RawField | None:
    return record.field(name) if record is not None else None


def _semantic_facts(
    path: Path,
    tables: tuple[TableSnapshot, ...],
) -> tuple[SemanticFact, ...]:
    by_name = {table.name: table for table in tables}
    task = by_name.get("Tasks")
    task_row = task.rows[0] if task and task.rows else None
    settings = by_name.get("TaskSettings")
    setting_records = settings.rows if settings else ()
    protocol = next(
        (record.field("Value") for record in setting_records if record.field("Setting") and record.field("Setting").value == "ProtocolFile"),
        None,
    )
    spread = next(
        (record.field("Value") for record in setting_records if record.field("Setting") and record.field("Setting").value == "SpreadFile"),
        None,
    )
    task_name = _first_field(task_row, "Name")
    array_code = _first_field(task_row, "ArrayCode")
    evidence = tuple(
        field.source for field in (task_name, protocol, spread, array_code) if field is not None
    )
    unknown = (
        SemanticFact(
            "dataset_kind",
            FactStatus.UNKNOWN,
            None,
            evidence,
            "Task/protocol text is preserved as evidence; the parser does not infer ERT or VES meaning.",
        ),
        SemanticFact(
            "array_and_protocol_code_meaning",
            FactStatus.UNKNOWN,
            None,
            tuple(field.source for field in (array_code, protocol, spread) if field is not None),
            "ArrayCode, ProtocolMode, and filenames are retained raw; no vendor enumeration is decoded.",
        ),
        SemanticFact(
            "electrode_numbering_and_switch_mapping",
            FactStatus.UNKNOWN,
            None,
            tuple(
                field.source
                for table_name, field_name in (("DP_ABMN", "DPKEY"), ("Electrodes", "SwitchAddress"))
                for field in [_first_field(by_name.get(table_name).rows[0] if by_name.get(table_name) and by_name.get(table_name).rows else None, field_name)]
                if field is not None
            ),
            "Role-labelled or switch fields do not establish a NiX integer numbering policy.",
        ),
        SemanticFact(
            "coordinate_reference_system_and_units",
            FactStatus.UNKNOWN,
            None,
            tuple(
                field.source
                for field in (
                    _first_field(by_name.get("DP_ABMN").rows[0] if by_name.get("DP_ABMN") and by_name.get("DP_ABMN").rows else None, "APosX"),
                    _first_field(task_row, "SpacingX"),
                )
                if field is not None
            ),
            "Stored coordinates and spacing are preserved, but CRS, datum, and universal units are not established.",
        ),
        SemanticFact(
            "quality_status_and_uncertainty_semantics",
            FactStatus.UNKNOWN,
            None,
            tuple(
                field.source
                for field in (
                    _first_field(by_name.get("DPV").rows[0] if by_name.get("DPV") and by_name.get("DPV").rows else None, "Status"),
                    _first_field(by_name.get("DPV").rows[0] if by_name.get("DPV") and by_name.get("DPV").rows else None, "DataSDev"),
                )
                if field is not None
            ),
            "Status, deviation, counts, and readiness fields are raw facts, not NiX QC decisions.",
        ),
        SemanticFact(
            "ves_persistence_in_nix",
            FactStatus.UNSUPPORTED,
            None,
            tuple(
                field.source
                for field in (
                    _first_field(by_name.get("DP_ABMN").rows[0] if by_name.get("DP_ABMN") and by_name.get("DP_ABMN").rows else None, "FocusZ"),
                    _first_field(task_row, "ArrayCode"),
                )
                if field is not None
            ),
            "The current intermediate layer does not create a NiX VES point or ProjectStore record.",
        ),
        SemanticFact(
            "ls2_communication",
            FactStatus.UNSUPPORTED,
            None,
            (SourceLocation(str(path)),),
            "This parser reads a local file only; it does not communicate with an LS2.",
        ),
    )
    return unknown


def _link_checks(path: Path, tables: tuple[TableSnapshot, ...]) -> tuple[RelationshipCheck, ...]:
    by_name = {table.name: table for table in tables}
    required = ("DP_MEASURE", "DP_ABMN", "Measures", "DPV")
    if any(name not in by_name for name in required):
        return ()
    links = by_name["DP_MEASURE"].rows
    geometry_by_id = _records_by_value(by_name["DP_ABMN"], "ID")
    measures_by_id = _records_by_value(by_name["Measures"], "ID")
    dpv_rows = by_name["DPV"].rows
    seen: set[tuple[Any, Any]] = set()
    checks: list[RelationshipCheck] = []
    for record in links:
        dpid = _first_field(record, "DPID")
        measure_id = _first_field(record, "MeasureID")
        source = SourceLocation(str(path), "DP_MEASURE", record.row_key)
        if dpid is None or measure_id is None:
            checks.append(RelationshipCheck("DP_MEASURE link", FactStatus.INVALID, source, None, "DPID and MeasureID are required"))
            continue
        key = (dpid.value, measure_id.value)
        duplicate = key in seen
        seen.add(key)
        geometry = geometry_by_id.get(dpid.value, [])
        measure = measures_by_id.get(measure_id.value, [])
        values = [
            row for row in dpv_rows
            if _first_field(row, "DPID") and _first_field(row, "DPID").value == dpid.value
            and _first_field(row, "MeasureID") and _first_field(row, "MeasureID").value == measure_id.value
        ]
        if duplicate:
            checks.append(RelationshipCheck("DP_MEASURE link", FactStatus.INVALID, source, None, "duplicate (DPID, MeasureID) link"))
        elif not geometry:
            checks.append(RelationshipCheck("DP_MEASURE link", FactStatus.INVALID, source, None, "missing DP_ABMN geometry"))
        elif not measure:
            checks.append(RelationshipCheck("DP_MEASURE link", FactStatus.INVALID, source, None, "missing Measures metadata"))
        elif not values:
            checks.append(RelationshipCheck("DP_MEASURE link", FactStatus.INVALID, source, None, "missing DPV values"))
        elif any(field.status is FactStatus.INVALID for field in geometry[0].fields):
            checks.append(RelationshipCheck("DP_MEASURE link", FactStatus.INVALID, source, SourceLocation(str(path), "DP_ABMN", geometry[0].row_key), "linked geometry contains an invalid value"))
        else:
            checks.append(RelationshipCheck("DP_MEASURE link", FactStatus.OBSERVED, source, SourceLocation(str(path), "DP_ABMN", geometry[0].row_key), "logical DP_MEASURE → DP_ABMN/Measures/DPV linkage is present"))
    return tuple(checks)


def parse_abem_intermediate(path: Path | str) -> ABEMIntermediateProject:
    """Parse an ABEM SQLite file read-only into factual intermediate records."""
    source = Path(path)
    if not source.is_file():
        raise ABEMIntermediateError(f"ABEM source does not exist: {source}")
    try:
        raw = source.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
    except OSError as exc:
        raise ABEMIntermediateError(f"Unable to read ABEM source: {exc}") from exc
    try:
        db = sqlite3.connect(f"file:{source.resolve().as_posix()}?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
    except sqlite3.DatabaseError as exc:
        raise ABEMIntermediateError(f"Unable to open ABEM source read-only: {exc}") from exc

    issues: list[str] = []
    try:
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        integrity_status = FactStatus.OBSERVED if integrity == "ok" else FactStatus.INVALID
        if integrity_status is FactStatus.INVALID:
            issues.append(f"SQLite integrity_check returned {integrity!r}")
        table_names = tuple(
            str(row[0])
            for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        )
        tables = tuple(_snapshot_table(db, source.resolve(), name) for name in table_names)
        required = {"ProjectSchemaVersion", "CommonSchemaVersion", "Tasks", "DPV", "DP_ABMN", "DP_MEASURE", "Measures", "Datatype", "Sessions"}
        missing = sorted(required - set(table_names))
        if missing:
            issues.append("missing required ABEM tables: " + ", ".join(missing))
        links = _link_checks(source.resolve(), tables)
        if "DP_MEASURE" in table_names and not links:
            issues.append("ABEM contains no observation links")
        invalid_links = sum(link.status is FactStatus.INVALID for link in links)
        if invalid_links:
            issues.append(f"{invalid_links} invalid logical observation link(s)")
        status = FactStatus.INVALID if issues else FactStatus.OBSERVED
        return ABEMIntermediateProject(
            source_path=source.resolve(),
            source_sha256=digest,
            byte_count=len(raw),
            integrity_status=integrity_status,
            tables=tables,
            observation_links=links,
            semantic_facts=_semantic_facts(source.resolve(), tables),
            issues=tuple(issues),
            status=status,
        )
    except sqlite3.DatabaseError as exc:
        raise ABEMIntermediateError(f"Unable to inspect ABEM source: {exc}") from exc
    finally:
        db.close()


__all__ = [
    "ABEMIntermediateError",
    "ABEMIntermediateProject",
    "FactStatus",
    "RawField",
    "RawRecord",
    "RelationshipCheck",
    "SemanticFact",
    "SourceLocation",
    "TableSnapshot",
    "parse_abem_intermediate",
]
