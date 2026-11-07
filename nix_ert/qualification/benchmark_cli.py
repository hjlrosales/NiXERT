"""Headless admission and execution entry point for a benchmark registry manifest.

The desktop application never runs an external benchmark. This module is the
non-interactive counterpart of :mod:`nix_ert.qualification.benchmark`: it reads a
registry manifest, admits each selected protocol, executes it against a case
file that carries the dataset's engine inputs, and reports the recorded outcome.

Nothing here supplies evidence. A manifest that cannot pass
:func:`nix_ert.qualification.benchmark.admit_benchmark_candidate` is refused and
nothing is executed, so the external gate can only move when real, licensed
evidence is supplied by the operator.

Usage::

    python tools/run_external_benchmark.py --manifest registry.json --admit-only
    python tools/run_external_benchmark.py --manifest registry.json --case ves.json --json out.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from nix_ert.ert.inversion2d import ERT2DError, ERTObservation, Mesh2D
from nix_ert.ert.inversion3d import ERT3DError, ERT3DObservation, Mesh3D
from nix_ert.qualification.benchmark import (
    BENCHMARK_PROCEDURE_VERSION,
    PROTOCOL_PARAMETER_KEY,
    BenchmarkAdmission,
    BenchmarkExecutionError,
    BenchmarkRun,
    ERT2DBenchmarkCase,
    ERT3DBenchmarkCase,
    VESBenchmarkCase,
    admit_benchmark_candidate,
    run_benchmark,
)
from nix_ert.qualification.dat_benchmark_case import (
    DATBenchmarkCaseError,
    build_dat_benchmark_case,
)
from nix_ert.qualification.ves_benchmark_case import (
    VESBenchmarkCaseError,
    build_ves_benchmark_case,
)
from nix_ert.qualification.registry import ComparisonStatus, QualificationRegistry
from nix_ert.ves.engine import VESError, VESPoint


CASE_FORMAT_VERSION = "benchmark-case-v1"
"""Case-file schema version; any other value is refused."""

EXIT_VALIDATED = 0
"""Every selected protocol was admitted and executed inside its frozen tolerance."""

EXIT_USAGE = 1
"""The manifest, a case file, or the case coverage is invalid. Nothing ran."""

EXIT_REFUSED = 2
"""At least one selected protocol failed admission and was not executed."""

EXIT_NOT_VALIDATED = 3
"""Every selected protocol executed, but at least one stayed outside tolerance."""


class BenchmarkCaseFileError(ValueError):
    """Raised when a case file is missing, malformed, or inconsistent."""


@dataclass(frozen=True)
class CaseSpec:
    """A parsed case file bound to the protocol it was prepared for."""

    protocol_id: str
    path: str
    case: VESBenchmarkCase | ERT2DBenchmarkCase | ERT3DBenchmarkCase


@dataclass(frozen=True)
class DATCaseRequest:
    """A request to convert one NiX DAT file into the case for one protocol."""

    protocol_id: str
    dat_path: str
    emit_path: str | None = None


@dataclass(frozen=True)
class VESCaseRequest:
    """A request to convert one VES text/CSV sounding into the case for one protocol."""

    protocol_id: str
    ves_path: str
    emit_path: str | None = None


@dataclass(frozen=True)
class ExecutionOutcome:
    """One protocol's admission decision and, when admitted, its run."""

    protocol_id: str
    admission: BenchmarkAdmission
    run: BenchmarkRun | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "protocol_id": self.protocol_id,
            "admission": self.admission.to_dict(),
            "run": None if self.run is None else self.run.to_dict(),
            "error": self.error,
        }


