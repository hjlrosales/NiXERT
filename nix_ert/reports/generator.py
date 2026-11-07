"""Structured offline technical report generation.

A report is a fixed, numbered section sequence rendered from structured data
only. The same `ReportData` produces HTML, PDF, a machine-readable JSON manifest,
and a flat CSV export; every format is derived from the same canonical content
digest, so a printed report and an archived export can be matched.

Nothing here invents geological conclusions. Sections whose data was not
supplied render an explicit "not supplied" note instead of being dropped or
inferred, and a provenance section records what the report actually represents.
"""

from __future__ import annotations

import csv
import hashlib
import html
import io
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class ReportData:
    title: str
    project: Mapping[str, object]
    surveys: Sequence[Mapping[str, object]] = ()
    qc_summary: Mapping[str, object] = field(default_factory=dict)
    pseudosection_csv: str | None = None
    inversion: Mapping[str, object] = field(default_factory=dict)
    ves_models: Sequence[Mapping[str, object]] = ()
    interpretation: Sequence[Mapping[str, object]] = ()
    appendices: Sequence[str] = ()
    generated_at: str | None = None
    provenance: Mapping[str, object] = field(default_factory=dict)
    conclusions: Sequence[Mapping[str, object]] = ()
    recommendations: Sequence[Mapping[str, object]] = ()
    limitations: Sequence[str] = ()


TABLE_SECTIONS: tuple[tuple[str, str], ...] = (
    ("project", "Project information"),
    ("surveys", "Survey methodology and organization"),
    ("qc_summary", "Data quality control summary"),
    ("inversion", "Inversion parameters and convergence"),
    ("ves_models", "VES models"),
    ("interpretation", "Interpretation"),
    ("conclusions", "Conclusions"),
    ("recommendations", "Recommendations"),
    ("limitations", "Limitations and scientific scope"),
    ("provenance", "Provenance and report identity"),
)
"""Numbered section order, shared by HTML, the manifest, and CSV."""

EMPTY_NOTES: Mapping[str, str] = {
    "conclusions": "No conclusions supplied. This report does not invent geological conclusions.",
    "recommendations": "No recommendations supplied. This report does not invent recommendations.",
    "limitations": "No limitations statement supplied.",
    "provenance": "No provenance supplied; the report cannot be matched to a project state.",
}
"""Explicit text for sections whose structured data was not supplied."""


def _value(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (dict, list, tuple)):
        return html.escape(json.dumps(value, sort_keys=True, default=str))
    return html.escape(str(value))


