"""M19 reproducibility and release-qualification tests."""

from __future__ import annotations

import hashlib
import tempfile
import threading
import unittest
from pathlib import Path

from nix_ert.app.operations import OperationCancelled, OperationExecutor
from nix_ert.app.workflow import ERTWorkflow, WorkflowError
from nix_ert.data.models import ProjectMetadata, SurveyType
from nix_ert.data.project import ProjectStore
from nix_ert.qualification.performance import measure
from nix_ert.qualification.release import (
    PROCEDURE_VERSION,
    ReleaseQualificationResult,
    build_manifest,
)


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


class M19ReleaseTests(unittest.TestCase):
    def test_manifest_is_machine_readable_and_deterministic(self) -> None:
        manifest = build_manifest(
            "m19-test-v1",
            dataset_id="internal-fixture-v1",
            source_sha256="a" * 64,
            project_id="project-1",
            survey_id="survey-1",
            processing={"version_id": "processing-1", "active_rows": [1, 2]},
            inversion={"version_id": "model-1", "max_iterations": 1},
            configuration={"python": "test", "platform": "test"},
            expected_outputs={"cell_count": 18, "report_provenance": "current"},
        )
        self.assertEqual(manifest.procedure_version, PROCEDURE_VERSION)
        self.assertEqual(manifest.to_json(), manifest.to_json())
        self.assertEqual(len(manifest.manifest_sha256), 64)
        restored = type(manifest).from_dict(manifest.to_dict())
        self.assertEqual(restored.to_dict(), manifest.to_dict())
        with self.assertRaises(ValueError):
            build_manifest("bad", dataset_id="x", source_sha256="not-a-hash", project_id="p", survey_id="s")

    def test_project_report_repeats_with_equivalent_scientific_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "line.dat"
            source.write_text(DAT, encoding="utf-8")
            store = ProjectStore(root / "project.sqlite3")
            store.open()
            store.save_metadata(ProjectMetadata("M19 reproducibility", location="Test site"))
            survey = store.add_survey("Line 1", SurveyType.ERT)
            workflow = ERTWorkflow(store)
            workflow.select_survey(survey.id)
            workflow.import_dat(source)
            processing = workflow.process_ert()
            workflow.invert_2d(max_iterations=1)
            model_id = workflow.selected_version_id
            first = workflow.report(root / "first.html")
            second = workflow.report(root / "second.html")
            stable_first = (first.title, first.project, first.surveys, first.qc_summary, first.inversion, first.interpretation, first.appendices)
            stable_second = (second.title, second.project, second.surveys, second.qc_summary, second.inversion, second.interpretation, second.appendices)
            self.assertEqual(stable_first, stable_second)
            self.assertEqual(first.inversion["State fingerprint"], second.inversion["State fingerprint"])
            source_record = store.list_imports(survey.id)[0]
            source_hash = source_record["sha256"]
            self.assertEqual(source_hash, hashlib.sha256(Path(source_record["stored_path"]).read_bytes()).hexdigest())
            manifest = build_manifest(
                "m19-lifecycle-v1", dataset_id="internal-dat-fixture", source_sha256=source_hash,
                project_id="M19 reproducibility", survey_id=survey.id,
                processing={"version_id": processing.id},
                inversion={"version_id": model_id, "max_iterations": 1},
                expected_outputs={"state_fingerprint": first.inversion["State fingerprint"], "report_equivalent": True},
            )
            self.assertEqual(manifest.dataset["source_sha256"], source_hash)
            store.close()

    def test_input_change_invalidates_downstream_report_and_manifest_does_not_guess(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "line.dat"
            source.write_text(DAT, encoding="utf-8")
            store = ProjectStore(root / "project.sqlite3")
            store.open()
            store.save_metadata(ProjectMetadata("M19 stale state"))
            survey = store.add_survey("Line 1", SurveyType.ERT)
            workflow = ERTWorkflow(store)
            workflow.select_survey(survey.id)
            workflow.import_dat(source)
            workflow.invert_2d(max_iterations=1)
            from nix_ert.processing.qc import QCEngine
            from nix_ert.data.measurements import MeasurementStatus
            QCEngine(store).set_status(survey.id, [5], MeasurementStatus.EXCLUDED)
            report = workflow.report(root / "stale.html")
            self.assertIn("Stale version", report.inversion["Provenance status"])
            self.assertFalse(workflow.snapshot().inversion_state == "not started")
            store.close()

    def test_cancellation_and_invalid_operation_are_fail_safe(self) -> None:
        executor = OperationExecutor()
        started = threading.Event()
        release = threading.Event()
        try:
            def operation(token):
                started.set()
                release.wait(timeout=2)
                token.raise_if_cancelled()
                return 1
            handle = executor.submit("m19 cancellation", operation)
            self.assertTrue(started.wait(timeout=2))
            handle.cancel()
            release.set()
            with self.assertRaises(OperationCancelled):
                handle.future.result(timeout=2)
            self.assertEqual(handle.snapshot().state, "cancelled")
        finally:
            executor.shutdown()

        with tempfile.TemporaryDirectory() as directory:
            store = ProjectStore(Path(directory) / "project.sqlite3")
            store.open()
            store.save_metadata(ProjectMetadata("Invalid operation"))
            survey = store.add_survey("Empty", SurveyType.ERT)
            workflow = ERTWorkflow(store)
            workflow.select_survey(survey.id)
            with self.assertRaises(WorkflowError):
                workflow.invert_2d(max_iterations=1)
            self.assertEqual(store.list_measurements(survey.id), [])
            store.close()

    def test_release_result_records_measured_values_without_threshold_claims(self) -> None:
        measurement = measure("m19-noop", lambda: sum(range(1000)), observations=0, scale="small")
        result = ReleaseQualificationResult(
            assessment="QUALIFIED_FOR_SUPPORTED_OFFLINE_WORKFLOW",
            environment={"python": "test", "platform": "test"},
            manifests=(build_manifest("m19-result-v1", dataset_id="fixture", source_sha256=None, project_id="p", survey_id="s"),),
            test_counts={"full_suite": 1, "m19": 1},
            reproducibility={"project_report_equivalent": True, "comparison_rule": "structured data excluding generated timestamp"},
            performance=({"name": measurement.name, "seconds": measurement.seconds, "peak_python_bytes": measurement.peak_python_bytes, "metadata": dict(measurement.metadata)},),
            cancellation_and_failure={"cancelled_without_commit": True, "invalid_input_rejected": True},
            limitations=("Internal fixture only; no independent field benchmark.",),
            blocked_capabilities=("ABEM importer", "physical LS2 communication"),
        )
        self.assertIn("m19-result-v1", result.to_json())
        self.assertIn("QUALIFIED_FOR_SUPPORTED_OFFLINE_WORKFLOW", result.to_markdown())
        self.assertNotIn("generated_at", result.to_json(include_timestamp=False))


if __name__ == "__main__":
    unittest.main()
