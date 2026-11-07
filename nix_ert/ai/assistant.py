"""Deterministic advisory analysis over existing NiX ERT project artifacts.

This first AI increment is intentionally local and provider-neutral. It does
not call a network model and it does not mutate project state while answering
questions. All findings are framed as observations or possible interpretations,
not geological conclusions.
"""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from nix_ert.data.measurements import Measurement, MeasurementStatus
from nix_ert.data.models import ProjectMetadata, Survey
from nix_ert.data.project import ProjectStore
from nix_ert.processing.qc import QCFlag, QCStatistics, QCEngine
from nix_ert.processing.versions import VersionRecord, VersionStore
from nix_ert.reports.generator import ReportData
from nix_ert.ves.engine import LayeredEarthModel, VESPoint, VESInversionResult, ves_apparent_resistivity
from nix_ert.visualization.model2d import ResistivitySection
from nix_ert.visualization.volume3d import ResistivityVolume


@dataclass(frozen=True)
class Finding:
    """A traceable advisory observation."""

    category: str
    title: str
    detail: str
    references: tuple[str, ...] = ()
    advisory: bool = True


@dataclass(frozen=True)
class AssistantResponse:
    """Structured response suitable for a UI, report draft, or API client."""

    answer: str
    findings: tuple[Finding, ...] = ()
    limitations: tuple[str, ...] = ()
    suggested_actions: tuple["ActionProposal", ...] = ()


@dataclass(frozen=True)
class ActionProposal:
    """A mutation proposal; creating it does not execute it."""

    id: str
    action: str
    survey_id: str
    row_numbers: tuple[int, ...]
    explanation: str
    reason: str
    requires_approval: bool = True


@dataclass
class ProjectContext:
    """Read-only snapshot of structured project artifacts used by the assistant."""

    metadata: ProjectMetadata | None = None
    surveys: tuple[Survey, ...] = ()
    measurements: dict[str, tuple[Measurement, ...]] = field(default_factory=dict)
    qc_flags: dict[str, tuple[QCFlag, ...]] = field(default_factory=dict)
    qc_statistics: dict[str, QCStatistics] = field(default_factory=dict)
    versions: tuple[VersionRecord, ...] = ()
    report_data: ReportData | None = None
    gis_summary: Mapping[str, object] = field(default_factory=dict)

    @classmethod
    def from_store(cls, store: ProjectStore) -> "ProjectContext":
        """Build a snapshot from the existing SQLite project without changing raw data."""
        surveys = tuple(store.list_surveys())
        engine = QCEngine(store)
        measurements = {survey.id: tuple(store.list_measurements(survey.id)) for survey in surveys}
        flags = {survey.id: engine.inspect(survey.id) for survey in surveys}
        statistics = {survey.id: engine.statistics(survey.id) for survey in surveys}
        versions: tuple[VersionRecord, ...] = ()
        version_table = store.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'versions'"
        ).fetchone()
        if version_table is not None:
            version_store = VersionStore(store)
            versions = tuple(record for survey in surveys for record in version_store.list(survey.id))
        return cls(store.load_metadata(), surveys, measurements, flags, statistics, versions)


