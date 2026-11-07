"""M17 headless workflow integration tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from nix_ert.app.workflow import ERTWorkflow, WorkflowError
from nix_ert.data.models import ProjectMetadata, SurveyType
from nix_ert.data.project import ProjectStore
from nix_ert.reports.project_report import ReportAssemblyError


DAT = """6
1
Wenner
0
1 2 3 4 100
1 3 4 6 120
2 4 5 6 90
1 4 2 3 110
2 5 3 4 105
3 6 4 5 95
"""


class WorkflowIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.source = root / "line.dat"
        self.source.write_text(DAT, encoding="utf-8")
        self.store = ProjectStore(root / "project.sqlite3")
        self.store.open()
        self.store.save_metadata(ProjectMetadata("M17 project", location="Test site"))
        self.survey = self.store.add_survey("Line 1", SurveyType.ERT)
        self.workflow = ERTWorkflow(self.store)
        self.workflow.select_survey(self.survey.id)

    def tearDown(self) -> None:
        self.store.close()
        self.directory.cleanup()

    def test_project_import_qc_process_invert_visualize_and_report(self) -> None:
        self.workflow.import_dat(self.source)
        snapshot = self.workflow.snapshot()
        self.assertEqual((snapshot.imported_sources, snapshot.measurements), (1, 6))
        self.assertGreaterEqual(self.workflow.flag_detected(), 0)
        points = self.workflow.build_pseudosection()
        self.assertEqual(len(points), 6)
        processing = self.workflow.process_ert()
        self.assertEqual(processing.kind, "processing")
        result = self.workflow.invert_2d(max_iterations=1)
        self.assertTrue(result.predicted)
        section = self.workflow.selected_model_section()
        self.assertEqual(section.resistivity.shape, (3, 6))
        report_path = Path(self.directory.name) / "report.html"
        report = self.workflow.report(report_path)
        self.assertTrue(report_path.exists())
        html = report_path.read_text(encoding="utf-8")
        self.assertIn("M17 project", html)
        self.assertIn("Current persisted project state", html)
        self.assertIn(result.message, html)
        runs = self.store.list_report_runs(self.survey.id)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["version_id"], self.workflow.selected_version_id)
        source_hashes = json.loads(runs[0]["source_hashes_json"])
        self.assertEqual(len(source_hashes), 1)
        self.assertEqual(len(source_hashes[0]), 64)

    def test_report_marks_model_stale_after_working_data_changes(self) -> None:
        self.workflow.import_dat(self.source)
        self.workflow.invert_2d(max_iterations=1)
        from nix_ert.data.measurements import MeasurementStatus
        from nix_ert.processing.qc import QCEngine
        QCEngine(self.store).set_status(self.survey.id, [5], MeasurementStatus.EXCLUDED)
        report = self.workflow.report(Path(self.directory.name) / "stale.html")
        self.assertIn("Stale version", str(report.inversion["Provenance status"]))

    def test_invalid_transitions_fail_without_mutation(self) -> None:
        with self.assertRaises(WorkflowError):
            self.workflow.process_ert()
        self.assertEqual(self.workflow.qc_statistics().total, 0)
        self.workflow.import_dat(self.source)
        report = self.workflow.report(Path(self.directory.name) / "report.html")
        self.assertIn("No persisted processing/model version selected", report.inversion["Provenance"])


    def test_report_rejects_version_from_another_survey(self) -> None:
        self.workflow.import_dat(self.source)
        version = self.workflow.process_ert()
        other = self.store.add_survey("Line 2", SurveyType.ERT)
        with self.assertRaises(ReportAssemblyError):
            from nix_ert.reports.project_report import build_project_report
            build_project_report(self.store, other.id, version_id=version.id)


if __name__ == "__main__":
    unittest.main()
