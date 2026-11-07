"""Tests for read-only Barugo/ABEM sample inspection."""

from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from nix_ert.data.abem_sample import ABEMInspectionError, inspect_abem_project


class ABEMSampleInspectionTests(unittest.TestCase):
    def _make_fixture(
        self,
        root: Path,
        *,
        ves: bool = False,
        duplicate_link: bool = False,
        missing_geometry: bool = False,
        missing_measure: bool = False,
        missing_dpv: bool = False,
        nonfinite_geometry: bool = False,
    ) -> Path:
        path = root / "project.db"
        db = sqlite3.connect(path)
        db.executescript(
            """
            CREATE TABLE ProjectSchemaVersion (Version INTEGER, Comment TEXT);
            CREATE TABLE CommonSchemaVersion (Version INTEGER, Comment TEXT);
            CREATE TABLE Tasks (ID INTEGER, Name TEXT, Active INTEGER, PosX REAL, PosY REAL, PosZ REAL, SpacingX REAL, SpacingY REAL, SpacingZ REAL, ArrayCode INTEGER, Time TEXT);
            CREATE TABLE DPV (ID INTEGER, TaskID INTEGER, MeasureID INTEGER, DPID INTEGER, Channel INTEGER, SeqNum INTEGER, DatatypeID INTEGER, DataValue REAL, DataSDev REAL, ADValue INTEGER, ADRange INTEGER, Status INTEGER, N INTEGER, MCycles INTEGER, DataSDevType INTEGER);
            CREATE TABLE DP_ABMN (ID INTEGER, TaskID INTEGER, DPKEY TEXT, APosX REAL, APosY REAL, APosZ REAL, BPosX REAL, BPosY REAL, BPosZ REAL, MPosX REAL, MPosY REAL, MPosZ REAL, NPosX REAL, NPosY REAL, NPosZ REAL, FocusX REAL, FocusY REAL, FocusZ REAL, Ready INTEGER, Note TEXT, Mode INTEGER, ModeValue REAL);
            CREATE TABLE DP_MEASURE (ID INTEGER, DPID INTEGER, MeasureID INTEGER, Ready INTEGER);
            CREATE TABLE Measures (ID INTEGER, StationID INTEGER, PosLatitude REAL, PosLongitude REAL, PosQuality INTEGER, Time TEXT, IntPowerVolt REAL, ExtPowerVolt REAL, Temp REAL, Light REAL, SessionID INTEGER, PositionId INTEGER);
            CREATE TABLE Datatype (ID INTEGER, Name TEXT, Unit TEXT, Explanation TEXT);
            CREATE TABLE Sessions (ID INTEGER, Time TEXT, TaskID INTEGER, InstrumentSerial TEXT, InstrumentSoftware TEXT, TransmitterSerial TEXT, TransmitterSoftware TEXT);
            CREATE TABLE TaskSettings (key1 INTEGER, key2 INTEGER, Setting TEXT, Value TEXT, Auto INTEGER);
            """
        )
        task_name = "VES Schlumberger_1" if ves else "Gradient_1"
        protocol = "/home/root/protocols/VES_Schlumberger.xml" if ves else "/home/root/protocols/Gradient_2x21.xml"
        db.execute("INSERT INTO ProjectSchemaVersion VALUES (4, 'fixture')")
        db.execute("INSERT INTO CommonSchemaVersion VALUES (3, 'fixture')")
        db.execute("INSERT INTO Tasks VALUES (1, ?, 1, 0, 0, 0, 1, 1, 1, ?, '2025-01-01')", (task_name, 7 if ves else 15))
        db.execute("INSERT INTO Datatype VALUES (2, 'ρapp', 'Ωm', 'Apparent Resistivity value')")
        db.execute("INSERT INTO Datatype VALUES (5, 'R', 'Ω', 'Resistance')")
        db.execute("INSERT INTO TaskSettings VALUES (1, -1, 'ProtocolFile', ?, 0)", (protocol,))
        db.execute("INSERT INTO Sessions VALUES (1, '2025-01-01', 1, 'MOCK-SERIAL', 'mock-software', 'mock-tx', 'mock-fw')")
        if not missing_measure:
            db.execute("INSERT INTO Measures VALUES (1, 1, NULL, NULL, NULL, '2025-01-01', NULL, NULL, NULL, NULL, 1, NULL)")
        if not missing_geometry:
            x_coordinate = "'nan'" if nonfinite_geometry else "3"
            db.execute(f"INSERT INTO DP_ABMN VALUES (1, 1, 'fixture', 0, 0, 0, {x_coordinate}, 0, 0, 1, 0, 0, 2, 0, 0, 1.5, 0, 0, 0, NULL, 1, NULL)")
        if not missing_dpv:
            db.execute("INSERT INTO DPV VALUES (1, 1, 1, 1, 0, 0, 2, 100, 0, 0, 0, 0, 0, 0, 0)")
            db.execute("INSERT INTO DPV VALUES (2, 1, 1, 1, 0, 0, 5, 2, 0, 0, 0, 0, 0, 0, 0)")
        db.execute("INSERT INTO DP_MEASURE VALUES (1, 1, 1, 1)")
        if duplicate_link:
            db.execute("INSERT INTO DP_MEASURE VALUES (2, 1, 1, 1)")
        db.commit()
        db.close()
        return path

    def test_inspection_is_read_only_and_classifies_explicit_vendor_facts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._make_fixture(Path(directory))
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            result = inspect_abem_project(path, label="Barugo fixture ERT")
            self.assertEqual(result.kind, "ERT")
            self.assertEqual(result.project_schema_version, 4)
            self.assertEqual(result.measurement_links, 1)
            self.assertEqual(result.apparent_resistivity_rows, 1)
            self.assertEqual(result.apparent_resistivity_minimum, 100.0)
            self.assertFalse(result.compatible_with_nix_project)
            self.assertIn("BARUGO SAMPLE DATA", result.summary())
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)

    def test_ves_classification_and_no_guessing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = inspect_abem_project(self._make_fixture(Path(directory), ves=True))
            self.assertEqual(result.kind, "VES")
            self.assertEqual(result.task_name, "VES Schlumberger_1")
            self.assertIn("NiX VES points are not persisted", result.compatibility_reasons[-1])

    def test_vendor_classification_boundary_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ert_root = Path(directory) / "ert"
            ves_root = Path(directory) / "ves"
            ert_root.mkdir()
            ves_root.mkdir()
            ert = inspect_abem_project(self._make_fixture(ert_root), label="fixture")
            ves = inspect_abem_project(self._make_fixture(ves_root, ves=True), label="fixture")
            self.assertEqual((ert.kind, ert.array_code), ("ERT", 15))
            self.assertEqual((ves.kind, ves.array_code), ("VES", 7))
            self.assertEqual(ert.protocol_file, "/home/root/protocols/Gradient_2x21.xml")
            self.assertEqual(ves.protocol_file, "/home/root/protocols/VES_Schlumberger.xml")
            for result in (ert, ves):
                self.assertFalse(result.compatible_with_nix_project)
                self.assertIn("ABEM vendor tables are not NiX", result.compatibility_reasons[0])
                self.assertIn("require a dedicated import contract", result.compatibility_reasons[1])

    def test_link_integrity_fail_closed_rules(self) -> None:
        cases = (
            ({"duplicate_link": True}, "duplicate observation links"),
            ({"missing_geometry": True}, "missing geometry"),
            ({"missing_measure": True}, "missing measurement metadata"),
            ({"missing_dpv": True}, "has no DPV values"),
            ({"nonfinite_geometry": True}, "non-finite coordinate"),
        )
        for options, message in cases:
            with self.subTest(options=options), tempfile.TemporaryDirectory() as directory:
                path = self._make_fixture(Path(directory), **options)
                with self.assertRaisesRegex(ABEMInspectionError, message):
                    inspect_abem_project(path)

    def test_no_linked_observations_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._make_fixture(Path(directory))
            db = sqlite3.connect(path)
            db.execute("DELETE FROM DP_MEASURE")
            db.commit()
            db.close()
            with self.assertRaisesRegex(ABEMInspectionError, "no linked measurements"):
                inspect_abem_project(path)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "incomplete.db"
            sqlite3.connect(path).close()
            with self.assertRaises(ABEMInspectionError):
                inspect_abem_project(path)
            with self.assertRaises(ABEMInspectionError):
                inspect_abem_project(Path(directory) / "missing.db")


if __name__ == "__main__":
    unittest.main()
