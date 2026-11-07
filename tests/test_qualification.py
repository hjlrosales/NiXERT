"""M17 qualification fixture and performance tests."""

from __future__ import annotations

import unittest

import numpy as np

from nix_ert.ert.inversion2d import forward_apparent_resistivity
from nix_ert.ert.inversion3d import forward_apparent_resistivity as forward_3d
from nix_ert.qualification.datasets import ert2d_qualification, ert3d_qualification, qualification_specs, ves_qualification
from nix_ert.qualification.performance import declared_performance_cases, format_measurement, measure
from nix_ert.ves.engine import LayeredEarthModel, invert_ves, layered_apparent_resistivity


class QualificationTests(unittest.TestCase):
    def test_specs_are_explicitly_internal_and_complete(self) -> None:
        specs = qualification_specs()
        self.assertEqual({spec.domain for spec in specs}, {"VES", "2D ERT", "3D ERT"})
        for spec in specs:
            self.assertIn("Internal", spec.source)
            self.assertTrue(spec.expected_behavior)
            self.assertTrue(spec.tolerance)
            self.assertTrue(spec.limitations)

    def test_clean_and_noisy_ves_fixtures_are_finite(self) -> None:
        fixture = ves_qualification()
        clean = [layered_apparent_resistivity(fixture.model, point.ab2, point.mn2) for point in fixture.clean_points]
        noisy = [point.apparent_resistivity for point in fixture.noisy_points]
        self.assertTrue(np.all(np.isfinite(clean)))
        inversion = invert_ves(fixture.noisy_points, LayeredEarthModel((80.0, 30.0, 180.0), (4.0, 10.0)), max_nfev=20)
        self.assertTrue(np.isfinite(inversion.rms_log10))
        self.assertTrue(np.all(np.isfinite(inversion.predicted)))

    def test_clean_and_noisy_2d_fixture_has_unit_homogeneous_reference(self) -> None:
        fixture = ert2d_qualification()
        homogeneous = forward_apparent_resistivity(
            np.ones_like(fixture.true_model), fixture.mesh, fixture.observations
        )
        self.assertTrue(np.all(np.isfinite(homogeneous)))
        self.assertTrue(np.all(np.asarray(homogeneous) > 0))
        self.assertEqual(len(fixture.noisy_observations), len(fixture.observations))
        from nix_ert.ert.inversion2d import invert_ert
        noisy_result = invert_ert(fixture.noisy_observations, fixture.mesh, 1.0, max_iterations=1)
        self.assertTrue(np.isfinite(noisy_result.rms_log10))

    def test_clean_and_noisy_3d_fixture_is_finite(self) -> None:
        fixture = ert3d_qualification()
        response = forward_3d(fixture.true_model, fixture.mesh, fixture.observations, fixture.electrodes)
        self.assertTrue(np.all(np.isfinite(response)))
        self.assertEqual(len(fixture.noisy_observations), len(fixture.observations))
        from nix_ert.ert.inversion3d import invert_ert3d
        _, _, history, _ = invert_ert3d(fixture.noisy_observations, fixture.mesh, fixture.electrodes, 1.0, max_iterations=1)
        self.assertTrue(history)
        self.assertTrue(np.all(np.isfinite(history)))

    def test_declared_performance_scales_are_not_overclaimed(self) -> None:
        cases = declared_performance_cases()
        self.assertEqual({case.scale.value for case in cases}, {"small", "medium", "large", "stress-scale"})
        self.assertEqual(sum(case.status == "measured" for case in cases), 1)
        self.assertTrue(all(case.observations > 0 and case.mesh_cells > 0 for case in cases))

        measurement = measure("qualification-noop", lambda: sum(range(100)), mesh_cells=1)
        self.assertGreaterEqual(measurement.seconds, 0.0)
        self.assertGreater(measurement.peak_python_bytes, 0)
        self.assertIn("qualification-noop", format_measurement(measurement))


if __name__ == "__main__":
    unittest.main()
