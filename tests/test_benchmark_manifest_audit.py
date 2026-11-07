"""Negative-path audit: no admission finding can be bypassed by a crafted manifest.

Each case starts from an otherwise admissible manifest and removes, weakens, or
re-spells exactly one item of required evidence. The test then asserts that

* the manifest is either rejected while loading, or
* admission is refused with the specific finding code, and
* no comparison is recorded and no engine is executed.

What this audit *cannot* prove is honesty: a manifest that asserts a licence,
provenance, and reference values which the operator fabricated is structurally
admissible. Admission enforces that the evidence is present, well-typed,
internally consistent, and not produced by NiX ERT; it cannot authenticate a
vendor's signature. That limitation is recorded in `docs/benchmark_execution.md`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from nix_ert.qualification import benchmark as bench
from nix_ert.qualification.datasets import ves_qualification
from nix_ert.qualification.registry import QualificationRegistry

FIXTURE_BYTES = b"audit-only manifest fixture; not external evidence\n"
JUSTIFICATION = "Audit-only bound; not a qualified tolerance."
REFERENCE_RESPONSE = [
    round(point.apparent_resistivity, 6) for point in ves_qualification().clean_points
]


def _baseline(tmp_path: Path) -> dict[str, object]:
    path = tmp_path / "candidate.dat"
    path.write_bytes(FIXTURE_BYTES)
    return {
        "datasets": [
            {
                "dataset_id": "audit-dataset",
                "classification": "user-supplied",
                "source": "Audit-only fixture; not external evidence.",
                "license_status": "permission confirmed",
                "permission_note": "Audit-only.",
                "acquisition_information": {
                    "sha256": hashlib.sha256(FIXTURE_BYTES).hexdigest(),
                    "array": "synthetic",
                },
                "electrode_configuration": "Wenner-Schlumberger",
                "electrode_spacing": 5.0,
                "coordinate_context": {"crs": "local"},
                "qualification_purpose": "Audit the admission path in a test only.",
                "data_path": str(path),
            }
        ],
        "protocols": [
            {
                "protocol_id": "audit-protocol",
                "dataset_id": "audit-dataset",
                "preprocessing_rules": ["none (frozen)"],
                "qc_rules": ["none (frozen)"],
                "inversion_parameters": {
                    "domain": "VES",
                    "max_nfev": 10,
                    "initial_resistivities": [40.0, 10.0, 200.0],
                    "initial_thicknesses": [4.0, 10.0],
                },
                "mesh_assumptions": {"layers": 3},
                "stopping_criteria": {"max_nfev": 10},
                "expected_reference_result": {
                    "producer": "Independent audit reference implementation",
                    "provenance": "Audit-only synthetic stand-in.",
                    "semantics": {
                        "model_space": "apparent resistivity",
                        "resistivity_unit": "ohm.m",
                        "depth_convention": "depth positive down",
                    },
                    "response": REFERENCE_RESPONSE,
                },
                "comparison_metrics": ["rmse", "log10_rmse"],
                "acceptable_tolerance": {
                    "rmse": {"max_absolute": 1e6, "justification": JUSTIFICATION},
                    "log10_rmse": {"max_absolute": 1e6, "justification": JUSTIFICATION},
                },
            }
        ],
        "comparisons": [],
    }


def _refusal(payload: dict[str, object]) -> tuple[str, ...]:
    """Return the refusal reason(s); manifest-load rejection counts as a refusal."""
    try:
        registry = QualificationRegistry.from_json(json.dumps(payload))
    except ValueError:
        return ("manifest_rejected",)
    return bench.admit_benchmark_candidate(registry, "audit-protocol").codes


def _mutate(payload: dict[str, object], mutate) -> dict[str, object]:
    mutate(payload)
    return payload


def _protocol(payload: dict[str, object]) -> dict[str, object]:
    return payload["protocols"][0]  # type: ignore[index]


def _without(key_path: list[str]) -> object:
    def mutate(payload: dict[str, object]) -> None:
        target: dict[str, object] = payload
        for key in key_path[:-1]:
            target = target[key]  # type: ignore[assignment]
        target.pop(key_path[-1], None)

    return mutate


def _set(key_path: list[str], value: object) -> object:
    def mutate(payload: dict[str, object]) -> None:
        target: dict[str, object] = payload
        for key in key_path[:-1]:
            target = target[key]  # type: ignore[assignment]
        target[key_path[-1]] = value

    return mutate


class TestBaselineIsAdmissible:
    def test_audit_baseline_is_admitted(self, tmp_path: Path) -> None:
        """The audit is meaningful only if the unmutated manifest is admissible."""
        assert _refusal(_baseline(tmp_path)) == ()


class TestEvidenceCannotBeRemoved:
    @pytest.mark.parametrize(
        ("mutation", "expected"),
        [
            # dataset eligibility; an unpermitted dataset can neither define nor be
            # paired with an independent reference result, so it is refused at load.
            (_set(["datasets", 0, "classification"], "internal synthetic"), "manifest_rejected"),
            (_set(["datasets", 0, "license_status"], "permission pending"), "manifest_rejected"),
            (_set(["datasets", 0, "license_status"], "not applicable"), "manifest_rejected"),
            (_set(["datasets", 0, "license_status"], "unknown"), "manifest_rejected"),
            # bytes and provenance
            (_without(["datasets", 0, "data_path"]), "dataset_bytes_missing"),
            (_set(["datasets", 0, "data_path"], "/nonexistent/audit.dat"), "dataset_bytes_missing"),
            (_without(["datasets", 0, "acquisition_information"]), "dataset_hash_unrecorded"),
            (_set(["datasets", 0, "acquisition_information", "sha256"], " " * 64), "dataset_hash_unrecorded"),
            (_set(["datasets", 0, "acquisition_information", "sha256"], "a" * 64), "dataset_hash_mismatch"),
            (_set(["datasets", 0, "acquisition_information"], {}), "dataset_hash_unrecorded"),
            # acquisition and geometry metadata
            (_set(["datasets", 0, "electrode_configuration"], ""), "dataset_geometry_missing"),
            (_set(["datasets", 0, "electrode_spacing"], None), "dataset_geometry_missing"),
            (_set(["datasets", 0, "coordinate_context"], {}), "dataset_geometry_missing"),
            # reference result
            (_set(["protocols", 0, "expected_reference_result"], {}), "reference_result_missing"),
            (_without(["protocols", 0, "expected_reference_result", "producer"]), "reference_provenance_missing"),
            (_set(["protocols", 0, "expected_reference_result", "producer"], "   "), "reference_provenance_missing"),
            (_without(["protocols", 0, "expected_reference_result", "provenance"]), "reference_provenance_missing"),
            (_without(["protocols", 0, "expected_reference_result", "semantics"]), "reference_semantics_missing"),
            (_set(["protocols", 0, "expected_reference_result", "semantics"], {"model_space": "apparent resistivity"}), "reference_semantics_missing"),
            (_set(["protocols", 0, "expected_reference_result", "semantics"], {"model_space": "apparent resistivity", "resistivity_unit": "ohm.m", "depth_convention": 3}), "reference_semantics_missing"),
            (_without(["protocols", 0, "expected_reference_result", "response"]), "reference_response_missing"),
            (_set(["protocols", 0, "expected_reference_result", "response"], []), "reference_response_missing"),
            (_set(["protocols", 0, "expected_reference_result", "response"], ["1.0"] * 8), "reference_response_missing"),
            (_set(["protocols", 0, "expected_reference_result", "response"], [0.0] * 8), "reference_response_missing"),
            # tolerance evidence
            (_set(["protocols", 0, "acceptable_tolerance"], {}), "tolerance_missing"),
            (_set(["protocols", 0, "acceptable_tolerance"], {"rmse": {"max_absolute": 1e6, "justification": JUSTIFICATION}}), "tolerance_missing"),
            (_set(["protocols", 0, "acceptable_tolerance", "rmse"], {"justification": JUSTIFICATION}), "tolerance_missing"),
            (_set(["protocols", 0, "acceptable_tolerance", "rmse"], {"max_absolute": -1.0, "justification": JUSTIFICATION}), "tolerance_missing"),
            (_set(["protocols", 0, "acceptable_tolerance", "rmse"], {"max_absolute": True, "justification": JUSTIFICATION}), "tolerance_missing"),
            (_set(["protocols", 0, "acceptable_tolerance", "rmse"], {"max_absolute": float("nan"), "justification": JUSTIFICATION}), "tolerance_missing"),
            (_set(["protocols", 0, "acceptable_tolerance", "rmse"], {"max_absolute": "1e6", "justification": JUSTIFICATION}), "tolerance_missing"),
            (_set(["protocols", 0, "acceptable_tolerance", "rmse"], {"max_absolute": 1e6}), "tolerance_justification_missing"),
            (_set(["protocols", 0, "acceptable_tolerance", "rmse"], {"max_absolute": 1e6, "justification": "   "}), "tolerance_justification_missing"),
            # frozen parameters
            (_without(["protocols", 0, "inversion_parameters", "max_nfev"]), "protocol_parameter_missing"),
            (_set(["protocols", 0, "inversion_parameters", "max_nfev"], "10"), "protocol_parameter_invalid"),
            (_set(["protocols", 0, "inversion_parameters", "max_nfev"], 0), "protocol_parameter_invalid"),
            (_set(["protocols", 0, "inversion_parameters", "initial_thicknesses"], [4.0]), "protocol_parameter_invalid"),
            (_set(["protocols", 0, "inversion_parameters", "initial_resistivities"], [40.0, -1.0, 200.0]), "protocol_parameter_invalid"),
            (_set(["protocols", 0, "inversion_parameters", "domain"], "VES "), "domain_unsupported"),
            (_without(["protocols", 0, "inversion_parameters", "domain"]), "domain_unsupported"),
            (_set(["protocols", 0, "stopping_criteria"], {"max_nfev": 99}), "stopping_criteria_mismatch"),
            # unsupported measurement
            (_set(["protocols", 0, "comparison_metrics"], ["rmse", "geological_certainty"]), "metric_unsupported"),
        ],
    )
    def test_missing_evidence_is_always_refused(
        self, tmp_path: Path, mutation, expected: str
    ) -> None:
        codes = _refusal(_mutate(_baseline(tmp_path), mutation))
        assert expected in codes, codes


class TestSelfReferenceCannotBeDisguised:
    @pytest.mark.parametrize(
        "producer",
        [
            "NiX ERT",
            "nix-ert",
            "NIX_ERT",
            "NiX\tERT",
            "NiX  ERT",
            "nixert",
            "NiX ERT independent replication",
            "Generated by NiX-ERT v0.1.0",
        ],
    )
    def test_self_produced_reference_is_refused(self, tmp_path: Path, producer: str) -> None:
        payload = _mutate(
            _baseline(tmp_path),
            _set(["protocols", 0, "expected_reference_result", "producer"], producer),
        )
        assert "reference_produced_by_nix_ert" in _refusal(payload)

    def test_unrelated_producer_is_accepted_by_the_self_reference_check(
        self, tmp_path: Path
    ) -> None:
        payload = _mutate(
            _baseline(tmp_path),
            _set(
                ["protocols", 0, "expected_reference_result", "producer"],
                "Independent third-party reference implementation",
            ),
        )
        assert _refusal(payload) == ()


class TestNoCompensation:
    """Extra or re-spelled material cannot satisfy a missing item."""

    def test_dataset_level_reference_does_not_replace_the_protocol_reference(
        self, tmp_path: Path
    ) -> None:
        payload = _baseline(tmp_path)
        payload["datasets"][0]["expected_reference_result"] = {  # type: ignore[index]
            "producer": "Independent audit reference implementation",
            "provenance": "Audit-only.",
            "semantics": {
                "model_space": "apparent resistivity",
                "resistivity_unit": "ohm.m",
                "depth_convention": "depth positive down",
            },
            "response": REFERENCE_RESPONSE,
        }
        payload["protocols"][0]["expected_reference_result"] = {}  # type: ignore[index]
        assert "reference_result_missing" in _refusal(payload)

    def test_extra_declared_fields_cannot_compensate(self, tmp_path: Path) -> None:
        payload = _mutate(
            _baseline(tmp_path),
            _set(["protocols", 0, "acceptable_tolerance", "rmse"], {"max_absolute": 1e6}),
        )
        _protocol(payload)["verified"] = True
        _protocol(payload)["tolerance_justification"] = JUSTIFICATION
        _protocol(payload)["independent"] = True
        assert "tolerance_justification_missing" in _refusal(payload)

    def test_tolerance_under_another_metric_name_cannot_compensate(
        self, tmp_path: Path
    ) -> None:
        payload = _mutate(
            _baseline(tmp_path),
            _set(
                ["protocols", 0, "acceptable_tolerance"],
                {"root_mean_square": {"max_absolute": 1e6, "justification": JUSTIFICATION}},
            ),
        )
        assert "tolerance_missing" in _refusal(payload)

    def test_duplicated_dataset_identity_is_rejected(self, tmp_path: Path) -> None:
        payload = _baseline(tmp_path)
        payload["datasets"].append(  # type: ignore[union-attr]
            json.loads(json.dumps(payload["datasets"][0]))  # type: ignore[index]
        )
        assert _refusal(payload) == ("manifest_rejected",)

    def test_protocol_cannot_reference_an_unregistered_dataset(self, tmp_path: Path) -> None:
        payload = _mutate(
            _baseline(tmp_path),
            _set(["protocols", 0, "dataset_id"], "some-other-dataset"),
        )
        assert _refusal(payload) == ("manifest_rejected",)

    def test_forged_validation_comparison_is_rejected_at_load(self, tmp_path: Path) -> None:
        payload = _baseline(tmp_path)
        payload["comparisons"] = [  # type: ignore[index]
            {
                "comparison_id": "forged",
                "protocol_id": "audit-protocol",
                "dataset_id": "audit-dataset",
                "status": "VALIDATED",
                "metrics": {},
                "convergence": {},
                "notes": "Forged validation without evidence.",
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        ]
        assert _refusal(payload) == ("manifest_rejected",)

    def test_missing_reference_result_cannot_be_replaced_by_a_dataset_digest(
        self, tmp_path: Path
    ) -> None:
        payload = _mutate(
            _baseline(tmp_path),
            _set(["protocols", 0, "expected_reference_result"], {"sha256": "a" * 64}),
        )
        codes = _refusal(payload)
        assert "reference_provenance_missing" in codes
        assert "reference_response_missing" in codes


class TestNoExecutionWithoutAdmission:
    def test_refused_manifest_never_reaches_the_engines(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Loads cleanly, but the bytes no longer match the recorded digest.
        payload = _mutate(
            _baseline(tmp_path),
            _set(["datasets", 0, "acquisition_information", "sha256"], "a" * 64),
        )
        registry = QualificationRegistry.from_json(json.dumps(payload))

        def explode(*_args, **_kwargs):
            raise AssertionError("an inadmissible protocol must never be executed")

        monkeypatch.setattr(bench, "_execute", explode)
        with pytest.raises(bench.BenchmarkAdmissionError):
            bench.run_benchmark(
                registry,
                "audit-protocol",
                bench.VESBenchmarkCase(points=ves_qualification().noisy_points),
            )
        assert registry.comparisons == []

    def test_repository_manifest_cannot_be_admitted_at_all(self) -> None:
        from nix_ert.qualification.registry import BenchmarkProtocol, internal_qualification_registry

        registry = internal_qualification_registry()
        for dataset_id in ("ves-layered-internal-v1", "ert-2d-anomaly-internal-v1", "ert-3d-anomaly-internal-v1"):
            protocol_id = f"audit-{dataset_id}"
            registry.add_protocol(
                BenchmarkProtocol(
                    protocol_id=protocol_id,
                    dataset_id=dataset_id,
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
            codes = bench.admit_benchmark_candidate(registry, protocol_id).codes
            assert "dataset_not_independent" in codes, dataset_id
        assert registry.comparisons == []
