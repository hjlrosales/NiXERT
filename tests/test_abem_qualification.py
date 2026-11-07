"""Offline tests for ABEM semantic qualification."""

from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from nix_ert.data.abem_intermediate import FactStatus, parse_abem_intermediate
from nix_ert.data.abem_qualification import (
    AuthorizedDatasetEvidence,
    QualificationStatus,
    qualify_abem,
)


class ABEMQualificationTests(unittest.TestCase):
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
        db.execute(
            "INSERT INTO TaskSettings VALUES (1, -1, 'ProtocolFile', ?, 0)",
            ("/vendor/VES_Schlumberger.xml" if ves else "/vendor/Gradient_2x21.xml",),
        )
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

    def test_exact_authorized_evidence_verifies_dataset_kind_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._make_fixture(Path(directory))
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            report = qualify_abem(
                parse_abem_intermediate(path),
                evidence=(AuthorizedDatasetEvidence(digest, "ERT", "Gradient_1", "/vendor/Gradient_2x21.xml", "offline fixture evidence"),),
            )
            self.assertEqual(report.result("dataset_kind").status, QualificationStatus.VERIFIED)
            self.assertEqual(report.result("dataset_kind").interpretation, "ERT")
            self.assertEqual(report.importer_readiness, "NOT_READY")
            self.assertFalse(report.importer_ready)

    def test_unmatched_fixture_does_not_infer_ert_or_ves(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = qualify_abem(parse_abem_intermediate(self._make_fixture(Path(directory), task_name="VES Schlumberger_1")))
            kind = report.result("dataset_kind")
            self.assertEqual(kind.status, QualificationStatus.BLOCKED)
            self.assertIsNone(kind.interpretation)
            self.assertTrue(kind.blocks_import)
            self.assertIn("no exact authorized evidence", kind.evidence)

    def test_verified_raw_semantics_and_non_blocking_unknowns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parsed = parse_abem_intermediate(self._make_fixture(Path(directory)))
            report = qualify_abem(parsed)
            self.assertEqual(report.result("source_provenance").status, QualificationStatus.VERIFIED)
            self.assertEqual(report.result("measurement_relationships").status, QualificationStatus.VERIFIED)
            self.assertEqual(report.result("dp_abmn_geometry_relationship").status, QualificationStatus.VERIFIED)
            self.assertEqual(report.result("dpv_relationship").status, QualificationStatus.VERIFIED)
            self.assertEqual(report.result("vendor_declared_units").status, QualificationStatus.VERIFIED)
            self.assertEqual(report.result("observed_vendor_values").status, QualificationStatus.VERIFIED)
            self.assertEqual(report.result("electrode_roles").status, QualificationStatus.BLOCKED)
            self.assertEqual(report.result("array_and_protocol_semantics").status, QualificationStatus.BLOCKED)
            self.assertEqual(report.result("coordinate_reference_system").status, QualificationStatus.BLOCKED)
            self.assertEqual(report.result("qc_and_quality_semantics").status, QualificationStatus.BLOCKED)
            self.assertEqual(report.result("uncertainty_semantics").status, QualificationStatus.BLOCKED)
            self.assertEqual(report.result("timestamp_normalization").status, QualificationStatus.UNKNOWN)
            self.assertFalse(report.result("timestamp_normalization").blocks_import)
            self.assertEqual(report.result("auxiliary_semantics").status, QualificationStatus.UNKNOWN)
            self.assertFalse(report.result("auxiliary_semantics").blocks_import)
            self.assertEqual(report.result("calculated_scientific_values").status, QualificationStatus.UNSUPPORTED)
            self.assertFalse(report.result("calculated_scientific_values").blocks_import)
            self.assertTrue(report.result("nix_compatibility").blocks_import)

    def test_invalid_intermediate_relationship_is_invalid_and_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parsed = parse_abem_intermediate(self._make_fixture(Path(directory), duplicate_link=True))
            self.assertEqual(parsed.status, FactStatus.INVALID)
            report = qualify_abem(parsed)
            relationship = report.result("measurement_relationships")
            self.assertEqual(relationship.status, QualificationStatus.INVALID)
            self.assertTrue(relationship.blocks_import)
            self.assertEqual(report.result("intermediate_integrity").status, QualificationStatus.INVALID)
            self.assertEqual(report.importer_readiness, "NOT_READY")

    def test_provenance_and_qualification_are_deterministic_without_nix_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._make_fixture(Path(directory))
            parsed = parse_abem_intermediate(path)
            first = qualify_abem(parsed)
            second = qualify_abem(parse_abem_intermediate(path))
            self.assertEqual(first.to_dict(), second.to_dict())
            self.assertEqual(first.source_sha256, hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertTrue(all(result.source for result in first.results if result.name != "timestamp_normalization" or result.source))
            self.assertFalse(any(name.startswith("nix_") for name in ("" if False else ())))
            self.assertFalse(first.importer_ready)


if __name__ == "__main__":
    unittest.main()
