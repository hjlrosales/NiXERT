"""Tests for the local, fail-safe advisory assistant."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from nix_ert.ai.assistant import AdvisoryAssistant, ProjectContext
from nix_ert.core.config import AppConfig
from nix_ert.data.import_service import import_dat_into_project
from nix_ert.data.measurements import MeasurementStatus
from nix_ert.data.models import ProjectMetadata, SurveyType
from nix_ert.data.project import ProjectManager
from nix_ert.processing.qc import QCEngine
from nix_ert.processing.versions import VersionStore
from nix_ert.reports.generator import ReportData
from nix_ert.ves.engine import LayeredEarthModel, VESPoint
from nix_ert.visualization.model2d import ResistivitySection
from nix_ert.visualization.volume3d import ResistivityVolume


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


class AdvisoryAssistantTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.source = root / "line.dat"
        self.source.write_text(DAT, encoding="utf-8")
        manager = ProjectManager(AppConfig.load(root / "config"))
        manager.create_project(root / "project", ProjectMetadata("AI test project"))
        assert manager.store is not None
        self.store = manager.store
        self.survey = self.store.add_survey("Line 1", SurveyType.ERT)
        import_dat_into_project(self.store, self.survey.id, self.source)
        self.version_store = VersionStore(self.store)
        self.first_model = self.version_store.create(
            self.survey.id, "model", "Model A", {"damping": 0.3}, {"rms_percent": 6.2, "converged": False}
        )
        self.second_model = self.version_store.create(
            self.survey.id, "model", "Model B", {"damping": 0.2}, {"rms_percent": 4.8, "converged": True}, parent_id=self.first_model.id
        )
        self.qc = QCEngine(self.store)
        self.context = ProjectContext.from_store(self.store)
        self.assistant = AdvisoryAssistant(self.context, self.qc)

    def tearDown(self) -> None:
        self.store.close()
        self.directory.cleanup()

    def test_project_analysis_and_suspicious_measurements_are_advisory(self) -> None:
        original = self.source.read_bytes()
        analysis = self.assistant.analyze_project()
        suspicious = self.assistant.suspicious_measurements(self.survey.id)
        self.assertIn("AI test project", analysis.answer)
        self.assertGreaterEqual(len(suspicious.findings), 1)
        self.assertTrue(all(finding.advisory for finding in suspicious.findings))
        self.assertEqual(self.source.read_bytes(), original)
        self.assertTrue(all(item.status == MeasurementStatus.ACTIVE for item in self.store.list_measurements(self.survey.id)))

    def test_qc_explanation_anomalies_and_query(self) -> None:
        explanation = self.assistant.explain_qc(self.survey.id, 8)
        self.assertIn("invalid apparent resistivity", explanation.findings[0].detail)
        anomalies = self.assistant.identify_resistivity_anomalies(self.survey.id)
        self.assertTrue(any("anomaly" in finding.category for finding in anomalies.findings))
        query = self.assistant.query("show suspicious measurements in Line 1")
        self.assertIn("QC-flagged", query.answer)
        unknown = self.assistant.query("what can you do?")
        self.assertIn("No project data was changed", unknown.answer)

    def test_model_inversion_and_report_assistance(self) -> None:
        comparison = self.assistant.compare_models(self.first_model.id, self.second_model.id)
        self.assertFalse(comparison.findings[0].detail == "No parameter differences.")
        summary = self.assistant.inversion_summary(self.survey.id)
        self.assertEqual(len(summary.findings), 2)
        ves = self.assistant.ves_interpretation_assistance(
            [VESPoint(10, 2, apparent_resistivity=100), VESPoint(20, 2, apparent_resistivity=50)],
            LayeredEarthModel((100, 20), (5,)),
        )
        self.assertTrue(any(finding.category == "VES" for finding in ves.findings))
        section = ResistivitySection((0, 1, 2), (0, 1), [[50, 100]])
        volume = ResistivityVolume((0, 1, 2), (0, 1), (0, 1), [[[50, 100]]])
        self.assertIn("validated cells", self.assistant.explain_2d_model(section).answer)
        self.assertIn("validated cells", self.assistant.explain_3d_model(volume).answer)
        self.assertIn("Preliminary advisory summary", self.assistant.draft_report())

    def test_mutations_require_proposal_explanation_and_explicit_approval(self) -> None:
        original = self.source.read_bytes()
        proposal = self.assistant.propose_exclusion(self.survey.id, [8], "Review negative apparent resistivity")
        self.assertTrue(proposal.requires_approval)
        with self.assertRaises(PermissionError):
            self.assistant.execute_proposal(proposal, approved=True)
        pending = self.assistant.explain_proposal(proposal)
        self.assertIn("has not executed", pending.answer)
        self.assertEqual(self.store.list_measurements(self.survey.id)[3].status, MeasurementStatus.ACTIVE)
        declined = self.assistant.execute_proposal(proposal)
        self.assertIn("has not executed", declined.answer)
        self.assertEqual(self.store.list_measurements(self.survey.id)[3].status, MeasurementStatus.ACTIVE)
        executed = self.assistant.execute_proposal(proposal, approved=True)
        self.assertIn("Approved exclusion executed", executed.answer)
        self.assertEqual(self.store.list_measurements(self.survey.id)[3].status, MeasurementStatus.EXCLUDED)
        self.assertEqual(self.source.read_bytes(), original)
        with self.assertRaises(KeyError):
            self.assistant.execute_proposal(proposal, approved=True)

    def test_context_snapshot_does_not_create_schema_on_legacy_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            from nix_ert.data.project import ProjectStore
            from nix_ert.data.models import ProjectMetadata
            store = ProjectStore(Path(directory) / "legacy.sqlite3")
            store.open()
            store.save_metadata(ProjectMetadata("Legacy"))
            survey = store.add_survey("Line", SurveyType.ERT)
            before = {row[0] for row in store.connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            context = ProjectContext.from_store(store)
            after = {row[0] for row in store.connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            self.assertEqual(context.versions, ())
            self.assertEqual(before, after)
            self.assertNotIn("versions", after)
            store.close()

        with self.assertRaises(KeyError):
            self.assistant.suspicious_measurements("missing")
        with self.assertRaises(ValueError):
            self.assistant.propose_exclusion(self.survey.id, [], "reason")
        with self.assertRaises(ValueError):
            self.assistant.query(" ")

    def test_proposal_rejects_ambiguous_rows_before_execution(self) -> None:
        second_source = self.directory.name
        second = Path(second_source) / "second.dat"
        second.write_text(DAT.replace("100\n", "101\n", 1), encoding="utf-8")
        import_dat_into_project(self.store, self.survey.id, second)
        assistant = AdvisoryAssistant(ProjectContext.from_store(self.store), self.qc)
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            assistant.propose_exclusion(self.survey.id, [8], "duplicate row review")


if __name__ == "__main__":
    unittest.main()