@dataclass(frozen=True)
class ManifestExecution:
    """The complete, deterministic result of one headless invocation."""

    manifest_path: str
    admission_only: bool
    outcomes: tuple[ExecutionOutcome, ...]
    record_path: str | None = None
    case_format_version: str = CASE_FORMAT_VERSION
    procedure_version: str = BENCHMARK_PROCEDURE_VERSION

    @property
    def exit_code(self) -> int:
        if any(outcome.error for outcome in self.outcomes):
            return EXIT_USAGE
        if any(not outcome.admission.admitted for outcome in self.outcomes):
            return EXIT_REFUSED
        if self.admission_only:
            return EXIT_VALIDATED
        if any(
            outcome.run is None or outcome.run.status is not ComparisonStatus.VALIDATED
            for outcome in self.outcomes
        ):
            return EXIT_NOT_VALIDATED
        return EXIT_VALIDATED

    def to_dict(self) -> dict[str, object]:
        return {
            "case_format_version": self.case_format_version,
            "procedure_version": self.procedure_version,
            "manifest_path": self.manifest_path,
            "record_path": self.record_path,
            "admission_only": self.admission_only,
            "exit_code": self.exit_code,
            "outcomes": [outcome.to_dict() for outcome in self.outcomes],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=2, default=str)

    def to_text(self) -> str:
        lines = [
            f"manifest: {self.manifest_path}",
            f"mode: {'admission only' if self.admission_only else 'admission + execution'}",
        ]
        if self.record_path:
            lines.append(f"recorded: {self.record_path}")
        for outcome in self.outcomes:
            admission = outcome.admission
            if not admission.admitted:
                lines.append(
                    f"[REFUSED] {outcome.protocol_id}: "
                    + ", ".join(sorted(set(admission.codes)))
                )
                for finding in admission.findings:
                    lines.append(f"    {finding.code}: {finding.detail}")
                continue
            if outcome.error:
                lines.append(f"[ERROR]   {outcome.protocol_id}: {outcome.error}")
                continue
            if outcome.run is None:
                lines.append(f"[ADMITTED] {outcome.protocol_id}: dataset {admission.dataset_id}")
                continue
            run = outcome.run
            metrics = ", ".join(
                f"{name}={value:.6g}" for name, value in sorted(run.metrics.items())
            )
            lines.append(
                f"[{run.status.value}] {outcome.protocol_id}: "
                f"{run.convergence.outcome.value}, {metrics or 'no metrics'}"
            )
            lines.append(f"    {run.notes}")
        lines.append(f"exit={self.exit_code}")
        return "\n".join(lines)


def _write_text(path: Path | str, text: str) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8", newline="\n")
    return destination


def _mapping(value: object, label: str, allowed: Sequence[str]) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise BenchmarkCaseFileError(f"{label} must be an object")
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        raise BenchmarkCaseFileError(f"{label} has unknown fields: {', '.join(unknown)}")
    return value


def _sequence(value: object, label: str, *, required: bool = True) -> Sequence[object]:
    if not isinstance(value, (list, tuple)):
        raise BenchmarkCaseFileError(f"{label} must be an array")
    if required and not value:
        raise BenchmarkCaseFileError(f"{label} must not be empty")
    return value


