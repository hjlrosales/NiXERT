"""Read-only inspection of ABEM/Terrameter project databases.

Barugo sample files use the vendor's ABEM project schema, not the NiX ERT
SQLite schema. This module deliberately stops at inspection: it never writes,
migrates, copies, or interprets the vendor database as a NiX project.
"""

from __future__ import annotations

import hashlib
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ABEMInspectionError(ValueError):
    """Raised when an ABEM project cannot be inspected without guessing."""


_REQUIRED_TABLES = {
    "ProjectSchemaVersion", "CommonSchemaVersion", "Tasks", "DPV",
    "DP_ABMN", "DP_MEASURE", "Measures", "Datatype", "Sessions",
}


@dataclass(frozen=True)
class ABEMSampleInspection:
    """Facts read from one ABEM project database, with no NiX conversion."""

    path: Path
    label: str
    kind: str
    project_schema_version: int
    common_schema_version: int
    task_name: str
    array_code: int | None
    protocol_file: str | None
    instrument_software: str | None
    transmitter_software: str | None
    instrument_serial: str | None
    measurement_links: int
    dpv_rows: int
    geometry_rows: int
    unique_positions: int
    apparent_resistivity_rows: int
    resistance_rows: int
    apparent_resistivity_minimum: float | None
    apparent_resistivity_maximum: float | None
    electrode_x_minimum: float | None
    electrode_x_maximum: float | None
    coordinate_dimensions: tuple[str, ...]
    compatible_with_nix_project: bool
    compatibility_reasons: tuple[str, ...]
    sha256: str
    byte_count: int

    @property
    def source_label(self) -> str:
        return "BARUGO SAMPLE DATA — REAL USER-PROVIDED DATA"

    def summary(self) -> str:
        rho_range = (
            "not available"
            if self.apparent_resistivity_minimum is None
            else f"{self.apparent_resistivity_minimum:g} to {self.apparent_resistivity_maximum:g} Ωm"
        )
        x_range = (
            "not available"
            if self.electrode_x_minimum is None
            else f"{self.electrode_x_minimum:g} to {self.electrode_x_maximum:g}"
        )
        reasons = " ; ".join(self.compatibility_reasons)
        return "\n".join(
            (
                self.source_label,
                f"Source: {self.path}",
                f"Kind: {self.kind}",
                f"ABEM schema: project={self.project_schema_version}, common={self.common_schema_version}",
                f"Task: {self.task_name}",
                f"Measurement links: {self.measurement_links}; DPV rows: {self.dpv_rows}; geometry rows: {self.geometry_rows}",
                f"Unique electrode positions: {self.unique_positions}; coordinate dimensions: {', '.join(self.coordinate_dimensions)}",
                f"Apparent resistivity rows: {self.apparent_resistivity_rows}; range: {rho_range}",
                f"Resistance rows: {self.resistance_rows}",
                f"Electrode X range: {x_range}",
                f"Instrument software: {self.instrument_software or 'not recorded'}; transmitter: {self.transmitter_software or 'not recorded'}",
                f"Instrument serial: {self.instrument_serial or 'not recorded'}",
                f"NiX project compatibility: {'yes' if self.compatible_with_nix_project else 'no'}",
                f"Compatibility decision: {reasons}",
                "Read-only inspection only; this is not live LS2 acquisition data.",
            )
        )


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _single_value(db: sqlite3.Connection, query: str, parameters: tuple[Any, ...] = ()) -> Any:
    row = db.execute(query, parameters).fetchone()
    return row[0] if row is not None else None


def _version(db: sqlite3.Connection, table: str) -> int:
    value = _single_value(db, f"SELECT Version FROM {_quote(table)} LIMIT 1")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ABEMInspectionError(f"{table} does not contain a numeric version") from exc


def _finite_range(values: list[float]) -> tuple[float | None, float | None]:
    finite = [value for value in values if math.isfinite(value)]
    return (min(finite), max(finite)) if finite else (None, None)


