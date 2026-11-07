"""M21 scientific qualification and benchmark-readiness tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from nix_ert.qualification.m21 import (
    EvidenceClass,
    ExternalBenchmarkReadiness,
    QualificationOutcome,
    ConvergenceRecord,
    build_m21_manifest,
    cancelled_record,
    comparison_metrics,
    objective_from_residuals,
    run_2d_sensitivity_studies,
    run_m21_internal_qualification,
    run_ves_starting_model_sensitivity,
)
from nix_ert.qualification.datasets import ert2d_qualification
from nix_ert.qualification.m21 import _ert2d_run


class M21QualificationTests(unittest.TestCase):
    def test_m21_manifest_is_deterministic_and_preserves_configuration(self) -> None:
        manifest = build_m21_manifest(
            "m21-test-v1", domain="2D ERT", dataset_id="fixture-v1",
            project_id="qualification", survey_id="line-1",
            configuration={"damping": 0.3, "max_iterations": 2, "noise_seed": 7},
            expected_outputs={"status": "internal synthetic"},
        )
        self.assertEqual(manifest.to_json(), manifest.to_json())
        self.assertEqual(len(manifest.manifest_sha256), 64)
        self.assertEqual(manifest.inversion["damping"], 0.3)
        self.assertEqual(manifest.procedure_version, "m21-scientific-qualification-v1")

    def test_convergence_states_and_failure_evidence_are_explicit(self) -> None:
        converged = ConvergenceRecord("VES", QualificationOutcome.CONVERGED, 1.0, (1.0, 0.1), 0.1, 2, "converged", True)
        terminated = ConvergenceRecord("2D ERT", QualificationOutcome.TERMINATED, 1.0, (1.0,), 1.0, 1, "maximum iterations reached", True)
        cancelled = cancelled_record("3D ERT")
        self.assertEqual(converged.to_dict()["outcome"], "CONVERGED")
        self.assertEqual(terminated.to_dict()["outcome"], "TERMINATED")
        self.assertEqual(cancelled.to_dict()["outcome"], "CANCELLED")
        with self.assertRaises(ValueError):
            ConvergenceRecord("2D ERT", QualificationOutcome.FAILED, None, (), None, 0, "solver failure", False)

    def test_invalid_input_is_recorded_without_solver_success_claim(self) -> None:
        fixture = ert2d_qualification()
        outcome, record, result = _ert2d_run(fixture, -1.0, damping=0.3, max_iterations=1)
        self.assertEqual(outcome, QualificationOutcome.INVALID_INPUT)
        self.assertEqual(record.outcome, QualificationOutcome.INVALID_INPUT)
        self.assertIsNotNone(record.error)
        self.assertIsNone(result)

    def test_metrics_are_deterministic_and_reject_invalid_shapes(self) -> None:
        shared = ("test", "resistivity", (0.0, 1.0, 2.0), (0.0, 1.0))
        first = comparison_metrics(
            (1.0, 2.0), (1.1, 1.8),
            reference_model=(1.0, 2.0), result_model=(1.1, 1.8), model_discretization=shared,
        )
        second = comparison_metrics(
            (1.0, 2.0), (1.1, 1.8),
            reference_model=(1.0, 2.0), result_model=(1.1, 1.8), model_discretization=shared,
        )
        self.assertEqual(first, second)
        self.assertGreater(first["rmse"], 0)
        self.assertGreater(first["model_l2_difference"], 0)
        self.assertAlmostEqual(objective_from_residuals((3.0, 4.0)), 3.5355339059)
        with self.assertRaises(ValueError):
            comparison_metrics((1.0,), (1.0, 2.0))
        with self.assertRaises(ValueError):
            objective_from_residuals(())

    def test_model_metrics_require_a_shared_discretization_identity(self) -> None:
        # M23: a length match is not a discretization match. Without an explicit
        # shared parameter-space identity the model distance is refused.
        with self.assertRaises(ValueError):
            comparison_metrics((1.0, 2.0), (1.1, 1.8), reference_model=(1.0, 2.0), result_model=(1.1, 1.8))
        metrics = comparison_metrics(
            (1.0, 2.0), (1.1, 1.8),
            reference_model=(1.0, 2.0), result_model=(1.1, 1.8),
            model_discretization=("2d", "resistivity", (0.0, 1.0, 2.0), (0.0, 1.0)),
        )
        self.assertIn("model_l2_difference", metrics)

    def test_controlled_2d_sensitivity_studies_are_reproducible(self) -> None:
        first = run_2d_sensitivity_studies()
        second = run_2d_sensitivity_studies()
        self.assertEqual([study.to_dict() for study in first], [study.to_dict() for study in second])
        self.assertEqual({study.domain for study in first}, {"2D ERT"})
        self.assertEqual({study.baseline_configuration.get("initial_resistivity") for study in first}, {1.0, None})
        self.assertTrue(all(study.cases for study in first))
        self.assertTrue(all(case.outcome in set(QualificationOutcome) for study in first for case in study.cases))

    def test_ves_starting_model_sensitivity_preserves_measured_differences(self) -> None:
        study = run_ves_starting_model_sensitivity()
        self.assertEqual(study.domain, "VES")
        self.assertEqual(study.baseline_configuration["max_nfev"], 20)
        self.assertEqual(len(study.cases), 2)
        self.assertTrue(all(case.outcome in {QualificationOutcome.CONVERGED, QualificationOutcome.TERMINATED} for case in study.cases))

    def test_internal_report_separates_qualitative_and_external_evidence(self) -> None:
        report = run_m21_internal_qualification()
        self.assertEqual(len(report.records), 3)
        self.assertEqual({record.evidence_class for record in report.records}, {EvidenceClass.QUALITATIVELY_CONSISTENT})
        self.assertEqual(report.external_benchmarks[0].status, EvidenceClass.NOT_VALIDATED)
        self.assertEqual(report.to_json(), report.to_json())
        self.assertIn("NOT VALIDATED", report.to_markdown())
        self.assertEqual(len(report.report_sha256), 64)

    def test_report_artifacts_are_machine_and_human_readable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = run_m21_internal_qualification()
            json_path = Path(directory) / "qualification.json"
            markdown_path = Path(directory) / "qualification.md"
            report.write_json(str(json_path))
            report.write_markdown(str(markdown_path))
            self.assertIn("m21-scientific-qualification-v1", json_path.read_text(encoding="utf-8"))
            self.assertIn("M21 scientific qualification result", markdown_path.read_text(encoding="utf-8"))

    def test_external_benchmark_requires_explicit_missing_evidence_reason(self) -> None:
        benchmark = ExternalBenchmarkReadiness(
            "benchmark-gate", "external-v1",
            reason="No licensed dataset or trustworthy reference result is available.",
            required_evidence=("license", "source hash", "reference result"),
        )
        self.assertEqual(benchmark.to_dict()["status"], "NOT VALIDATED")
        with self.assertRaises(ValueError):
            ExternalBenchmarkReadiness("bad", "external", reason="")
        with self.assertRaises(ValueError):
            ExternalBenchmarkReadiness("bad-status", "external", EvidenceClass.VALIDATED, "not allowed")

    def test_report_preserves_provenance_and_does_not_modify_fixture(self) -> None:
        fixture = ert2d_qualification()
        before = tuple(item.apparent_resistivity for item in fixture.noisy_observations)
        report = run_m21_internal_qualification()
        manifest = report.records[1].manifest
        self.assertEqual(manifest.dataset["dataset_id"], fixture.spec.name)
        self.assertEqual(before, tuple(item.apparent_resistivity for item in fixture.noisy_observations))
        self.assertTrue(np.isfinite(report.records[1].convergence.final_objective))


if __name__ == "__main__":
    unittest.main()
