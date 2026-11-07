"""Deterministic, read-only forensic probe for ABEM SQLite project files.

The probe opens SQLite with ``mode=ro`` and reports structural/value evidence.
It never creates, migrates, attaches, vacuums, or writes a database.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


def _json_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {
            "kind": "blob",
            "length": len(value),
            "hex_prefix": value[:64].hex(),
            "utf8_prefix": value[:256].decode("utf-8", errors="replace"),
        }
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    return value


def _rows(db: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [
        {key: _json_value(row[key]) for key in row.keys()}
        for row in db.execute(sql, params).fetchall()
    ]


def _scalar(db: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> Any:
    row = db.execute(sql, params).fetchone()
    return None if row is None else row[0]


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _distribution(db: sqlite3.Connection, table: str, column: str) -> list[dict[str, Any]]:
    table_q, column_q = _quote(table), _quote(column)
    return _rows(
        db,
        f"SELECT {column_q} AS value, COUNT(*) AS count FROM {table_q} "
        f"GROUP BY {column_q} ORDER BY count DESC, value",
    )


def _number(element: ElementTree.Element | None, name: str, default: float = 0.0) -> float:
    if element is None:
        return default
    child = element.find(name)
    return default if child is None or child.text is None else float(child.text.strip())


def _official_protocol_comparison(
    db: sqlite3.Connection, archive_path: Path
) -> dict[str, Any]:
    settings = {
        str(row["Setting"]): str(row["Value"])
        for row in db.execute("SELECT Setting, Value FROM TaskSettings")
    }
    protocol_name = Path(settings["ProtocolFile"]).name.lower()
    spread_name = Path(settings["SpreadFile"]).name.lower()
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.namelist()
        protocol_members = [name for name in members if Path(name).name.lower() == protocol_name]
        spread_members = [name for name in members if Path(name).name.lower() == spread_name]
        spread_variants = {hashlib.sha256(archive.read(name)).hexdigest(): name for name in spread_members}
        protocol_variants = {hashlib.sha256(archive.read(name)).hexdigest(): name for name in protocol_members}
        if len(protocol_variants) != 1 or len(spread_variants) != 1:
            return {
                "status": "not_unique",
                "protocol_members": protocol_members,
                "spread_members": spread_members,
            }
        protocol_member = next(iter(protocol_variants.values()))
        spread_member = next(iter(spread_variants.values()))
        protocol = ElementTree.fromstring(archive.read(protocol_member))
        spread = ElementTree.fromstring(archive.read(spread_member))

    electrode_positions: dict[int, tuple[float, float, float]] = {}
    for electrode in spread.findall(".//Electrode"):
        identifier = electrode.findtext("Id")
        if identifier is not None:
            electrode_positions[int(identifier.strip())] = (
                _number(electrode, "X"),
                _number(electrode, "Y"),
                _number(electrode, "Z"),
            )

    sequence = protocol.find("Sequence")
    if sequence is None:
        raise ValueError("official protocol has no Sequence")
    measure_specs: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for measure in sequence.findall("Measure"):
        tx_text = measure.findtext("Tx") or ""
        tx = tuple(int(value) for value in tx_text.split())
        for rx_element in measure.findall("Rx"):
            rx = tuple(int(value) for value in (rx_element.text or "").split())
            if len(tx) == 2 and len(rx) == 2:
                measure_specs.append(((tx[0], tx[1]), (rx[0], rx[1])))

    configurations: list[tuple[float, ...]] = []
    selections = protocol.findall(".//UserSelect/Select")
    if selections:
        for selection in selections:
            selected_positions = dict(electrode_positions)
            for move in selection.findall("Move"):
                if move.text is None:
                    continue
                identifier_text = (move.text or "").strip()
                identifier = int(identifier_text.split()[0]) if identifier_text else None
                if identifier is not None:
                    selected_positions[identifier] = (
                        _number(move, "X"), _number(move, "Y"), _number(move, "Z")
                    )
            for tx, rx in measure_specs:
                configurations.append(
                    tuple(value for identifier in (*tx, *rx) for value in selected_positions[identifier])
                )
    else:
        for tx, rx in measure_specs:
            configurations.append(
                tuple(value for identifier in (*tx, *rx) for value in electrode_positions[identifier])
            )

    database_configurations = [
        tuple(float(row[f"{role}Pos{axis}"]) for role in "ABMN" for axis in "XYZ")
        for row in db.execute("SELECT * FROM DP_ABMN ORDER BY ID")
    ]
    official_counter = Counter(configurations)
    database_counter = Counter(database_configurations)
    intersection = official_counter & database_counter
    missing = list((official_counter - database_counter).elements())
    extra = list((database_counter - official_counter).elements())
    return {
        "status": "compared",
        "archive_sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        "protocol_member": protocol_member,
        "spread_member": spread_member,
        "official_array_code": (protocol.findtext("Arraycode") or "").strip(),
        "official_name": (protocol.findtext("Name") or "").strip(),
        "official_description": (protocol.findtext("Description") or "").strip(),
        "official_configuration_count": len(configurations),
        "database_configuration_count": len(database_configurations),
        "multiset_match_count": sum(intersection.values()),
        "official_missing_count": len(missing),
        "database_extra_count": len(extra),
        "official_missing_examples": [list(item) for item in missing[:5]],
        "database_extra_examples": [list(item) for item in extra[:5]],
    }


def inspect(path: Path, protocol_zip: Path | None = None) -> dict[str, Any]:
    raw_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    uri = f"file:{path.resolve().as_posix()}?mode=ro&immutable=1"
    db = sqlite3.connect(uri, uri=True)
    db.row_factory = sqlite3.Row
    try:
        objects = _rows(
            db,
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name",
        )
        table_names = [item["name"] for item in objects if item["type"] == "table"]
        tables: dict[str, Any] = {}
        for table in table_names:
            columns = _rows(db, f"PRAGMA table_info({_quote(table)})")
            count = int(_scalar(db, f"SELECT COUNT(*) FROM {_quote(table)}") or 0)
            sample = _rows(db, f"SELECT * FROM {_quote(table)} ORDER BY rowid LIMIT 3")
            blob_columns = [
                column["name"]
                for column in columns
                if "BLOB" in str(column["type"] or "").upper()
            ]
            blob_samples: dict[str, Any] = {}
            for column in blob_columns:
                blob_samples[column] = _rows(
                    db,
                    f"SELECT rowid, length({_quote(column)}) AS length, "
                    f"hex(substr({_quote(column)}, 1, 64)) AS hex_prefix "
                    f"FROM {_quote(table)} WHERE {_quote(column)} IS NOT NULL "
                    "ORDER BY rowid LIMIT 10",
                )
            tables[table] = {
                "count": count,
                "columns": columns,
                "foreign_keys": _rows(db, f"PRAGMA foreign_key_list({_quote(table)})"),
                "indexes": _rows(db, f"PRAGMA index_list({_quote(table)})"),
                "sample": sample,
                "blob_samples": blob_samples,
            }

        distributions: dict[str, Any] = {}
        candidates = {
            "Tasks": ("Active", "ArrayCode"),
            "TaskSettings": ("Setting", "Auto"),
            "AcqSettings": ("Setting", "Auto"),
            "DP_MEASURE": ("Ready",),
            "DP_ABMN": ("Ready", "Mode", "ModeValue"),
            "DPV": ("Channel", "SeqNum", "DatatypeID", "Status", "DataSDevType", "N", "MCycles", "ADRange"),
            "Measures": ("StationID", "PosQuality", "SessionID", "PositionId"),
            "Positions": ("PositionType", "IsRemote", "MeasurePhase"),
            "ElectrodeTestData": ("TestStatus", "UserSetting", "TxStatus", "SwitchNumber", "SwitchAddress"),
            "GPSPositions": ("GPSSOURCE", "smask", "sig", "fix", "INUSE", "INVIEW"),
            "Datasets": ("ExcludeSet",),
            "ExternalData": ("PhaseID", "PhaseType", "PhasePolarity", "DatatypeID", "Status", "N"),
            "Log": ("SourceTypeID", "EventClass", "EventClassId"),
        }
        for table, columns in candidates.items():
            if table not in tables:
                continue
            present = {column["name"] for column in tables[table]["columns"]}
            distributions[table] = {
                column: _distribution(db, table, column)
                for column in columns
                if column in present
            }

        findings: dict[str, Any] = {
            "integrity_check": _scalar(db, "PRAGMA integrity_check"),
            "foreign_key_check": _rows(db, "PRAGMA foreign_key_check"),
            "task_settings": _rows(db, "SELECT * FROM TaskSettings ORDER BY key1, key2, Setting") if "TaskSettings" in tables else [],
            "acq_settings": _rows(db, "SELECT * FROM AcqSettings ORDER BY key1, key2, Setting") if "AcqSettings" in tables else [],
            "datatypes": _rows(db, "SELECT * FROM Datatype ORDER BY ID") if "Datatype" in tables else [],
            "log_messages": _rows(
                db,
                "SELECT WhatEnglish, EventClass, EventClassId, SourceTypeID, COUNT(*) count, "
                "MIN(MeasureID) min_measure_id, MAX(MeasureID) max_measure_id "
                "FROM Log GROUP BY WhatEnglish,EventClass,EventClassId,SourceTypeID "
                "ORDER BY MIN(ID)",
            ) if "Log" in tables else [],
        }
        if protocol_zip is not None and "TaskSettings" in tables:
            findings["official_protocol_comparison"] = _official_protocol_comparison(db, protocol_zip)
        required = {"DP_MEASURE", "DP_ABMN", "Measures", "DPV", "Datatype"}
        if required.issubset(tables):
            dpkey_mismatch_count = 0
            dpkey_bad_format_count = 0
            for row in db.execute("SELECT * FROM DP_ABMN ORDER BY ID"):
                try:
                    tokens = [float(token) for token in str(row["DPKEY"]).split(";")]
                    expected = [float(row[f"{role}Pos{axis}"]) for role in "ABMN" for axis in "XYZ"]
                    if len(tokens) != 13 or tokens[-1] != -2.0 or tokens[:12] != expected:
                        dpkey_mismatch_count += 1
                except (TypeError, ValueError):
                    dpkey_bad_format_count += 1
            findings.update(
                {
                    "dpkey_encoding": {
                        "row_count": int(_scalar(db, "SELECT COUNT(*) FROM DP_ABMN") or 0),
                        "bad_format_count": dpkey_bad_format_count,
                        "coordinate_or_sentinel_mismatch_count": dpkey_mismatch_count,
                        "format": "Axyz;Bxyz;Mxyz;Nxyz;-2",
                    },
                    "link_integrity": _rows(
                        db,
                        "SELECT "
                        "SUM(CASE WHEN a.ID IS NULL THEN 1 ELSE 0 END) AS missing_abmn, "
                        "SUM(CASE WHEN m.ID IS NULL THEN 1 ELSE 0 END) AS missing_measure, "
                        "SUM(CASE WHEN v.cnt IS NULL THEN 1 ELSE 0 END) AS missing_dpv "
                        "FROM DP_MEASURE l "
                        "LEFT JOIN DP_ABMN a ON a.ID=l.DPID "
                        "LEFT JOIN Measures m ON m.ID=l.MeasureID "
                        "LEFT JOIN (SELECT DPID,MeasureID,COUNT(*) cnt FROM DPV GROUP BY DPID,MeasureID) v "
                        "ON v.DPID=l.DPID AND v.MeasureID=l.MeasureID",
                    ),
                    "duplicate_links": _rows(
                        db,
                        "SELECT DPID, MeasureID, COUNT(*) count FROM DP_MEASURE "
                        "GROUP BY DPID, MeasureID HAVING COUNT(*)>1",
                    ),
                    "unlinked_abmn": int(
                        _scalar(db, "SELECT COUNT(*) FROM DP_ABMN a WHERE NOT EXISTS (SELECT 1 FROM DP_MEASURE l WHERE l.DPID=a.ID)") or 0
                    ),
                    "unlinked_measures": int(
                        _scalar(db, "SELECT COUNT(*) FROM Measures m WHERE NOT EXISTS (SELECT 1 FROM DP_MEASURE l WHERE l.MeasureID=m.ID)") or 0
                    ),
                    "unlinked_dpv": int(
                        _scalar(db, "SELECT COUNT(*) FROM DPV v WHERE NOT EXISTS (SELECT 1 FROM DP_MEASURE l WHERE l.DPID=v.DPID AND l.MeasureID=v.MeasureID)") or 0
                    ),
                    "dpv_matrix": _rows(
                        db,
                        "SELECT d.Name, d.Unit, v.Channel, v.SeqNum, v.Status, "
                        "v.DataSDevType, v.N, v.MCycles, v.ADRange, COUNT(*) count, "
                        "MIN(v.DataValue) min_value, MAX(v.DataValue) max_value, "
                        "MIN(v.DataSDev) min_sdev, MAX(v.DataSDev) max_sdev "
                        "FROM DPV v JOIN Datatype d ON d.ID=v.DatatypeID "
                        "GROUP BY d.Name,d.Unit,v.Channel,v.SeqNum,v.Status,v.DataSDevType,v.N,v.MCycles,v.ADRange "
                        "ORDER BY d.ID,v.Channel,v.SeqNum,v.Status",
                    ),
                    "dpv_per_link_counts": _rows(
                        db,
                        "SELECT value_count, COUNT(*) links FROM ("
                        "SELECT l.ID, COUNT(v.ID) value_count FROM DP_MEASURE l "
                        "LEFT JOIN DPV v ON v.DPID=l.DPID AND v.MeasureID=l.MeasureID "
                        "GROUP BY l.ID) GROUP BY value_count ORDER BY value_count",
                    ),
                    "unknown_datatype_rows": _rows(
                        db,
                        "SELECT v.DatatypeID, v.Channel, v.SeqNum, v.Status, "
                        "v.DataSDevType, v.N, v.MCycles, v.ADRange, COUNT(*) count, "
                        "MIN(v.DataValue) min_value, MAX(v.DataValue) max_value, "
                        "MIN(v.DataSDev) min_sdev, MAX(v.DataSDev) max_sdev "
                        "FROM DPV v LEFT JOIN Datatype d ON d.ID=v.DatatypeID "
                        "WHERE d.ID IS NULL "
                        "GROUP BY v.DatatypeID,v.Channel,v.SeqNum,v.Status,v.DataSDevType,v.N,v.MCycles,v.ADRange "
                        "ORDER BY v.DatatypeID,v.Channel,v.SeqNum,v.Status",
                    ),
                    "status_hex": [
                        {"value": row["value"], "hex": hex(int(row["value"])), "count": row["count"]}
                        for row in _distribution(db, "DPV", "Status")
                        if row["value"] is not None
                    ],
                    "coordinate_summary": _rows(
                        db,
                        "SELECT COUNT(*) linked_rows, "
                        "MIN(a.APosX) min_ax, MAX(a.APosX) max_ax, "
                        "MIN(a.BPosX) min_bx, MAX(a.BPosX) max_bx, "
                        "MIN(a.MPosX) min_mx, MAX(a.MPosX) max_mx, "
                        "MIN(a.NPosX) min_nx, MAX(a.NPosX) max_nx, "
                        "SUM(CASE WHEN a.APosY!=0 OR a.BPosY!=0 OR a.MPosY!=0 OR a.NPosY!=0 THEN 1 ELSE 0 END) nonzero_y, "
                        "SUM(CASE WHEN a.APosZ!=0 OR a.BPosZ!=0 OR a.MPosZ!=0 OR a.NPosZ!=0 THEN 1 ELSE 0 END) nonzero_z "
                        "FROM DP_MEASURE l JOIN DP_ABMN a ON a.ID=l.DPID",
                    ),
                    "geometry_ready_linkage": _rows(
                        db,
                        "SELECT a.Ready, CASE WHEN l.ID IS NULL THEN 0 ELSE 1 END linked, COUNT(*) count "
                        "FROM DP_ABMN a LEFT JOIN DP_MEASURE l ON l.DPID=a.ID "
                        "GROUP BY a.Ready, linked ORDER BY a.Ready, linked",
                    ),
                    "primary_value_consistency": _rows(
                        db,
                        "SELECT a.Ready AS geometry_ready, v.Channel, "
                        "COUNT(*) count, SUM(CASE WHEN v.DataValue<0 THEN 1 ELSE 0 END) negative_count, "
                        "MIN(v.DataSDev) min_sdev, MAX(v.DataSDev) max_sdev, "
                        "MIN(v.N) min_n, MAX(v.N) max_n, "
                        "MIN(v.MCycles) min_cycles, MAX(v.MCycles) max_cycles "
                        "FROM DP_MEASURE l JOIN DP_ABMN a ON a.ID=l.DPID "
                        "JOIN DPV v ON v.DPID=l.DPID AND v.MeasureID=l.MeasureID "
                        "WHERE v.DatatypeID=2 AND v.SeqNum=0 "
                        "GROUP BY a.Ready,v.Channel ORDER BY a.Ready,v.Channel",
                    ),
                    "ready_error_limit_correlation": _rows(
                        db,
                        "SELECT a.Ready AS geometry_ready, "
                        "SUM(CASE WHEN ABS(v.DataValue)>0 AND ABS(v.DataSDev/v.DataValue)>0.01 THEN 1 ELSE 0 END) above_one_percent, "
                        "SUM(CASE WHEN ABS(v.DataValue)>0 AND ABS(v.DataSDev/v.DataValue)<=0.01 THEN 1 ELSE 0 END) at_or_below_one_percent, "
                        "COUNT(*) count, MIN(ABS(v.DataSDev/NULLIF(v.DataValue,0))) min_cv, "
                        "MAX(ABS(v.DataSDev/NULLIF(v.DataValue,0))) max_cv "
                        "FROM DP_MEASURE l JOIN DP_ABMN a ON a.ID=l.DPID "
                        "JOIN DPV v ON v.DPID=l.DPID AND v.MeasureID=l.MeasureID "
                        "WHERE v.DatatypeID=2 AND v.SeqNum=0 GROUP BY a.Ready ORDER BY a.Ready",
                    ),
                    "sdev_propagation": _rows(
                        db,
                        "SELECT COUNT(*) compared, "
                        "MAX(ABS((rho.DataSDev/NULLIF(ABS(rho.DataValue),0))-(r.DataSDev/NULLIF(ABS(r.DataValue),0)))) max_rho_r_cv_difference, "
                        "MAX(ABS((du.DataSDev/NULLIF(ABS(du.DataValue),0))-(r.DataSDev/NULLIF(ABS(r.DataValue),0)))) max_du_r_cv_difference "
                        "FROM DP_MEASURE l "
                        "JOIN DPV rho ON rho.DPID=l.DPID AND rho.MeasureID=l.MeasureID AND rho.DatatypeID=2 AND rho.SeqNum=0 "
                        "JOIN DPV r ON r.DPID=l.DPID AND r.MeasureID=l.MeasureID AND r.DatatypeID=5 AND r.Channel=rho.Channel AND r.SeqNum=0 "
                        "JOIN DPV du ON du.DPID=l.DPID AND du.MeasureID=l.MeasureID AND du.DatatypeID=7 AND du.Channel=rho.Channel AND du.SeqNum=0",
                    ),
                    "link_channel_consistency": _rows(
                        db,
                        "SELECT links_per_measure, primary_channels, COUNT(*) measure_count FROM ("
                        "SELECT l.MeasureID, COUNT(DISTINCT l.ID) links_per_measure, "
                        "COUNT(DISTINCT CASE WHEN v.DatatypeID=2 AND v.SeqNum=0 THEN v.Channel END) primary_channels "
                        "FROM DP_MEASURE l LEFT JOIN DPV v ON v.DPID=l.DPID AND v.MeasureID=l.MeasureID "
                        "GROUP BY l.MeasureID) GROUP BY links_per_measure,primary_channels "
                        "ORDER BY links_per_measure,primary_channels",
                    ),
                    "measure_coordinates": _rows(
                        db,
                        "SELECT COUNT(*) count, "
                        "SUM(CASE WHEN PosLatitude IS NOT NULL THEN 1 ELSE 0 END) lat_present, "
                        "SUM(CASE WHEN PosLongitude IS NOT NULL THEN 1 ELSE 0 END) lon_present, "
                        "MIN(PosLatitude) min_lat, MAX(PosLatitude) max_lat, "
                        "MIN(PosLongitude) min_lon, MAX(PosLongitude) max_lon "
                        "FROM Measures",
                    ),
                }
            )

        return {
            "path": str(path.resolve()),
            "sha256": raw_hash,
            "byte_count": path.stat().st_size,
            "sqlite": {
                "application_id": _scalar(db, "PRAGMA application_id"),
                "user_version": _scalar(db, "PRAGMA user_version"),
                "encoding": _scalar(db, "PRAGMA encoding"),
                "page_size": _scalar(db, "PRAGMA page_size"),
                "page_count": _scalar(db, "PRAGMA page_count"),
                "journal_mode": _scalar(db, "PRAGMA journal_mode"),
            },
            "objects": objects,
            "tables": tables,
            "distributions": distributions,
            "findings": findings,
        }
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol-zip", type=Path)
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    result = [inspect(path, args.protocol_zip) for path in args.paths]
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
