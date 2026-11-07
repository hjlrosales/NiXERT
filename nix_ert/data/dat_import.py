"""Parser for the documented NiX ERT DAT text dialect.

Dialect definition (this is the *only* format claimed to be supported)
--------------------------------------------------------------------
Header, one value per line, in this order::

    <data count>            integer >= 0
    <electrode spacing>     metres, positive
    <array type>            integer code 1-6 or a documented array name
    <topography count>      optional integer >= 0 (a single-token line)
    <topography rows>       ``distance elevation`` pairs, when the count > 0
    <measurement rows>      exactly ``data count`` rows

Measurement rows are either ``A B M N rho`` (canonical) or
``index A B M N rho`` (indexed), with up to three additional documented numeric
columns preserved as ``resistance``, ``current`` and ``voltage``. Electrode
numbers are 1-based integers; ``rho`` is in ohm-metres. Electrode geometry is
derived by this dialect as ``x = (number - 1) * spacing`` with ``y = 0`` and no
elevation; that convention is recorded with the source instead of being
re-inferred later.

Scope and evidence limits
-------------------------
Vendor conformance has **not** been established: no authentic RES2DINV or
Terrameter LS2 export fixtures are available in this repository, so no equivalent
header order, array-code mapping, or unit convention is claimed. Files whose
header order, row width, or array code differs from the dialect above are
rejected instead of guessed. Vendor conformance remains evidence-blocked (see
``docs/m23_forward_physics_correction.md``).

The parser intentionally does not infer apparent resistivity from resistance.
That calculation belongs to the independently validated processing milestone.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from nix_ert.data.measurements import Electrode, ImportedDataset, Measurement


class DATParseError(ValueError):
    """Raised when a DAT file cannot be interpreted without guessing."""


ARRAY_TYPES: dict[int, str] = {
    1: "Wenner",
    2: "Pole-Pole",
    3: "Dipole-Dipole",
    4: "Pole-Dipole",
    5: "Wenner-Schlumberger",
    6: "Multiple Gradient",
}

_FLOAT = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"


@dataclass(frozen=True)
class DATPreview:
    """Metadata available before a dataset is persisted."""

    source_name: str
    data_count: int
    parsed_count: int
    electrode_spacing: float
    array_type: str
    electrode_count: int
    invalid_measurement_count: int
    warnings: tuple[str, ...] = ()


def _data_lines(text: str) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    for line_number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(("#", ";", "!")):
            continue
        result.append((line_number, line))
    return result


def _integer(value: str, label: str, line_number: int) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise DATParseError(f"Line {line_number}: {label} must be an integer") from exc
    return parsed


def _number(value: str, label: str, line_number: int) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise DATParseError(f"Line {line_number}: {label} must be numeric") from exc
    if not math.isfinite(parsed):
        raise DATParseError(f"Line {line_number}: {label} must be finite")
    return parsed


def _array_name(raw: str, line_number: int) -> str:
    try:
        code = int(raw)
    except ValueError:
        value = raw.strip().lower().replace("_", "-")
        aliases = {
            "wenner": "Wenner",
            "dipole-dipole": "Dipole-Dipole",
            "dipole dipole": "Dipole-Dipole",
            "pole-pole": "Pole-Pole",
            "pole-pole": "Pole-Pole",
            "pole-dipole": "Pole-Dipole",
            "wenner-schlumberger": "Wenner-Schlumberger",
            "multiple-gradient": "Multiple Gradient",
        }
        if value in aliases:
            return aliases[value]
        raise DATParseError(f"Line {line_number}: unsupported array type {raw!r}")
    if code not in ARRAY_TYPES:
        raise DATParseError(f"Line {line_number}: unsupported array type code {code}")
    return ARRAY_TYPES[code]


def _measurement_from_row(
    tokens: list[str], line_number: int, *, row_format: str = "auto",
) -> Measurement:
    if len(tokens) < 5:
        raise DATParseError(
            f"Line {line_number}: measurement requires A B M N and apparent resistivity"
        )
    if row_format not in {"auto", "canonical", "indexed"}:
        raise DATParseError(f"unsupported DAT row format: {row_format}")
    # Five to eight columns can be canonical A B M N rho followed by up to
    # three documented electrical fields. Six to nine columns can also be an
    # indexed row. In auto mode, overlapping widths are rejected rather than
    # guessed; an incorrect shift would corrupt electrode identity and values.
    if len(tokens) > 9:
        raise DATParseError(
            f"Line {line_number}: DAT row has {len(tokens)} columns; the documented dialect "
            "supports at most A B M N rho plus an index and three electrical columns"
        )
    canonical_possible = 5 <= len(tokens) <= 8
    indexed_possible = 6 <= len(tokens) <= 9
    if row_format == "canonical":
        if not canonical_possible:
            raise DATParseError(f"Line {line_number}: invalid canonical DAT row width")
        offset = 0
    elif row_format == "indexed":
        if not indexed_possible:
            raise DATParseError(f"Line {line_number}: invalid indexed DAT row width")
        offset = 1
    elif canonical_possible and indexed_possible:
        raise DATParseError(
            f"Line {line_number}: ambiguous DAT row width {len(tokens)}; "
            "specify canonical or indexed row format"
        )
    else:
        offset = 0 if canonical_possible else 1
    electrode_tokens = tokens[offset : offset + 4]
    if len(electrode_tokens) != 4:
        raise DATParseError(f"Line {line_number}: incomplete electrode tuple")
    electrodes = []
    for token in electrode_tokens:
        value = _integer(token, "electrode number", line_number)
        if value <= 0:
            raise DATParseError(f"Line {line_number}: electrode numbers must be positive")
        electrodes.append(value)
    rho = _number(tokens[offset + 4], "apparent resistivity", line_number)
    extra: dict[str, float] = {}
    labels = ("resistance", "current", "voltage")
    trailing = tokens[offset + 5 :]
    if len(trailing) > len(labels):
        raise DATParseError(
            f"Line {line_number}: {len(trailing)} trailing columns found; at most "
            f"{len(labels)} documented electrical columns are supported"
        )
    for label, token in zip(labels, trailing):
        extra[label] = _number(token, label, line_number)
    return Measurement(
        row_number=line_number,
        a=electrodes[0], b=electrodes[1], m=electrodes[2], n=electrodes[3],
        apparent_resistivity=rho,
        measurement_index=_integer(tokens[0], "measurement index", line_number) if offset else None,
        resistance=extra.get("resistance"), current=extra.get("current"),
        voltage=extra.get("voltage"), extra=extra or None,
    )



def parse_dat(
    text: str, source_name: str = "<memory>", *,    row_format: str = "auto",
) -> ImportedDataset:
    """Parse the documented NiX ERT DAT dialect described in this module.

    Header: data count, electrode spacing, array type, optional topography
    count. Data rows are either ``A B M N rho`` or ``index A B M N rho``.
    The optional values after rho are preserved as resistance/current/voltage
    in that order when present. In ``auto`` mode, overlapping row widths are
    rejected; use ``row_format=\"canonical\"`` or ``row_format=\"indexed\"``
    when the row format is known.

    Every rejection names the source and line. No unsupported header order,
    array code, row width, or extra column is accepted or guessed.
    """
    lines = _data_lines(text)
    if len(lines) < 3:
        raise DATParseError(f"{source_name}: DAT file must contain at least three header values")
    count_line, spacing_line, array_line = lines[:3]
    for line_number, line in (count_line, spacing_line, array_line):
        if len(line.split()) != 1:
            raise DATParseError(
                f"{source_name} line {line_number}: header values must be a single value per line "
                f"in the documented dialect, found {line!r}"
            )
    data_count = _integer(count_line[1], "data count", count_line[0])
    if data_count < 0:
        raise DATParseError(f"Line {count_line[0]}: data count cannot be negative")
    spacing = _number(spacing_line[1], "electrode spacing", spacing_line[0])
    if spacing <= 0:
        raise DATParseError(f"Line {spacing_line[0]}: electrode spacing must be positive")
    array_type = _array_name(array_line[1], array_line[0])

    cursor = 3
    topography: list[tuple[float, float]] = []
    header_lines = [count_line[1], spacing_line[1], array_line[1]]
    # In this dialect a single-token line after the array header *is* the
    # topography point count. It is never inferred from the remaining line
    # count, and a declared count that the file cannot satisfy is an error.
    if cursor < len(lines) and len(lines[cursor][1].split()) == 1:
        potential_count = _integer(lines[cursor][1], "topography count", lines[cursor][0])
        if potential_count < 0:
            raise DATParseError(f"Line {lines[cursor][0]}: topography count cannot be negative")
        if potential_count > len(lines) - cursor - 1:
            raise DATParseError(
                f"Line {lines[cursor][0]}: topography count {potential_count} exceeds the "
                f"{len(lines) - cursor - 1} remaining line(s)"
            )
        header_lines.append(lines[cursor][1])
        cursor += 1
        for _ in range(potential_count):
            line_number, line = lines[cursor]
            tokens = line.split()
            if len(tokens) != 2:
                raise DATParseError(
                    f"Line {line_number}: topography requires exactly distance and elevation"
                )
            topography.append((_number(tokens[0], "topography distance", line_number), _number(tokens[1], "topography elevation", line_number)))
            cursor += 1

    remaining = lines[cursor:]
    if len(remaining) != data_count:
        raise DATParseError(
            f"Expected {data_count} measurement rows, found {len(remaining)}"
        )
    measurements = tuple(
        _measurement_from_row(line.split(), line_number, row_format=row_format) for line_number, line in remaining
    )
    electrode_numbers = sorted({number for measurement in measurements for number in (measurement.a, measurement.b, measurement.m, measurement.n)})
    electrodes = tuple(Electrode(number=number, x=(number - 1) * spacing) for number in electrode_numbers)
    return ImportedDataset(
        source_name=source_name, data_count=data_count, electrode_spacing=spacing,
        array_type=array_type, measurements=measurements, electrodes=electrodes,
        header_lines=tuple(header_lines), topography=tuple(topography),
    )


def parse_dat_file(path: Path | str) -> ImportedDataset:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DATParseError(f"Unable to decode {path.name} as UTF-8 text") from exc
    except OSError as exc:
        raise DATParseError(f"Unable to read {path}: {exc}") from exc
    return parse_dat(text, source_name=path.name)


def preview_dat(text: str, source_name: str = "<memory>") -> DATPreview:
    dataset = parse_dat(text, source_name)
    warnings = tuple(
        f"{dataset.invalid_measurement_count} measurement(s) have non-positive apparent resistivity"
        for _ in range(dataset.invalid_measurement_count > 0)
    )
    return DATPreview(
        source_name=dataset.source_name, data_count=dataset.data_count,
        parsed_count=len(dataset.measurements), electrode_spacing=dataset.electrode_spacing,
        array_type=dataset.array_type, electrode_count=len(dataset.electrodes),
        invalid_measurement_count=dataset.invalid_measurement_count, warnings=warnings,
    )
