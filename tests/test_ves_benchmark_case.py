"""Tests for converting the documented VES text/CSV dialect into a benchmark case."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest

from nix_ert.qualification.benchmark_cli import (
    EXIT_USAGE,
    EXIT_VALIDATED,
    BenchmarkCaseFileError,
    VESCaseRequest,
    build_case,
    execute_manifest,
    load_case,
    main,
)
from nix_ert.qualification.registry import (
    BenchmarkProtocol,
    ComparisonStatus,
    QualificationDataset,
    QualificationRegistry,
)
from nix_ert.qualification.ves_benchmark_case import (
    CASE_DOMAIN,
    CASE_FORMAT_VERSION,
    VESBenchmarkCaseError,
    build_ves_benchmark_case,
    describe_ves_case,
)
from nix_ert.ves.engine import LayeredEarthModel, layered_apparent_resistivity, VESPoint


VES = """# Test-only sounding; not external evidence.
AB/2,MN/2,resistance
2,0.5,10.0
4,0.5,5.0
8,0.5,2.5
16,0.5,1.25
32,0.5,0.625
"""
SPACINGS = ((2.0, 0.5), (4.0, 0.5), (8.0, 0.5), (16.0, 0.5), (32.0, 0.5))
INITIAL_MODEL = LayeredEarthModel((100.0, 10.0), (20.0,))
JUSTIFICATION = "Test-only bound; not a qualified tolerance."


def _write(tmp_path: Path, text: str = VES, name: str = "sounding.csv") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _measured_rho(ab2: float, mn2: float, resistance: float) -> float:
    """Schlumberger apparent resistivity for the documented three-column row."""
    return math.pi * (ab2**2 - mn2**2) / (2 * mn2) * resistance


class TestConverter:
    def test_payload_matches_the_documented_dialect(self, tmp_path: Path) -> None:
        converted = build_ves_benchmark_case(_write(tmp_path), "sounding")
        payload = converted.to_payload()
        assert payload["protocol_id"] == "sounding"
        assert payload["domain"] == CASE_DOMAIN
        assert payload["case_format_version"] == CASE_FORMAT_VERSION
        assert len(payload["points"]) == 5
        assert payload["points"][0] == {
            "ab2": 2.0,
            "mn2": 0.5,
            "apparent_resistivity": pytest.approx(_measured_rho(2.0, 0.5, 10.0)),
            "resistance": 10.0,
            "excluded": False,
        }
        assert [point["ab2"] for point in payload["points"]] == [2.0, 4.0, 8.0, 16.0, 32.0]

    def test_supplied_resistivity_is_carried_through_unchanged(self, tmp_path: Path) -> None:
        text = "AB/2 MN/2 resistance apparent_resistivity\n2 0.5 10 42.5\n4 0.5 5 21.25\n"
        converted = build_ves_benchmark_case(_write(tmp_path, text), "sounding")
        points = converted.to_payload()["points"]
        assert [point["apparent_resistivity"] for point in points] == [42.5, 21.25]
        assert [point["resistance"] for point in points] == [10.0, 5.0]
        assert points[0]["apparent_resistivity"] != pytest.approx(_measured_rho(2.0, 0.5, 10.0))

    def test_payload_keeps_both_the_measured_and_the_derived_quantity(
        self, tmp_path: Path
    ) -> None:
        converted = build_ves_benchmark_case(_write(tmp_path), "sounding")
        first = converted.to_payload()["points"][0]
        assert first["resistance"] == 10.0
        assert first["apparent_resistivity"] == pytest.approx(_measured_rho(2.0, 0.5, 10.0))
        assert converted.points[0].resistance == 10.0

    def test_payload_is_accepted_by_the_case_schema(self, tmp_path: Path) -> None:
        converted = build_ves_benchmark_case(_write(tmp_path), "sounding")
        spec = build_case("sounding", converted.to_payload())
        assert spec.case.domain == "VES"
        assert spec.case.active_observation_count() == 5
        assert [point.ab2 for point in spec.case.points] == [2.0, 4.0, 8.0, 16.0, 32.0]

    def test_description_reports_facts_without_claiming_evidence(self, tmp_path: Path) -> None:
        converted = build_ves_benchmark_case(_write(tmp_path), "sounding")
        facts = describe_ves_case(converted)
        assert facts["domain"] == "VES"
        assert facts["point_count"] == 5
        assert facts["active_point_count"] == 5
        assert facts["excluded_point_count"] == 0
        assert facts["ab2_range"] == [2.0, 32.0]
        assert facts["mn2_range"] == [0.5, 0.5]
        assert facts["apparent_resistivity_range"] == pytest.approx(
            [_measured_rho(2.0, 0.5, 10.0), _measured_rho(32.0, 0.5, 0.625)]
        )
        assert "not scientific evidence" in facts["note"]

    def test_converted_json_round_trips(self, tmp_path: Path) -> None:
        converted = build_ves_benchmark_case(_write(tmp_path), "sounding")
        assert json.loads(converted.to_json()) == converted.to_payload()


class TestRefusal:
    def test_blank_protocol_id_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(VESBenchmarkCaseError, match="protocol ID"):
            build_ves_benchmark_case(_write(tmp_path), "   ")

    def test_malformed_row_is_refused_with_its_source_and_line(self, tmp_path: Path) -> None:
        text = VES.replace("4,0.5,5.0", "4,0.5,not-a-number")
        with pytest.raises(VESBenchmarkCaseError, match="sounding.csv line 4"):
            build_ves_benchmark_case(_write(tmp_path, text), "sounding")

    def test_invalid_schlumberger_geometry_is_refused(self, tmp_path: Path) -> None:
        text = VES.replace("4,0.5,5.0", "0.5,4,5.0")
        with pytest.raises(VESBenchmarkCaseError, match="AB/2 must be greater than MN/2"):
            build_ves_benchmark_case(_write(tmp_path, text), "sounding")

    def test_non_positive_resistance_is_refused(self, tmp_path: Path) -> None:
        text = VES.replace("4,0.5,5.0", "4,0.5,-5.0")
        with pytest.raises(VESBenchmarkCaseError, match="resistance must be positive"):
            build_ves_benchmark_case(_write(tmp_path, text), "sounding")

    @pytest.mark.parametrize("resistivity", ["0", "-42.5", "nan", "1e400"])
    def test_unusable_supplied_resistivity_is_refused(
        self, tmp_path: Path, resistivity: str
    ) -> None:
        text = VES.replace("4,0.5,5.0", f"4,0.5,5.0,{resistivity}")
        with pytest.raises(VESBenchmarkCaseError):
            build_ves_benchmark_case(_write(tmp_path, text), "sounding")

    def test_extra_column_is_refused(self, tmp_path: Path) -> None:
        text = VES.replace("4,0.5,5.0", "4,0.5,5.0,50.0,extra")
        with pytest.raises(VESBenchmarkCaseError, match="expected at most 4 columns"):
            build_ves_benchmark_case(_write(tmp_path, text), "sounding")

    def test_sounding_without_measurements_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(VESBenchmarkCaseError):
            build_ves_benchmark_case(_write(tmp_path, "AB/2,MN/2,resistance\n"), "sounding")

    def test_missing_file_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(VESBenchmarkCaseError, match="Unable to read"):
            build_ves_benchmark_case(tmp_path / "absent.csv", "sounding")


def _manifest(tmp_path: Path, source_path: Path, *, domain: str = "VES") -> Path:
    payload_bytes = source_path.read_bytes()
    dataset = QualificationDataset.from_dict(
        {
            "dataset_id": "ves-case-dataset",
            "classification": "user-supplied",
            "source": "Test-only fixture; not external evidence.",
            "license_status": "permission confirmed",
            "permission_note": "Test-only.",
            "acquisition_information": {
                "sha256": hashlib.sha256(payload_bytes).hexdigest(),
                "array": "Schlumberger",
            },
            "electrode_configuration": "Schlumberger",
            "electrode_spacing": 1.0,
            "coordinate_context": {"crs": "local"},
            "qualification_purpose": "Exercise VES case conversion in a test only.",
            "data_path": str(source_path),
        }
    )
    if domain == "VES":
        parameters = {
            "domain": "VES",
            "initial_resistivities": list(INITIAL_MODEL.resistivities),
            "initial_thicknesses": list(INITIAL_MODEL.thicknesses),
            "max_nfev": 1,
        }
        response = [
            layered_apparent_resistivity(INITIAL_MODEL, ab2, mn2) for ab2, mn2 in SPACINGS
        ]
        protocol_id = "ves-protocol"
    else:
        parameters = {
            "domain": "2D ERT",
            "initial_resistivity": 1.0,
            "max_iterations": 1,
            "damping": 0.3,
            "jacobian_step": 1e-3,
            "convergence_rms": 1e-3,
        }
        response = [100.0, 120.0, 90.0]
        protocol_id = "ert-protocol"
    protocol = BenchmarkProtocol.from_dict(
        {
            "protocol_id": protocol_id,
            "dataset_id": "ves-case-dataset",
            "preprocessing_rules": ["none (frozen)"],
            "qc_rules": ["none (frozen)"],
            "inversion_parameters": parameters,
            "mesh_assumptions": {"nz": 3},
            "stopping_criteria": {"max_nfev": 1},
            "expected_reference_result": {
                "producer": "Test stand-in reference implementation",
                "provenance": "Test-only synthetic stand-in.",
                "semantics": {
                    "model_space": "apparent resistivity",
                    "resistivity_unit": "ohm.m",
                    "depth_convention": "depth positive down",
                },
                "response": response,
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
    def test_ves_case_executes_and_records(self, tmp_path: Path) -> None:
        ves_path = _write(tmp_path)
        manifest = _manifest(tmp_path, ves_path)
        execution = execute_manifest(
            manifest,
            ves_cases=(VESCaseRequest("ves-protocol", str(ves_path)),),
            record_to=manifest,
        )
        assert execution.exit_code == EXIT_VALIDATED
        run = execution.outcomes[0].run
        assert run is not None and run.status is ComparisonStatus.VALIDATED
        assert run.convergence.domain == "VES"
        restored = QualificationRegistry.read_manifest(manifest)
        assert len(restored.comparisons) == 1

    def test_emit_case_writes_a_loadable_payload(self, tmp_path: Path) -> None:
        ves_path = _write(tmp_path)
        manifest = _manifest(tmp_path, ves_path)
        emitted = tmp_path / "cases" / "ves-case.json"
        assert (
            main(
                [
                    "--manifest",
                    str(manifest),
                    "--case-from-ves",
                    f"ves-protocol={ves_path}",
                    "--emit-case",
                    f"ves-protocol={emitted}",
                ]
            )
            == EXIT_VALIDATED
        )
        payload = json.loads(emitted.read_text(encoding="utf-8"))
        assert payload["domain"] == "VES"
        assert len(payload["points"]) == 5
        spec = load_case("ves-protocol", emitted)
        assert spec.case.active_observation_count() == 5

    def test_ves_case_for_unselected_protocol_is_a_usage_error(self, tmp_path: Path) -> None:
        ves_path = _write(tmp_path)
        manifest = _manifest(tmp_path, ves_path)
        with pytest.raises(BenchmarkCaseFileError, match="not selected"):
            execute_manifest(
                manifest,
                ves_cases=(VESCaseRequest("other-protocol", str(ves_path)),),
            )

    def test_ves_conversion_for_a_non_ves_protocol_is_refused(self, tmp_path: Path) -> None:
        ves_path = _write(tmp_path)
        manifest = _manifest(tmp_path, ves_path, domain="2D ERT")
        with pytest.raises(BenchmarkCaseFileError, match="can only build a VES case"):
            execute_manifest(
                manifest,
                ves_cases=(VESCaseRequest("ert-protocol", str(ves_path)),),
            )

    def test_case_file_and_ves_conversion_cannot_both_apply(self, tmp_path: Path) -> None:
        ves_path = _write(tmp_path)
        manifest = _manifest(tmp_path, ves_path)
        converted = build_ves_benchmark_case(ves_path, "ves-protocol")
        case = build_case("ves-protocol", converted.to_payload())
        with pytest.raises(BenchmarkCaseFileError, match="both a case file and a VES"):
            execute_manifest(
                manifest,
                cases=(case,),
                ves_cases=(VESCaseRequest("ves-protocol", str(ves_path)),),
            )

    def test_conversion_failure_reports_a_usage_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ves_path = _write(tmp_path, "AB/2,MN/2,resistance\n2,0.5,broken\n")
        manifest = _manifest(tmp_path, ves_path)
        code = main(
            [
                "--manifest",
                str(manifest),
                "--case-from-ves",
                f"ves-protocol={ves_path}",
            ]
        )
        assert code == EXIT_USAGE
        message = capsys.readouterr().err
        assert "cannot convert" in message
        assert "line 2" in message

    def test_emit_without_conversion_is_a_usage_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ves_path = _write(tmp_path)
        manifest = _manifest(tmp_path, ves_path)
        code = main(
            ["--manifest", str(manifest), "--emit-case", f"ves-protocol={tmp_path / 'x.json'}"]
        )
        assert code == EXIT_USAGE
        assert "no --case-from-dat conversion" in capsys.readouterr().err
