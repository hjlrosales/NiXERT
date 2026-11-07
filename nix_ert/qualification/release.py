"""Deterministic M19 reproducibility and release-qualification contracts.

This module records evidence; it does not declare geological or production
fitness automatically. Runtime measurements are captured as supplied facts and
are never converted into arbitrary pass/fail thresholds.
"""

from __future__ import annotations

import hashlib
import json
import platform
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from nix_ert import __version__


PROCEDURE_VERSION = "m19-release-qualification-v1"


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class QualificationManifest:
    """Machine-readable identity of one reproducible qualification run."""

    manifest_id: str
    dataset: Mapping[str, Any]
    project: Mapping[str, Any]
    processing: Mapping[str, Any] = field(default_factory=dict)
    inversion: Mapping[str, Any] = field(default_factory=dict)
    configuration: Mapping[str, Any] = field(default_factory=dict)
    expected_outputs: Mapping[str, Any] = field(default_factory=dict)
    procedure_version: str = PROCEDURE_VERSION
    software_version: str = __version__

    def __post_init__(self) -> None:
        if not self.manifest_id.strip():
            raise ValueError("manifest_id is required")
        if not self.dataset:
            raise ValueError("dataset identity is required")
        if not self.project:
            raise ValueError("project/survey identity is required")
        if not self.procedure_version.strip() or not self.software_version.strip():
            raise ValueError("procedure and software versions are required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_id": self.manifest_id,
            "procedure_version": self.procedure_version,
            "software_version": self.software_version,
            "dataset": dict(self.dataset),
            "project": dict(self.project),
            "processing": dict(self.processing),
            "inversion": dict(self.inversion),
            "configuration": dict(self.configuration),
            "expected_outputs": dict(self.expected_outputs),
        }

    @property
    def manifest_sha256(self) -> str:
        return _digest(self.to_dict())

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=2, ensure_ascii=True, default=str) + "\n"

    def write_json(self, path: str) -> None:
        from pathlib import Path
        Path(path).write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "QualificationManifest":
        try:
            return cls(
                manifest_id=str(payload["manifest_id"]),
                dataset=dict(payload["dataset"]),
                project=dict(payload["project"]),
                processing=dict(payload.get("processing", {})),
                inversion=dict(payload.get("inversion", {})),
                configuration=dict(payload.get("configuration", {})),
                expected_outputs=dict(payload.get("expected_outputs", {})),
                procedure_version=str(payload.get("procedure_version", PROCEDURE_VERSION)),
                software_version=str(payload.get("software_version", __version__)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid qualification manifest") from exc


@dataclass(frozen=True)
class ReleaseQualificationResult:
    """Evidence record for an M19 release-qualification execution."""

    assessment: str
    environment: Mapping[str, Any]
    manifests: tuple[QualificationManifest, ...]
    test_counts: Mapping[str, int]
    reproducibility: Mapping[str, Any]
    performance: tuple[Mapping[str, Any], ...]
    cancellation_and_failure: Mapping[str, Any]
    limitations: tuple[str, ...]
    blocked_capabilities: tuple[str, ...]
    generated_at: str = ""

    def __post_init__(self) -> None:
        if self.assessment not in {"QUALIFIED_FOR_SUPPORTED_OFFLINE_WORKFLOW", "NOT_QUALIFIED"}:
            raise ValueError("unsupported release assessment")
        if not self.manifests:
            raise ValueError("at least one qualification manifest is required")
        if any(value < 0 for value in self.test_counts.values()):
            raise ValueError("test counts cannot be negative")

    @staticmethod
    def environment_snapshot() -> dict[str, str]:
        """Return non-secret environment facts used to interpret measurements."""
        return {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        }

    def to_dict(self, *, include_timestamp: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "assessment": self.assessment,
            "environment": dict(self.environment),
            "manifests": [manifest.to_dict() | {"manifest_sha256": manifest.manifest_sha256} for manifest in self.manifests],
            "test_counts": dict(self.test_counts),
            "reproducibility": dict(self.reproducibility),
            "performance": [dict(item) for item in self.performance],
            "cancellation_and_failure": dict(self.cancellation_and_failure),
            "limitations": list(self.limitations),
            "blocked_capabilities": list(self.blocked_capabilities),
        }
        if include_timestamp and self.generated_at:
            payload["generated_at"] = self.generated_at
        return payload

    def to_json(self, *, include_timestamp: bool = True) -> str:
        return json.dumps(self.to_dict(include_timestamp=include_timestamp), sort_keys=True, indent=2, ensure_ascii=True, default=str) + "\n"

    def write_json(self, path: str, *, include_timestamp: bool = True) -> None:
        from pathlib import Path
        Path(path).write_text(self.to_json(include_timestamp=include_timestamp), encoding="utf-8")

    def write_markdown(self, path: str) -> None:
        from pathlib import Path
        Path(path).write_text(self.to_markdown(), encoding="utf-8")

    def to_markdown(self) -> str:
        lines = [
            "# M19 release qualification result",
            "",
            f"**Assessment:** `{self.assessment}`",
            f"**Procedure:** `{PROCEDURE_VERSION}`",
            "",
            "## Environment",
            "",
        ]
        lines.extend(f"- **{key}:** {value}" for key, value in self.environment.items())
        lines.extend(["", "## Qualification manifests", ""])
        for manifest in self.manifests:
            lines.append(f"- `{manifest.manifest_id}` — source hash: `{manifest.dataset.get('source_sha256', 'not supplied')}`; manifest hash: `{manifest.manifest_sha256}`")
        lines.extend(["", "## Test counts", ""])
        lines.extend(f"- **{key}:** {value}" for key, value in self.test_counts.items())
        lines.extend(["", "## Reproducibility", ""])
        lines.extend(f"- **{key}:** {value}" for key, value in self.reproducibility.items())
        lines.extend(["", "## Performance measurements", ""])
        if self.performance:
            for item in self.performance:
                lines.append(f"- `{item.get('name', 'unnamed')}`: {item.get('seconds', 'not measured')} s; peak Python bytes: {item.get('peak_python_bytes', 'not measured')}; metadata: `{item.get('metadata', {})}`")
        else:
            lines.append("- No performance measurement was recorded.")
        lines.extend(["", "## Cancellation and failure safety", ""])
        lines.extend(f"- **{key}:** {value}" for key, value in self.cancellation_and_failure.items())
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in self.limitations)
        lines.extend(["", "## Blocked capabilities", ""])
        lines.extend(f"- {item}" for item in self.blocked_capabilities)
        return "\n".join(lines) + "\n"


def build_manifest(
    manifest_id: str,
    *,
    dataset_id: str,
    source_sha256: str | None,
    project_id: str,
    survey_id: str,
    processing: Mapping[str, Any] | None = None,
    inversion: Mapping[str, Any] | None = None,
    configuration: Mapping[str, Any] | None = None,
    expected_outputs: Mapping[str, Any] | None = None,
) -> QualificationManifest:
    """Build a manifest with explicit absence rather than fabricated hashes."""
    if source_sha256 is not None and (len(source_sha256) != 64 or any(char not in "0123456789abcdef" for char in source_sha256.lower())):
        raise ValueError("source_sha256 must be a hexadecimal SHA-256 value")
    return QualificationManifest(
        manifest_id=manifest_id,
        dataset={"dataset_id": dataset_id, "source_sha256": source_sha256, "classification": "internal synthetic"},
        project={"project_id": project_id, "survey_id": survey_id},
        processing=processing or {},
        inversion=inversion or {},
        configuration=configuration or {},
        expected_outputs=expected_outputs or {},
    )


__all__ = [
    "PROCEDURE_VERSION",
    "QualificationManifest",
    "ReleaseQualificationResult",
    "build_manifest",
]
