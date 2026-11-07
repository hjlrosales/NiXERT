"""Tests for safe DAT import persistence."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from nix_ert.core.config import AppConfig
from nix_ert.data.import_service import import_dat_into_project
from nix_ert.data.measurements import MeasurementStatus
from nix_ert.data.models import ProjectMetadata, SurveyType
from nix_ert.data.project import ProjectManager, ProjectStore


DAT = """2
5
1
0
1 2 3 4 100
2 3 4 5 -25
"""


class DATImportPersistenceTests(unittest.TestCase):
    def test_import_preserves_source_and_records_measurements(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "field.dat"
            source.write_text(DAT, encoding="utf-8")
            original_bytes = source.read_bytes()
            manager = ProjectManager(AppConfig.load(root / "config"))
            manager.create_project(root / "project", ProjectMetadata("Import test"))
            assert manager.store is not None
            survey = manager.store.add_survey("Line 1", SurveyType.ERT)

            result = import_dat_into_project(manager.store, survey.id, source)

            self.assertEqual(source.read_bytes(), original_bytes)
            self.assertEqual(result.sha256, hashlib.sha256(original_bytes).hexdigest())
            self.assertEqual(result.stored_path.read_bytes(), original_bytes)
            self.assertEqual(len(manager.store.list_imports(survey.id)), 1)
            stored = manager.store.list_imports(survey.id)[0]
            self.assertEqual(stored["sha256"], result.sha256)
            self.assertEqual(manager.store.get_survey(survey.id).metadata["import"]["data_count"], 2)
            measurement_count = manager.store.connection.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]
            self.assertEqual(measurement_count, 2)
            manager.close()

    def test_status_updates_are_source_scoped_and_legacy_rows_are_rejected_when_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.dat"
            second = root / "second.dat"
            first.write_text(DAT, encoding="utf-8")
            second.write_text(DAT.replace("100\n", "101\n", 1), encoding="utf-8")
            store = ProjectStore(root / "project.sqlite3")
            store.open()
            store.save_metadata(ProjectMetadata("Multi-source"))
            survey = store.add_survey("Line 1", SurveyType.ERT)
            import_dat_into_project(store, survey.id, first)
            import_dat_into_project(store, survey.id, second)
            with self.assertRaisesRegex(ValueError, "ambiguous"):
                store.set_measurement_status(survey.id, [(5, MeasurementStatus.EXCLUDED)])
            measurements = store.list_measurements(survey.id)
            source_ids = {item.source_id for item in measurements if item.row_number == 5}
            self.assertEqual(len(source_ids), 2)
            source_id = next(iter(source_ids))
            store.set_measurement_status(survey.id, [(source_id, 5, MeasurementStatus.EXCLUDED)])
            statuses = {(item.source_id, item.row_number): item.status for item in store.list_measurements(survey.id)}
            self.assertEqual(sum(status == MeasurementStatus.EXCLUDED for status in statuses.values()), 1)
            store.close()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "field.dat"
            source.write_text(DAT, encoding="utf-8")
            manager = ProjectManager()
            manager.create_project(root / "project", ProjectMetadata("Import test"))
            assert manager.store is not None
            survey = manager.store.add_survey("Line 1", SurveyType.ERT)
            import_dat_into_project(manager.store, survey.id, source)
            with self.assertRaisesRegex(ValueError, "already imported"):
                import_dat_into_project(manager.store, survey.id, source)
            manager.close()


if __name__ == "__main__":
    unittest.main()
