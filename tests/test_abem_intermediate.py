"""Offline qualification tests for the factual ABEM intermediate parser."""

from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from nix_ert.data.abem_intermediate import FactStatus, parse_abem_intermediate


class ABEMIntermediateParserTests(unittest.TestCase):
    def _make_fixture(
        self,
        root: Path,
        *,
        task_name: str = "Gradient_1",
        duplicate_link: bool = False,
        missing_geometry: bool = False,
        missing_measure: bool = False,
        missing_dpv: bool = False,
        invalid_geometry: bool = False,
    ) -> Path:
        path = root / "project.db"
        db = sqlite3.connect(path)
        db.executescript(
            """
            CREATE TABLE ProjectSchemaVersion (Version INTEGER, Comment TEXT);
            CREATE TABLE CommonSchemaVersion (Version INTEGER, Comment TEXT);
            CREATE TABLE Tasks (ID INTEGER, Name TEXT, Active INTEGER, PosX REAL, PosY REAL, PosZ REAL, SpacingX REAL, SpacingY REAL, SpacingZ REAL, ArrayCode INTEGER, Time TEXT);
            CREATE TABLE TaskSettings (key1 INTEGER, key2 INTEGER, Setting TEXT, Value TEXT, Auto INTEGER);
            CREATE TABLE Sessions (ID INTEGER, Time TEXT, TaskID INTEGER, InstrumentSerial TEXT, InstrumentSoftware TEXT, TransmitterSerial TEXT, TransmitterSoftware TEXT);
            CREATE TABLE Measures (ID INTEGER, StationID INTEGER, PosLatitude REAL, PosLongitude REAL, PosQuality INTEGER, Time TEXT, IntPowerVolt REAL, ExtPowerVolt REAL, Temp REAL, Light REAL, SessionID INTEGER, PositionId INTEGER);
            CREATE TABLE DP_ABMN (ID INTEGER, TaskID INTEGER, DPKEY TEXT, APosX REAL, APosY REAL, APosZ REAL, BPosX REAL, BPosY REAL, BPosZ REAL, MPosX REAL, MPosY REAL, MPosZ REAL, NPosX REAL, NPosY REAL, NPosZ REAL, FocusX REAL, FocusY REAL, FocusZ REAL, Ready INTEGER, Note TEXT, Mode INTEGER, ModeValue REAL);
            CREATE TABLE DP_MEASURE (ID INTEGER, DPID INTEGER, MeasureID INTEGER, Ready INTEGER);
            CREATE TABLE DPV (ID INTEGER, TaskID INTEGER, MeasureID INTEGER, DPID INTEGER, Channel INTEGER, SeqNum INTEGER, DatatypeID INTEGER, DataValue REAL, DataSDev REAL, ADValue INTEGER, ADRange INTEGER, Status INTEGER, N INTEGER, MCycles INTEGER, DataSDevType INTEGER);
            CREATE TABLE Datatype (ID INTEGER, Name TEXT, Unit TEXT, Explanation TEXT);
            CREATE TABLE VendorBlob (ID INTEGER, Payload BLOB);
            """
        )
        ves = "VES" in task_name
        db.execute("INSERT INTO ProjectSchemaVersion VALUES (4, 'fixture')")
        db.execute("INSERT INTO CommonSchemaVersion VALUES (3, 'fixture')")
        db.execute(
            "INSERT INTO Tasks VALUES (1, ?, 1, 0, 0, 0, 1, 1, 1, ?, '2025-01-01')",
            (task_name, 7 if ves else 15),
        )
        db.execute("INSERT INTO TaskSettings VALUES (1, -1, 'ProtocolFile', ?, 0)", ("VES_Schlumberger.xml" if ves else "Gradient_2x21.xml",))
        db.execute("INSERT INTO Sessions VALUES (1, '2025-01-01', 1, 'MOCK', 'mock-software', 'mock-tx', 'mock-fw')")
        if not missing_measure:
            db.execute("INSERT INTO Measures VALUES (1, 1, NULL, NULL, NULL, '2025-01-01', NULL, NULL, NULL, NULL, 1, NULL)")
        if not missing_geometry:
            x = "not-a-number" if invalid_geometry else 3
            db.execute(
                "INSERT INTO DP_ABMN VALUES (1, 1, ?, 0, 0, 0, ?, 0, 0, 1, 0, 0, 2, 0, 0, 1.5, 0, 0, 0, NULL, 1, NULL)",
                (f"0;0;0;{x};0;0;1;0;0;2;0;0;-2", x),
            )
        if not missing_dpv:
            db.execute("INSERT INTO DPV VALUES (1, 1, 1, 1, 0, 0, 2, 100, 0, 0, 0, 0, 0, 0, 0)")
            db.execute("INSERT INTO DPV VALUES (2, 1, 1, 1, 1, 1, 5, 2, 0, 0, 0, 0, 0, 0, 0)")
        db.execute("INSERT INTO Datatype VALUES (2, 'ρapp', 'Ωm', 'Apparent Resistivity value')")
        db.execute("INSERT INTO Datatype VALUES (5, 'R', 'Ω', 'Resistance')")
        db.execute("INSERT INTO VendorBlob VALUES (1, X'00FF')")
        db.execute("INSERT INTO DP_MEASURE VALUES (1, 1, 1, 1)")
        if duplicate_link:
            db.execute("INSERT INTO DP_MEASURE VALUES (2, 1, 1, 1)")
        db.commit()
        db.close()
        return path

    def test_raw_values_provenance_and_relationship_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._make_fixture(Path(directory))
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            parsed = parse_abem_intermediate(path)
            self.assertEqual(parsed.status, FactStatus.OBSERVED)
            self.assertFalse(parsed.importer_ready)
            task = parsed.table("Tasks")
            self.assertIsNotNone(task)
            assert task is not None
            name = task.rows[0].field("Name")
            self.assertIsNotNone(name)
            assert name is not None
            self.assertEqual(name.value, "Gradient_1")
            self.assertEqual(name.status, FactStatus.OBSERVED)
            self.assertEqual(name.source.table, "Tasks")
            self.assertEqual(name.source.row, "ID=1")
            blob = parsed.table("VendorBlob")
            self.assertIsNotNone(blob)
            assert blob is not None
            self.assertEqual(blob.rows[0].field("Payload").value, b"\x00\xff")
            self.assertEqual(len(parsed.observation_links), 1)
            self.assertEqual(parsed.observation_links[0].status, FactStatus.OBSERVED)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)

    def test_unknown_and_unsupported_semantics_are_not_guessed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ert = parse_abem_intermediate(self._make_fixture(Path(directory)))
            ves_root = Path(directory) / "ves"
            ves_root.mkdir()
            ves = parse_abem_intermediate(self._make_fixture(ves_root, task_name="VES Schlumberger_1"))
            for parsed in (ert, ves):
                self.assertEqual(parsed.semantic("dataset_kind").status, FactStatus.UNKNOWN)
                self.assertEqual(parsed.semantic("array_and_protocol_code_meaning").status, FactStatus.UNKNOWN)
                self.assertEqual(parsed.semantic("electrode_numbering_and_switch_mapping").status, FactStatus.UNKNOWN)
                self.assertEqual(parsed.semantic("coordinate_reference_system_and_units").status, FactStatus.UNKNOWN)
                self.assertEqual(parsed.semantic("quality_status_and_uncertainty_semantics").status, FactStatus.UNKNOWN)
                self.assertEqual(parsed.semantic("ves_persistence_in_nix").status, FactStatus.UNSUPPORTED)
                self.assertEqual(parsed.semantic("ls2_communication").status, FactStatus.UNSUPPORTED)
                self.assertFalse(parsed.importer_ready)

    def test_invalid_links_are_retained_and_marked_invalid(self) -> None:
        cases = (
            ({"duplicate_link": True}, "duplicate"),
            ({"missing_geometry": True}, "missing DP_ABMN"),
            ({"missing_measure": True}, "missing Measures"),
            ({"missing_dpv": True}, "missing DPV"),
            ({"invalid_geometry": True}, "invalid value"),
        )
        for options, expected in cases:
            with self.subTest(options=options), tempfile.TemporaryDirectory() as directory:
                parsed = parse_abem_intermediate(self._make_fixture(Path(directory), **options))
                self.assertEqual(parsed.status, FactStatus.INVALID)
                self.assertTrue(parsed.has_invalid_facts or parsed.issues)
                self.assertTrue(any(expected in issue for issue in parsed.issues) or any(expected in link.note for link in parsed.observation_links))

    def test_missing_required_tables_are_invalid_not_reinterpreted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "incomplete.db"
            db = sqlite3.connect(path)
            db.execute("CREATE TABLE Tasks (ID INTEGER, Name TEXT)")
            db.commit()
            db.close()
            parsed = parse_abem_intermediate(path)
            self.assertEqual(parsed.status, FactStatus.INVALID)
            self.assertIn("missing required ABEM tables", parsed.issues[0])
            self.assertFalse(parsed.importer_ready)

    def test_repeated_parsing_has_deterministic_factual_view(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._make_fixture(Path(directory))
            first = parse_abem_intermediate(path).to_dict()
            second = parse_abem_intermediate(path).to_dict()
            self.assertEqual(first, second)
            self.assertEqual(first["status"], "observed")
            self.assertEqual(first["tables"][0]["name"], "CommonSchemaVersion")


if __name__ == "__main__":
    unittest.main()
