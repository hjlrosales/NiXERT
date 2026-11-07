"""Offscreen end-to-end smoke test of the desktop report export path.

The format registry, the writer and the combo box are tested separately in
``tests/test_report_export.py``. This module drives the real shell with a
persisted project, clicking the actual export button, so the operator's path is
exercised: chosen format -> button -> save-dialog path -> suffix resolution ->
written file -> reported digest, including the refusal paths.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from nix_ert.app.report_export import REPORT_EXPORT_FORMATS

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

DAT = """6
1
Wenner
0
1 2 3 4 100
1 3 4 6 120
2 4 5 6 90
1 4 2 3 110
2 5 3 4 105
3 6 4 5 95
"""

DIGEST = re.compile(r"Report content SHA-256: ([0-9a-f]{64})")


@dataclass
class _Message:
    kind: str
    title: str
    text: str


class _MessageBoxRecorder:
    """Stand-in for QMessageBox so a refusal is recorded instead of shown modally."""

    def __init__(self) -> None:
        self.calls: list[_Message] = []

    def warning(self, parent: object, title: str, text: str) -> None:
        self.calls.append(_Message("warning", title, text))

    def critical(self, parent: object, title: str, text: str) -> None:
        self.calls.append(_Message("critical", title, text))

    def information(self, parent: object, title: str, text: str) -> None:
        self.calls.append(_Message("information", title, text))


@pytest.fixture()
def shell(tmp_path: Path):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from nix_ert.app.main import MainWindow
    from nix_ert.app.workflow import ERTWorkflow
    from nix_ert.data.models import ProjectMetadata, SurveyType
    from nix_ert.data.project import ProjectManager

    application = QApplication.instance() or QApplication([])
    assert application is not None

    project_root = tmp_path / "project"
    project_root.mkdir()
    manager = ProjectManager()
    manager.create_project(project_root, ProjectMetadata("Smoke project", location="Test site"))
    store = manager.store
    assert store is not None
    survey = store.add_survey("Line 1", SurveyType.ERT)
    source = tmp_path / "line.dat"
    source.write_text(DAT, encoding="utf-8")
    workflow = ERTWorkflow(store)
    workflow.select_survey(survey.id)
    workflow.import_dat(source)

    window = MainWindow(manager)
    messages = _MessageBoxRecorder()
    window._message_box = messages
    window.refresh()
    window.select_survey(0)
    assert window.workflow is not None

    try:
        yield window, messages, tmp_path
    finally:
        window.workflow = None
        window.ves_workflow = None
        window._executor.shutdown(wait=True)
        window.deleteLater()
        manager.close()


def _export(window) -> None:
    """Click the export button exactly as the operator would."""
    assert window.report_button.isEnabled(), "the export button must be enabled"
    window.report_button.click()


def _select_format(window, key: str) -> None:
    index = next(
        position for position, item in enumerate(REPORT_EXPORT_FORMATS) if item.key == key
    )
    window.report_format.setCurrentIndex(index)


def _answer_dialog(monkeypatch: pytest.MonkeyPatch, target: Path | str) -> list[dict[str, str]]:
    """Answer the save dialog, recording the arguments the shell supplied."""
    from PySide6.QtWidgets import QFileDialog

    calls: list[dict[str, str]] = []

    def fake(parent: object, caption: str, directory: str, filters: str) -> tuple[str, str]:
        calls.append({"caption": caption, "directory": directory, "filters": filters})
        return (str(target), "")

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(fake))
    return calls


class TestExportFromTheShell:
    @pytest.mark.parametrize("key", ["html", "csv", "json"])
    def test_selected_format_is_written_and_reported(
        self, shell, monkeypatch: pytest.MonkeyPatch, key: str
    ) -> None:
        window, messages, root = shell
        item = next(entry for entry in REPORT_EXPORT_FORMATS if entry.key == key)
        target = root / f"exported{item.suffix}"
        _select_format(window, key)
        _answer_dialog(monkeypatch, target)

        _export(window)

        assert messages.calls == []
        assert target.is_file() and target.stat().st_size > 0
        report = window.report_output.toPlainText()
        assert f"Format: {item.label}" in report
        assert f"Written: {target}" in report
        assert DIGEST.search(report) is not None
        assert "Smoke project" in report

    def test_dialog_cancellation_writes_nothing(
        self, shell, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        window, messages, root = shell
        _answer_dialog(monkeypatch, "")

        _export(window)

        assert messages.calls == []
        assert list(root.glob("*.html")) == []
        assert window.report_output.toPlainText() == ""

    def test_missing_suffix_takes_the_selected_extension(
        self, shell, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        window, messages, root = shell
        _select_format(window, "json")
        calls = _answer_dialog(monkeypatch, root / "no-extension")

        _export(window)

        assert messages.calls == []
        written = root / "no-extension.json"
        assert written.is_file()
        assert "JSON manifest" in window.report_output.toPlainText()
        # The shell's own suggestion and filter list must follow the selection.
        assert calls[0]["caption"] == "Export current project report"
        assert calls[0]["directory"] == "project-report.json"
        for item in REPORT_EXPORT_FORMATS:
            assert f"{item.label} (*{item.suffix})" in calls[0]["filters"]

    def test_typed_suffix_wins_over_the_selected_format(
        self, shell, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        window, messages, root = shell
        _select_format(window, "html")
        target = root / "typed.csv"
        _answer_dialog(monkeypatch, target)

        _export(window)

        assert messages.calls == []
        assert target.is_file()
        report = window.report_output.toPlainText()
        assert "Format: CSV data export" in report
        assert not (root / "typed.csv.html").exists()

    def test_unsupported_suffix_is_refused_without_writing(
        self, shell, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        window, messages, root = shell
        _select_format(window, "html")
        target = root / "report.docx"
        _answer_dialog(monkeypatch, target)

        _export(window)

        assert [call.kind for call in messages.calls] == ["warning"]
        assert "unsupported report export format" in messages.calls[0].text
        assert not target.exists()
        assert window.report_output.toPlainText() == ""

    def test_pdf_export_succeeds_or_reports_the_missing_dependency(
        self, shell, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        window, messages, root = shell
        target = root / "report.pdf"
        _select_format(window, "pdf")
        _answer_dialog(monkeypatch, target)

        _export(window)

        try:
            import matplotlib  # noqa: F401
        except ImportError:
            assert [call.kind for call in messages.calls] == ["warning"]
            assert "matplotlib is required" in messages.calls[0].text
            assert not target.exists()
            return
        assert messages.calls == []
        assert target.is_file() and target.stat().st_size > 0
        report = window.report_output.toPlainText()
        assert "text-only rendering" in report
        assert DIGEST.search(report) is not None

    def test_repeated_exports_keep_the_format_selector_and_report_independent(
        self, shell, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        window, messages, root = shell
        for key in ("html", "json"):
            item = next(entry for entry in REPORT_EXPORT_FORMATS if entry.key == key)
            target = root / f"second{item.suffix}"
            _select_format(window, key)
            _answer_dialog(monkeypatch, target)
            _export(window)
            assert messages.calls == []
            assert target.is_file()
            assert f"Format: {item.label}" in window.report_output.toPlainText()
