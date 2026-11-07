"""Scientific qualification fixtures, registries, and performance baselines."""

from nix_ert.qualification.benchmark import (
    BenchmarkAdmission,
    BenchmarkAdmissionError,
    BenchmarkExecutionError,
    BenchmarkProvenance,
    BenchmarkRun,
    admit_benchmark_candidate,
    run_benchmark,
)
from nix_ert.qualification.performance import PerformanceCase, PerformanceScale
from nix_ert.qualification.m21 import (
    EvidenceClass,
    QualificationOutcome,
    M21QualificationReport,
    run_m21_internal_qualification,
)
from nix_ert.qualification.m22 import (
    ConvergenceContract,
    FinalModelStatus,
    M22QualificationReport,
    run_m22_qualification,
    run_m22_studies,
)
from nix_ert.qualification.release import (
    PROCEDURE_VERSION,
    QualificationManifest,
    ReleaseQualificationResult,
    build_manifest,
)

__all__ = [
    "BenchmarkAdmission",
    "BenchmarkAdmissionError",
    "BenchmarkExecutionError",
    "BenchmarkProvenance",
    "BenchmarkRun",
    "admit_benchmark_candidate",
    "run_benchmark",
    "PerformanceCase",
    "PerformanceScale",
    "PROCEDURE_VERSION",
    "QualificationManifest",
    "ReleaseQualificationResult",
    "build_manifest",
    "EvidenceClass",
    "QualificationOutcome",
    "M21QualificationReport",
    "run_m21_internal_qualification",
    "ConvergenceContract",
    "FinalModelStatus",
    "M22QualificationReport",
    "run_m22_qualification",
    "run_m22_studies",
]
