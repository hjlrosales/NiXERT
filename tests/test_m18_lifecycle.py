"""M18 lifecycle, provenance, and operation qualification tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from nix_ert.app.workflow import ERTWorkflow
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


class M18LifecycleTests(unittest.TestCase):
    def test_project_lifecycle_reopen_inspect_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "line.dat"
            source.write_text(DAT, encoding="utf-8")
            path = root / "project.sqlite3"
            store = ProjectStore(path)
            store.open()
            store.save_metadata(ProjectMetadata("Lifecycle"))
            survey = store.add_survey("Line 1", SurveyType.ERT)
            workflow = ERTWorkflow(store)
            workflow.select_survey(survey.id)
            workflow.import_dat(source)
            workflow.process_ert()
            workflow.invert_2d(max_iterations=1)
            model_id = workflow.selected_version_id
            store.close()

            reopened = ProjectStore(path)
            reopened.open(initialize=False)
            restored = ERTWorkflow(reopened)
            restored.select_survey(survey.id)
            restored.selected_version_id = model_id
            self.assertEqual(len(restored.inspect_measurements()), 6)
            self.assertEqual(restored.inspect_model().cell_count, 18)
            report_path = root / "lifecycle.html"
            report = restored.report(report_path)
            self.assertTrue(report_path.is_file())
            self.assertEqual(len(reopened.list_report_runs(survey.id)), 1)
            self.assertIn("State fingerprint", report.inversion)
            reopened.close()

    def test_report_rejects_source_path_outside_managed_raw_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "line.dat"
            source.write_text(DAT, encoding="utf-8")
            store = ProjectStore(root / "project.sqlite3")
            store.open()
            store.save_metadata(ProjectMetadata("Path safety"))
            survey = store.add_survey("Line 1", SurveyType.ERT)
            workflow = ERTWorkflow(store)
            workflow.select_survey(survey.id)
            workflow.import_dat(source)
            outside = root / "outside.dat"
            outside.write_bytes(source.read_bytes())
            store.connection.execute(
                "UPDATE imported_sources SET stored_path = ? WHERE survey_id = ?",
                (str(outside), survey.id),
            )
            store.connection.commit()
            with self.assertRaisesRegex(ReportAssemblyError, "outside project raw"):
                workflow.report(root / "blocked.html")
            self.assertEqual(store.list_report_runs(survey.id), [])
            store.close()


if __name__ == "__main__":
    unittest.main()
