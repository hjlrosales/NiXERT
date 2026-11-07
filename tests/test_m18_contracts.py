"""M18 operation safety and qualification registry tests."""

from __future__ import annotations

import threading
import time
import unittest

from nix_ert.app.operations import OperationCancelled, OperationExecutor
from nix_ert.qualification.registry import (
    BenchmarkComparison,
    BenchmarkProtocol,
    ComparisonStatus,
    DatasetClassification,
    LicenseStatus,
    QualificationDataset,
    QualificationRegistry,
    internal_qualification_registry,
)


class OperationSafetyTests(unittest.TestCase):
    def test_cancelled_operation_does_not_run_commit_side_effect(self) -> None:
        executor = OperationExecutor()
        started = threading.Event()
        release = threading.Event()
        committed: list[bool] = []
        try:
            def operation(token):
                started.set()
                release.wait(timeout=2)
                return "detached result"

            handle = executor.submit("cancel test", operation)
            self.assertTrue(started.wait(timeout=2))
            handle.cancel()
            release.set()
            with self.assertRaises(OperationCancelled):
                handle.future.result(timeout=2)
            self.assertEqual(committed, [])
            self.assertEqual(handle.snapshot().state, "cancelled")
        finally:
            executor.shutdown()

    def test_completed_operation_reports_progress_and_result(self) -> None:
        executor = OperationExecutor()
        try:
            handle = executor.submit(
                "progress test",
                lambda token: (token.update(progress=0.5, detail="halfway", iteration=1), 7)[1],
            )
            self.assertEqual(handle.future.result(timeout=2), 7)
            snapshot = handle.snapshot()
            self.assertEqual(snapshot.state, "complete")
            self.assertEqual(snapshot.iteration, 1)
        finally:
            executor.shutdown()


class QualificationRegistryTests(unittest.TestCase):
    def test_internal_registry_cannot_be_presented_as_external_benchmark(self) -> None:
        registry = internal_qualification_registry()
        dataset = next(iter(registry.datasets.values()))
        self.assertFalse(dataset.independent_benchmark_eligible)
        protocol = BenchmarkProtocol(
            "internal-protocol", dataset.dataset_id, (), (), {}, {},
            {"max_iterations": 1}, {}, ("residual",), {},
        )
        with self.assertRaises(ValueError):
            registry.add_protocol(protocol.__class__(
                protocol.protocol_id, protocol.dataset_id, protocol.preprocessing_rules,
                protocol.qc_rules, protocol.inversion_parameters, protocol.mesh_assumptions,
                protocol.stopping_criteria, {"reference": "invented"},
                protocol.comparison_metrics, protocol.acceptable_tolerance,
            ))

    def test_manifest_round_trip_preserves_comparison_status(self) -> None:
        registry = QualificationRegistry()
        dataset = QualificationDataset(
            "published-example", DatasetClassification.PUBLISHED_REFERENCE,
            "User-supplied citation; bytes not bundled", LicenseStatus.PERMISSION_CONFIRMED,
            permission_note="Permission recorded outside repository",
            qualification_purpose="Future independent comparison",
        )
        registry.add_dataset(dataset)
        protocol = BenchmarkProtocol(
            "protocol-1", dataset.dataset_id,
            ("Use supplied values without filtering",), ("Apply documented QC only",),
            {"max_iterations": 3}, {"domain": "documented by fixture"},
            {"max_iterations": 3}, {"reference": "not bundled"},
            ("apparent-resistivity error", "residual",), {"status": "predefined"},
        )
        registry.add_protocol(protocol)
        comparison = BenchmarkComparison.create(
            protocol, ComparisonStatus.NOT_VALIDATED, {"reason": "No bytes available"},
            {"converged": False}, "Reference data are unavailable; comparison was not run.",
        )
        registry.add_comparison(comparison)
        restored = QualificationRegistry.from_json(registry.to_json())
        self.assertEqual(restored.datasets[dataset.dataset_id].classification, DatasetClassification.PUBLISHED_REFERENCE)
        self.assertEqual(restored.comparisons[0].status, ComparisonStatus.NOT_VALIDATED)


if __name__ == "__main__":
    unittest.main()
