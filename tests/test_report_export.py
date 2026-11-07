"""Tests for the report export formats offered by the desktop shell."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from nix_ert.app.report_export import (
    DEFAULT_EXPORT_KEY,
    REPORT_EXPORT_FORMATS,
    dialog_filters,
    default_filename,
    format_by_key,
    format_for_suffix,
    populate_format_selector,
    resolve_export_path,
)
from nix_ert.reports.generator import ReportData, write_report


class _FakeSelector:
    """Minimal stand-in for a combo box, so the populating logic is testable."""

    def __init__(self) -> None:
        self.items: list[tuple[str, object]] = []
        self.current_index: int | None = None

    def addItem(self, text: str, userData: object = None) -> None:  # noqa: N802
        self.items.append((text, userData))

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802
        self.current_index = index


def _data() -> ReportData:
    return ReportData(
        title="Export fixture",
        project={"Client": "Acme"},
        generated_at="2026-09-14T00:00:00+00:00",
        provenance={"Software": "NiX ERT 0.1.0"},
    )


class ReportExportFormatTests(unittest.TestCase):
    def test_formats_cover_every_supported_export_suffix(self) -> None:
        suffixes = {item.suffix for item in REPORT_EXPORT_FORMATS}
        self.assertEqual(suffixes, {".html", ".pdf", ".csv", ".json"})
        self.assertEqual([item.key for item in REPORT_EXPORT_FORMATS], ["html", "pdf", "csv", "json"])
        self.assertEqual(format_by_key(DEFAULT_EXPORT_KEY).suffix, ".html")

    def test_dialog_filters_list_every_format(self) -> None:
        filters = dialog_filters()
        self.assertEqual(filters.count("(*."), len(REPORT_EXPORT_FORMATS))
        for item in REPORT_EXPORT_FORMATS:
            self.assertIn(f"{item.label} (*{item.suffix})", filters)

    def test_default_filename_carries_the_format_extension(self) -> None:
        self.assertEqual(default_filename("project-report", "json"), "project-report.json")
        self.assertEqual(default_filename("", "csv"), "project-report.csv")

    def test_unknown_format_key_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            format_by_key("docx")
        with self.assertRaises(ValueError):
            default_filename("report", "docx")

    def test_suffix_lookup_accepts_case_and_htm(self) -> None:
        self.assertEqual(format_for_suffix(".JSON").key, "json")
        self.assertEqual(format_for_suffix("csv").key, "csv")
        self.assertEqual(format_for_suffix(".htm").key, "html")
        self.assertIsNone(format_for_suffix(".docx"))

    def test_populating_a_selector_selects_the_default(self) -> None:
        selector = _FakeSelector()
        populate_format_selector(selector)
        self.assertEqual([key for _, key in selector.items], ["html", "pdf", "csv", "json"])
        self.assertEqual(selector.current_index, 0)
        self.assertEqual(
            [label for label, _ in selector.items],
            [item.label for item in REPORT_EXPORT_FORMATS],
        )


class ResolveExportPathTests(unittest.TestCase):
    def test_missing_suffix_gets_the_selected_extension(self) -> None:
        path, chosen = resolve_export_path(Path("reports/site"), "json")
        self.assertEqual(path.name, "site.json")
        self.assertEqual(chosen.key, "json")

    def test_explicit_supported_suffix_wins(self) -> None:
        path, chosen = resolve_export_path("/tmp/site.csv", "html")
        self.assertEqual(path.name, "site.csv")
        self.assertEqual(chosen.key, "csv")

    def test_explicit_unsupported_suffix_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            resolve_export_path("site.docx", "html")
        with self.assertRaises(ValueError):
            resolve_export_path("site", "docx")


class ExportIntegrationTests(unittest.TestCase):
    def test_every_offered_format_is_written_by_the_report_writer(self) -> None:
        """The UI's format list and the writer must agree."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for item in REPORT_EXPORT_FORMATS:
                path, chosen = resolve_export_path(root / "site", item.key)
                self.assertEqual(chosen.key, item.key)
                try:
                    written = write_report(_data(), path)
                except RuntimeError as exc:  # matplotlib-only PDF dependency
                    self.assertIn("matplotlib is required", str(exc))
                    continue
                self.assertEqual(written, path)
                self.assertTrue(path.is_file(), item.key)
                self.assertGreater(path.stat().st_size, 0, item.key)


class QtSelectorTests(unittest.TestCase):
    def test_real_combo_box_is_populated_with_format_keys(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication, QComboBox
        except ImportError:  # pragma: no cover - optional desktop dependency
            self.skipTest("PySide6 is not installed")
        application = QApplication.instance() or QApplication([])
        self.assertIsNotNone(application)
        combo = QComboBox()
        populate_format_selector(combo)
        self.assertEqual(combo.count(), len(REPORT_EXPORT_FORMATS))
        self.assertEqual(combo.currentData(), DEFAULT_EXPORT_KEY)
        self.assertEqual(
            [combo.itemData(index) for index in range(combo.count())],
            [item.key for item in REPORT_EXPORT_FORMATS],
        )


if __name__ == "__main__":
    unittest.main()