def inspect_abem_project(path: Path | str, *, label: str | None = None) -> ABEMSampleInspection:
    """Inspect an ABEM project in SQLite read-only mode.

    The inspection requires explicit vendor tables and named ``ρapp`` data.
    It does not infer missing geometry, recalculate values, or open any
    instrument/network interface.
    """
    source = Path(path)
    if not source.is_file():
        raise ABEMInspectionError(f"ABEM sample database does not exist: {source}")
    try:
        raw = source.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
    except OSError as exc:
        raise ABEMInspectionError(f"Unable to read ABEM sample database: {exc}") from exc
    try:
        db = sqlite3.connect(f"file:{source.resolve().as_posix()}?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
    except sqlite3.DatabaseError as exc:
        raise ABEMInspectionError(f"Unable to open ABEM sample database read-only: {exc}") from exc
    try:
        tables = {
            row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        missing = sorted(_REQUIRED_TABLES - tables)
        if missing:
            raise ABEMInspectionError("ABEM database is missing required tables: " + ", ".join(missing))
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ABEMInspectionError("ABEM database failed SQLite integrity_check")

        project_version = _version(db, "ProjectSchemaVersion")
        common_version = _version(db, "CommonSchemaVersion")
        task = db.execute("SELECT * FROM Tasks ORDER BY ID LIMIT 1").fetchone()
        if task is None:
            raise ABEMInspectionError("ABEM database contains no task")
        task_name = str(task["Name"] or "")
        settings = {
            str(row["Setting"]): row["Value"]
            for row in db.execute("SELECT Setting, Value FROM TaskSettings")
        } if "TaskSettings" in tables else {}
        sessions = db.execute(
            "SELECT InstrumentSerial, InstrumentSoftware, TransmitterSoftware FROM Sessions ORDER BY ID LIMIT 1"
        ).fetchone()
        instrument_serial = str(sessions["InstrumentSerial"]) if sessions and sessions["InstrumentSerial"] else None
        instrument_software = str(sessions["InstrumentSoftware"]) if sessions and sessions["InstrumentSoftware"] else None
        transmitter_software = str(sessions["TransmitterSoftware"]) if sessions and sessions["TransmitterSoftware"] else None

        links = db.execute("SELECT DPID, MeasureID FROM DP_MEASURE ORDER BY ID").fetchall()
        if not links:
            raise ABEMInspectionError("ABEM database contains no linked measurements")
        link_keys = [(int(link["DPID"]), int(link["MeasureID"])) for link in links]
        if len(set(link_keys)) != len(link_keys):
            raise ABEMInspectionError("ABEM DP_MEASURE contains duplicate observation links")
        for dpid, measure_id in link_keys:
            geometry = db.execute(
                "SELECT TaskID FROM DP_ABMN WHERE ID = ?", (dpid,)
            ).fetchone()
            if geometry is None:
                raise ABEMInspectionError(
                    f"ABEM observation link references missing geometry: DPID={dpid}"
                )
            if "Measures" in tables and db.execute(
                "SELECT 1 FROM Measures WHERE ID = ?", (measure_id,)
            ).fetchone() is None:
                raise ABEMInspectionError(
                    f"ABEM observation link references missing measurement metadata: MeasureID={measure_id}"
                )
            if db.execute(
                "SELECT 1 FROM DPV WHERE DPID = ? AND MeasureID = ? LIMIT 1",
                (dpid, measure_id),
            ).fetchone() is None:
                raise ABEMInspectionError(
                    f"ABEM observation link has no DPV values: DPID={dpid}, MeasureID={measure_id}"
                )
        rho_values: list[float] = []
        rho_rows = 0
        resistance_rows = 0
        for link in links:
            values = db.execute(
                """SELECT dt.Name, dt.Unit, dv.DataValue
                   FROM DPV dv JOIN Datatype dt ON dt.ID = dv.DatatypeID
                   WHERE dv.DPID = ? AND dv.MeasureID = ?""",
                (link["DPID"], link["MeasureID"]),
            ).fetchall()
            for value in values:
                name = str(value["Name"] or "")
                number = value["DataValue"]
                if name == "ρapp" and number is not None:
                    rho_rows += 1
                    if math.isfinite(float(number)):
                        rho_values.append(float(number))
                elif name == "R" and number is not None and math.isfinite(float(number)):
                    resistance_rows += 1

        coordinate_rows = db.execute(
            """SELECT APosX, APosY, APosZ, BPosX, BPosY, BPosZ,
                      MPosX, MPosY, MPosZ, NPosX, NPosY, NPosZ
               FROM DP_MEASURE JOIN DP_ABMN ON DP_ABMN.ID = DP_MEASURE.DPID
               ORDER BY DP_MEASURE.ID"""
        ).fetchall()
        positions = set()
        for row in coordinate_rows:
            for prefix in "ABMN":
                position = tuple(row[f"{prefix}Pos{axis}"] for axis in "XYZ")
                if any(value is None or not math.isfinite(float(value)) for value in position):
                    raise ABEMInspectionError("ABEM geometry contains a missing or non-finite coordinate")
                positions.add(tuple(float(value) for value in position))
        x_min, x_max = _finite_range([position[0] for position in positions])
        dimensions = tuple(
            axis for index, axis in enumerate(("X", "Y", "Z"))
            if len({position[index] for position in positions}) > 1
        )
        kind = "VES" if "ves" in task_name.lower() or "ves" in str(settings.get("ProtocolFile", "")).lower() else "ERT"
        reasons = (
            "ABEM vendor tables are not NiX schema_info/project_metadata/surveys/measurements tables",
            "ABEM DP_MEASURE/DPV linkage and coordinate geometry require a dedicated import contract",
            "NiX VES points are not persisted in the current ProjectStore schema" if kind == "VES" else "ABEM array code/protocol semantics are not a NiX DAT array declaration",
        )
        return ABEMSampleInspection(
            source, label or source.stem, kind, project_version, common_version, task_name,
            int(task["ArrayCode"]) if task["ArrayCode"] is not None else None,
            str(settings["ProtocolFile"]) if settings.get("ProtocolFile") else None,
            instrument_software, transmitter_software, instrument_serial,
            len(links), int(_single_value(db, "SELECT COUNT(*) FROM DPV") or 0),
            len(coordinate_rows), len(positions), rho_rows, resistance_rows,
            *_finite_range(rho_values), x_min, x_max, dimensions, False, reasons,
            digest, len(raw),
        )
    except sqlite3.DatabaseError as exc:
        raise ABEMInspectionError(f"Unable to inspect ABEM sample database: {exc}") from exc
    finally:
        db.close()


def inspect_barugo_samples(root: Path | str) -> tuple[ABEMSampleInspection, ...]:
    """Inspect the two requested Barugo files without writing either source."""
    root = Path(root)
    paths = (
        ("Barugo ERT", root / "ERT Survey Data" / "Project7" / "project.db"),
        ("Barugo VES", root / "VES Survey Data" / "Project8" / "project.db"),
    )
    return tuple(inspect_abem_project(path, label=label) for label, path in paths)