def _number(value: object, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BenchmarkCaseFileError(f"{label} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise BenchmarkCaseFileError(f"{label} must be finite")
    if positive and number <= 0:
        raise BenchmarkCaseFileError(f"{label} must be positive")
    return number


def _integer(value: object, label: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BenchmarkCaseFileError(f"{label} must be an integer")
    if positive and value < 1:
        raise BenchmarkCaseFileError(f"{label} must be positive")
    return value


def _optional_bool(value: object, label: str) -> bool:
    if value is None:
        return False
    if not isinstance(value, bool):
        raise BenchmarkCaseFileError(f"{label} must be a boolean")
    return value


_CASE_FIELDS = {
    "VES": ("protocol_id", "domain", "case_format_version", "points"),
    "2D ERT": ("protocol_id", "domain", "case_format_version", "x_edges", "depth_edges", "observations"),
    "3D ERT": (
        "protocol_id", "domain", "case_format_version", "x_edges", "y_edges",
        "depth_edges", "electrodes", "observations",
    ),
}

_OBSERVATION_FIELDS = ("a", "b", "m", "n", "apparent_resistivity", "excluded")
_VES_POINT_FIELDS = ("ab2", "mn2", "apparent_resistivity", "resistance", "excluded")


def build_case(protocol_id: str, payload: Mapping[str, object], *, path: str = "") -> CaseSpec:
    """Build a validated engine case from a parsed case-file payload."""
    domain = payload.get("domain")
    if domain not in _CASE_FIELDS:
        raise BenchmarkCaseFileError(
            f"case domain must be one of {', '.join(sorted(_CASE_FIELDS))}"
        )
    version = payload.get("case_format_version", CASE_FORMAT_VERSION)
    if version != CASE_FORMAT_VERSION:
        raise BenchmarkCaseFileError(
            f"case_format_version must be {CASE_FORMAT_VERSION!r}, not {version!r}"
        )
    body = _mapping(payload, "case", _CASE_FIELDS[str(domain)])
    declared = body.get("protocol_id")
    if declared != protocol_id:
        raise BenchmarkCaseFileError(
            f"case declares protocol_id {declared!r} but was supplied for {protocol_id!r}"
        )

    try:
        if domain == "VES":
            points = []
            for index, item in enumerate(_sequence(body.get("points"), "points")):
                entry = _mapping(item, f"points[{index}]", _VES_POINT_FIELDS)
                points.append(
                    VESPoint(
                        ab2=_number(entry.get("ab2"), f"points[{index}].ab2", positive=True),
                        mn2=_number(entry.get("mn2"), f"points[{index}].mn2", positive=True),
                        apparent_resistivity=(
                            None
                            if entry.get("apparent_resistivity") is None
                            else _number(
                                entry.get("apparent_resistivity"),
                                f"points[{index}].apparent_resistivity",
                                positive=True,
                            )
                        ),
                        resistance=(
                            None
                            if entry.get("resistance") is None
                            else _number(entry.get("resistance"), f"points[{index}].resistance")
                        ),
                        excluded=_optional_bool(entry.get("excluded"), f"points[{index}].excluded"),
                    )
                )
            case = VESBenchmarkCase(points=tuple(points))
        else:
            records: list[tuple[int, int, int, int, float, bool]] = []
            for index, item in enumerate(_sequence(body.get("observations"), "observations")):
                entry = _mapping(item, f"observations[{index}]", _OBSERVATION_FIELDS)
                records.append(
                    (
                        _integer(entry.get("a"), f"observations[{index}].a", positive=True),
                        _integer(entry.get("b"), f"observations[{index}].b", positive=True),
                        _integer(entry.get("m"), f"observations[{index}].m", positive=True),
                        _integer(entry.get("n"), f"observations[{index}].n", positive=True),
                        _number(
                            entry.get("apparent_resistivity"),
                            f"observations[{index}].apparent_resistivity",
                            positive=True,
                        ),
                        _optional_bool(
                            entry.get("excluded"), f"observations[{index}].excluded"
                        ),
                    )
                )
            x_edges = tuple(
                _number(item, f"x_edges[{index}]")
                for index, item in enumerate(_sequence(body.get("x_edges"), "x_edges"))
            )
            depth_edges = tuple(
                _number(item, f"depth_edges[{index}]")
                for index, item in enumerate(_sequence(body.get("depth_edges"), "depth_edges"))
            )
            if domain == "2D ERT":
                case = ERT2DBenchmarkCase(
                    mesh=Mesh2D(x_edges=x_edges, depth_edges=depth_edges),
                    observations=tuple(ERTObservation(*record) for record in records),
                )
            else:
                y_edges = tuple(
                    _number(item, f"y_edges[{index}]")
                    for index, item in enumerate(_sequence(body.get("y_edges"), "y_edges"))
                )
                electrodes: list[tuple[float, float]] = []
                for index, pair in enumerate(_sequence(body.get("electrodes"), "electrodes")):
                    values = _sequence(pair, f"electrodes[{index}]")
                    if len(values) != 2:
                        raise BenchmarkCaseFileError(
                            f"electrodes[{index}] must be a pair of numbers"
                        )
                    electrodes.append(
                        (
                            _number(values[0], f"electrodes[{index}][0]"),
                            _number(values[1], f"electrodes[{index}][1]"),
                        )
                    )
                case = ERT3DBenchmarkCase(
                    mesh=Mesh3D(x_edges=x_edges, y_edges=y_edges, depth_edges=depth_edges),
                    electrodes=tuple(electrodes),
                    observations=tuple(ERT3DObservation(*record) for record in records),
                )
    except (ERT2DError, ERT3DError, VESError, BenchmarkExecutionError, TypeError) as exc:
        raise BenchmarkCaseFileError(f"case is invalid: {exc}") from exc
    return CaseSpec(protocol_id=protocol_id, path=path, case=case)


def load_case(protocol_id: str, path: Path | str) -> CaseSpec:
    """Read and validate one case file for the given protocol."""
    case_path = Path(path)
    try:
        payload = json.loads(case_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise BenchmarkCaseFileError(f"cannot read case file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise BenchmarkCaseFileError(f"case file {path} is not valid JSON: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise BenchmarkCaseFileError(f"case file {path} must contain a JSON object")
    return build_case(protocol_id, payload, path=str(case_path))


def execute_manifest(
    manifest_path: Path | str,
    *,
    cases: Sequence[CaseSpec] = (),
    dat_cases: Sequence[DATCaseRequest] = (),
    ves_cases: Sequence[VESCaseRequest] = (),
    protocol_ids: Sequence[str] = (),
    admission_only: bool = False,
    record_to: Path | str | None = None,
) -> ManifestExecution:
    """Admit and optionally execute every selected protocol in a manifest.

    Recorded comparisons are only durable if ``record_to`` is supplied: the
    updated registry manifest is then written there. Admission-only runs never
    write, so a refusal cannot modify the caller's evidence file.
    """
    registry = QualificationRegistry.read_manifest(manifest_path)
    selected = [str(item) for item in protocol_ids] or sorted(registry.protocols)
    if not selected:
        raise BenchmarkCaseFileError("the manifest registers no protocols to run")
    unknown = [item for item in selected if item not in registry.protocols]
    if unknown:
        raise BenchmarkCaseFileError("unknown protocol(s): " + ", ".join(unknown))

    by_protocol = {spec.protocol_id: spec for spec in cases}
    if len(by_protocol) != len(cases):
        raise BenchmarkCaseFileError("more than one case file was supplied for one protocol")
    stray = sorted(set(by_protocol) - set(selected))
    if stray:
        raise BenchmarkCaseFileError(
            "case file(s) supplied for protocol(s) that are not selected: " + ", ".join(stray)
        )
    sources: dict[str, str] = {spec.protocol_id: "case file" for spec in cases}

    def claim(protocol_id: str, kind: str) -> None:
        """Refuse a second set of engine inputs for the same protocol."""
        prior = sources.get(protocol_id)
        if prior is not None:
            raise BenchmarkCaseFileError(
                f"both a {prior} and a {kind} were supplied for {protocol_id!r}"
            )
        sources[protocol_id] = kind

    for request in dat_cases:
        if request.protocol_id not in selected:
            raise BenchmarkCaseFileError(
                f"--case-from-dat was supplied for protocol {request.protocol_id!r}, which is "
                "not selected"
            )
        claim(request.protocol_id, "DAT conversion")
        protocol = registry.protocols[request.protocol_id]
        try:
            converted = build_dat_benchmark_case(
                request.dat_path, request.protocol_id, protocol.mesh_assumptions
            )
        except DATBenchmarkCaseError as exc:
            raise BenchmarkCaseFileError(
                f"cannot convert {request.dat_path} for {request.protocol_id!r}: {exc}"
            ) from exc
        if request.emit_path:
            try:
                _write_text(request.emit_path, converted.to_json())
            except OSError as exc:
                raise BenchmarkCaseFileError(
                    f"cannot write derived case {request.emit_path}: {exc}"
                ) from exc
        by_protocol[request.protocol_id] = build_case(
            request.protocol_id, converted.to_payload(), path=request.dat_path
        )
    for request in ves_cases:
        if request.protocol_id not in selected:
            raise BenchmarkCaseFileError(
                f"--case-from-ves was supplied for protocol {request.protocol_id!r}, which is "
                "not selected"
            )
        claim(request.protocol_id, "VES conversion")
        protocol = registry.protocols[request.protocol_id]
        domain = protocol.inversion_parameters.get(PROTOCOL_PARAMETER_KEY)
        if domain != "VES":
            raise BenchmarkCaseFileError(
                f"--case-from-ves was supplied for protocol {request.protocol_id!r}, which "
                f"targets {domain!r}; a VES sounding can only build a VES case"
            )
        try:
            converted = build_ves_benchmark_case(request.ves_path, request.protocol_id)
        except VESBenchmarkCaseError as exc:
            raise BenchmarkCaseFileError(
                f"cannot convert {request.ves_path} for {request.protocol_id!r}: {exc}"
            ) from exc
        if request.emit_path:
            try:
                _write_text(request.emit_path, converted.to_json())
            except OSError as exc:
                raise BenchmarkCaseFileError(
                    f"cannot write derived case {request.emit_path}: {exc}"
                ) from exc
        by_protocol[request.protocol_id] = build_case(
            request.protocol_id, converted.to_payload(), path=request.ves_path
        )
    admissions = {
        protocol_id: admit_benchmark_candidate(registry, protocol_id)
        for protocol_id in selected
    }
    if not admission_only:
        # Only a protocol that can actually be executed needs engine inputs; an
        # inadmissible protocol is reported as refused instead of as a usage error.
        missing = [
            protocol_id
            for protocol_id, admission in admissions.items()
            if admission.admitted and protocol_id not in by_protocol
        ]
        if missing:
            raise BenchmarkCaseFileError(
                "no case file supplied for admitted protocol(s): " + ", ".join(missing)
            )

    outcomes: list[ExecutionOutcome] = []
    for protocol_id in selected:
        admission = admissions[protocol_id]
        if not admission.admitted or admission_only:
            outcomes.append(ExecutionOutcome(protocol_id, admission))
            continue
        try:
            run = run_benchmark(registry, protocol_id, by_protocol[protocol_id].case)
        except (BenchmarkExecutionError, ValueError) as exc:
            outcomes.append(ExecutionOutcome(protocol_id, admission, error=str(exc)))
            continue
        outcomes.append(ExecutionOutcome(protocol_id, admission, run=run))

    record_path: str | None = None
    if record_to is not None and registry.comparisons:
        registry.write_manifest(record_to)
        record_path = str(record_to)
    return ManifestExecution(
        manifest_path=str(manifest_path),
        admission_only=bool(admission_only),
        outcomes=tuple(outcomes),
        record_path=record_path,
    )


def _emit_target(protocol_id: str, emit_items: Sequence[str]) -> str | None:
    """Return the single ``--emit-case`` target for one protocol, if any."""
    emit_path: str | None = None
    for emit_item in emit_items:
        emit_protocol, emit_separator, emit_target = str(emit_item).partition("=")
        if not emit_separator or not emit_protocol.strip() or not emit_target.strip():
            raise BenchmarkCaseFileError("--emit-case expects PROTOCOL_ID=PATH")
        if emit_protocol.strip() == protocol_id:
            if emit_path is not None:
                raise BenchmarkCaseFileError(
                    f"more than one --emit-case target was given for {protocol_id!r}"
                )
            emit_path = emit_target.strip()
    return emit_path


def _dat_request(item: str, flag: str, emit_items: Sequence[str]) -> DATCaseRequest:
    protocol_id, separator, dat_path = str(item).partition("=")
    if not separator or not protocol_id.strip() or not dat_path.strip():
        raise BenchmarkCaseFileError(f"{flag} expects PROTOCOL_ID=PATH")
    protocol_id = protocol_id.strip()
    return DATCaseRequest(
        protocol_id=protocol_id,
        dat_path=dat_path.strip(),
        emit_path=_emit_target(protocol_id, emit_items),
    )


def _ves_request(item: str, flag: str, emit_items: Sequence[str]) -> VESCaseRequest:
    protocol_id, separator, ves_path = str(item).partition("=")
    if not separator or not protocol_id.strip() or not ves_path.strip():
        raise BenchmarkCaseFileError(f"{flag} expects PROTOCOL_ID=PATH")
    protocol_id = protocol_id.strip()
    return VESCaseRequest(
        protocol_id=protocol_id,
        ves_path=ves_path.strip(),
        emit_path=_emit_target(protocol_id, emit_items),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the headless benchmark tool and print a report."""
    parser = argparse.ArgumentParser(
        prog="run_external_benchmark",
        description=(
            "Admit a benchmark registry manifest and execute its frozen protocols "
            "over the unmodified NiX ERT engines. Execution requires a case file "
            "for every selected protocol; admission alone never validates anything."
        ),
    )
    parser.add_argument("--manifest", required=True, help="registry manifest JSON file")
    parser.add_argument(
        "--protocol",
        action="append",
        default=[],
        metavar="ID",
        help="protocol to select (repeatable; default: every registered protocol)",
    )
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        metavar="PROTOCOL_ID=PATH",
        help="case file for a selected protocol (repeatable)",
    )
    parser.add_argument(
        "--case-from-dat",
        action="append",
        default=[],
        metavar="PROTOCOL_ID=DAT_PATH",
        help=(
            "build the case for a protocol from a NiX dialect DAT file instead of a "
            "hand-written case file; the protocol's mesh_assumptions supply nz/depth"
        ),
    )
    parser.add_argument(
        "--case-from-ves",
        action="append",
        default=[],
        metavar="PROTOCOL_ID=VES_PATH",
        help=(
            "build the case for a VES protocol from a documented text/CSV sounding "
            "instead of a hand-written case file"
        ),
    )
    parser.add_argument(
        "--emit-case",
        action="append",
        default=[],
        metavar="PROTOCOL_ID=PATH",
        help=(
            "write the converted case payload (JSON) for review; requires the same "
            "protocol's --case-from-dat or --case-from-ves conversion"
        ),
    )
    parser.add_argument(
        "--admit-only",
        action="store_true",
        help="stop after admission; execute and record nothing",
    )
    parser.add_argument("--json", metavar="PATH", help="write the machine-readable result here")
    parser.add_argument(
        "--record-to",
        metavar="PATH",
        help=(
            "registry manifest to write recorded comparisons into "
            "(default: the input manifest; ignored with --admit-only)"
        ),
    )
    arguments = parser.parse_args(list(argv) if argv is not None else None)

    try:
        cases: list[CaseSpec] = []
        for item in arguments.case:
            protocol_id, separator, case_path = str(item).partition("=")
            if not separator or not protocol_id.strip() or not case_path.strip():
                raise BenchmarkCaseFileError("--case expects PROTOCOL_ID=PATH")
            cases.append(load_case(protocol_id.strip(), case_path.strip()))
        dat_requests = [
            _dat_request(item, "--case-from-dat", arguments.emit_case)
            for item in arguments.case_from_dat
        ]
        ves_requests = [
            _ves_request(item, "--case-from-ves", arguments.emit_case)
            for item in arguments.case_from_ves
        ]
        converted_ids = {
            request.protocol_id for request in (*dat_requests, *ves_requests)
        }
        for emit_item in arguments.emit_case:
            emit_protocol, emit_separator, emit_target = str(emit_item).partition("=")
            if not emit_separator or not emit_protocol.strip() or not emit_target.strip():
                raise BenchmarkCaseFileError("--emit-case expects PROTOCOL_ID=PATH")
            if emit_protocol.strip() not in converted_ids:
                raise BenchmarkCaseFileError(
                    f"--emit-case was supplied for {emit_protocol.strip()!r}, which has no "
                    "--case-from-dat conversion or --case-from-ves conversion"
                )
        execution = execute_manifest(
            arguments.manifest,
            cases=tuple(cases),
            dat_cases=tuple(dat_requests),
            ves_cases=tuple(ves_requests),
            protocol_ids=tuple(arguments.protocol),
            admission_only=bool(arguments.admit_only),
            record_to=(
                None
                if arguments.admit_only
                else (arguments.record_to or arguments.manifest)
            ),
        )
    except (BenchmarkCaseFileError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    if arguments.json:
        try:
            Path(arguments.json).write_text(execution.to_json(), encoding="utf-8", newline="\n")
        except OSError as exc:
            print(f"error: cannot write {arguments.json}: {exc}", file=sys.stderr)
            return EXIT_USAGE
    print(execution.to_text())
    return execution.exit_code


if __name__ == "__main__":  # pragma: no cover - exercised through tools/
    raise SystemExit(main())
