"""M22 inversion robustness and scientific hardening tests.

These tests assert contract semantics, determinism, and the measured relationships
recorded by the M22 studies. They do not assert arbitrary scientific thresholds:
where a numeric comparison appears it is a relative, self-consistent observation
(for example "the 20-to-40 evaluation change is far smaller than the 10-to-20
change"), never an invented pass/fail limit.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from nix_ert.ert.inversion3d import (
    ERT3D_CONVERGENCE_RMS,
    invert_ert3d,
)
from nix_ert.qualification.datasets import (
    ert2d_qualification,
    ert3d_qualification,
    ves_qualification,
)
from nix_ert.qualification.m22 import (
    ERT2D_NOISE_FACTORS_V1,
    ERT3D_NOISE_FACTORS_V1,
    HISTORY_RECORDED,
    HISTORY_UNAVAILABLE,
    MAXIMUM_UNITS_EVALUATIONS,
    PROCEDURE_VERSION,
    VES_NOISE_FACTORS_V1,
    ConvergenceContract,
    FinalModelStatus,
    M22QualificationReport,
    build_m22_manifest,
    cancelled_contract,
    classify_outcome,
    failed_contract,
    invalid_input_contract,
    metric_definitions,
    model_log10_vector,
    outcome_coverage,
    run_cancellation_evidence,
    run_ert2d_contract,
    run_ert3d_contract,
    run_m22_qualification,
    run_ves_contract,
    unavailable_evidence,
    unvalidated_claims,
)
from nix_ert.qualification.m21 import EvidenceClass, QualificationOutcome
from nix_ert.ves.engine import LayeredEarthModel

_BASELINE_VES_INITIAL = LayeredEarthModel((80.0, 30.0, 180.0), (4.0, 10.0))
_ARTIFACT_JSON = Path(__file__).resolve().parents[1] / "docs" / "m22_scientific_hardening.json"

_CACHE: dict[str, M22QualificationReport] = {}


def qualification_report() -> M22QualificationReport:
    """Return one shared full M22 qualification run for the non-determinism tests."""
    if "report" not in _CACHE:
        _CACHE["report"] = run_m22_qualification()
    return _CACHE["report"]


def _study(report: M22QualificationReport, study_id: str):
    for study in report.studies:
        if study.study_id == study_id:
            return study
    raise AssertionError(f"study {study_id} is missing from the M22 report")


def _case(study, case_id: str):
    for case in study.cases:
        if case.case_id == case_id:
            return case
    raise AssertionError(f"case {case_id} is missing from study {study.study_id}")


def _contract_of(case) -> dict[str, object]:
    return case.result_summary["convergence"]


class M22OutcomeSemanticsTests(unittest.TestCase):
    """Test area 1: one normalized outcome vocabulary for every engine."""

    def test_solver_outcomes_are_the_documented_five(self) -> None:
        self.assertEqual(
            {item.value for item in QualificationOutcome},
            {"CONVERGED", "TERMINATED", "FAILED", "INVALID_INPUT", "CANCELLED", "NOT_VALIDATED"},
        )
        self.assertEqual(classify_outcome(convergence_criterion_satisfied=True), QualificationOutcome.CONVERGED)
        self.assertEqual(classify_outcome(), QualificationOutcome.TERMINATED)
        self.assertEqual(classify_outcome(cancelled=True), QualificationOutcome.CANCELLED)
        self.assertEqual(classify_outcome(invalid_input=True, error="bad"), QualificationOutcome.INVALID_INPUT)
        self.assertEqual(
            classify_outcome(numerical_failure=True, error="boom"), QualificationOutcome.FAILED
        )

    def test_convergence_requires_a_satisfied_criterion_not_completion(self) -> None:
        with self.assertRaises(ValueError):
            ConvergenceContract(
                domain="2D ERT", outcome=QualificationOutcome.CONVERGED, history_status=HISTORY_UNAVAILABLE,
                objective_history=(), trajectory=(), initial_objective=None,
                initial_objective_source="test", final_objective=1.0, iteration_count=1, evaluation_count=1,
                configured_maximum=1, configured_maximum_units="iterations", configured_maximum_reached=False,
                convergence_criterion="test criterion", convergence_tolerance=1e-3,
                convergence_criterion_satisfied=False, termination_reason="solver finished",
                cancellation_requested=False, invalid_input=False, numerical_failure=False,
                final_model_status=FinalModelStatus.VALID,
            )

    def test_bounded_completion_is_terminated_and_never_failed(self) -> None:
        outcome, contract, result = run_ert2d_contract(ert2d_qualification(), max_iterations=1)
        self.assertEqual(outcome, QualificationOutcome.TERMINATED)
        self.assertTrue(contract.bounded_completion_only)
        self.assertTrue(contract.configured_maximum_reached)
        self.assertFalse(contract.numerical_failure)
        self.assertEqual(contract.final_model_status, FinalModelStatus.VALID)
        self.assertIsNotNone(result)
        with self.assertRaises(ValueError):
            ConvergenceContract(
                domain="2D ERT", outcome=QualificationOutcome.FAILED, history_status=HISTORY_UNAVAILABLE,
                objective_history=(), trajectory=(), initial_objective=None,
                initial_objective_source="test", final_objective=None, iteration_count=None, evaluation_count=None,
                configured_maximum=1, configured_maximum_units="iterations", configured_maximum_reached=True,
                convergence_criterion="test criterion", convergence_tolerance=1e-3,
                convergence_criterion_satisfied=False, termination_reason="limit reached",
                cancellation_requested=False, invalid_input=False, numerical_failure=False,
                final_model_status=FinalModelStatus.NOT_PRODUCED,
            )

    def test_invalid_input_and_cancelled_never_commit_a_model(self) -> None:
        invalid = invalid_input_contract("VES", "bad controls", error_class="ValueError")
        self.assertEqual(invalid.outcome, QualificationOutcome.INVALID_INPUT)
        self.assertTrue(invalid.invalid_input)
        self.assertEqual(invalid.final_model_status, FinalModelStatus.NOT_PRODUCED)
        cancelled = cancelled_contract("3D ERT")
        self.assertEqual(cancelled.outcome, QualificationOutcome.CANCELLED)
        self.assertTrue(cancelled.cancellation_requested)
        self.assertEqual(cancelled.error, None)
        with self.assertRaises(ValueError):
            ConvergenceContract(
                domain="3D ERT", outcome=QualificationOutcome.CANCELLED, history_status=HISTORY_UNAVAILABLE,
                objective_history=(), trajectory=(), initial_objective=None,
                initial_objective_source="test", final_objective=0.5, iteration_count=1, evaluation_count=1,
                configured_maximum=1, configured_maximum_units="iterations", configured_maximum_reached=False,
                convergence_criterion="test criterion", convergence_tolerance=1e-3,
                convergence_criterion_satisfied=False, termination_reason="cancelled",
                cancellation_requested=True, invalid_input=False, numerical_failure=False,
                final_model_status=FinalModelStatus.VALID,
            )
        with self.assertRaises(ValueError):
            invalid_input_contract("VES", "")

    def test_numerical_failure_requires_an_error_and_no_valid_model(self) -> None:
        failed = failed_contract("3D ERT", "singular system", error_class="LinAlgError")
        self.assertEqual(failed.outcome, QualificationOutcome.FAILED)
        self.assertTrue(failed.numerical_failure)
        self.assertEqual(failed.final_model_status, FinalModelStatus.NOT_PRODUCED)
        with self.assertRaises(ValueError):
            failed_contract("3D ERT", "")


class M22ConvergenceRecordTests(unittest.TestCase):
    """Test areas 2, 3, 4: record determinism, history preservation, bounded evidence."""

    def test_records_are_deterministic_for_identical_inputs(self) -> None:
        first = run_ert2d_contract(ert2d_qualification(), max_iterations=2)
        second = run_ert2d_contract(ert2d_qualification(), max_iterations=2)
        self.assertEqual(first[1].to_dict(), second[1].to_dict())
        self.assertEqual(first[0], second[0])
        manifest_one = build_m22_manifest(
            "m22-determinism", domain="2D ERT", dataset_id="fixture", project_id="qualification",
            survey_id="line", configuration={"damping": 0.3},
        )
        manifest_two = build_m22_manifest(
            "m22-determinism", domain="2D ERT", dataset_id="fixture", project_id="qualification",
            survey_id="line", configuration={"damping": 0.3},
        )
        self.assertEqual(manifest_one.manifest_sha256, manifest_two.manifest_sha256)

    def test_unavailable_history_is_recorded_as_unavailable_never_invented(self) -> None:
        # A bounded VES run (10 evaluations) is used here because the corrected
        # forward model converges the 3-layer fit within its configured limit.
        _, contract, _ = run_ves_contract(ves_qualification(), _BASELINE_VES_INITIAL, max_nfev=10)
        self.assertEqual(contract.history_status, HISTORY_UNAVAILABLE)
        self.assertEqual(contract.objective_history, ())
        self.assertEqual(contract.trajectory, ())
        self.assertIsNone(contract.iteration_count)
        self.assertEqual(contract.evaluation_count, 10)
        self.assertEqual(contract.configured_maximum_units, MAXIMUM_UNITS_EVALUATIONS)
        with self.assertRaises(ValueError):
            ConvergenceContract(
                domain="VES", outcome=QualificationOutcome.TERMINATED, history_status=HISTORY_UNAVAILABLE,
                objective_history=(1.0,), trajectory=(), initial_objective=1.0,
                initial_objective_source="test", final_objective=1.0, iteration_count=None, evaluation_count=20,
                configured_maximum=20, configured_maximum_units=MAXIMUM_UNITS_EVALUATIONS,
                configured_maximum_reached=True, convergence_criterion="criterion", convergence_tolerance=None,
                convergence_criterion_satisfied=False, termination_reason="limit reached",
                cancellation_requested=False, invalid_input=False, numerical_failure=False,
                final_model_status=FinalModelStatus.VALID,
            )

    def test_recorded_history_spans_initial_to_returned_model(self) -> None:
        _, contract, result = run_ert2d_contract(ert2d_qualification(), max_iterations=2)
        self.assertEqual(contract.history_status, HISTORY_RECORDED)
        self.assertEqual(len(contract.objective_history), len(result.iterations) + 1)
        self.assertEqual(contract.objective_history[0], contract.initial_objective)
        self.assertEqual(contract.objective_history[-1], contract.final_objective)
        self.assertEqual(contract.trajectory[-1].origin, "final_model_evaluation")
        self.assertTrue(all(point.origin == "solver_evaluation" for point in contract.trajectory[:-1]))
        self.assertEqual(contract.objective_history[0], 0.17264464867512536)
        # Bounded completion: the history decreases but never satisfies the criterion.
        self.assertLess(contract.objective_history[-1], contract.objective_history[0])
        self.assertFalse(contract.convergence_criterion_satisfied)

    def test_history_must_begin_and_end_at_declared_objectives(self) -> None:
        with self.assertRaises(ValueError):
            ConvergenceContract(
                domain="2D ERT", outcome=QualificationOutcome.TERMINATED, history_status=HISTORY_RECORDED,
                objective_history=(0.5, 0.4), trajectory=(*run_ert2d_contract(ert2d_qualification(), max_iterations=1)[1].trajectory,),
                initial_objective=0.9, initial_objective_source="test", final_objective=0.4,
                iteration_count=1, evaluation_count=2, configured_maximum=1,
                configured_maximum_units="iterations", configured_maximum_reached=True,
                convergence_criterion="criterion", convergence_tolerance=1e-3,
                convergence_criterion_satisfied=False, termination_reason="limit reached",
                cancellation_requested=False, invalid_input=False, numerical_failure=False,
                final_model_status=FinalModelStatus.VALID,
            )

    def test_bounded_3d_run_reports_only_the_configured_limit(self) -> None:
        outcome, contract, _ = run_ert3d_contract(ert3d_qualification(), max_iterations=1)
        self.assertEqual(outcome, QualificationOutcome.TERMINATED)
        self.assertEqual(contract.configured_maximum, 1)
        self.assertEqual(contract.configured_maximum_units, "iterations")
        self.assertTrue(contract.configured_maximum_reached)
        self.assertFalse(contract.numerical_failure)
        self.assertEqual(contract.convergence_tolerance, ERT3D_CONVERGENCE_RMS)


class M22EngineReportingRegressionTests(unittest.TestCase):
    """Test areas 16 and 5: regression coverage for the corrected 3D reporting defect."""

    def test_3d_history_and_flag_describe_the_returned_model(self) -> None:
        fixture = ert3d_qualification()
        model, predicted, history, converged = invert_ert3d(
            fixture.noisy_observations, fixture.mesh, fixture.electrodes, 1.0,
            damping=0.5, max_iterations=1,
        )
        observed = np.log10([item.apparent_resistivity for item in fixture.noisy_observations])
        returned_rms = float(np.sqrt(np.mean((observed - np.log10(np.asarray(predicted))) ** 2)))
        # Before the M22 correction the engine returned the pre-update objective
        # here (0.20213359...) and derived the flag from a discarded model.
        self.assertAlmostEqual(history[-1], returned_rms, places=12)
        self.assertEqual(converged, returned_rms <= ERT3D_CONVERGENCE_RMS)
        self.assertAlmostEqual(history[0], 0.2021335923930331, places=12)
        self.assertLess(history[-1], history[0])

    def test_3d_history_length_covers_steps_plus_returned_model(self) -> None:
        fixture = ert3d_qualification()
        for iterations in (1, 3):
            _, _, history, _ = invert_ert3d(
                fixture.noisy_observations, fixture.mesh, fixture.electrodes, 1.0,
                damping=0.5, max_iterations=iterations,
            )
            self.assertEqual(len(history), iterations + 1)
            self.assertTrue(all(np.isfinite(history)))

    def test_3d_recorded_objective_reduction_is_measured_not_hidden(self) -> None:
        _, contract, _ = run_ert3d_contract(ert3d_qualification(), max_iterations=1)
        self.assertAlmostEqual(contract.initial_objective, 0.2021335923930331, places=12)
        self.assertAlmostEqual(contract.final_objective, 0.14952966792891723, places=12)
        self.assertLess(contract.final_objective, contract.initial_objective)
        self.assertEqual(contract.objective_history[-1], contract.final_objective)

    def test_engines_are_deterministic_under_identical_inputs(self) -> None:
        first_ves = run_ves_contract(ves_qualification(), _BASELINE_VES_INITIAL, max_nfev=10)
        second_ves = run_ves_contract(ves_qualification(), _BASELINE_VES_INITIAL, max_nfev=10)
        self.assertEqual(first_ves[1].to_dict(), second_ves[1].to_dict())
        self.assertEqual(first_ves[2].predicted, second_ves[2].predicted)
        self.assertEqual(first_ves[2].model, second_ves[2].model)
        first_2d = run_ert2d_contract(ert2d_qualification(), max_iterations=1)
        second_2d = run_ert2d_contract(ert2d_qualification(), max_iterations=1)
        self.assertEqual(first_2d[2].predicted, second_2d[2].predicted)
        self.assertTrue(np.array_equal(first_2d[2].resistivity, second_2d[2].resistivity))
        first_3d = run_ert3d_contract(ert3d_qualification(), max_iterations=1)
        second_3d = run_ert3d_contract(ert3d_qualification(), max_iterations=1)
        self.assertEqual(first_3d[2][1], second_3d[2][1])
        self.assertTrue(np.array_equal(first_3d[2][0], second_3d[2][0]))


class M22FailurePathTests(unittest.TestCase):
    """Test areas 6, 7, 8: cancellation, invalid input, and numerical failure."""

    def test_invalid_input_is_rejected_before_a_result(self) -> None:
        outcome, contract, result = run_ert2d_contract(ert2d_qualification(), initial_model=-1.0, max_iterations=1)
        self.assertEqual(outcome, QualificationOutcome.INVALID_INPUT)
        self.assertEqual(contract.final_model_status, FinalModelStatus.NOT_PRODUCED)
        self.assertEqual(contract.error_class, "ERT2DError")
        self.assertEqual(contract.failure_phase, "input_validation")
        self.assertIsNotNone(contract.error)
        self.assertIsNone(result)
        ves_outcome, ves_contract, ves_result = run_ves_contract(
            ves_qualification(), _BASELINE_VES_INITIAL, max_nfev=0
        )
        self.assertEqual(ves_outcome, QualificationOutcome.INVALID_INPUT)
        self.assertEqual(ves_contract.error_class, "VESError")
        self.assertEqual(ves_contract.failure_phase, "input_validation")
        self.assertIsNone(ves_result)

    def test_invalid_domain_configuration_is_preserved_as_evidence(self) -> None:
        report = qualification_report()
        cases = [
            _case(_study(report, "m22-ert2d-mesh-domain-v1"), "ert2d-mesh-too-coarse"),
            _case(_study(report, "m22-ert3d-mesh-domain-v1"), "ert3d-mesh-too-coarse"),
        ]
        self.assertEqual({case.outcome for case in cases}, {QualificationOutcome.INVALID_INPUT})
        for case in cases:
            contract = _contract_of(case)
            self.assertEqual(contract["final_model_status"], "NOT_PRODUCED")
            self.assertIsNotNone(contract["error"])

    def test_numerical_failures_are_classified_as_failed(self) -> None:
        fixture = ert2d_qualification()
        with mock.patch("nix_ert.qualification.m22.invert_ert", side_effect=RuntimeError("solver exploded")):
            outcome, contract, result = run_ert2d_contract(fixture, max_iterations=1)
        self.assertEqual(outcome, QualificationOutcome.FAILED)
        self.assertTrue(contract.numerical_failure)
        self.assertEqual(contract.error_class, "RuntimeError")
        self.assertEqual(contract.final_model_status, FinalModelStatus.NOT_PRODUCED)
        self.assertIsNone(result)
        with mock.patch("nix_ert.qualification.m22.invert_ert", side_effect=np.linalg.LinAlgError("singular")):
            outcome, contract, _ = run_ert2d_contract(fixture, max_iterations=1)
        self.assertEqual(outcome, QualificationOutcome.FAILED)
        self.assertEqual(contract.error_class, "LinAlgError")
        with mock.patch("nix_ert.qualification.m22.invert_ert", side_effect=ValueError("rejected controls")):
            outcome, contract, _ = run_ert2d_contract(fixture, max_iterations=1)
        self.assertEqual(outcome, QualificationOutcome.INVALID_INPUT)
        self.assertTrue(contract.invalid_input)

    def test_cancellation_commits_no_partial_state(self) -> None:
        contract, evidence = run_cancellation_evidence()
        self.assertEqual(contract.outcome, QualificationOutcome.CANCELLED)
        self.assertTrue(contract.cancellation_requested)
        self.assertEqual(contract.final_model_status, FinalModelStatus.NOT_PRODUCED)
        self.assertEqual(evidence["executor_state"], "cancelled")
        self.assertEqual(evidence["committed_state_entries"], 0)

    def test_report_preserves_all_outcome_categories(self) -> None:
        report = qualification_report()
        coverage = report.outcome_coverage
        self.assertEqual(
            set(coverage),
            {"CONVERGED", "TERMINATED", "FAILED", "INVALID_INPUT", "CANCELLED"},
        )
        self.assertGreaterEqual(coverage["CONVERGED"], 1)
        self.assertGreaterEqual(coverage["TERMINATED"], 1)
        self.assertGreaterEqual(coverage["INVALID_INPUT"], 1)
        self.assertGreaterEqual(coverage["CANCELLED"], 1)
        # No numerical failure occurred in the committed bounded studies; this
        # must be reported as zero rather than papered over or fabricated.
        self.assertEqual(coverage["FAILED"], 0)
        self.assertEqual(report.cancellation_evidence["committed_state_entries"], 0)


class M22StudyCoverageTests(unittest.TestCase):
    """Test areas 9, 10, 11, 12, 13: the expanded deterministic sensitivity studies."""

    def test_starting_model_studies_cover_every_engine(self) -> None:
        report = qualification_report()
        for study_id, expected_cases in (
            ("m22-ves-starting-model-v1", 3),
            ("m22-ert2d-starting-model-v1", 2),
            ("m22-ert3d-starting-model-v1", 2),
        ):
            study = _study(report, study_id)
            self.assertEqual(len(study.cases), expected_cases)
            self.assertIn("initial_resistivities" if study.domain == "VES" else "initial_resistivity",
                          json.dumps(study.baseline_configuration))
            for case in study.cases:
                contract = _contract_of(case)
                self.assertIn(contract["outcome"], {"CONVERGED", "TERMINATED"})
                self.assertIsNotNone(case.objective)
        two_layer = _case(_study(report, "m22-ves-starting-model-v1"), "ves-starting-two-layer")
        # Models of different complexity are not compared vector-to-vector.
        self.assertNotIn("model_l2_difference", two_layer.metrics)
        self.assertEqual(two_layer.result_summary["final_model"]["resistivities"].__len__(), 2)

    def test_damping_studies_exist_only_where_the_engine_exposes_damping(self) -> None:
        report = qualification_report()
        for study_id in ("m22-ert2d-damping-v1", "m22-ert3d-damping-v1"):
            study = _study(report, study_id)
            self.assertEqual({case.changed_parameter for case in study.cases}, {"damping"})
            self.assertEqual(len(study.cases), 2)
        reasons = {(item["domain"], item["evidence"]): item for item in report.unavailable_evidence}
        self.assertIn(("VES", "damping study"), reasons)
        self.assertEqual(reasons[("VES", "damping study")]["status"], "UNAVAILABLE")

    def test_mesh_and_domain_studies_record_shape_and_measured_differences(self) -> None:
        report = qualification_report()
        mesh_2d = _study(report, "m22-ert2d-mesh-domain-v1")
        shapes = {_case(mesh_2d, case.case_id).result_summary.get("mesh_cells") for case in mesh_2d.cases}
        self.assertEqual(shapes, {12, 15, 18, 24})
        for case in mesh_2d.cases:
            if case.outcome is QualificationOutcome.INVALID_INPUT:
                self.assertEqual(case.metrics, {})
                continue
            self.assertGreater(case.metrics["rmse"], 0.0)
            # M23: every mesh variant changes the discretization (different cell
            # count, depth extent, or cell locations), so no cell-wise model
            # distance is defined and each case must document the omission.
            self.assertNotIn("model_l2_difference", case.metrics)
            self.assertIn("model_comparison_omitted", case.result_summary)
            self.assertNotIn("model_discretization", case.result_summary)
        depth_case = _case(mesh_2d, "ert2d-mesh-depth-6")
        self.assertNotIn("model_l2_difference", depth_case.metrics)
        self.assertIn("different discretizations", depth_case.result_summary["model_comparison_omitted"])
        mesh_3d = _study(report, "m22-ert3d-mesh-domain-v1")
        self.assertIn(32, {case.result_summary.get("mesh_cells") for case in mesh_3d.cases})
        self.assertEqual(len(mesh_3d.cases), 4)

    def test_stopping_limit_studies_measure_bounded_and_completed_outcomes(self) -> None:
        report = qualification_report()
        ves = _study(report, "m22-ves-stopping-limit-v1")
        objectives = {case.case_id: case.objective for case in ves.cases}
        # Measured after the M23 forward-model correction: the 10-evaluation run
        # is truncated, and the 20/40-evaluation runs both satisfy the scipy
        # termination criteria at 13 evaluations.
        self.assertAlmostEqual(objectives["ves-max-nfev-10"], 0.011501158022312705, places=9)
        self.assertAlmostEqual(objectives["ves-max-nfev-40"], 0.011501149486299902, places=9)
        # Allowing more evaluations changes the recorded result less between 20
        # and 40 than between 10 and 20: a relative stabilization observation.
        coarse_change = abs(objectives["ves-max-nfev-10"] - objectives["ves-max-nfev-20"])
        fine_change = abs(objectives["ves-max-nfev-20"] - objectives["ves-max-nfev-40"])
        self.assertGreater(coarse_change, 0.0)
        self.assertLessEqual(fine_change * 100, coarse_change)
        self.assertEqual(_case(ves, "ves-max-nfev-10").outcome, QualificationOutcome.TERMINATED)
        self.assertEqual(_case(ves, "ves-max-nfev-40").outcome, QualificationOutcome.CONVERGED)
        for study_id in ("m22-ert2d-stopping-limit-v1", "m22-ert3d-stopping-limit-v1"):
            study = _study(report, study_id)
            self.assertEqual(len(study.cases), 3)
            self.assertEqual(
                {case.outcome for case in study.cases}, {QualificationOutcome.TERMINATED}
            )

    def test_additional_iterations_do_not_automatically_move_toward_the_baseline(self) -> None:
        report = qualification_report()
        study = _study(report, "m22-ert2d-stopping-limit-v1")
        objectives = [case.objective for case in study.cases]
        model_distances = [case.metrics["model_l2_difference"] for case in study.cases]
        self.assertEqual(objectives, sorted(objectives, reverse=True))
        # The residual decreases monotonically while the distance from the
        # 3-iteration baseline model does not: lower residual is not a model claim.
        self.assertNotEqual(model_distances, sorted(model_distances, reverse=True))

    def test_deterministic_noise_studies_are_reproducible_and_distinct(self) -> None:
        fixture_2d = ert2d_qualification()
        fixture_factors = tuple(round(item.apparent_resistivity, 12) for item in fixture_2d.observations)
        self.assertEqual(len(ERT2D_NOISE_FACTORS_V1), len(fixture_2d.observations))
        self.assertNotEqual(list(ERT2D_NOISE_FACTORS_V1), [1.03, 0.98, 1.01, 0.96, 1.04, 0.99])
        self.assertNotEqual(list(ERT3D_NOISE_FACTORS_V1), [1.04, 0.97])
        self.assertEqual(len(VES_NOISE_FACTORS_V1), len(ves_qualification().clean_points))
        self.assertTrue(fixture_factors)
        fixture_3d = ert3d_qualification()
        noisy = tuple(
            type(item)(item.a, item.b, item.m, item.n, item.apparent_resistivity * factor)
            for item, factor in zip(fixture_3d.observations, ERT3D_NOISE_FACTORS_V1)
        )
        first = run_ert3d_contract(fixture_3d, observations=noisy, max_iterations=3)
        second = run_ert3d_contract(fixture_3d, observations=noisy, max_iterations=3)
        self.assertEqual(first[1].to_dict(), second[1].to_dict())
        baseline = run_ert3d_contract(fixture_3d, max_iterations=3)
        self.assertNotEqual(first[1].final_objective, baseline[1].final_objective)
        report = qualification_report()
        noise = _case(_study(report, "m22-ert2d-deterministic-noise-v1"), "ert2d-noise-deterministic-v1")
        self.assertGreater(noise.metrics["rmse"], 0.0)
        self.assertIn(noise.outcome.value, {"TERMINATED", "CONVERGED"})

    def test_every_study_case_has_exactly_one_conserved_contract(self) -> None:
        report = qualification_report()
        case_ids = [case.case_id for study in report.studies for case in study.cases]
        self.assertEqual(len(case_ids), len(set(case_ids)))
        contract_count = sum(
            1 for study in report.studies for case in study.cases if _contract_of(case)["domain"] == study.domain
        )
        self.assertEqual(contract_count, len(case_ids))
        self.assertEqual(len(report.study_manifests), len(report.studies))


class M22QualificationArtifactTests(unittest.TestCase):
    """Test areas 14 and 15: reproducibility and qualification provenance."""

    def test_repeated_qualification_runs_are_equivalent(self) -> None:
        first = qualification_report()
        second = run_m22_qualification()
        self.assertEqual(first.procedure_version, second.procedure_version)
        self.assertEqual(first.report_sha256, second.report_sha256)
        self.assertEqual(first.to_dict()["records"], second.to_dict()["records"])
        self.assertEqual(first.to_dict()["studies"], second.to_dict()["studies"])
        self.assertEqual(first.outcome_coverage, second.outcome_coverage)
        self.assertEqual(
            [manifest.manifest_sha256 for manifest in first.study_manifests],
            [manifest.manifest_sha256 for manifest in second.study_manifests],
        )
        self.assertEqual(first.environment, second.environment)

    def test_report_separates_measured_unavailable_and_unvalidated_evidence(self) -> None:
        report = qualification_report()
        self.assertEqual(report.procedure_version, PROCEDURE_VERSION)
        self.assertEqual(report.evidence_class, EvidenceClass.QUALITATIVELY_CONSISTENT)
        self.assertTrue(unavailable_evidence())
        self.assertTrue(unvalidated_claims())
        self.assertTrue(report.selection_rule.strip())
        self.assertEqual({item.status for item in report.external_benchmarks}, {EvidenceClass.NOT_VALIDATED})
        self.assertGreaterEqual(len(report.records), 5)
        self.assertEqual({record.domain for record in report.records}, {"VES", "2D ERT", "3D ERT"})
        self.assertEqual(len(report.report_sha256), 64)
        self.assertEqual(set(metric_definitions()), set(report.metric_definitions))
        for definition in report.metric_definitions.values():
            self.assertTrue(definition["measures"])
            self.assertTrue(definition["requires"])
            self.assertTrue(definition["does_not_establish"])

    def test_record_provenance_is_retained(self) -> None:
        report = qualification_report()
        for record in report.records:
            self.assertEqual(record.manifest.procedure_version, PROCEDURE_VERSION)
            self.assertEqual(record.manifest.dataset["classification"], "internal synthetic")
            self.assertTrue(record.manifest.project["survey_id"])
            self.assertEqual(len(record.manifest.manifest_sha256), 64)
            self.assertEqual(record.convergence.domain, record.domain)
        for manifest in report.study_manifests:
            self.assertEqual(manifest.processing["qualification_procedure"], PROCEDURE_VERSION)
            self.assertIn("case_ids", manifest.inversion)

    def test_report_writes_machine_and_human_readable_artifacts(self) -> None:
        report = qualification_report()
        with tempfile.TemporaryDirectory() as directory:
            json_path = Path(directory) / "m22.json"
            markdown_path = Path(directory) / "m22.md"
            report.write_json(str(json_path))
            report.write_markdown(str(markdown_path))
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["report_sha256"], report.report_sha256)
            self.assertEqual(payload["procedure_version"], PROCEDURE_VERSION)
            self.assertEqual(
                payload["external_benchmarks"][0]["status"], "NOT VALIDATED"
            )
            markdown = markdown_path.read_text(encoding="utf-8")
            for heading in (
                "Convergence and outcome records", "Sensitivity studies", "Result-selection rule",
                "Metric definitions", "Unavailable evidence", "Unvalidated claims",
                "External benchmark readiness",
            ):
                self.assertIn(heading, markdown)
            self.assertNotIn("\r\n", markdown)

    def test_checked_in_artifact_is_self_consistent(self) -> None:
        self.assertTrue(_ARTIFACT_JSON.exists(), "the M22 JSON artifact must be checked in")
        payload = json.loads(_ARTIFACT_JSON.read_text(encoding="utf-8"))
        recorded = payload.pop("report_sha256")
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
        self.assertEqual(hashlib.sha256(canonical.encode("utf-8")).hexdigest(), recorded)
        self.assertEqual(payload["procedure_version"], PROCEDURE_VERSION)
        self.assertEqual(payload["outcome_coverage"]["FAILED"], 0)

    def test_outcome_coverage_counts_match_the_supplied_records(self) -> None:
        coverage = outcome_coverage((
            invalid_input_contract("VES", "bad"),
            cancelled_contract("2D ERT"),
        ))
        self.assertEqual(coverage["INVALID_INPUT"], 1)
        self.assertEqual(coverage["CANCELLED"], 1)
        self.assertEqual(coverage["CONVERGED"], 0)
        self.assertEqual(sum(coverage.values()), 2)

    def test_metric_helper_rejects_incomparable_model_vectors(self) -> None:
        with self.assertRaises(ValueError):
            model_log10_vector((1.0, 0.0))
        self.assertEqual(model_log10_vector((10.0, 100.0)), (1.0, 2.0))


if __name__ == "__main__":
    unittest.main()
