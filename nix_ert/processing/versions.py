"""Reproducible immutable processing and model version records."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from nix_ert.data.project import ProjectStore


class VersioningError(ValueError):
    """Raised for invalid or missing version records."""


@dataclass(frozen=True)
class VersionRecord:
    id: str
    survey_id: str
    kind: str
    name: str
    parent_id: str | None
    parameters: Mapping[str, Any]
    snapshot: Mapping[str, Any]
    parameter_hash: str
    notes: str
    created_at: str


def canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def parameter_hash(parameters: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(parameters).encode("utf-8")).hexdigest()


class VersionStore:
    """Version records backed by the project's existing SQLite connection."""

    def __init__(self, project: ProjectStore, *, create: bool = True):
        self.project = project
        if project.connection is None:
            raise RuntimeError("Project store must be open")
        if create:
            self._initialize()
        elif not self._exists():
            raise VersioningError("version table is not available")

    def _exists(self) -> bool:
        row = self.project.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'versions'"
        ).fetchone()
        return row is not None

    def _initialize(self) -> None:
        self.project.connection.execute(
            """CREATE TABLE IF NOT EXISTS versions (
                id TEXT PRIMARY KEY, survey_id TEXT NOT NULL, kind TEXT NOT NULL,
                name TEXT NOT NULL, parent_id TEXT, parameters_json TEXT NOT NULL,
                snapshot_json TEXT NOT NULL, parameter_hash TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
            )"""
        )
        self.project.connection.commit()

    def create(
        self, survey_id: str, kind: str, name: str, parameters: Mapping[str, Any],
        snapshot: Mapping[str, Any], parent_id: str | None = None, notes: str = "",
    ) -> VersionRecord:
        if self.project.get_survey(survey_id) is None:
            raise VersioningError(f"Unknown survey: {survey_id}")
        if not kind.strip() or not name.strip():
            raise VersioningError("version kind and name cannot be empty")
        if parent_id is not None and self.get(parent_id) is None:
            raise VersioningError(f"Unknown parent version: {parent_id}")
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        record = VersionRecord(
            id=str(uuid.uuid4()), survey_id=survey_id, kind=kind.strip(), name=name.strip(),
            parent_id=parent_id, parameters=dict(parameters), snapshot=dict(snapshot),
            parameter_hash=parameter_hash(parameters), notes=notes, created_at=now,
        )
        self.project.connection.execute(
            "INSERT INTO versions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (record.id, record.survey_id, record.kind, record.name, record.parent_id,
             canonical_json(record.parameters), canonical_json(record.snapshot),
             record.parameter_hash, record.notes, record.created_at),
        )
        self.project.connection.commit()
        return record

    def get(self, version_id: str) -> VersionRecord | None:
        row = self.project.connection.execute("SELECT * FROM versions WHERE id = ?", (version_id,)).fetchone()
        if row is None:
            return None
        return VersionRecord(
            id=row["id"], survey_id=row["survey_id"], kind=row["kind"], name=row["name"],
            parent_id=row["parent_id"], parameters=json.loads(row["parameters_json"]),
            snapshot=json.loads(row["snapshot_json"]), parameter_hash=row["parameter_hash"],
            notes=row["notes"], created_at=row["created_at"],
        )

    def list(self, survey_id: str, kind: str | None = None) -> list[VersionRecord]:
        query = "SELECT * FROM versions WHERE survey_id = ?"
        args: list[str] = [survey_id]
        if kind is not None:
            query += " AND kind = ?"
            args.append(kind)
        query += " ORDER BY created_at, id"
        return [self.get(row["id"]) for row in self.project.connection.execute(query, args).fetchall()]  # type: ignore[misc]

    def rename(self, version_id: str, name: str) -> None:
        if not name.strip():
            raise VersioningError("version name cannot be empty")
        cursor = self.project.connection.execute("UPDATE versions SET name = ? WHERE id = ?", (name.strip(), version_id))
        if cursor.rowcount != 1:
            raise VersioningError(f"Unknown version: {version_id}")
        self.project.connection.commit()

    def update_notes(self, version_id: str, notes: str) -> None:
        cursor = self.project.connection.execute("UPDATE versions SET notes = ? WHERE id = ?", (notes, version_id))
        if cursor.rowcount != 1:
            raise VersioningError(f"Unknown version: {version_id}")
        self.project.connection.commit()

    def compare(self, first_id: str, second_id: str) -> dict[str, object]:
        first, second = self.get(first_id), self.get(second_id)
        if first is None or second is None:
            raise VersioningError("both versions must exist")
        keys = sorted(set(first.parameters) | set(second.parameters))
        return {
            "same_survey": first.survey_id == second.survey_id,
            "same_kind": first.kind == second.kind,
            "parameter_hash_equal": first.parameter_hash == second.parameter_hash,
            "parameter_changes": {key: (first.parameters.get(key), second.parameters.get(key)) for key in keys if first.parameters.get(key) != second.parameters.get(key)},
            "snapshot_equal": first.snapshot == second.snapshot,
        }

    def restore_by_copy(self, version_id: str, name: str | None = None, notes: str = "") -> VersionRecord:
        source = self.get(version_id)
        if source is None:
            raise VersioningError(f"Unknown version: {version_id}")
        return self.create(source.survey_id, source.kind, name or f"Copy of {source.name}", source.parameters, source.snapshot, parent_id=source.id, notes=notes)
