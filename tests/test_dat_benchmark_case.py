"""Tests for converting the documented NiX DAT dialect into a benchmark case."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from nix_ert.ert.inversion2d import Mesh2D
from nix_ert.qualification.benchmark_cli import (
    EXIT_USAGE,
    EXIT_VALIDATED,
    BenchmarkCaseFileError,
    DATCaseRequest,
    build_case,
    execute_manifest,
    load_case,
    main,
)
from nix_ert.qualification.dat_benchmark_case import (
    CASE_DOMAIN,
    CASE_FORMAT_VERSION,
    DATBenchmarkCaseError,
    build_dat_benchmark_case,
    describe_dat_case,
)
from nix_ert.qualification.registry import (
    BenchmarkProtocol,
    ComparisonStatus,
    QualificationDataset,
    QualificationRegistry,
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
MESH_ASSUMPTIONS = {"nz": 3, "depth": 3}
JUSTIFICATION = "Test-only bound; not a qualified tolerance."


def _write(tmp_path: Path, text: str = DAT, name: str = "line.dat") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


class TestConverter:
    def test_payload_matches_the_documented_dialect(self, tmp_path: Path) -> None:
        converted = build_dat_benchmark_case(_write(tmp_path), "candidate", MESH_ASSUMPTIONS)
        payload = converted.to_payload()
        assert payload["protocol_id"] == "candidate"
        assert payload["domain"] == CASE_DOMAIN
        assert payload["case_format_version"] == CASE_FORMAT_VERSION
        self_check = Mesh2D.from_electrodes([0, 1, 2, 3, 4, 5], nz=3, depth=3)
        assert payload["x_edges"] == list(self_check.x_edges)
        assert payload["depth_edges"] == list(self_check.depth_edges)
        assert len(payload["observations"]) == 6
        assert payload["observations"][0] == {
            "a": 1, "b": 2, "m": 3, "n": 4, "apparent_resistivity": 100.0, "excluded": False
        }

    def test_payload_is_accepted_by_the_case_schema(self, tmp_path: Path) -> None:
        converted = build_dat_benchmark_case(_write(tmp_path), "candidate", MESH_ASSUMPTIONS)
        spec = build_case("candidate", converted.to_payload())
        assert spec.case.domain == "2D ERT"
        assert spec.case.active_observation_count() == 6
        assert spec.case.mesh.nz == 3

    def test_description_reports_facts_without_claiming_evidence(self, tmp_path: Path) -> None:
        converted = build_dat_benchmark_case(_write(tmp_path), "candidate", MESH_ASSUMPTIONS)
        facts = describe_dat_case(converted)
        assert facts["declared_array"] == "Wenner"
        assert facts["electrode_spacing"] == 1.0
        assert facts["electrode_count"] == 6
        assert facts["observation_count"] == 6
        assert "not used as scientific evidence" in facts["note"]

    def test_converted_json_round_trips(self, tmp_path: Path) -> None:
        converted = build_dat_benchmark_case(_write(tmp_path), "candidate", MESH_ASSUMPTIONS)
        payload = json.loads(converted.to_json())
        assert payload == converted.to_payload()


class TestRefusal:
    def test_mesh_assumptions_are_required(self, tmp_path: Path) -> None:
        with pytest.raises(DATBenchmarkCaseError, match="mesh_assumptions"):
            build_dat_benchmark_case(_write(tmp_path), "candidate", {})

    @pytest.mark.parametrize("assumptions", [{"nz": 0}, {"nz": "3"}, {"nz": 3.0}, {"nz": True}])
    def test_invalid_mesh_resolution_is_refused(self, tmp_path: Path, assumptions) -> None:
        with pytest.raises(DATBenchmarkCaseError, match="mesh_assumptions.nz"):
            build_dat_benchmark_case(_write(tmp_path), "candidate", assumptions)

    @pytest.mark.parametrize("depth", [0, -1, float("nan"), "3"])
    def test_invalid_depth_is_refused(self, tmp_path: Path, depth) -> None:
        with pytest.raises(DATBenchmarkCaseError, match="mesh_assumptions.depth"):
            build_dat_benchmark_case(
                _write(tmp_path), "candidate", {"nz": 3, "depth": depth}
            )

    def test_topography_is_refused_rather_than_flattened(self, tmp_path: Path) -> None:
        text = DAT.replace("Wenner\n0\n", "Wenner\n2\n0 1\n1 2\n")
        with pytest.raises(DATBenchmarkCaseError, match="topography"):
            build_dat_benchmark_case(_write(tmp_path, text), "candidate", MESH_ASSUMPTIONS)

    def test_invalid_apparent_resistivity_is_refused(self, tmp_path: Path) -> None:
        text = DAT.replace("1 2 3 4 100", "1 2 3 4 -100")
        with pytest.raises(DATBenchmarkCaseError, match="no usable apparent resistivity"):
            build_dat_benchmark_case(_write(tmp_path, text), "candidate", MESH_ASSUMPTIONS)

    def test_dataset_without_electrodes_is_refused(self, tmp_path: Path) -> None:
        text = "0\n1\nWenner\n0\n"
        with pytest.raises(DATBenchmarkCaseError, match="electrode"):
            build_dat_benchmark_case(_write(tmp_path, text), "candidate", MESH_ASSUMPTIONS)

    def test_malformed_dat_is_refused_with_its_own_error(self, tmp_path: Path) -> None:
        with pytest.raises(DATBenchmarkCaseError):
            build_dat_benchmark_case(_write(tmp_path, "not a dat file\n"), "candidate", MESH_ASSUMPTIONS)

    def test_blank_protocol_id_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(DATBenchmarkCaseError, match="protocol ID"):
            build_dat_benchmark_case(_write(tmp_path), "  ", MESH_ASSUMPTIONS)


def _manifest(tmp_path: Path, dat_path: Path) -> Path:
    payload_bytes = dat_path.read_bytes()
    dataset = QualificationDataset.from_dict(
        {
            "dataset_id": "dat-case-dataset",
            "classification": "user-supplied",
            "source": "Test-only fixture; not external evidence.",
            "license_status": "permission confirmed",
            "permission_note": "Test-only.",
            "acquisition_information": {
                "sha256": hashlib.sha256(payload_bytes).hexdigest(),
                "array": "Wenner",
            },
            "electrode_configuration": "Wenner",
            "electrode_spacing": 1.0,
            "coordinate_context": {"crs": "local"},
            "qualification_purpose": "Exercise DAT case conversion in a test only.",
            "data_path": str(dat_path),
        }
    )
    protocol = BenchmarkProtocol.from_dict(
        {
            "protocol_id": "dat-protocol",
            "dataset_id": "dat-case-dataset",
            "preprocessing_rules": ["none (frozen)"],
            "qc_rules": ["none (frozen)"],
            "inversion_parameters": {
                "domain": "2D ERT",
                "initial_resistivity": 1.0,
                "max_iterations": 1,
                "damping": 0.3,
                "jacobian_step": 1e-3,
                "convergence_rms": 1e-3,
            },
            "mesh_assumptions": MESH_ASSUMPTIONS,
            "stopping_criteria": {"max_iterations": 1},
            "expected_reference_result": {
                "producer": "Test stand-in reference implementation",
                "provenance": "Test-only synthetic stand-in.",
                "semantics": {
                    "model_space": "apparent resistivity",
                    "resistivity_unit": "ohm.m",
                    "depth_convention": "depth positive down",
                },
                "response": [100.0, 120.0, 90.0, 110.0, 105.0, 95.0],
            },
            "comparison_metrics": ["rmse"],
            "acceptable_tolerance": {
                "rmse": {"max_absolute": 1e9, "justification": JUSTIFICATION}
            },
        }
    )
    registry = QualificationRegistry()
    registry.add_dataset(dataset)
    registry.add_protocol(protocol)
    manifest = tmp_path / "registry.json"
    registry.write_manifest(manifest)
    return manifest


class TestCli:
    def test_dat_case_executes_and_records(self, tmp_path: Path) -> None:
        dat_path = _write(tmp_path)
        manifest = _manifest(tmp_path, dat_path)
        execution = execute_manifest(
            manifest,
            dat_cases=(DATCaseRequest("dat-protocol", str(dat_path)),),
            record_to=manifest,
        )
        assert execution.exit_code == EXIT_VALIDATED
        run = execution.outcomes[0].run
        assert run is not None and run.status is ComparisonStatus.VALIDATED
        assert run.convergence.domain == "2D ERT"
        restored = QualificationRegistry.read_manifest(manifest)
        assert len(restored.comparisons) == 1

    def test_emit_case_writes_a_loadable_payload(self, tmp_path: Path) -> None:
        dat_path = _write(tmp_path)
        manifest = _manifest(tmp_path, dat_path)
        emitted = tmp_path / "cases" / "dat-case.json"
        assert (
            main(
                [
                    "--manifest",
                    str(manifest),
                    "--case-from-dat",
                    f"dat-protocol={dat_path}",
                    "--emit-case",
                    f"dat-protocol={emitted}",
                ]
            )
            == EXIT_VALIDATED
        )
        payload = json.loads(emitted.read_text(encoding="utf-8"))
        assert payload["domain"] == "2D ERT"
        assert len(payload["observations"]) == 6
        spec = load_case("dat-protocol", emitted)
        assert spec.case.active_observation_count() == 6

    def test_dat_case_for_unselected_protocol_is_a_usage_error(self, tmp_path: Path) -> None:
        dat_path = _write(tmp_path)
        manifest = _manifest(tmp_path, dat_path)
        with pytest.raises(BenchmarkCaseFileError, match="not selected"):
            execute_manifest(
                manifest,
                dat_cases=(DATCaseRequest("other-protocol", str(dat_path)),),
            )

    def test_case_file_and_dat_conversion_cannot_both_apply(self, tmp_path: Path) -> None:
        dat_path = _write(tmp_path)
        manifest = _manifest(tmp_path, dat_path)
        converted = build_dat_benchmark_case(dat_path, "dat-protocol", MESH_ASSUMPTIONS)
        case = build_case("dat-protocol", converted.to_payload())
        with pytest.raises(BenchmarkCaseFileError, match="both a case file and a DAT"):
            execute_manifest(
                manifest,
                cases=(case,),
                dat_cases=(DATCaseRequest("dat-protocol", str(dat_path)),),
            )

    def test_emit_without_conversion_is_a_usage_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        dat_path = _write(tmp_path)
        manifest = _manifest(tmp_path, dat_path)
        code = main(
            ["--manifest", str(manifest), "--emit-case", f"dat-protocol={tmp_path / 'x.json'}"]
        )
        assert code == EXIT_USAGE
        assert "no --case-from-dat conversion" in capsys.readouterr().err

    def test_conversion_failure_reports_a_usage_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        dat_path = _write(tmp_path, "1\n1\nWenner\n0\nbroken row\n")
        manifest = _manifest(tmp_path, dat_path)
        code = main(
            [
                "--manifest",
                str(manifest),
                "--case-from-dat",
                f"dat-protocol={dat_path}",
            ]
        )
        assert code == EXIT_USAGE
        message = capsys.readouterr().err
        assert "cannot convert" in message
