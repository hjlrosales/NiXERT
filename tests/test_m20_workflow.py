"""M20 supported offline desktop-workflow acceptance tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from nix_ert.app.workflow import ERTWorkflow, VESWorkflow, WorkflowError
from nix_ert.data.models import ProjectMetadata, SurveyType
from nix_ert.data.project import ProjectStore
from nix_ert.ves.engine import LayeredEarthModel


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

VES = """AB/2,MN/2,resistance
10,2,3
20,2,4
30,2,5
40,2,6
50,2,7
60,2,8
"""


class M20WorkflowAcceptanceTests(unittest.TestCase):
    def test_ert_acceptance_preserves_source_and_reports_current_model(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "line.dat"
            source.write_text(DAT, encoding="utf-8")
            original = source.read_bytes()
            store = ProjectStore(root / "project.sqlite3")
            store.open()
            store.save_metadata(ProjectMetadata("M20 ERT"))
            survey = store.add_survey("Line 1", SurveyType.ERT)
            workflow = ERTWorkflow(store)
            workflow.select_survey(survey.id)
            workflow.import_dat(source)
            self.assertEqual(workflow.snapshot().measurements, 6)
            workflow.process_ert()
            workflow.invert_2d(max_iterations=1)
            self.assertEqual(workflow.inspect_model().cell_count, 18)
            report = workflow.report(root / "report.html")
            self.assertIn("Current selected version", report.inversion["Provenance status"])
            self.assertEqual(source.read_bytes(), original)
            store.close()

    def test_ves_acceptance_persists_curve_and_inversion_versions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = ProjectStore(root / "project.sqlite3")
            store.open()
            store.save_metadata(ProjectMetadata("M20 VES"))
            survey = store.add_survey("VES 1", SurveyType.VES)
            workflow = VESWorkflow(store)
            workflow.select_survey(survey.id)
            points = workflow.import_text(VES)
            self.assertEqual(len(points), 6)
            processing = workflow.process()
            result = workflow.invert(LayeredEarthModel((100.0, 20.0), (5.0,)), max_nfev=2)
            self.assertEqual(processing.kind, "ves-processing")
            self.assertGreaterEqual(result.iterations, 1)
            snapshot = workflow.snapshot()
            self.assertEqual(snapshot.point_count, 6)
            self.assertEqual(snapshot.inversion_state, "complete")
            report = workflow.report(root / "ves.html")
            self.assertIn("VES 1D layered-earth inversion", report.inversion["Selected version"])
            self.assertEqual(report.surveys[0]["Sources"], 0)
            self.assertEqual(report.surveys[0]["Source datasets"][0]["Provenance"], "Manually supplied VES input; no LS2 acquisition claimed")
            store.close()

    def test_invalid_ves_transition_does_not_create_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ProjectStore(Path(directory) / "project.sqlite3")
            store.open()
            store.save_metadata(ProjectMetadata("M20 invalid"))
            survey = store.add_survey("VES 1", SurveyType.VES)
            workflow = VESWorkflow(store)
            workflow.select_survey(survey.id)
            try:
                with self.assertRaises(WorkflowError):
                    workflow.process()
                self.assertIsNone(store.connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='versions'"
                ).fetchone())
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