class AdvisoryAssistant:
    """Fail-safe local analysis service over a project snapshot.

    The service is intentionally read-only except for the explicit
    ``execute_proposal(..., approved=True)`` path. It never deletes rows,
    changes raw files, changes model parameters, or writes inversion results.
    """

    DISCLAIMER = "Advisory observation only; this does not establish geological certainty."
    LIMITATIONS = (
        "Findings are deterministic data observations, not geological conclusions.",
        "QC and anomaly thresholds inherit the configured scientific services.",
        "No external language model or network service is used by this provider-neutral increment.",
    )

    def __init__(self, context: ProjectContext, qc_engine: QCEngine | None = None):
        self.context = context
        self.qc_engine = qc_engine
        self._pending: dict[str, ActionProposal] = {}
        self._explained: set[str] = set()

    def analyze_project(self) -> AssistantResponse:
        survey_count = len(self.context.surveys)
        measurement_count = sum(len(items) for items in self.context.measurements.values())
        flagged = sum(stats.flagged for stats in self.context.qc_statistics.values())
        excluded = sum(stats.excluded for stats in self.context.qc_statistics.values())
        name = self.context.metadata.name if self.context.metadata else "unnamed project"
        finding = Finding(
            "project", "Project inventory",
            f"{name} contains {survey_count} survey(s), {measurement_count} persisted measurement(s), "
            f"{flagged} flagged row(s), and {excluded} excluded row(s).",
            tuple(survey.id for survey in self.context.surveys),
        )
        return AssistantResponse(
            answer=f"Project analysis is available for {name}. {self.DISCLAIMER}",
            findings=(finding,), limitations=self.LIMITATIONS,
        )

    def suspicious_measurements(self, survey_id: str, limit: int = 20) -> AssistantResponse:
        self._require_survey(survey_id)
        if limit < 1:
            raise ValueError("limit must be positive")
        flags = self.context.qc_flags.get(survey_id, ())
        findings = tuple(
            Finding("qc", f"Suspicious measurement row {flag.row_number}", "; ".join(flag.reasons), (str(flag.row_number),))
            for flag in flags[:limit]
        )
        answer = f"Found {len(flags)} QC-flagged measurement(s); showing {len(findings)}. {self.DISCLAIMER}"
        return AssistantResponse(answer, findings, self.LIMITATIONS)

    def explain_qc(self, survey_id: str, row_number: int | None = None) -> AssistantResponse:
        self._require_survey(survey_id)
        flags = self.context.qc_flags.get(survey_id, ())
        selected = tuple(flag for flag in flags if row_number is None or flag.row_number == row_number)
        if row_number is not None and not any(item.row_number == row_number for item in self.context.measurements.get(survey_id, ())):
            raise KeyError(f"Unknown measurement row {row_number}")
        findings = tuple(
            Finding("qc", f"QC explanation for row {flag.row_number}", self._explain_reasons(flag.reasons), (str(flag.row_number),))
            for flag in selected
        )
        if not findings:
            answer = "No current deterministic QC flags match that request. This is not proof that the measurement is geologically or instrumentally valid."
        else:
            answer = f"Explained {len(findings)} QC finding(s). {self.DISCLAIMER}"
        return AssistantResponse(answer, findings, self.LIMITATIONS)

    def identify_resistivity_anomalies(self, survey_id: str, limit: int = 10) -> AssistantResponse:
        self._require_survey(survey_id)
        if limit < 1:
            raise ValueError("limit must be positive")
        items = [
            item for item in self.context.measurements.get(survey_id, ())
            if item.status != MeasurementStatus.EXCLUDED and item.apparent_resistivity is not None
            and math.isfinite(item.apparent_resistivity) and item.apparent_resistivity > 0
        ]
        if not items:
            return AssistantResponse("No active positive apparent-resistivity values are available for anomaly ranking.", limitations=self.LIMITATIONS)
        logs = [math.log10(item.apparent_resistivity) for item in items]
        median = sorted(logs)[len(logs) // 2] if len(logs) % 2 else (sorted(logs)[len(logs) // 2 - 1] + sorted(logs)[len(logs) // 2]) / 2
        ranked = sorted(items, key=lambda item: abs(math.log10(item.apparent_resistivity) - median), reverse=True)[:limit]
        findings = tuple(
            Finding(
                "resistivity anomaly", f"Row {item.row_number} is far from the dataset median",
                f"Apparent resistivity is {item.apparent_resistivity:g}; log10 distance from median is "
                f"{abs(math.log10(item.apparent_resistivity) - median):.3f}. This is a statistical anomaly candidate, not a geological interpretation.",
                (str(item.row_number),),
            )
            for item in ranked
        )
        return AssistantResponse(f"Ranked {len(findings)} possible resistivity anomaly candidate(s). {self.DISCLAIMER}", findings, self.LIMITATIONS)

    def compare_models(self, first_id: str, second_id: str) -> AssistantResponse:
        versions = {version.id: version for version in self.context.versions}
        first, second = versions.get(first_id), versions.get(second_id)
        if first is None or second is None:
            raise KeyError("both model/version IDs must exist")
        changed = sorted(set(first.parameters) | set(second.parameters))
        changed = [key for key in changed if first.parameters.get(key) != second.parameters.get(key)]
        findings = (
            Finding("model comparison", "Parameter differences", ", ".join(changed) if changed else "No parameter differences.", (first.id, second.id)),
            Finding("model comparison", "Snapshot comparison", "Snapshots are equal." if first.snapshot == second.snapshot else "Snapshots differ.", (first.id, second.id)),
        )
        return AssistantResponse(
            f"Compared {first.name} with {second.name}. The comparison is metadata/snapshot based and does not declare one model geologically superior. {self.DISCLAIMER}",
            findings, self.LIMITATIONS,
        )

    def inversion_summary(self, survey_id: str | None = None) -> AssistantResponse:
        versions = [version for version in self.context.versions if version.kind.lower() in {"model", "inversion"} and (survey_id is None or version.survey_id == survey_id)]
        findings = tuple(
            Finding("inversion", version.name, self._summarize_snapshot(version.snapshot), (version.id,))
            for version in versions
        )
        return AssistantResponse(
            f"Found {len(findings)} stored inversion/model version(s). Summaries report stored metadata only. {self.DISCLAIMER}",
            findings, self.LIMITATIONS,
        )

    def ves_interpretation_assistance(
        self, points: Sequence[VESPoint], model: LayeredEarthModel | VESInversionResult | None = None,
    ) -> AssistantResponse:
        active = [point for point in points if not point.excluded]
        values = [ves_apparent_resistivity(point) for point in active]
        findings: list[Finding] = []
        if values:
            trend = "increases" if values[-1] > values[0] else "decreases" if values[-1] < values[0] else "is approximately unchanged"
            findings.append(Finding("VES", "Observed curve trend", f"Across the supplied active points, apparent resistivity {trend} from the first to last point."))
            if any(values[index] > values[index - 1] and values[index + 1] < values[index] for index in range(1, len(values) - 1)):
                findings.append(Finding("VES", "Curve shape candidate", "The sampled curve contains a local maximum; this may motivate layered-model review, but is not a unique earth-model interpretation."))
        if model is not None:
            fitted = model.model if isinstance(model, VESInversionResult) else model
            findings.append(Finding("VES", "Layered model supplied", f"Model contains {len(fitted.resistivities)} resistivity layer value(s) and {len(fitted.thicknesses)} finite thickness value(s). Review equivalence and uncertainty before geological use."))
        return AssistantResponse(f"VES assistance reviewed {len(active)} active point(s). {self.DISCLAIMER}", tuple(findings), self.LIMITATIONS)

    def explain_2d_model(self, section: ResistivitySection) -> AssistantResponse:
        minimum, maximum = section.display_limits
        finding = Finding("2D model", "Displayed model range", f"Cells range from {minimum:g} to {maximum:g} in the current display limits; logarithmic={section.controls.logarithmic}.")
        return AssistantResponse(f"The 2D view contains {section.resistivity.size} validated cells. Display controls do not change model values. {self.DISCLAIMER}", (finding,), self.LIMITATIONS)

    def explain_3d_model(self, volume: ResistivityVolume) -> AssistantResponse:
        visible = int(volume.threshold_mask().sum())
        finding = Finding("3D model", "Volume visibility", f"{visible} of {volume.resistivity.size} cells pass the current threshold. Thresholding is a display operation, not geological classification.")
        return AssistantResponse(f"The 3D view contains {volume.resistivity.size} validated cells. {self.DISCLAIMER}", (finding,), self.LIMITATIONS)

    def draft_report(self) -> str:
        project = self.context.metadata.name if self.context.metadata else "Unnamed project"
        lines = [f"# Preliminary advisory summary: {project}", "", "## Scope", "This draft summarizes structured NiX ERT data and automated QC observations. It requires professional review.", ""]
        for survey in self.context.surveys:
            stats = self.context.qc_statistics.get(survey.id)
            lines.append(f"## {survey.name} ({survey.survey_type.value})")
            if stats:
                lines.append(f"Measurements: {stats.total}; active: {stats.active}; flagged: {stats.flagged}; excluded: {stats.excluded}.")
            lines.append("Interpretation: possible data patterns should be reviewed against acquisition context, coordinates, and inversion uncertainty.")
            lines.append("")
        lines.extend(["## Advisory limitations", *[f"- {item}" for item in self.LIMITATIONS]])
        return "\n".join(lines)

    def query(self, text: str) -> AssistantResponse:
        """Answer a bounded natural-language project query without executing actions."""
        query = text.strip().lower()
        if not query:
            raise ValueError("query cannot be empty")
        if any(term in query for term in ("suspicious", "qc flag", "flagged")):
            survey = self._survey_from_query(query)
            if survey:
                return self.suspicious_measurements(survey.id)
            return self.analyze_project()
        if any(term in query for term in ("highest resistivity", "anomal", "outlier")):
            survey = self._survey_from_query(query)
            if survey:
                return self.identify_resistivity_anomalies(survey.id)
            return AssistantResponse("Specify a survey for resistivity anomaly ranking.", limitations=self.LIMITATIONS)
        if "qc" in query or "quality" in query:
            survey = self._survey_from_query(query)
            return self.explain_qc(survey.id if survey else self.context.surveys[0].id) if survey or self.context.surveys else self.analyze_project()
        if any(term in query for term in ("report", "summarize", "summary")):
            return AssistantResponse(self.draft_report(), limitations=self.LIMITATIONS)
        if "survey" in query or "project" in query:
            return self.analyze_project()
        return AssistantResponse(
            "I can analyze the project, explain QC, rank resistivity anomaly candidates, summarize stored inversions, compare version IDs, assist with VES/model review, draft a report, or answer survey-scoped queries. No project data was changed.",
            limitations=self.LIMITATIONS,
        )

    def propose_exclusion(self, survey_id: str, row_numbers: Sequence[int], reason: str) -> ActionProposal:
        """Create an approval-required exclusion proposal without changing state."""
        self._require_survey(survey_id)
        rows = tuple(sorted(set(int(row) for row in row_numbers)))
        if not rows or any(row <= 0 for row in rows):
            raise ValueError("at least one positive measurement row is required")
        existing_items = [
            item for item in self.context.measurements.get(survey_id, ())
            if item.row_number in rows
        ]
        source_ids_by_row: dict[int, set[str | None]] = {}
        for item in existing_items:
            source_ids_by_row.setdefault(item.row_number, set()).add(item.source_id)
        ambiguous = [
            row for row, source_ids in source_ids_by_row.items()
            if len(source_ids) > 1
        ]
        if ambiguous:
            raise ValueError(
                "measurement rows are ambiguous across imported sources: "
                + ", ".join(str(row) for row in sorted(ambiguous))
            )
        if not reason.strip():
            raise ValueError("an exclusion reason is required")
        proposal = ActionProposal(str(uuid.uuid4()), "exclude_measurements", survey_id, rows, "Exclude only the selected working measurement statuses; raw source bytes remain unchanged.", reason.strip())
        self._pending[proposal.id] = proposal
        return proposal

    def explain_proposal(self, proposal: ActionProposal) -> AssistantResponse:
        if proposal.id not in self._pending:
            raise KeyError("proposal is not pending")
        self._explained.add(proposal.id)
        finding = Finding("approval", "Pending user approval", f"{proposal.explanation} Reason: {proposal.reason}", (proposal.id,))
        return AssistantResponse("This action has not executed. Explicit user approval is required.", (finding,), self.LIMITATIONS, (proposal,))

    def execute_proposal(self, proposal: ActionProposal, *, approved: bool = False) -> AssistantResponse:
        """Execute only an existing proposal when approval is explicitly true."""
        if self._pending.get(proposal.id) != proposal:
            raise KeyError("proposal is not pending")
        if not approved:
            return self.explain_proposal(proposal)
        if proposal.id not in self._explained:
            raise PermissionError("proposal must be explained before approval can execute")
        if self.qc_engine is None:
            raise RuntimeError("a live QC engine is required to execute proposals")
        self.qc_engine.set_status(proposal.survey_id, proposal.row_numbers, MeasurementStatus.EXCLUDED)
        del self._pending[proposal.id]
        self._explained.discard(proposal.id)
        return AssistantResponse("Approved exclusion executed on working statuses only; raw data and model parameters were not modified.", limitations=self.LIMITATIONS)

    def _survey_from_query(self, query: str) -> Survey | None:
        return next((survey for survey in self.context.surveys if survey.name.lower() in query or survey.id.lower() in query), None)

    def _require_survey(self, survey_id: str) -> None:
        if not any(survey.id == survey_id for survey in self.context.surveys):
            raise KeyError(f"Unknown survey: {survey_id}")

    @staticmethod
    def _explain_reasons(reasons: Sequence[str]) -> str:
        return "The deterministic QC rules reported: " + "; ".join(reasons) + ". These are review triggers, not proof of error or geology."

    @staticmethod
    def _summarize_snapshot(snapshot: Mapping[str, Any]) -> str:
        keys = ("rms_percent", "rms_log10", "converged", "iterations", "message")
        values = [f"{key}={snapshot[key]}" for key in keys if key in snapshot]
        return ", ".join(values) if values else "No standard convergence fields were stored in this snapshot."
