"""Report export formats offered by the desktop shell.

The UI never decides how a report is written: it only collects a path and the
operator's format choice, and this module maps that choice to the existing
suffix-dispatched writer in :func:`nix_ert.reports.generator.write_report`. That
keeps the format list, the dialog filters, and the written file in agreement, so
the shell cannot claim a format it does not produce.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ReportExportFormat:
    """One selectable export format."""

    key: str
    label: str
    suffix: str
    description: str

    @property
    def dialog_filter(self) -> str:
        return f"{self.label} (*{self.suffix})"


REPORT_EXPORT_FORMATS: tuple[ReportExportFormat, ...] = (
    ReportExportFormat("html", "HTML report", ".html", "Canonical printed report"),
    ReportExportFormat("pdf", "PDF report", ".pdf", "Text-only PDF rendering"),
    ReportExportFormat("csv", "CSV data export", ".csv", "Flat section/item/value rows"),
    ReportExportFormat("json", "JSON manifest", ".json", "Machine-readable report manifest"),
)
"""Formats in menu order; every suffix is supported by ``write_report``."""

DEFAULT_EXPORT_KEY = "html"


class FormatSelector(Protocol):
    """The subset of a combo box this module populates."""

    def addItem(self, text: str, userData: object = ...) -> None: ...  # noqa: N802

    def setCurrentIndex(self, index: int) -> None: ...  # noqa: N802


def dialog_filters() -> str:
    """Return the Qt save-dialog filter string for every offered format."""
    return ";;".join(item.dialog_filter for item in REPORT_EXPORT_FORMATS)


def format_by_key(key: str) -> ReportExportFormat:
    for item in REPORT_EXPORT_FORMATS:
        if item.key == key:
            return item
    raise ValueError(
        f"unknown report export format {key!r}; choose one of "
        + ", ".join(item.key for item in REPORT_EXPORT_FORMATS)
    )


def format_for_suffix(suffix: str) -> ReportExportFormat | None:
    normalised = suffix.lower() if suffix.startswith(".") else f".{suffix.lower()}"
    for item in REPORT_EXPORT_FORMATS:
        if item.suffix == normalised or (normalised == ".htm" and item.suffix == ".html"):
            return item
    return None


def default_filename(stem: str, key: str) -> str:
    """Return the suggested file name for a format, with its extension."""
    return f"{stem.strip() or 'project-report'}{format_by_key(key).suffix}"


def resolve_export_path(path: str | Path, selected_key: str) -> tuple[Path, ReportExportFormat]:
    """Return the destination and the format it will actually be written as.

    A path with no suffix gets the selected format's extension. A path with a
    supported suffix keeps that suffix, because the operator typed it explicitly
    and the writer dispatches on it. An unsupported suffix is refused rather than
    silently replaced.
    """
    selected = format_by_key(selected_key)
    destination = Path(path)
    if not destination.suffix:
        destination = destination.with_name(destination.name + selected.suffix)
        return destination, selected
    resolved = format_for_suffix(destination.suffix)
    if resolved is None:
        raise ValueError(
            f"unsupported report export format {destination.suffix!r}; choose "
            + ", ".join(item.suffix for item in REPORT_EXPORT_FORMATS)
        )
    return destination, resolved


def populate_format_selector(selector: FormatSelector) -> None:
    """Fill a combo box with every format and select the default."""
    for item in REPORT_EXPORT_FORMATS:
        selector.addItem(item.label, item.key)
    selector.setCurrentIndex(
        next(
            index
            for index, item in enumerate(REPORT_EXPORT_FORMATS)
            if item.key == DEFAULT_EXPORT_KEY
        )
    )
