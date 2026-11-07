"""Tests for the benchmark admission and execution readiness path (R-1 … R-4).

The registries and datasets built here are **test-only**: they exist to exercise
the code path and are never written to a qualification artifact. They are not
external evidence, they are not bundled data, and they do not change any gate
status — ``test_repository_gate_stays_not_validated`` asserts exactly that.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from nix_ert.ert.inversion2d import ERTObservation, Mesh2D
from nix_ert.ert.inversion3d import ERT3DObservation, Mesh3D
from nix_ert.qualification import benchmark as bench
from nix_ert.qualification.datasets import (
    ert2d_qualification,
    ert3d_qualification,
    ves_qualification,
)
from nix_ert.qualification.registry import (
    BenchmarkProtocol,
    ComparisonStatus,
    QualificationDataset,
    QualificationRegistry,
    internal_qualification_registry,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_BYTES = b"test-only benchmark fixture; not external evidence\n"
TOLERANCE_JUSTIFICATION = "Test-only bound; not a qualified tolerance."
WIDE_JUSTIFICATION = "Deliberately wide test-only bound."


def _digest(payload: bytes = FIXTURE_BYTES) -> str:
    return hashlib.sha256(payload).hexdigest()


def _ves_reference() -> list[float]:
    """Reference values are the engine's response from a different known model.

    This is a test stand-in that lets the execution path produce a real metric;
    the protocol records it as such and it is never presented as independent
    scientific evidence.
    """
    qualification = ves_qualification()
    return [point.apparent_resistivity for point in qualification.clean_points]


def _build(
    tmp_path: Path,
    *,
    dataset_overrides: dict[str, object] | None = None,
    protocol_overrides: dict[str, object] | None = None,
    include_reference: bool = True,
    tolerance: float = 1e6,
) -> tuple[QualificationRegistry, str]:
    path = tmp_path / "candidate.dat"
    path.write_bytes(FIXTURE_BYTES)
    dataset_payload: dict[str, object] = {
        "dataset_id": "candidate-test-dataset",
        "classification": "user-supplied",
        "source": "Test-only in-memory fixture; not external evidence.",
        "license_status": "permission confirmed",
        "permission_note": "Test-only.",
        "acquisition_information": {"sha256": _digest(), "array": "synthetic"},
        "electrode_configuration": "Wenner-Schlumberger",
        "electrode_spacing": 5.0,
        "coordinate_context": {"crs": "local", "axis": "x"},
        "qualification_purpose": "Exercise the benchmark execution path in a test only.",
        "data_path": str(path),
    }
    dataset_payload.update(dataset_overrides or {})
    protocol_payload: dict[str, object] = {
        "protocol_id": "candidate-test-protocol",
        "dataset_id": dataset_payload["dataset_id"],
        "preprocessing_rules": ["none (frozen)"],
        "qc_rules": ["none (frozen)"],
        "inversion_parameters": {
            "domain": "VES",
            "max_nfev": 25,
            "initial_resistivities": [40.0, 10.0, 200.0],
            "initial_thicknesses": [4.0, 10.0],
        },
        "mesh_assumptions": {"layers": 3},
        "stopping_criteria": {"max_nfev": 25},
        "expected_reference_result": (
            {
                "producer": "Test stand-in reference implementation",
                "provenance": "Test-only synthetic stand-in; not a published reference.",
                "semantics": {
                    "model_space": "apparent resistivity",
                    "resistivity_unit": "ohm.m",
                    "depth_convention": "depth positive down",
                },
                "response": _ves_reference(),
            }
            if include_reference
            else {}
        ),
        "comparison_metrics": ["rmse", "log10_rmse"],
        "acceptable_tolerance": {
            metric: {
                "max_absolute": tolerance,
                "justification": (
                    WIDE_JUSTIFICATION if tolerance >= 1e3 else TOLERANCE_JUSTIFICATION
                ),
            }
            for metric in ("rmse", "log10_rmse")
        },
    }
    protocol_payload.update(protocol_overrides or {})
    registry = QualificationRegistry()
    registry.add_dataset(QualificationDataset.from_dict(dataset_payload))
    registry.add_protocol(BenchmarkProtocol.from_dict(protocol_payload))
    return registry, "candidate-test-protocol"


def _codes(registry: QualificationRegistry, protocol_id: str = "candidate-test-protocol") -> tuple[str, ...]:
    return bench.admit_benchmark_candidate(registry, protocol_id).codes


class TestAdmission:
    def test_admissible_candidate_has_no_findings(self, tmp_path: Path) -> None:
        registry, protocol_id = _build(tmp_path)
        admission = bench.admit_benchmark_candidate(registry, protocol_id)
        assert admission.admitted, admission.to_dict()
        assert admission.dataset_sha256 == _digest()
        assert len(admission.protocol_sha256) == 64

    def test_repository_internal_fixtures_are_refused(self) -> None:
        """No reachable repository dataset can enter the gate."""
        registry = internal_qualification_registry()
        registry.add_protocol(
            BenchmarkProtocol(
                protocol_id="internal-only",
                dataset_id="ves-layered-internal-v1",
                preprocessing_rules=(),
                qc_rules=(),
                inversion_parameters={"domain": "VES"},
                mesh_assumptions={},
                stopping_criteria={"max_nfev": 1},
                expected_reference_result={},
                comparison_metrics=("rmse",),
                acceptable_tolerance={},
            )
        )
        admission = bench.admit_benchmark_candidate(registry, "internal-only")
        assert not admission.admitted
        assert bench.DATASET_NOT_INDEPENDENT in admission.codes
        with pytest.raises(bench.BenchmarkAdmissionError):
            admission.require()
        assert registry.comparisons == []

    def test_unknown_protocol_is_refused(self, tmp_path: Path) -> None:
        registry, _ = _build(tmp_path)
        admission = bench.admit_benchmark_candidate(registry, "absent")
        assert admission.codes == (bench.PROTOCOL_NOT_REGISTERED,)
        assert admission.dataset_id is None

    def test_unpermitted_external_dataset_is_refused(self, tmp_path: Path) -> None:
        registry, protocol_id = _build(
            tmp_path,
            dataset_overrides={"license_status": "permission pending"},
            include_reference=False,
        )
        codes = _codes(registry, protocol_id)
        assert bench.DATASET_NOT_INDEPENDENT in codes

    def test_missing_data_path_is_refused(self, tmp_path: Path) -> None:
        registry, protocol_id = _build(tmp_path, dataset_overrides={"data_path": None})
        assert bench.DATASET_BYTES_MISSING in _codes(registry, protocol_id)

    def test_absent_dataset_file_is_refused(self, tmp_path: Path) -> None:
        registry, protocol_id = _build(
            tmp_path, dataset_overrides={"data_path": str(tmp_path / "missing.dat")}
        )
        assert bench.DATASET_BYTES_MISSING in _codes(registry, protocol_id)

    def test_unrecorded_source_digest_is_refused(self, tmp_path: Path) -> None:
        registry, protocol_id = _build(
            tmp_path, dataset_overrides={"acquisition_information": {"array": "synthetic"}}
        )
        assert bench.DATASET_HASH_UNRECORDED in _codes(registry, protocol_id)

    def test_changed_dataset_bytes_are_refused(self, tmp_path: Path) -> None:
        registry, protocol_id = _build(
            tmp_path,
            dataset_overrides={"acquisition_information": {"sha256": "0" * 64}},
        )
        assert bench.DATASET_HASH_MISMATCH in _codes(registry, protocol_id)

    def test_missing_geometry_metadata_is_refused(self, tmp_path: Path) -> None:
        for overrides in (
            {"electrode_configuration": ""},
            {"electrode_spacing": None},
            {"coordinate_context": {}},
        ):
            registry, protocol_id = _build(tmp_path, dataset_overrides=overrides)
            assert bench.DATASET_GEOMETRY_MISSING in _codes(registry, protocol_id), overrides

    def test_missing_reference_result_is_refused(self, tmp_path: Path) -> None:
        registry, protocol_id = _build(tmp_path, include_reference=False)
        assert bench.REFERENCE_RESULT_MISSING in _codes(registry, protocol_id)

    def test_reference_without_provenance_is_refused(self, tmp_path: Path) -> None:
        reference = {
            "producer": "Some independent solver",
            "provenance": "",
            "semantics": {
                "model_space": "apparent resistivity",
                "resistivity_unit": "ohm.m",
                "depth_convention": "depth positive down",
            },
            "response": _ves_reference(),
        }
        registry, protocol_id = _build(
            tmp_path,
            protocol_overrides={"expected_reference_result": reference},
        )
        assert bench.REFERENCE_PROVENANCE_MISSING in _codes(registry, protocol_id)

    def test_reference_produced_by_nix_is_refused(self, tmp_path: Path) -> None:
        reference = {
            "producer": "NiX-ERT internal pipeline",
            "provenance": "Self-produced.",
            "semantics": {
                "model_space": "apparent resistivity",
                "resistivity_unit": "ohm.m",
                "depth_convention": "depth positive down",
            },
            "response": _ves_reference(),
        }
        registry, protocol_id = _build(
            tmp_path,
            protocol_overrides={"expected_reference_result": reference},
        )
        assert bench.REFERENCE_PRODUCED_BY_NIX in _codes(registry, protocol_id)

    def test_incomplete_reference_semantics_is_refused(self, tmp_path: Path) -> None:
        reference = {
            "producer": "Some independent solver",
            "provenance": "Documented reference run.",
            "semantics": {"model_space": "apparent resistivity"},
            "response": _ves_reference(),
        }
        registry, protocol_id = _build(
            tmp_path,
            protocol_overrides={"expected_reference_result": reference},
        )
        assert bench.REFERENCE_SEMANTICS_MISSING in _codes(registry, protocol_id)

    def test_reference_without_values_is_refused(self, tmp_path: Path) -> None:
        reference = {
            "producer": "Some independent solver",
            "provenance": "Documented reference run.",
            "semantics": {
                "model_space": "apparent resistivity",
                "resistivity_unit": "ohm.m",
                "depth_convention": "depth positive down",
            },
            "response": [],
        }
        registry, protocol_id = _build(
            tmp_path,
            protocol_overrides={"expected_reference_result": reference},
        )
        assert bench.REFERENCE_RESPONSE_MISSING in _codes(registry, protocol_id)

    def test_metric_without_tolerance_is_refused(self, tmp_path: Path) -> None:
        registry, protocol_id = _build(
            tmp_path,
            protocol_overrides={
                "acceptable_tolerance": {"rmse": {"max_absolute": 1e6, "justification": TOLERANCE_JUSTIFICATION}}
            },
        )
        codes = _codes(registry, protocol_id)
        assert bench.TOLERANCE_MISSING in codes

    def test_tolerance_without_justification_is_refused(self, tmp_path: Path) -> None:
        registry, protocol_id = _build(
            tmp_path,
            protocol_overrides={
                "acceptable_tolerance": {
                    metric: {"max_absolute": 1e6} for metric in ("rmse", "log10_rmse")
                }
            },
        )
        assert bench.TOLERANCE_JUSTIFICATION_MISSING in _codes(registry, protocol_id)

    def test_negative_tolerance_is_refused(self, tmp_path: Path) -> None:
        registry, protocol_id = _build(tmp_path, tolerance=-1.0)
        assert bench.TOLERANCE_MISSING in _codes(registry, protocol_id)

    def test_unsupported_metric_is_refused(self, tmp_path: Path) -> None:
        registry, protocol_id = _build(
            tmp_path,
            protocol_overrides={
                "comparison_metrics": ["rmse", "geological_certainty"],
                "acceptable_tolerance": {
                    "rmse": {"max_absolute": 1e6, "justification": TOLERANCE_JUSTIFICATION},
                    "geological_certainty": {"max_absolute": 1.0, "justification": TOLERANCE_JUSTIFICATION},
                },
            },
        )
        assert bench.METRIC_UNSUPPORTED in _codes(registry, protocol_id)

    def test_unknown_domain_is_refused(self, tmp_path: Path) -> None:
        registry, protocol_id = _build(
            tmp_path,
            protocol_overrides={
                "inversion_parameters": {"domain": "seismic", "max_nfev": 25},
                "stopping_criteria": {"max_nfev": 25},
            },
        )
        assert bench.DOMAIN_UNSUPPORTED in _codes(registry, protocol_id)

    def test_missing_frozen_parameter_is_refused(self, tmp_path: Path) -> None:
        registry, protocol_id = _build(
            tmp_path,
            protocol_overrides={
                "inversion_parameters": {
                    "domain": "VES",
                    "initial_resistivities": [40.0, 10.0, 200.0],
                    "initial_thicknesses": [4.0, 10.0],
                },
                "stopping_criteria": {"max_nfev": 25},
            },
        )
        assert bench.PROTOCOL_PARAMETER_MISSING in _codes(registry, protocol_id)

    def test_invalid_frozen_parameter_is_refused(self, tmp_path: Path) -> None:
        registry, protocol_id = _build(
            tmp_path,
            protocol_overrides={
                "inversion_parameters": {
                    "domain": "VES",
                    "max_nfev": 0,
                    "initial_resistivities": [40.0, 10.0, 200.0],
                    "initial_thicknesses": [4.0, 10.0],
                },
                "stopping_criteria": {"max_nfev": 25},
            },
        )
        assert bench.PROTOCOL_PARAMETER_INVALID in _codes(registry, protocol_id)

    def test_inconsistent_layer_count_is_refused(self, tmp_path: Path) -> None:
        registry, protocol_id = _build(
            tmp_path,
            protocol_overrides={
                "inversion_parameters": {
                    "domain": "VES",
                    "max_nfev": 25,
                    "initial_resistivities": [40.0, 10.0, 200.0],
                    "initial_thicknesses": [4.0],
                },
                "stopping_criteria": {"max_nfev": 25},
            },
        )
        assert bench.PROTOCOL_PARAMETER_INVALID in _codes(registry, protocol_id)

    def test_ambiguous_initial_model_is_refused(self, tmp_path: Path) -> None:
        registry, protocol_id = _build(
            tmp_path,
            protocol_overrides={
                "inversion_parameters": {
                    "domain": "2D ERT",
                    "initial_resistivity": 1.0,
                    "initial_model": [[1.0, 1.0], [1.0, 1.0]],
                    "max_iterations": 1,
                    "damping": 0.3,
                    "jacobian_step": 1e-3,
                    "convergence_rms": 1e-3,
                },
                "stopping_criteria": {"max_iterations": 1},
            },
        )
        assert bench.PROTOCOL_PARAMETER_INVALID in _codes(registry, protocol_id)

    def test_contradictory_stopping_criteria_are_refused(self, tmp_path: Path) -> None:
        registry, protocol_id = _build(
            tmp_path,
            protocol_overrides={"stopping_criteria": {"max_nfev": 5}},
        )
        assert bench.STOPPING_CRITERIA_MISMATCH in _codes(registry, protocol_id)


class TestExecution:
    def test_admission_failure_prevents_execution_and_recording(self, tmp_path: Path) -> None:
        registry, protocol_id = _build(tmp_path, dataset_overrides={"electrode_spacing": None})
        case = bench.VESBenchmarkCase(points=ves_qualification().noisy_points)
        with pytest.raises(bench.BenchmarkAdmissionError):
            bench.run_benchmark(registry, protocol_id, case)
        assert registry.comparisons == []

    def test_run_records_metrics_convergence_and_status(self, tmp_path: Path) -> None:
        registry, protocol_id = _build(tmp_path)
        case = bench.VESBenchmarkCase(points=ves_qualification().noisy_points)
        run = bench.run_benchmark(registry, protocol_id, case, created_at="2026-01-01T00:00:00+00:00")
        assert run.status is ComparisonStatus.VALIDATED
        assert set(run.metrics) == {"rmse", "log10_rmse"}
        assert all(item.passed for item in run.tolerances)
        assert run.convergence.domain == "VES"
        assert registry.comparisons == [run.comparison]
        assert run.comparison.created_at == "2026-01-01T00:00:00+00:00"
        assert registry.protocols[protocol_id].comparison_metrics == ("rmse", "log10_rmse")
        registry.validate()

    def test_frozen_tolerance_decides_the_status(self, tmp_path: Path) -> None:
        """The same run under a strict frozen bound must not claim validation."""
        registry, protocol_id = _build(tmp_path, tolerance=0.0)
        case = bench.VESBenchmarkCase(points=ves_qualification().noisy_points)
        run = bench.run_benchmark(registry, protocol_id, case)
        assert run.status is ComparisonStatus.NOT_VALIDATED
        assert any(not item.passed for item in run.tolerances)
        assert run.metrics
        assert "outside tolerance" in run.notes

    def test_provenance_is_recorded_on_the_comparison(self, tmp_path: Path) -> None:
        registry, protocol_id = _build(tmp_path)
        case = bench.VESBenchmarkCase(points=ves_qualification().noisy_points)
        run = bench.run_benchmark(registry, protocol_id, case)
        provenance = run.comparison.provenance
        assert provenance["dataset_sha256"] == _digest()
        assert provenance["protocol_id"] == protocol_id
        assert provenance["protocol_sha256_pre_execution"] == run.provenance.protocol_sha256_pre_execution
        assert provenance["protocol_unchanged"] is True
        assert len(provenance["engine_source_sha256"]) == 64
        assert provenance["inputs_sha256"] == case.inputs_sha256()
        assert provenance["discretization_sha256"] == case.discretization_sha256()
        assert provenance["reference_producer"] == "Test stand-in reference implementation"
        assert provenance["environment"]["python"] and provenance["environment"]["numpy"]
        assert provenance["procedure_version"] == bench.BENCHMARK_PROCEDURE_VERSION

    def test_engine_failure_is_recorded_instead_of_hidden(self, tmp_path: Path) -> None:
        # Thicknesses below the certified domain make the engine reject the run.
        registry, protocol_id = _build(
            tmp_path,
            protocol_overrides={
                "inversion_parameters": {
                    "domain": "VES",
                    "max_nfev": 25,
                    "initial_resistivities": [40.0, 10.0, 200.0],
                    "initial_thicknesses": [1e-6, 10.0],
                }
            },
        )
        case = bench.VESBenchmarkCase(points=ves_qualification().noisy_points)
        run = bench.run_benchmark(registry, protocol_id, case)
        assert run.status is ComparisonStatus.NOT_VALIDATED
        assert run.metrics == {}
        assert run.convergence.outcome.value in {"INVALID_INPUT", "FAILED"}
        assert "not produce a response" in run.notes
        assert registry.comparisons == [run.comparison]

    def test_reference_length_mismatch_is_refused(self, tmp_path: Path) -> None:
        reference = {
            "producer": "Some independent solver",
            "provenance": "Documented reference run.",
            "semantics": {
                "model_space": "apparent resistivity",
                "resistivity_unit": "ohm.m",
                "depth_convention": "depth positive down",
            },
            "response": _ves_reference()[:3],
        }
        registry, protocol_id = _build(
            tmp_path, protocol_overrides={"expected_reference_result": reference}
        )
        case = bench.VESBenchmarkCase(points=ves_qualification().noisy_points)
        with pytest.raises(bench.BenchmarkExecutionError):
            bench.run_benchmark(registry, protocol_id, case)
        assert registry.comparisons == []

    def test_domain_mismatch_is_refused(self, tmp_path: Path) -> None:
        registry, protocol_id = _build(tmp_path)
        mesh = Mesh2D.from_electrodes([0, 1, 2, 3], nz=1, depth=2)
        observations = (ERTObservation(1, 4, 2, 3, 1.0),)
        with pytest.raises(bench.BenchmarkExecutionError):
            bench.run_benchmark(registry, protocol_id, bench.ERT2DBenchmarkCase(mesh=mesh, observations=observations))
        assert registry.comparisons == []

    def test_protocol_change_during_execution_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        registry, protocol_id = _build(tmp_path)
        digests = iter(["a" * 64, "b" * 64])
        monkeypatch.setattr(bench, "protocol_digest", lambda _protocol: next(digests))
        case = bench.VESBenchmarkCase(points=ves_qualification().noisy_points)
        with pytest.raises(bench.BenchmarkExecutionError):
            bench.run_benchmark(registry, protocol_id, case)
        assert registry.comparisons == []

    def test_two_dimensional_execution_path(self, tmp_path: Path) -> None:
        qualification = ert2d_qualification()
        reference = [item.apparent_resistivity for item in qualification.observations]
        registry, protocol_id = _build(
            tmp_path,
            protocol_overrides={
                "comparison_metrics": ["rmse"],
                "acceptable_tolerance": {
                    "rmse": {"max_absolute": 1e9, "justification": WIDE_JUSTIFICATION}
                },
                "inversion_parameters": {
                    "domain": "2D ERT",
                    "initial_resistivity": 1.0,
                    "max_iterations": 1,
                    "damping": 0.3,
                    "jacobian_step": 1e-3,
                    "convergence_rms": 1e-3,
                },
                "stopping_criteria": {"max_iterations": 1},
                "expected_reference_result": {
                    "producer": "Test stand-in reference implementation",
                    "provenance": "Test-only synthetic stand-in.",
                    "semantics": {
                        "model_space": "apparent resistivity",
                        "resistivity_unit": "ohm.m",
                        "depth_convention": "depth positive down",
                    },
                    "response": reference,
                },
            },
        )
        case = bench.ERT2DBenchmarkCase(
            mesh=qualification.mesh, observations=qualification.noisy_observations
        )
        run = bench.run_benchmark(registry, protocol_id, case)
        assert run.convergence.domain == "2D ERT"
        assert "rmse" in run.metrics
        assert run.status is ComparisonStatus.VALIDATED
        registry.validate()

    def test_two_dimensional_initial_model_path(self, tmp_path: Path) -> None:
        qualification = ert2d_qualification()
        reference = [item.apparent_resistivity for item in qualification.observations]
        mesh = qualification.mesh
        registry, protocol_id = _build(
            tmp_path,
            protocol_overrides={
                "comparison_metrics": ["rmse"],
                "acceptable_tolerance": {
                    "rmse": {"max_absolute": 1e9, "justification": WIDE_JUSTIFICATION}
                },
                "inversion_parameters": {
                    "domain": "2D ERT",
                    "initial_model": [[1.0] * mesh.nx for _ in range(mesh.nz)],
                    "max_iterations": 1,
                    "damping": 0.3,
                    "jacobian_step": 1e-3,
                    "convergence_rms": 1e-3,
                },
                "stopping_criteria": {"max_iterations": 1},
                "expected_reference_result": {
                    "producer": "Test stand-in reference implementation",
                    "provenance": "Test-only synthetic stand-in.",
                    "semantics": {
                        "model_space": "apparent resistivity",
                        "resistivity_unit": "ohm.m",
                        "depth_convention": "depth positive down",
                    },
                    "response": reference,
                },
            },
        )
        case = bench.ERT2DBenchmarkCase(mesh=mesh, observations=qualification.noisy_observations)
        run = bench.run_benchmark(registry, protocol_id, case)
        assert run.status is ComparisonStatus.VALIDATED
        assert run.metrics["rmse"] >= 0.0

    def test_three_dimensional_execution_path(self, tmp_path: Path) -> None:
        qualification = ert3d_qualification()
        reference = [item.apparent_resistivity for item in qualification.observations]
        registry, protocol_id = _build(
            tmp_path,
            protocol_overrides={
                "comparison_metrics": ["rmse"],
                "acceptable_tolerance": {
                    "rmse": {"max_absolute": 1e9, "justification": WIDE_JUSTIFICATION}
                },
                "inversion_parameters": {
                    "domain": "3D ERT",
                    "initial_resistivity": 1.0,
                    "max_iterations": 1,
                    "damping": 0.5,
                },
                "stopping_criteria": {"max_iterations": 1},
                "expected_reference_result": {
                    "producer": "Test stand-in reference implementation",
                    "provenance": "Test-only synthetic stand-in.",
                    "semantics": {
                        "model_space": "apparent resistivity",
                        "resistivity_unit": "ohm.m",
                        "depth_convention": "depth positive down",
                    },
                    "response": reference,
                },
            },
        )
        case = bench.ERT3DBenchmarkCase(
            mesh=qualification.mesh,
            electrodes=qualification.electrodes,
            observations=qualification.noisy_observations,
        )
        run = bench.run_benchmark(registry, protocol_id, case)
        assert run.convergence.domain == "3D ERT"
        assert "rmse" in run.metrics
        registry.validate()


class TestRecordContract:
    def test_provenance_survives_a_manifest_round_trip(self, tmp_path: Path) -> None:
        registry, protocol_id = _build(tmp_path)
        case = bench.VESBenchmarkCase(points=ves_qualification().noisy_points)
        run = bench.run_benchmark(registry, protocol_id, case)
        restored = QualificationRegistry.from_json(registry.to_json())
        assert restored.comparisons[0].to_dict() == run.comparison.to_dict()
        assert restored.comparisons[0].provenance["dataset_sha256"] == _digest()
        restored.validate()

    def test_recorded_provenance_is_immutable(self, tmp_path: Path) -> None:
        registry, protocol_id = _build(tmp_path)
        case = bench.VESBenchmarkCase(points=ves_qualification().noisy_points)
        comparison = bench.run_benchmark(registry, protocol_id, case).comparison
        with pytest.raises(TypeError):
            comparison.provenance["dataset_sha256"] = "tampered"  # type: ignore[index]

    def test_repository_gate_stays_not_validated(self) -> None:
        """Delivering the execution path must not move the external gate."""
        registry = internal_qualification_registry()
        assert len(registry.protocols) == 0
        assert registry.comparisons == []
        for name in ("m21_scientific_qualification.json", "m22_scientific_hardening.json"):
            payload = json.loads((ROOT / "docs" / name).read_text(encoding="utf-8"))
            if "external_benchmarks" in payload:
                statuses = {entry["status"] for entry in payload["external_benchmarks"]}
                assert statuses == {"NOT VALIDATED"}, name
            else:
                assert payload["external_benchmark"]["status"] == "NOT VALIDATED", name
        assert [dataset.dataset_id for dataset in registry.datasets.values() if dataset.independent_benchmark_eligible] == []
