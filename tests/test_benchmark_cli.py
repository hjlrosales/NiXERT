"""Tests for the headless benchmark manifest CLI.

Every manifest and dataset here is test-only: it exercises the tool, is written
to a temporary directory, and is never checked in or presented as evidence.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from nix_ert.qualification import benchmark_cli
from nix_ert.qualification.benchmark_cli import (
    CASE_FORMAT_VERSION,
    EXIT_NOT_VALIDATED,
    EXIT_REFUSED,
    EXIT_USAGE,
    EXIT_VALIDATED,
    BenchmarkCaseFileError,
    build_case,
    execute_manifest,
    load_case,
    main,
)
from nix_ert.qualification.datasets import ves_qualification
from nix_ert.qualification.registry import (
    BenchmarkComparison,
    BenchmarkProtocol,
    ComparisonStatus,
    QualificationDataset,
    QualificationRegistry,
    internal_qualification_registry,
)

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "run_external_benchmark.py"
DATASET_BYTES = b"test-only CLI fixture; not external evidence\n"
JUSTIFICATION = "Test-only bound; not a qualified tolerance."


def _write_manifest(
    tmp_path: Path,
    *,
    tolerance: float = 1e6,
    domain_parameters: dict[str, object] | None = None,
    metrics: list[str] | None = None,
    identifier: str = "cli-protocol",
    digest: str | None = None,
) -> tuple[Path, str]:
    dataset_path = tmp_path / "candidate.dat"
    dataset_path.write_bytes(DATASET_BYTES)
    dataset = QualificationDataset.from_dict(
        {
            "dataset_id": "cli-test-dataset",
            "classification": "user-supplied",
            "source": "Test-only in-memory fixture; not external evidence.",
            "license_status": "permission confirmed",
            "permission_note": "Test-only.",
            "acquisition_information": {
                "sha256": digest or hashlib.sha256(DATASET_BYTES).hexdigest(),
                "array": "synthetic",
            },
            "electrode_configuration": "Wenner-Schlumberger",
            "electrode_spacing": 5.0,
            "coordinate_context": {"crs": "local"},
            "qualification_purpose": "Exercise the headless benchmark tool in a test only.",
            "data_path": str(dataset_path),
        }
    )
    parameters = domain_parameters or {
        "domain": "VES",
        "max_nfev": 25,
        "initial_resistivities": [40.0, 10.0, 200.0],
        "initial_thicknesses": [4.0, 10.0],
    }
    protocol = BenchmarkProtocol.from_dict(
        {
            "protocol_id": identifier,
            "dataset_id": "cli-test-dataset",
            "preprocessing_rules": ["none (frozen)"],
            "qc_rules": ["none (frozen)"],
            "inversion_parameters": parameters,
            "mesh_assumptions": {"layers": 3},
            "stopping_criteria": {"max_nfev": parameters.get("max_nfev", 25)},
            "expected_reference_result": {
                "producer": "Test stand-in reference implementation",
                "provenance": "Test-only synthetic stand-in; not a published reference.",
                "semantics": {
                    "model_space": "apparent resistivity",
                    "resistivity_unit": "ohm.m",
                    "depth_convention": "depth positive down",
                },
                "response": [
                    point.apparent_resistivity for point in ves_qualification().clean_points
                ],
            },
            "comparison_metrics": metrics or ["rmse", "log10_rmse"],
            "acceptable_tolerance": {
                metric: {"max_absolute": tolerance, "justification": JUSTIFICATION}
                for metric in (metrics or ["rmse", "log10_rmse"])
            },
        }
    )
    registry = QualificationRegistry()
    registry.add_dataset(dataset)
    registry.add_protocol(protocol)
    manifest = tmp_path / "manifest.json"
    registry.write_manifest(manifest)
    return manifest, identifier


def _write_case(tmp_path: Path, protocol_id: str, *, domain: str = "VES") -> Path:
    points = [
        {
            "ab2": point.ab2,
            "mn2": point.mn2,
            "apparent_resistivity": point.apparent_resistivity,
        }
        for point in ves_qualification().noisy_points
    ]
    payload: dict[str, object] = {
        "protocol_id": protocol_id,
        "domain": domain,
        "case_format_version": CASE_FORMAT_VERSION,
        "points": points,
    }
    if domain != "VES":
        payload.pop("points")
        payload["x_edges"] = [0.0, 1.0, 2.0, 3.0]
        payload["depth_edges"] = [0.0, 2.0]
        payload["observations"] = [
            {"a": 1, "b": 4, "m": 2, "n": 3, "apparent_resistivity": 1.0}
        ]
    case = tmp_path / "case.json"
    case.write_text(json.dumps(payload), encoding="utf-8")
    return case


class TestCaseFiles:
    def test_case_requires_matching_protocol_id(self, tmp_path: Path) -> None:
        case = _write_case(tmp_path, "someone-else")
        with pytest.raises(BenchmarkCaseFileError, match="protocol_id"):
            load_case("cli-protocol", case)

    def test_case_rejects_unknown_fields(self, tmp_path: Path) -> None:
        case = _write_case(tmp_path, "cli-protocol")
        payload = json.loads(case.read_text(encoding="utf-8"))
        payload["tolerance"] = 1.0
        case.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(BenchmarkCaseFileError, match="unknown fields"):
            load_case("cli-protocol", case)

    def test_case_rejects_unknown_format_version(self, tmp_path: Path) -> None:
        case = _write_case(tmp_path, "cli-protocol")
        payload = json.loads(case.read_text(encoding="utf-8"))
        payload["case_format_version"] = "benchmark-case-v2"
        case.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(BenchmarkCaseFileError, match="case_format_version"):
            load_case("cli-protocol", case)

    def test_case_rejects_non_finite_geometry(self) -> None:
        with pytest.raises(BenchmarkCaseFileError, match="finite"):
            build_case(
                "cli-protocol",
                {
                    "protocol_id": "cli-protocol",
                    "domain": "2D ERT",
                    "x_edges": [0.0, float("inf"), 2.0],
                    "depth_edges": [0.0, 1.0],
                    "observations": [
                        {"a": 1, "b": 3, "m": 2, "n": 3, "apparent_resistivity": 1.0}
                    ],
                },
            )

    def test_case_accepts_all_three_domains(self, tmp_path: Path) -> None:
        ves = load_case("cli-protocol", _write_case(tmp_path, "cli-protocol"))
        assert ves.case.domain == "VES"
        two_d = load_case(
            "cli-protocol", _write_case(tmp_path, "cli-protocol", domain="2D ERT")
        )
        assert two_d.case.domain == "2D ERT"
        payload = {
            "protocol_id": "cli-protocol",
            "domain": "3D ERT",
            "x_edges": [0.0, 1.0, 2.0, 3.0],
            "y_edges": [0.0, 1.0],
            "depth_edges": [0.0, 1.0],
            "electrodes": [[0.5, 0.5], [1.5, 0.5], [2.5, 0.5], [3.5, 0.5]],
            "observations": [
                {"a": 1, "b": 4, "m": 2, "n": 3, "apparent_resistivity": 1.0}
            ],
        }
        assert build_case("cli-protocol", payload).case.domain == "3D ERT"


class TestExecution:
    def test_admission_only_never_executes(self, tmp_path: Path) -> None:
        manifest, protocol_id = _write_manifest(tmp_path)
        execution = execute_manifest(manifest, admission_only=True)
        assert execution.exit_code == EXIT_VALIDATED
        assert execution.outcomes[0].admission.admitted
        assert execution.outcomes[0].run is None
        restored = QualificationRegistry.read_manifest(manifest)
        assert restored.comparisons == []

    def test_refused_manifest_exits_two_and_records_nothing(self, tmp_path: Path) -> None:
        manifest = tmp_path / "refused.json"
        registry = internal_qualification_registry()
        registry.add_protocol(
            BenchmarkProtocol(
                protocol_id="internal-check",
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
        registry.write_manifest(manifest)
        execution = execute_manifest(manifest, admission_only=True)
        assert execution.exit_code == EXIT_REFUSED
        assert "dataset_not_independent" in execution.outcomes[0].admission.codes
        assert "REFUSED" in execution.to_text()

    def test_execution_records_a_validation(self, tmp_path: Path) -> None:
        manifest, protocol_id = _write_manifest(tmp_path)
        case = load_case(protocol_id, _write_case(tmp_path, protocol_id))
        execution = execute_manifest(manifest, cases=(case,), record_to=manifest)
        assert execution.exit_code == EXIT_VALIDATED
        outcome = execution.outcomes[0]
        assert outcome.run is not None
        assert outcome.run.status is ComparisonStatus.VALIDATED
        restored = QualificationRegistry.read_manifest(manifest)
        assert len(restored.comparisons) == 1
        assert restored.comparisons[0].provenance["dataset_sha256"]
        assert "VALIDATED" in execution.to_text()

    def test_strict_frozen_tolerance_exits_three(self, tmp_path: Path) -> None:
        manifest, protocol_id = _write_manifest(tmp_path, tolerance=0.0)
        case = load_case(protocol_id, _write_case(tmp_path, protocol_id))
        execution = execute_manifest(manifest, cases=(case,), record_to=manifest)
        assert execution.exit_code == EXIT_NOT_VALIDATED
        restored = QualificationRegistry.read_manifest(manifest)
        assert restored.comparisons[0].status is ComparisonStatus.NOT_VALIDATED

    def test_changed_dataset_bytes_are_refused(self, tmp_path: Path) -> None:
        manifest, protocol_id = _write_manifest(tmp_path)
        (tmp_path / "candidate.dat").write_bytes(b"substituted bytes")
        execution = execute_manifest(manifest, admission_only=True)
        assert execution.exit_code == EXIT_REFUSED
        assert "dataset_hash_mismatch" in execution.outcomes[0].admission.codes

    def test_missing_case_for_admitted_protocol_is_a_usage_error(self, tmp_path: Path) -> None:
        manifest, _ = _write_manifest(tmp_path)
        with pytest.raises(BenchmarkCaseFileError, match="no case file"):
            execute_manifest(manifest)

    def test_execution_without_record_target_leaves_the_manifest_untouched(
        self, tmp_path: Path
    ) -> None:
        manifest, protocol_id = _write_manifest(tmp_path)
        before = manifest.read_bytes()
        case = load_case(protocol_id, _write_case(tmp_path, protocol_id))
        execution = execute_manifest(manifest, cases=(case,))
        assert execution.outcomes[0].run is not None
        assert execution.record_path is None
        assert manifest.read_bytes() == before

    def test_case_for_unselected_protocol_is_a_usage_error(self, tmp_path: Path) -> None:
        manifest, protocol_id = _write_manifest(tmp_path)
        registry = QualificationRegistry.read_manifest(manifest)
        registry.add_protocol(
            BenchmarkProtocol.from_dict(
                json.loads(manifest.read_text(encoding="utf-8"))["protocols"][0]
                | {"protocol_id": "cli-protocol-second"}
            )
        )
        registry.write_manifest(manifest)
        case = load_case("cli-protocol-second", _write_case(tmp_path, "cli-protocol-second"))
        with pytest.raises(BenchmarkCaseFileError, match="not selected"):
            execute_manifest(manifest, cases=(case,), protocol_ids=(protocol_id,))

    def test_unknown_protocol_selection_is_a_usage_error(self, tmp_path: Path) -> None:
        manifest, _ = _write_manifest(tmp_path)
        with pytest.raises(BenchmarkCaseFileError, match="unknown protocol"):
            execute_manifest(manifest, protocol_ids=("missing",), admission_only=True)

    def test_domain_mismatch_is_reported_without_recording(self, tmp_path: Path) -> None:
        manifest, protocol_id = _write_manifest(tmp_path)
        case = load_case(protocol_id, _write_case(tmp_path, protocol_id, domain="2D ERT"))
        execution = execute_manifest(manifest, cases=(case,))
        assert execution.exit_code == EXIT_USAGE
        assert execution.outcomes[0].error
        restored = QualificationRegistry.read_manifest(manifest)
        assert restored.comparisons == []

    def test_json_output_is_deterministic_and_complete(self, tmp_path: Path) -> None:
        manifest, protocol_id = _write_manifest(tmp_path)
        case = load_case(protocol_id, _write_case(tmp_path, protocol_id))
        execution = execute_manifest(manifest, cases=(case,))
        payload = json.loads(execution.to_json())
        assert payload["case_format_version"] == CASE_FORMAT_VERSION
        assert payload["exit_code"] == EXIT_VALIDATED
        assert payload["outcomes"][0]["run"]["comparison"]["provenance"]["dataset_sha256"]
        assert json.loads(execution.to_json()) == payload


class TestCommandLine:
    def test_main_reports_refusal_for_internal_manifest(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        manifest = tmp_path / "internal.json"
        registry = internal_qualification_registry()
        registry.add_protocol(
            BenchmarkProtocol(
                protocol_id="internal-check",
                dataset_id="ert-2d-anomaly-internal-v1",
                preprocessing_rules=(),
                qc_rules=(),
                inversion_parameters={"domain": "2D ERT"},
                mesh_assumptions={},
                stopping_criteria={"max_iterations": 1},
                expected_reference_result={},
                comparison_metrics=("rmse",),
                acceptable_tolerance={},
            )
        )
        registry.write_manifest(manifest)
        assert main(["--manifest", str(manifest), "--admit-only"]) == EXIT_REFUSED
        captured = capsys.readouterr()
        assert "dataset_not_independent" in captured.out

    def test_main_writes_json_result(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        manifest, protocol_id = _write_manifest(tmp_path)
        case_path = _write_case(tmp_path, protocol_id)
        out = tmp_path / "result.json"
        code = main(
            [
                "--manifest",
                str(manifest),
                "--case",
                f"{protocol_id}={case_path}",
                "--json",
                str(out),
            ]
        )
        assert code == EXIT_VALIDATED
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["outcomes"][0]["run"]["status"] == "VALIDATED"
        assert "VALIDATED" in capsys.readouterr().out

    def test_main_rejects_a_forged_manifest_before_running(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        manifest, protocol_id = _write_manifest(tmp_path)
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["comparisons"] = [
            BenchmarkComparison.create(
                BenchmarkProtocol.from_dict(payload["protocols"][0]),
                ComparisonStatus.VALIDATED,
                metrics={},
                convergence={},
                notes="Forged: a validation claim without measured evidence.",
            ).to_dict()
        ]
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        assert main(["--manifest", str(manifest), "--admit-only"]) == EXIT_USAGE
        assert "invalid qualification manifest" in capsys.readouterr().err

    def test_tool_runs_headless_from_the_project_root(self, tmp_path: Path) -> None:
        manifest, protocol_id = _write_manifest(tmp_path)
        case_path = _write_case(tmp_path, protocol_id)
        out = tmp_path / "result.json"
        completed = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--manifest",
                str(manifest),
                "--case",
                f"{protocol_id}={case_path}",
                "--json",
                str(out),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == EXIT_VALIDATED, completed.stderr
        assert "VALIDATED" in completed.stdout
        assert json.loads(out.read_text(encoding="utf-8"))["exit_code"] == EXIT_VALIDATED
