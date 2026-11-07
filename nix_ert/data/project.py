"""SQLite persistence for project metadata and survey organization."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from nix_ert.data.measurements import ImportedDataset, Measurement, MeasurementStatus
from nix_ert.data.models import ProjectMetadata, Survey, SurveyType, utc_now

SCHEMA_VERSION = 4


class ProjectStore:
    """Small, transactional SQLite store for one NiX ERT project."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.connection: sqlite3.Connection | None = None

    def open(self, *, initialize: bool = True) -> None:
        if self.connection is not None:
            return
        if not initialize and not self.path.is_file():
            raise FileNotFoundError(self.path)
        existed = self.path.exists()
        if initialize:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        create_schema = initialize and not existed
        try:
            connection = sqlite3.connect(self.path)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            if not create_schema:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                required = {
                    "schema_info", "project_metadata", "surveys", "imported_sources",
                    "electrodes", "measurements",
                }
                if not required.issubset(tables):
                    raise ValueError("project database is missing required NiX ERT tables")
            else:
                connection.execute("PRAGMA journal_mode = WAL")
            self.connection = connection
            if create_schema:
                self._initialize_schema()
            else:
                self._migrate_schema()
        except (sqlite3.DatabaseError, ValueError) as exc:
            self.connection = None
            if "connection" in locals():
                connection.close()
            if isinstance(exc, ValueError):
                raise
            raise ValueError(f"Unable to open project database {self.path}: {exc}") from exc

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def __enter__(self) -> "ProjectStore":
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _db(self) -> sqlite3.Connection:
        if self.connection is None:
            raise RuntimeError("Project store is not open")
        return self.connection

    def _initialize_schema(self) -> None:
        db = self._db()
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_info (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS project_metadata (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                name TEXT NOT NULL,
                client TEXT NOT NULL DEFAULT '',
                location TEXT NOT NULL DEFAULT '',
                survey_date TEXT,
                operator TEXT NOT NULL DEFAULT '',
                instrument TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS surveys (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                survey_type TEXT NOT NULL CHECK (survey_type IN ('ERT', 'VES', '3D ERT')),
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS imported_sources (
                id TEXT PRIMARY KEY,
                survey_id TEXT NOT NULL REFERENCES surveys(id) ON DELETE CASCADE,
                original_name TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                byte_count INTEGER NOT NULL,
                imported_at TEXT NOT NULL,
                UNIQUE(survey_id, sha256)
            );
            CREATE TABLE IF NOT EXISTS electrodes (
                source_id TEXT NOT NULL REFERENCES imported_sources(id) ON DELETE CASCADE,
                number INTEGER NOT NULL,
                x REAL NOT NULL,
                y REAL NOT NULL DEFAULT 0,
                elevation REAL,
                PRIMARY KEY(source_id, number)
            );
            CREATE TABLE IF NOT EXISTS measurements (
                source_id TEXT NOT NULL REFERENCES imported_sources(id) ON DELETE CASCADE,
                row_number INTEGER NOT NULL,
                measurement_index INTEGER,
                a INTEGER NOT NULL,
                b INTEGER NOT NULL,
                m INTEGER NOT NULL,
                n INTEGER NOT NULL,
                apparent_resistivity REAL,
                resistance REAL,
                current REAL,
                voltage REAL,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                quality TEXT,
                extra_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY(source_id, row_number)
            );
            CREATE TABLE IF NOT EXISTS report_runs (
                id TEXT PRIMARY KEY,
                survey_id TEXT NOT NULL REFERENCES surveys(id) ON DELETE CASCADE,
                version_id TEXT,
                source_hashes_json TEXT NOT NULL,
                output_path TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                state_fingerprint TEXT NOT NULL DEFAULT ''
            );
            INSERT OR REPLACE INTO schema_info(key, value) VALUES ('schema_version', '4');
            """
        )
        db.commit()

    def _migrate_schema(self) -> None:
        """Apply only supported, additive schema migrations."""
        db = self._db()
        row = db.execute(
            "SELECT value FROM schema_info WHERE key = 'schema_version'"
        ).fetchone()
        if row is None:
            raise ValueError("project database has no supported schema version")
        try:
            version = int(row["value"])
        except (TypeError, ValueError) as exc:
            raise ValueError("project database has an invalid schema version") from exc
        if version > SCHEMA_VERSION:
            raise ValueError(
                f"project schema version {version} is newer than supported version {SCHEMA_VERSION}"
            )
        if version < 2:
            raise ValueError(f"project schema version {version} is unsupported")
        if version < 3:
            db.execute(
                """CREATE TABLE IF NOT EXISTS report_runs (
                    id TEXT PRIMARY KEY,
                    survey_id TEXT NOT NULL REFERENCES surveys(id) ON DELETE CASCADE,
                    version_id TEXT,
                    source_hashes_json TEXT NOT NULL,
                    output_path TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    state_fingerprint TEXT NOT NULL DEFAULT ''
                )"""
            )
            version = 3
        if version < 4:
            columns = {
                row["name"]
                for row in db.execute("PRAGMA table_info(report_runs)").fetchall()
            }
            if "state_fingerprint" not in columns:
                db.execute(
                    "ALTER TABLE report_runs ADD COLUMN state_fingerprint TEXT NOT NULL DEFAULT ''"
                )
            version = 4
        db.execute(
            "INSERT OR REPLACE INTO schema_info(key, value) VALUES ('schema_version', ?)",
            (str(version),),
        )
        db.commit()

    def save_metadata(self, metadata: ProjectMetadata) -> None:
        now = utc_now().isoformat()
        db = self._db()
        existing = db.execute("SELECT created_at FROM project_metadata WHERE id = 1").fetchone()
        created_at = existing["created_at"] if existing else now
        db.execute(
            """
            INSERT INTO project_metadata
                (id, name, client, location, survey_date, operator, instrument, notes, created_at, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, client=excluded.client, location=excluded.location,
                survey_date=excluded.survey_date, operator=excluded.operator,
                instrument=excluded.instrument, notes=excluded.notes, updated_at=excluded.updated_at
            """,
            (
                metadata.name, metadata.client, metadata.location,
                metadata.survey_date.isoformat() if metadata.survey_date else None,
                metadata.operator, metadata.instrument, metadata.notes,
                created_at, now,
            ),
        )
        db.commit()

    def load_metadata(self) -> ProjectMetadata | None:
        row = self._db().execute("SELECT * FROM project_metadata WHERE id = 1").fetchone()
        if row is None:
            return None
        parsed_date = date.fromisoformat(row["survey_date"]) if row["survey_date"] else None
        return ProjectMetadata(
            name=row["name"], client=row["client"], location=row["location"],
            survey_date=parsed_date, operator=row["operator"],
            instrument=row["instrument"], notes=row["notes"],
        )

    def add_survey(
        self, name: str, survey_type: SurveyType, metadata: dict[str, Any] | None = None
    ) -> Survey:
        if not name.strip():
            raise ValueError("Survey name cannot be empty")
        now = utc_now()
        survey = Survey(
            id=str(uuid.uuid4()), name=name.strip(), survey_type=survey_type,
            metadata=dict(metadata or {}), created_at=now, updated_at=now,
        )
        self._db().execute(
            "INSERT INTO surveys(id, name, survey_type, metadata_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (survey.id, survey.name, survey.survey_type.value, json.dumps(survey.metadata), now.isoformat(), now.isoformat()),
        )
        self._db().commit()
        return survey

    def list_surveys(self) -> list[Survey]:
        rows = self._db().execute("SELECT * FROM surveys ORDER BY created_at, name").fetchall()
        return [self._row_to_survey(row) for row in rows]

    def get_survey(self, survey_id: str) -> Survey | None:
        row = self._db().execute("SELECT * FROM surveys WHERE id = ?", (survey_id,)).fetchone()
        return self._row_to_survey(row) if row else None

    def update_survey(self, survey: Survey, commit: bool = True) -> None:
        if not survey.name.strip():
            raise ValueError("Survey name cannot be empty")
        updated = utc_now()
        cursor = self._db().execute(
            "UPDATE surveys SET name = ?, survey_type = ?, metadata_json = ?, updated_at = ? WHERE id = ?",
            (survey.name.strip(), survey.survey_type.value, json.dumps(survey.metadata), updated.isoformat(), survey.id),
        )
        if cursor.rowcount != 1:
            raise KeyError(f"Unknown survey: {survey.id}")
        if commit:
            self._db().commit()

    def record_import(
        self, survey_id: str, original_name: str, stored_path: Path | str,
        sha256: str, byte_count: int, dataset: ImportedDataset,
    ) -> None:
        """Record immutable source provenance and parsed survey facts."""
        if self.get_survey(survey_id) is None:
            raise KeyError(f"Unknown survey: {survey_id}")
        db = self._db()
        source_id = str(uuid.uuid4())
        try:
            with db:
                db.execute(
                    "INSERT INTO imported_sources(id, survey_id, original_name, stored_path, sha256, byte_count, imported_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (source_id, survey_id, original_name, str(stored_path), sha256, byte_count, utc_now().isoformat()),
                )
                db.executemany(
                    "INSERT INTO electrodes(source_id, number, x, y, elevation) VALUES (?, ?, ?, ?, ?)",
                    [(source_id, e.number, e.x, e.y, e.elevation) for e in dataset.electrodes],
                )
                db.executemany(
                    """INSERT INTO measurements
                    (source_id, row_number, measurement_index, a, b, m, n,
                     apparent_resistivity, resistance, current, voltage, status,
                     quality, extra_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    [
                        (source_id, item.row_number, item.measurement_index, item.a, item.b,
                         item.m, item.n, item.apparent_resistivity, item.resistance,
                         item.current, item.voltage, item.status.value, item.quality,
                         json.dumps(item.extra or {}))
                        for item in dataset.measurements
                    ],
                )
                metadata = {
                    "data_count": dataset.data_count,
                    "electrode_spacing": dataset.electrode_spacing,
                    "array_type": dataset.array_type,
                    "electrode_count": len(dataset.electrodes),
                    "invalid_measurement_count": dataset.invalid_measurement_count,
                }
                survey = self.get_survey(survey_id)
                assert survey is not None
                survey.metadata = {**survey.metadata, "import": metadata}
                self.update_survey(survey, commit=False)
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"This source is already imported for survey {survey_id}") from exc

    def list_imports(self, survey_id: str) -> list[dict[str, Any]]:
        rows = self._db().execute(
            "SELECT id, original_name, stored_path, sha256, byte_count, imported_at FROM imported_sources WHERE survey_id = ? ORDER BY imported_at",
            (survey_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def verify_import_sources(self, survey_id: str) -> tuple[str, ...]:
        """Verify every managed raw source still matches its recorded SHA-256.

        Paths stored in the project are accepted only below this project's
        managed ``raw`` directory. A hand-edited database cannot make report
        provenance read arbitrary files elsewhere on the system.
        """
        import hashlib

        missing_or_changed: list[str] = []
        raw_root = (self.path.parent / "raw").resolve()
        for item in self.list_imports(survey_id):
            source = Path(item["stored_path"])
            if not source.is_absolute():
                source = self.path.parent / source
            try:
                resolved = source.resolve()
                resolved.relative_to(raw_root)
            except (OSError, ValueError):
                missing_or_changed.append(f"{item['original_name']}: managed source path is outside project raw data")
                continue
            if not resolved.is_file():
                missing_or_changed.append(f"{item['original_name']}: missing managed source")
                continue
            try:
                digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
            except OSError:
                missing_or_changed.append(f"{item['original_name']}: managed source cannot be read")
                continue
            if digest != item["sha256"]:
                missing_or_changed.append(f"{item['original_name']}: managed source hash mismatch")
        return tuple(missing_or_changed)

    def list_electrodes(self, survey_id: str) -> list[tuple[str, int, float, float, float | None]]:
        """Return ``(source_id, number, x, y, elevation)`` for every imported source.

        Electrode geometry is stored per source at import time. Callers that
        build a scientific mesh must bind to these positions instead of
        reconstructing a uniform spacing from survey-level metadata, which is
        overwritten by the most recent import and would let one source silently
        change another source's geometry.
        """
        rows = self._db().execute(
            """SELECT e.source_id, e.number, e.x, e.y, e.elevation FROM electrodes e
            JOIN imported_sources s ON s.id = e.source_id
            WHERE s.survey_id = ? ORDER BY e.source_id, e.number""",
            (survey_id,),
        ).fetchall()
        return [
            (row["source_id"], row["number"], row["x"], row["y"], row["elevation"])
            for row in rows
        ]

    def list_measurements(self, survey_id: str) -> list[Measurement]:
        rows = self._db().execute(
            """SELECT m.* FROM measurements m
            JOIN imported_sources s ON s.id = m.source_id
            WHERE s.survey_id = ? ORDER BY m.row_number""",
            (survey_id,),
        ).fetchall()
        return [
            Measurement(
                source_id=row["source_id"], row_number=row["row_number"],
                a=row["a"], b=row["b"], m=row["m"], n=row["n"],
                apparent_resistivity=row["apparent_resistivity"], resistance=row["resistance"],
                current=row["current"], voltage=row["voltage"],
                measurement_index=row["measurement_index"],
                status=MeasurementStatus(row["status"]), quality=row["quality"],
                extra=json.loads(row["extra_json"]),
            )
            for row in rows
        ]

    def set_measurement_status(
        self, survey_id: str,
        changes: list[tuple[int, MeasurementStatus] | tuple[str, int, MeasurementStatus]],
    ) -> None:
        """Persist explicit status changes, scoped to source when available."""
        db = self._db()
        with db:
            for change in changes:
                if len(change) == 2:
                    row_number, status = change
                    matches = db.execute(
                        """SELECT COUNT(*) FROM measurements
                        WHERE row_number = ? AND source_id IN
                        (SELECT id FROM imported_sources WHERE survey_id = ?)""",
                        (row_number, survey_id),
                    ).fetchone()[0]
                    if matches == 0:
                        raise KeyError(f"Unknown measurement row {row_number} in survey {survey_id}")
                    if matches != 1:
                        raise ValueError(
                            f"Measurement row {row_number} is ambiguous in survey {survey_id}; source_id is required"
                        )
                    source_clause = ""
                    parameters = (status.value, row_number, survey_id)
                else:
                    source_id, row_number, status = change
                    source_clause = " AND source_id = ?"
                    parameters = (status.value, row_number, survey_id, source_id)
                cursor = db.execute(
                    """UPDATE measurements SET status = ? WHERE row_number = ?
                    AND source_id IN (SELECT id FROM imported_sources WHERE survey_id = ?)""" + source_clause,
                    parameters,
                )
                if cursor.rowcount != 1:
                    raise KeyError(f"Unknown measurement row {row_number} in survey {survey_id}")

    def record_report_run(
        self, survey_id: str, version_id: str | None,
        source_hashes: tuple[str, ...], output_path: Path | str,
        state_fingerprint: str = "",
    ) -> None:
        """Record a report artifact and its source/version provenance."""
        if self.get_survey(survey_id) is None:
            raise KeyError(f"Unknown survey: {survey_id}")
        self._db().execute(
            """INSERT INTO report_runs
            (id, survey_id, version_id, source_hashes_json, output_path, generated_at, state_fingerprint)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()), survey_id, version_id, json.dumps(source_hashes),
                str(output_path), utc_now().isoformat(), state_fingerprint,
            ),
        )
        self._db().commit()

    def list_report_runs(self, survey_id: str) -> list[dict[str, Any]]:
        rows = self._db().execute(
            "SELECT * FROM report_runs WHERE survey_id = ? ORDER BY generated_at",
            (survey_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _row_to_survey(self, row: sqlite3.Row) -> Survey:
        return Survey(
            id=row["id"], name=row["name"], survey_type=SurveyType(row["survey_type"]),
            metadata=json.loads(row["metadata_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )


class ProjectManager:
    """Lifecycle and recent-project facade used by the UI."""

    PROJECT_FILENAME = "project.nixert.sqlite3"

    def __init__(self, config: Any | None = None):
        self.config = config
        self.store: ProjectStore | None = None
        self.project_path: Path | None = None

    def create_project(self, directory: Path | str, metadata: ProjectMetadata) -> Path:
        directory = Path(directory)
        path = directory / self.PROJECT_FILENAME
        self.close()
        self.store = ProjectStore(path)
        self.store.open()
        self.store.save_metadata(metadata)
        self.project_path = path
        self._remember(path)
        return path

    def open_project(self, path: Path | str) -> ProjectMetadata | None:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(path)
        candidate = ProjectStore(path)
        try:
            candidate.open(initialize=False)
            metadata = candidate.load_metadata()
        except Exception:
            candidate.close()
            raise
        self.close()
        self.store = candidate
        self.project_path = path
        self._remember(path)
        return metadata

    def save(self, metadata: ProjectMetadata) -> None:
        if self.store is None:
            raise RuntimeError("No project is open")
        self.store.save_metadata(metadata)

    def close(self) -> None:
        if self.store is not None:
            self.store.close()
        self.store = None
        self.project_path = None

    def _remember(self, path: Path) -> None:
        if self.config is not None:
            self.config.remember_project(path)
            self.config.save()

    def __enter__(self) -> "ProjectManager":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
