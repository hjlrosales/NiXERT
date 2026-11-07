"""Tests for non-destructive QC behavior."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from nix_ert.data.import_service import import_dat_into_project
from nix_ert.data.models import ProjectMetadata, SurveyType
from nix_ert.data.project import ProjectStore
from nix_ert.data.measurements import MeasurementStatus
from nix_ert.processing.qc import QCEngine, QCSettings


DAT = """5
1
Wenner
0
1 2 3 4 100
1 2 3 4 100
2 3 4 5 10000
3 4 5 6 -1
4 5 6 7 50
"""


class QCTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.source = root / "line.dat"
        self.source.write_text(DAT, encoding="utf-8")
        self.store = ProjectStore(root / "project.sqlite3")
        self.store.open()
        self.store.save_metadata(ProjectMetadata("QC test"))
        survey = self.store.add_survey("Line 1", SurveyType.ERT)
        import_dat_into_project(self.store, survey.id, self.source)
        self.survey_id = survey.id
        self.engine = QCEngine(self.store, QCSettings(extreme_log10_distance=1.0, noise_log10_distance=0.5))

    def tearDown(self) -> None:
        self.store.close()
        self.directory.cleanup()

    def test_inspection_is_deterministic_and_detects_invalid_extreme_duplicate(self) -> None:
        flags = self.engine.inspect(self.survey_id)
        by_row = {flag.row_number: flag.reasons for flag in flags}
        self.assertIn("duplicate electrode tuple (row 5)", by_row[6])
        self.assertIn("extreme apparent resistivity", by_row[7])
        self.assertIn("invalid apparent resistivity", by_row[8])
        self.assertEqual(flags, self.engine.inspect(self.survey_id))

    def test_flag_exclude_restore_and_undo_redo_preserve_raw_source(self) -> None:
        original = self.source.read_bytes()
        self.engine.flag_detected(self.survey_id)
        statuses = {item.row_number: item.status for item in self.store.list_measurements(self.survey_id)}
        self.assertEqual(statuses[8], MeasurementStatus.FLAGGED)
        self.engine.set_status(self.survey_id, [8], MeasurementStatus.EXCLUDED)
        self.assertEqual(self.store.list_measurements(self.survey_id)[3].status, MeasurementStatus.EXCLUDED)
        self.assertTrue(self.engine.undo())
        self.assertEqual(self.store.list_measurements(self.survey_id)[3].status, MeasurementStatus.FLAGGED)
        self.assertTrue(self.engine.redo())
        self.assertEqual(self.store.list_measurements(self.survey_id)[3].status, MeasurementStatus.EXCLUDED)
        self.assertEqual(self.source.read_bytes(), original)

    def test_statistics_report_statuses_and_valid_value_range(self) -> None:
        stats = self.engine.statistics(self.survey_id)
        self.assertEqual((stats.total, stats.active, stats.invalid, stats.duplicate), (5, 5, 1, 1))
        self.assertEqual(stats.minimum_apparent_resistivity, 50)
        self.assertEqual(stats.maximum_apparent_resistivity, 10000)


if __name__ == "__main__":
    unittest.main()