def _table(rows: Iterable[Mapping[str, object]], *, empty: str | None = None) -> str:
    rows = list(rows)
    if not rows:
        return f'<p class="empty">{html.escape(empty or "No structured records supplied.")}</p>'
    columns: list[str] = []
    for row in rows:
        for column in row:
            if column not in columns:
                columns.append(column)
    header = "".join(f"<th>{html.escape(str(column))}</th>" for column in columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{_value(row.get(column))}</td>" for column in columns) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>"


def _list(items: Iterable[str], *, empty: str | None = None) -> str:
    values = [str(item) for item in items]
    if not values:
        return f'<p class="empty">{html.escape(empty or "No statements supplied.")}</p>'
    return "<ul>" + "".join(f"<li>{html.escape(value)}</li>" for value in values) + "</ul>"


def _rows(section: str, value: object) -> list[dict[str, object]]:
    """Flatten one section into `record,item,value` rows for tables and export."""
    rows: list[dict[str, object]] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            rows.append({"section": section, "record": "", "item": str(key), "value": item})
    elif isinstance(value, (list, tuple)):
        for index, entry in enumerate(value, start=1):
            if isinstance(entry, Mapping):
                for key, item in entry.items():
                    rows.append(
                        {"section": section, "record": str(index), "item": str(key), "value": item}
                    )
            else:
                rows.append(
                    {"section": section, "record": str(index), "item": "", "value": entry}
                )
    elif value is not None:
        rows.append({"section": section, "record": "", "item": "", "value": value})
    return rows


def section_titles(data: ReportData) -> tuple[str, ...]:
    """Return the numbered section titles this report actually contains."""
    titles = [title for _, title in TABLE_SECTIONS]
    if data.pseudosection_csv is not None:
        titles.append("Pseudosection data appendix")
    if data.appendices:
        titles.append("Appendices")
    return tuple(titles)


def _canonical_payload(data: ReportData) -> dict[str, object]:
    """Return the content the digest is computed from, independent of the format."""
    return {
        "title": data.title,
        "generated_at": data.generated_at,
        "project": dict(data.project),
        "surveys": [dict(item) for item in data.surveys],
        "qc_summary": dict(data.qc_summary),
        "inversion": dict(data.inversion),
        "ves_models": [dict(item) for item in data.ves_models],
        "interpretation": [dict(item) for item in data.interpretation],
        "conclusions": [dict(item) for item in data.conclusions],
        "recommendations": [dict(item) for item in data.recommendations],
        "limitations": [str(item) for item in data.limitations],
        "provenance": dict(data.provenance),
        "appendices": [str(item) for item in data.appendices],
        "pseudosection_csv": data.pseudosection_csv,
        "sections": list(section_titles(data)),
    }


def report_content_sha256(data: ReportData) -> str:
    """Return the canonical digest of the report content (not of any rendering)."""
    canonical = json.dumps(
        _canonical_payload(data), sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _iso_timestamp(data: ReportData) -> str:
    return data.generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def report_manifest(data: ReportData) -> dict[str, object]:
    """Return the machine-readable form of a report, including its digest."""
    payload = _canonical_payload(data)
    digest = report_content_sha256(data)
    return {
        "report_format_version": "nix-ert-report-v2",
        "title": data.title,
        "generated_at": _iso_timestamp(data),
        "content_sha256": digest,
        "sections": [
            {"number": index, "title": title, "anchor": f"section-{index}"}
            for index, title in enumerate(section_titles(data), start=1)
        ],
        **{key: value for key, value in payload.items() if key not in {"title", "generated_at", "sections"}},
    }


def _section_body(key: str, value: object) -> str:
    """Render one section from structured data, never inventing content."""
    if key == "limitations":
        return _list(value if isinstance(value, (list, tuple)) else (), empty=EMPTY_NOTES[key])
    if isinstance(value, Mapping):
        rows = [{"Metric": str(name), "Value": item} for name, item in value.items()]
        return _table(rows, empty=EMPTY_NOTES.get(key))
    if isinstance(value, (list, tuple)):
        records = [
            dict(entry) if isinstance(entry, Mapping) else {"Statement": entry}
            for entry in value
        ]
        return _table(records, empty=EMPTY_NOTES.get(key))
    return _table([], empty=EMPTY_NOTES.get(key))


def render_html(data: ReportData) -> str:
    generated = _iso_timestamp(data)
    digest = report_content_sha256(data)
    titles = section_titles(data)
    contents = "".join(
        f'<li><a href="#section-{index}">{html.escape(title)}</a></li>'
        for index, title in enumerate(titles, start=1)
    )
    sections = [
        f'<section class="cover"><h1>{html.escape(data.title)}</h1>'
        f"<p>Generated: {html.escape(generated)}</p>"
        f"<p>NiX ERT structured technical report</p></section>",
        f'<section class="contents"><h2>Contents</h2><ol>{contents}</ol></section>',
    ]
    index = 0
    for key, title in TABLE_SECTIONS:
        index += 1
        sections.append(
            f'<section id="section-{index}"><h2>{index}. {html.escape(title)}</h2>'
            f"{_section_body(key, getattr(data, key))}</section>"
        )
    if data.pseudosection_csv is not None:
        index += 1
        sections.append(
            f'<section id="section-{index}"><h2>{index}. Pseudosection data appendix</h2>'
            f"<pre>{html.escape(data.pseudosection_csv)}</pre></section>"
        )
    if data.appendices:
        index += 1
        sections.append(
            f'<section id="section-{index}"><h2>{index}. Appendices</h2>'
            + "".join(f"<pre>{html.escape(text)}</pre>" for text in data.appendices)
            + "</section>"
        )
    footer = (
        f'<footer><p>Report content SHA-256: <code>{digest}</code></p>'
        f"<p>NiX ERT structured technical report</p></footer>"
    )
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>%s</title>
<style>
body{font-family:Arial,sans-serif;color:#20252b;max-width:1100px;margin:2rem auto;line-height:1.45}
h1{font-size:2.2rem}.cover{border-bottom:3px solid #234e70;padding:3rem 0;margin-bottom:2rem}
.contents{break-after:page}section{break-inside:avoid;margin:2rem 0}
h2{color:#234e70;border-bottom:1px solid #c8d2dc;padding-bottom:.3rem}
table{border-collapse:collapse;width:100%%}th,td{border:1px solid #c8d2dc;padding:.45rem;text-align:left}th{background:#edf3f7}
pre{white-space:pre-wrap;background:#f5f7f8;padding:1rem;overflow:auto}.empty{color:#68737d;font-style:italic}
footer{margin-top:3rem;border-top:1px solid #c8d2dc;color:#68737d;font-size:.85rem}
</style></head><body>%s%s</body></html>""" % (html.escape(data.title), "".join(sections), footer)


def render_csv(data: ReportData) -> str:
    """Return a flat `section,record,item,value` export with a stable row order."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(("section", "record", "item", "value"))
    for key, title in TABLE_SECTIONS:
        for row in _rows(title, getattr(data, key)):
            writer.writerow(
                (row["section"], row["record"], row["item"], _csv_value(row["value"]))
            )
    if data.pseudosection_csv is not None:
        writer.writerow(("Pseudosection data appendix", "", "csv", data.pseudosection_csv))
    for index, text in enumerate(data.appendices, start=1):
        writer.writerow(("Appendices", str(index), "", str(text)))
    writer.writerow(("Report identity", "", "content_sha256", report_content_sha256(data)))
    return buffer.getvalue()


def _csv_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True, default=str)
    return str(value)


def render_json(data: ReportData) -> str:
    return json.dumps(report_manifest(data), sort_keys=True, indent=2, default=str)


def _write(path: Path | str, text: str) -> Path:
    destination = Path(path)
    destination.write_text(text, encoding="utf-8", newline="\n")
    return destination


def write_html(data: ReportData, path: Path | str) -> None:
    _write(path, render_html(data))


def write_csv(data: ReportData, path: Path | str) -> None:
    _write(path, render_csv(data))


def write_json(data: ReportData, path: Path | str) -> None:
    _write(path, render_json(data))


def write_report(data: ReportData, path: Path | str) -> Path:
    """Write the report in the format implied by the path suffix.

    Unknown or missing suffixes are rejected rather than silently written as
    HTML, so an export never claims a format it does not produce.
    """
    suffix = Path(path).suffix.lower()
    if suffix in {".html", ".htm"}:
        write_html(data, path)
    elif suffix == ".pdf":
        write_pdf(data, path)
    elif suffix == ".csv":
        write_csv(data, path)
    elif suffix == ".json":
        write_json(data, path)
    else:
        raise ValueError(
            f"unsupported report export format {suffix or '(none)'}; "
            "use .html, .pdf, .csv, or .json"
        )
    return Path(path)


def write_pdf(data: ReportData, path: Path | str) -> None:
    """Write a simple multi-page PDF; HTML remains the canonical report.

    The PDF is a text rendering only: tables are flattened to text, images are
    not embedded, and the structured HTML/JSON artifacts remain authoritative.
    """
    try:
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("matplotlib is required for PDF reports") from exc
    destination = Path(path)
    with PdfPages(destination) as pdf:
        lines = render_html(data).replace("</p>", "</p>\n").splitlines()
        page: list[str] = []
        for line in lines:
            text = line.replace("<", " ").replace(">", " ").strip()
            if text and not text.startswith(("style", "body", "h1", "table", "th", "td", "pre")):
                page.append(text)
            if len(page) >= 38:
                _pdf_page(pdf, page)
                page = []
        if page:
            _pdf_page(pdf, page)


def _pdf_page(pdf: object, lines: Sequence[str]) -> None:
    import matplotlib.pyplot as plt
    figure = plt.figure(figsize=(8.27, 11.69))
    figure.text(0.08, 0.95, "\n".join(lines), va="top", family="DejaVu Sans", fontsize=9)
    pdf.savefig(figure)  # type: ignore[attr-defined]
    plt.close(figure)
