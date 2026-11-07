"""NiX ERT desktop entry point and workflow shell."""

from __future__ import annotations

import sys
from pathlib import Path

from nix_ert import __version__
from nix_ert.ai.assistant import AdvisoryAssistant, ProjectContext
from nix_ert.app.operations import OperationCancelled, OperationExecutor, OperationHandle
from nix_ert.app.report_export import (
    dialog_filters,
    default_filename,
    populate_format_selector,
    resolve_export_path,
)
from nix_ert.app.workflow import ERTWorkflow, VESWorkflow, WorkflowError
from nix_ert.core.config import AppConfig
from nix_ert.core.logging import configure_logging
from nix_ert.data.ls2_connection import (
    LS2ConnectionState,
    LS2Session,
    LS2Status,
    LS2TransportKind,
    MockUSBTransport,
    MockWiFiTransport,
    UnsupportedUSBTransport,
    UnsupportedWiFiTransport,
)
from nix_ert.data.abem_sample import ABEMInspectionError, inspect_abem_project
from nix_ert.data.models import ProjectMetadata, SurveyType
from nix_ert.data.project import ProjectManager
from nix_ert.reports.generator import report_content_sha256
from nix_ert.ves.engine import LayeredEarthModel


def main(argv: list[str] | None = None) -> int:
    """Start the Qt application."""
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("PySide6 is required to run the NiX ERT desktop application") from exc

    args = sys.argv[1:] if argv is None else argv
    app = QApplication(["nix-ert", *args])
    configure_logging(Path.home() / ".nix-ert" / "logs")
    window = MainWindow(ProjectManager(AppConfig.load()))
    window.show()
    return app.exec()


def _qt_main_window_base():
    from PySide6.QtWidgets import QMainWindow
    return QMainWindow


class MainWindow(_qt_main_window_base()):  # pragma: no cover - visual behavior is manual
    """Project-to-report workflow shell backed by existing domain services."""

    def __init__(self, manager: ProjectManager):
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import (
            QComboBox,
            QFormLayout,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QListWidget,
            QMessageBox,
            QPushButton,
            QTabWidget,
            QTextEdit,
            QVBoxLayout,
            QWidget,
        )

        super().__init__()
        self.manager = manager
        self.workflow: ERTWorkflow | None = None
        self.ves_workflow: VESWorkflow | None = None
        self._executor = OperationExecutor()
        self._operation: OperationHandle | None = None
        self._operation_work = None
        self._ls2_sessions: dict[LS2TransportKind, LS2Session] = {}
        self._message_box = QMessageBox
        self.setWindowTitle(f"NiX ERT {__version__}")
        self.resize(1100, 760)

        project_menu = self.menuBar().addMenu("Project")
        for label, callback in (
            ("New Project…", self.new_project),
            ("Open Project…", self.open_project),
            ("Close Project", self.close_project),
        ):
            action = QAction(label, self)
            action.triggered.connect(callback)
            project_menu.addAction(action)
            if label == "Open Project…":
                project_menu.addSeparator()

        tabs = QTabWidget()

        project_tab = QWidget()
        project_layout = QVBoxLayout(project_tab)
        self.project_label = QLabel("No project open")
        self.project_label.setStyleSheet("font-size: 20px; font-weight: 600;")
        project_layout.addWidget(self.project_label)
        self.survey_list = QListWidget()
        self.survey_list.currentRowChanged.connect(self.select_survey)
        project_layout.addWidget(self.survey_list)
        project_buttons = QHBoxLayout()
        self.add_survey_button = QPushButton("Add survey")
        self.add_survey_button.clicked.connect(self.add_survey)
        project_buttons.addWidget(self.add_survey_button)
        self.import_dat_button = QPushButton("Import DAT")
        self.import_dat_button.clicked.connect(self.import_dat)
        project_buttons.addWidget(self.import_dat_button)
        self.barugo_ert_button = QPushButton("Inspect Barugo ERT Sample")
        self.barugo_ert_button.clicked.connect(self.inspect_barugo_ert)
        project_buttons.addWidget(self.barugo_ert_button)
        self.barugo_ves_button = QPushButton("Inspect Barugo VES Sample")
        self.barugo_ves_button.clicked.connect(self.inspect_barugo_ves)
        project_buttons.addWidget(self.barugo_ves_button)
        project_layout.addLayout(project_buttons)
        tabs.addTab(project_tab, "Project / Import")

        ls2_tab = QWidget()
        ls2_layout = QVBoxLayout(ls2_tab)
        ls2_layout.addWidget(QLabel(
            "Offline diagnostics only. No acquisition, settings changes, serial commands, port scans, or VNC access are performed."
        ))
        usb_row = QHBoxLayout()
        self.ls2_usb_status = QLabel("USB: disconnected")
        usb_row.addWidget(self.ls2_usb_status)
        usb_button = QPushButton("Check USB")
        usb_button.clicked.connect(self.check_ls2_usb)
        usb_row.addWidget(usb_button)
        usb_mock_button = QPushButton("Run MOCK/TEST USB")
        usb_mock_button.clicked.connect(self.check_ls2_usb_mock)
        usb_row.addWidget(usb_mock_button)
        ls2_layout.addLayout(usb_row)
        wifi_row = QHBoxLayout()
        self.ls2_wifi_address = QLineEdit("192.168.23.1")
        self.ls2_wifi_address.setPlaceholderText("User-supplied LS2 IP address")
        wifi_row.addWidget(self.ls2_wifi_address)
        self.ls2_wifi_status = QLabel("Wi-Fi: disconnected")
        wifi_row.addWidget(self.ls2_wifi_status)
        wifi_button = QPushButton("Check Wi-Fi")
        wifi_button.clicked.connect(self.check_ls2_wifi)
        wifi_row.addWidget(wifi_button)
        wifi_mock_button = QPushButton("Run MOCK/TEST Wi-Fi")
        wifi_mock_button.clicked.connect(self.check_ls2_wifi_mock)
        wifi_row.addWidget(wifi_mock_button)
        ls2_layout.addLayout(wifi_row)
        self.ls2_connection_detail = QTextEdit()
        self.ls2_connection_detail.setReadOnly(True)
        self.ls2_connection_detail.setPlainText(
            "Status: disconnected\\n"
            "Protocol unknown — do not implement communication.\\n"
            "Hardware validation required before any future read-only test."
        )
        ls2_layout.addWidget(self.ls2_connection_detail)
        ls2_layout.addWidget(QLabel(
            "Required future sequence: Connect → Detect → Identify → Verify documented communication → Stop."
        ))
        tabs.addTab(ls2_tab, "LS2 Connection")

        workflow_tab = QWidget()
        workflow_layout = QVBoxLayout(workflow_tab)
        self.workflow_state = QLabel("Select an imported survey to begin.")
        self.workflow_state.setWordWrap(True)
        workflow_layout.addWidget(self.workflow_state)
        action_row = QHBoxLayout()
        self.qc_button = QPushButton("QC summary / flag")
        self.qc_button.clicked.connect(self.run_qc)
        action_row.addWidget(self.qc_button)
        self.process_button = QPushButton("Process active data")
        self.process_button.clicked.connect(self.process_data)
        action_row.addWidget(self.process_button)
        self.invert_button = QPushButton("Run 2D baseline inversion")
        self.invert_button.clicked.connect(self.invert_data)
        action_row.addWidget(self.invert_button)
        self.cancel_button = QPushButton("Cancel inversion")
        self.cancel_button.clicked.connect(self.cancel_operation)
        self.cancel_button.setEnabled(False)
        action_row.addWidget(self.cancel_button)
        self.inspect_measurements_button = QPushButton("Inspect measurements")
        self.inspect_measurements_button.clicked.connect(self.inspect_measurements)
        action_row.addWidget(self.inspect_measurements_button)
        self.visualize_button = QPushButton("Visualize selected 2D model")
        self.visualize_button.clicked.connect(self.visualize_model)
        action_row.addWidget(self.visualize_button)
        self.visualize_3d_button = QPushButton("Inspect 3D output status")
        self.visualize_3d_button.clicked.connect(self.inspect_3d_model)
        action_row.addWidget(self.visualize_3d_button)
        workflow_layout.addLayout(action_row)
        self.workflow_output = QTextEdit()
        self.workflow_output.setReadOnly(True)
        self.workflow_output.setPlaceholderText("Workflow status, QC, processing, inversion, model, and measurement semantics.")
        workflow_layout.addWidget(self.workflow_output)
        from PySide6.QtCore import QTimer
        self._operation_timer = QTimer(self)
        self._operation_timer.setInterval(100)
        self._operation_timer.timeout.connect(self.poll_operation)
        tabs.addTab(workflow_tab, "QC / Process / Invert / Visualize")

        interpretation_tab = QWidget()
        interpretation_layout = QVBoxLayout(interpretation_tab)
        interpretation_layout.addWidget(QLabel("Interpretation is advisory and does not establish geological certainty."))
        self.interpretation_input = QTextEdit()
        self.interpretation_input.setPlaceholderText("Optional interpretation notes for the report…")
        interpretation_layout.addWidget(self.interpretation_input)
        report_format_row = QHBoxLayout()
        report_format_row.addWidget(QLabel("Export format:"))
        self.report_format = QComboBox()
        populate_format_selector(self.report_format)
        self.report_format.setToolTip(
            "HTML and JSON are the authoritative artifacts; the PDF is a text "
            "rendering and the CSV is a flat data export."
        )
        report_format_row.addWidget(self.report_format, 1)
        interpretation_layout.addLayout(report_format_row)
        self.report_button = QPushButton("Export current project report…")
        self.report_button.clicked.connect(self.generate_report)
        interpretation_layout.addWidget(self.report_button)
        self.report_output = QTextEdit()
        self.report_output.setReadOnly(True)
        interpretation_layout.addWidget(self.report_output)
        tabs.addTab(interpretation_tab, "Interpret / Report")

        ves_tab = QWidget()
        ves_layout = QVBoxLayout(ves_tab)
        ves_layout.addWidget(QLabel(
            "VES workflow: enter or paste AB/2, MN/2, resistance[, apparent resistivity]. "
            "The curve and inversion are persisted as version snapshots."
        ))
        self.ves_input = QTextEdit()
        self.ves_input.setPlaceholderText("AB/2,MN/2,resistance[,apparent_resistivity]\\n10,2,3\\n20,2,4")
        ves_layout.addWidget(self.ves_input)
        ves_buttons = QHBoxLayout()
        self.ves_import_button = QPushButton("Load VES curve")
        self.ves_import_button.clicked.connect(self.load_ves_curve)
        ves_buttons.addWidget(self.ves_import_button)
        self.ves_process_button = QPushButton("Persist VES curve")
        self.ves_process_button.clicked.connect(self.process_ves)
        ves_buttons.addWidget(self.ves_process_button)
        self.ves_invert_button = QPushButton("Run 1D inversion")
        self.ves_invert_button.clicked.connect(self.invert_ves)
        ves_buttons.addWidget(self.ves_invert_button)
        ves_layout.addLayout(ves_buttons)
        self.ves_output = QTextEdit()
        self.ves_output.setReadOnly(True)
        ves_layout.addWidget(self.ves_output)
        tabs.addTab(ves_tab, "VES")

        assistant_tab = QWidget()
        assistant_layout = QVBoxLayout(assistant_tab)
        self.assistant_output = QTextEdit()
        self.assistant_output.setReadOnly(True)
        self.assistant_output.setPlaceholderText("Advisory project analysis will appear here.")
        assistant_layout.addWidget(self.assistant_output)
        query_row = QHBoxLayout()
        self.assistant_query_input = QLineEdit()
        self.assistant_query_input.setPlaceholderText("Ask about QC, anomalies, models, surveys, or reports…")
        self.assistant_query_input.returnPressed.connect(self.run_assistant_query)
        query_row.addWidget(self.assistant_query_input)
        assistant_button = QPushButton("Ask assistant")
        assistant_button.clicked.connect(self.run_assistant_query)
        query_row.addWidget(assistant_button)
        assistant_layout.addLayout(query_row)
        tabs.addTab(assistant_tab, "Assistant")

        self.setCentralWidget(tabs)
        self.refresh()

    def _cancel_running_operation(self) -> None:
        if self._operation is not None:
            self._operation.cancel()
            self._operation_timer.stop()
            self._executor.shutdown(wait=True)
            self._operation = None
            self._operation_work = None
            self._executor = OperationExecutor()

    def check_ls2_usb(self) -> None:
        session = LS2Session(UnsupportedUSBTransport())
        self._ls2_sessions[LS2TransportKind.USB] = session
        self._show_ls2_status(session.connect())

    def check_ls2_usb_mock(self) -> None:
        self._run_ls2_mock(LS2TransportKind.USB)

    def check_ls2_wifi(self) -> None:
        try:
            session = LS2Session(UnsupportedWiFiTransport(self.ls2_wifi_address.text()))
        except ValueError as exc:
            self._show_ls2_text(LS2TransportKind.WIFI, LS2ConnectionState.ERROR, str(exc))
            return
        self._ls2_sessions[LS2TransportKind.WIFI] = session
        self._show_ls2_status(session.connect())

    def check_ls2_wifi_mock(self) -> None:
        self._run_ls2_mock(LS2TransportKind.WIFI)

    def _run_ls2_mock(self, transport: LS2TransportKind) -> None:
        if transport is LS2TransportKind.USB:
            session = LS2Session(MockUSBTransport())
        else:
            try:
                session = LS2Session(MockWiFiTransport(self.ls2_wifi_address.text()))
            except ValueError as exc:
                self._show_ls2_text(transport, LS2ConnectionState.ERROR, str(exc))
                return
        self._ls2_sessions[transport] = session
        session.connect()
        session.detect()
        session.identify()
        self._show_ls2_status(session.verify_documented_communication())

    def _show_ls2_status(self, status: LS2Status) -> None:
        label = self.ls2_usb_status if status.transport is LS2TransportKind.USB else self.ls2_wifi_status
        label.setText(f"{status.transport.value}: {status.state.value}")
        lines = [
            f"Transport: {status.transport.value}",
            f"Status: {status.state.value}",
            f"Detail: {status.detail}",
            f"Identity: {status.identity or 'not available'}",
            f"Address: {status.address or 'not available'}",
            f"Mock/TEST: {'yes' if status.mock else 'no'}",
            "No acquisition or instrument mutation was performed.",
        ]
        self.ls2_connection_detail.setPlainText("\\n".join(lines))

    def _show_ls2_text(self, transport: LS2TransportKind, state: LS2ConnectionState, detail: str) -> None:
        label = self.ls2_usb_status if transport is LS2TransportKind.USB else self.ls2_wifi_status
        label.setText(f"{transport.value}: {state.value}")
        self.ls2_connection_detail.setPlainText(
            f"Transport: {transport.value}\\nStatus: {state.value}\\nDetail: {detail}\\n"
            "No acquisition or instrument mutation was performed."
        )

    def new_project(self) -> None:
        self._cancel_running_operation()
        from PySide6.QtWidgets import QFileDialog, QInputDialog
        directory = QFileDialog.getExistingDirectory(self, "Choose project directory")
        if not directory:
            return
        name, accepted = QInputDialog.getText(self, "New Project", "Project name:")
        if accepted and name.strip():
            try:
                self.manager.create_project(directory, ProjectMetadata(name=name.strip()))
                self.refresh()
            except (OSError, ValueError) as exc:
                self._message_box.critical(self, "New project failed", str(exc))

    def open_project(self) -> None:
        self._cancel_running_operation()
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Open NiX ERT project", "", "NiX ERT (*.sqlite3)")
        if path:
            try:
                self.manager.open_project(path)
                self.refresh()
            except (OSError, ValueError) as exc:
                self._message_box.critical(self, "Open project failed", str(exc))

    def close_project(self) -> None:
        self._cancel_running_operation()
        self.manager.close()
        self.workflow = None
        self.ves_workflow = None
        self.refresh()

    def add_survey(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        if self.manager.store is None:
            return
        name, accepted = QInputDialog.getText(self, "Add survey", "Survey name:")
        if not accepted or not name.strip():
            return
        survey_type, accepted = QInputDialog.getItem(
            self, "Survey type", "Type:", [item.value for item in SurveyType], 0, False
        )
        if accepted:
            self.manager.store.add_survey(name, SurveyType(survey_type))
            self.refresh()

    def select_survey(self, row: int) -> None:
        if self._operation is not None:
            self._cancel_running_operation()
        if self.manager.store is None:
            self.workflow = None
            self.refresh_buttons()
            return
        surveys = self.manager.store.list_surveys()
        if row < 0 or row >= len(surveys):
            self.workflow = None
            self.refresh_buttons()
            return
        previous_version = (
            self.workflow.selected_version_id
            if self.workflow is not None and self.workflow.survey_id == surveys[row].id
            else None
        )
        if surveys[row].survey_type is SurveyType.VES:
            self.workflow = None
            self.ves_workflow = VESWorkflow(self.manager.store)
            self.ves_workflow.select_survey(surveys[row].id)
        else:
            self.ves_workflow = None
            self.workflow = ERTWorkflow(self.manager.store)
            self.workflow.select_survey(surveys[row].id)
            self.workflow.selected_version_id = previous_version
        self.update_workflow_state()
        self.refresh_buttons()

    def inspect_barugo_ert(self) -> None:
        self._inspect_barugo_sample("Barugo ERT", "ERT Survey Data/Project7/project.db")

    def inspect_barugo_ves(self) -> None:
        self._inspect_barugo_sample("Barugo VES", "VES Survey Data/Project8/project.db")

    def _inspect_barugo_sample(self, label: str, relative_path: str) -> None:
        """Display real user-provided ABEM facts without importing or writing them."""
        from PySide6.QtWidgets import QFileDialog
        default = Path("D:/This PC/Documents/ABEM Georesistivity/Barugo Georesistivity Survey") / relative_path
        path = default if default.is_file() else None
        if path is None:
            selected, _ = QFileDialog.getOpenFileName(
                self, f"Select {label} project.db (read-only)", "", "SQLite database (*.db);;All files (*)"
            )
            if not selected:
                return
            path = Path(selected)
        try:
            inspection = inspect_abem_project(path, label=label)
        except (OSError, ABEMInspectionError, ValueError) as exc:
            self._message_box.warning(self, f"{label} inspection unavailable", str(exc))
            return
        self.workflow_output.setPlainText(inspection.summary())
        self._message_box.information(
            self, f"{label} inspected",
            "The source was opened read-only. It was not imported, migrated, copied, or treated as live LS2 data.\n\n"
            + inspection.summary(),
        )

    def import_dat(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        if self.workflow is None:
            self._message_box.warning(self, "Import DAT", "Select an ERT survey first.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Import DAT file", "", "DAT files (*.dat *.DAT);;All files (*)")
        if not path:
            return
        try:
            result = self.workflow.import_dat(path)
        except (OSError, ValueError, WorkflowError) as exc:
            self._message_box.critical(self, "Import DAT failed", str(exc))
            return
        self._message_box.information(
            self, "DAT imported",
            f"{result.dataset.source_name} validated and preserved.\n"
            f"Measurements: {result.dataset.data_count}\n"
            f"Array: {result.dataset.array_type}\n"
            f"Non-positive values retained for QC: {result.dataset.invalid_measurement_count}",
        )
        self.update_workflow_state()
        self.refresh()

    def run_qc(self) -> None:
        if self.workflow is None:
            return
        try:
            stats_before = self.workflow.qc_statistics()
            flagged = self.workflow.flag_detected()
            stats = self.workflow.qc_statistics()
            self.workflow_output.setPlainText(
                f"QC: total={stats.total}, active={stats.active}, flagged={stats.flagged}, "
                f"excluded={stats.excluded}, invalid={stats.invalid}, duplicates={stats.duplicate}\n"
                f"Detected rows marked FLAGGED: {flagged} (previously flagged: {stats_before.flagged})\n\n"
                "QC flags are review triggers. No raw data was changed or deleted."
            )
            self.update_workflow_state()
        except (ValueError, WorkflowError) as exc:
            self.show_workflow_error(exc)

    def process_data(self) -> None:
        if self.workflow is None:
            return
        try:
            version = self.workflow.process_ert()
            self.workflow_output.setPlainText(
                f"Processing version created: {version.name}\nID: {version.id}\n"
                "The active/excluded working state was snapshotted; raw data remains immutable."
            )
            self.update_workflow_state()
        except (ValueError, WorkflowError) as exc:
            self.show_workflow_error(exc)

    def invert_data(self) -> None:
        if self.workflow is None:
            return
        if self._operation is not None:
            self.show_workflow_error(RuntimeError("An inversion is already running"))
            return
        try:
            self._operation, self._operation_work = self.workflow.start_invert_2d(
                self._executor, max_iterations=3
            )
            self.workflow_output.setPlainText(
                "2D baseline inversion is running on a detached snapshot.\n"
                "The project will be changed only after successful completion and input revalidation.\n"
                "Cancellation stops the commit; the last valid model/version is preserved."
            )
            self.cancel_button.setEnabled(True)
            self.invert_button.setEnabled(False)
            self._operation_timer.start()
        except (ValueError, WorkflowError) as exc:
            self.show_workflow_error(exc)

    def cancel_operation(self) -> None:
        if self._operation is not None:
            self._operation.cancel()
            self.workflow_output.setPlainText(
                "Cancellation requested. The detached computation will not be committed."
            )

    def poll_operation(self) -> None:
        if self._operation is None:
            self._operation_timer.stop()
            return
        snapshot = self._operation.snapshot()
        if snapshot.state in {"running", "cancelling"}:
            progress = "unknown" if snapshot.progress is None else f"{snapshot.progress:.0%}"
            self.workflow_output.setPlainText(
                f"{snapshot.name}: {snapshot.state} ({progress})\n"
                f"{snapshot.detail or 'Computing detached result'}\n"
                f"Elapsed: {snapshot.elapsed_seconds:.1f} s; iteration: {snapshot.iteration or '—'}\n"
                "Cancel is safe: no partial model/version is written."
            )
            return
        handle = self._operation
        work = self._operation_work
        self._operation = None
        self._operation_work = None
        self._operation_timer.stop()
        self.cancel_button.setEnabled(False)
        self.invert_button.setEnabled(self.workflow is not None)
        try:
            if snapshot.state == "cancelled":
                self.workflow_output.setPlainText(
                    "2D inversion cancelled before persistence. The last valid model/version was preserved."
                )
                return
            if snapshot.state == "failed":
                raise RuntimeError(snapshot.error or "2D inversion failed")
            if self.workflow is None or work is None:
                raise WorkflowError("The selected workflow is no longer available")
            result = handle.future.result()
            self.workflow.commit_inversion(result, work)
            self.workflow_output.setPlainText(
                f"2D baseline inversion completed: {result.message}\n"
                f"RMS log10: {result.rms_log10:.6g}\nRMS percent: {result.rms_percent:.4g}\n\n"
                "This is a bounded finite-volume baseline, not RES2DINV equivalence or geological certainty."
            )
            self.update_workflow_state()
        except (OperationCancelled, ValueError, WorkflowError, RuntimeError) as exc:
            self.show_workflow_error(exc)

    def visualize_model(self) -> None:
        if self.workflow is None:
            return
        try:
            section = self.workflow.selected_model_section()
            model = self.workflow.inspect_model()
            minimum, maximum = section.display_limits
            self.workflow_output.setPlainText(
                f"Selected 2D model: {model.name} ({model.version_id})\n"
                f"Cells: {model.cell_count}; resistivity: {model.resistivity_minimum:g} to {model.resistivity_maximum:g}\n"
                f"Iterations: {model.iteration_count or '—'}; RMS percent: {model.rms_percent!r}; converged: {model.converged!r}\n"
                f"Display range: {minimum:g} to {maximum:g}\n"
                "Depth is flat-coordinate model depth, not elevation. The section is a visualization of the stored baseline model.\n"
                "This is a visualization of a bounded numerical baseline, not a true 3D geological interpretation."
            )
        except (ValueError, WorkflowError) as exc:
            self.show_workflow_error(exc)

    def inspect_measurements(self) -> None:
        if self.workflow is None:
            return
        try:
            records = self.workflow.inspect_measurements()
            if not records:
                self.workflow_output.setPlainText("No measurements are persisted for this survey.")
                return
            lines = ["Source-aware measurement inspection:"]
            for item in records:
                reasons = "; ".join(item.suspicious_reasons) or "none"
                lines.append(
                    f"source={item.source_id or 'unscoped'} row={item.row_number} "
                    f"A/B/M/N={item.electrode_configuration} R={item.measured_resistance!r} "
                    f"rho_a={item.apparent_resistivity!r} status={item.status} "
                    f"note={item.exclusion_reason or '—'} suspicious={reasons}"
                )
            self.workflow_output.setPlainText("\n".join(lines))
        except (ValueError, WorkflowError) as exc:
            self.show_workflow_error(exc)


    def load_ves_curve(self) -> None:
        if self.ves_workflow is None:
            self.ves_output.setPlainText("Select a VES survey before loading a curve.")
            return
        try:
            points = self.ves_workflow.import_text(self.ves_input.toPlainText())
            self.ves_output.setPlainText(
                f"Loaded {len(points)} VES points.\\n"
                f"AB/2: {min(point.ab2 for point in points):g} to {max(point.ab2 for point in points):g}\\n"
                "Schlumberger half-spacing semantics are explicit; interpretation remains advisory."
            )
            self.update_workflow_state()
        except (ValueError, WorkflowError) as exc:
            self.show_workflow_error(exc)

    def process_ves(self) -> None:
        if self.ves_workflow is None:
            return
        try:
            version = self.ves_workflow.process()
            self.ves_output.setPlainText(f"VES curve version persisted: {version.id}\\nRaw input remains unchanged.")
        except (ValueError, WorkflowError) as exc:
            self.show_workflow_error(exc)

    def invert_ves(self) -> None:
        if self.ves_workflow is None:
            return
        try:
            if not self.ves_workflow.points:
                self.ves_workflow.import_text(self.ves_input.toPlainText())
            result = self.ves_workflow.invert(LayeredEarthModel((100.0, 20.0), (5.0,)), max_nfev=20)
            self.ves_output.setPlainText(
                "VES 1D inversion persisted.\\n"
                f"Layers: {result.model.resistivities}\\nThicknesses: {result.model.thicknesses}\\n"
                f"RMS log10: {result.rms_log10:.6g}; RMS percent: {result.rms_percent:.4g}\\n"
                "This is a bounded layered-earth fit, not unique geological truth."
            )
        except (ValueError, WorkflowError) as exc:
            self.show_workflow_error(exc)

    def inspect_3d_model(self) -> None:
        if self.workflow is None:
            return
        try:
            status = self.workflow.inspect_3d_status()
            self.workflow_output.setPlainText(
                f"3D model available: {status['available']}\\n{status['reason']}\\n"
                "A 3D visualization is not presented as a true 3D geological inversion."
            )
        except (ValueError, WorkflowError) as exc:
            self.show_workflow_error(exc)

    def generate_report(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        active_workflow = self.workflow or self.ves_workflow
        if active_workflow is None:
            return
        selected_format = str(self.report_format.currentData() or "html")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export current project report",
            default_filename("project-report", selected_format),
            dialog_filters(),
        )
        if not path:
            return
        notes = self.interpretation_input.toPlainText().strip()
        interpretation = {"User notes": notes} if notes else None
        try:
            destination, export_format = resolve_export_path(path, selected_format)
            data = active_workflow.report(destination, interpretation=interpretation)
            detail = (
                "PDF is a text-only rendering; HTML and JSON remain authoritative."
                if export_format.key == "pdf"
                else "Source hashes, QC state, software version, and selected model provenance were included."
            )
            self.report_output.setPlainText(
                f"Report exported from current project state:\n{data.title}\n"
                f"Format: {export_format.label} ({export_format.description})\n"
                f"Written: {destination}\n"
                f"Report content SHA-256: {report_content_sha256(data)}\n\n{detail}"
            )
        except (OSError, RuntimeError, ValueError, WorkflowError) as exc:
            self.show_workflow_error(exc)

    def run_assistant_query(self) -> None:
        query = self.assistant_query_input.text().strip()
        if not query:
            return
        if self.manager.store is None:
            self.assistant_output.setPlainText("Open a project before asking the advisory assistant.")
            return
        try:
            assistant = AdvisoryAssistant(ProjectContext.from_store(self.manager.store))
            response = assistant.query(query)
        except (KeyError, ValueError, RuntimeError) as exc:
            self.assistant_output.setPlainText(f"Assistant could not answer: {exc}")
            return
        lines = [response.answer, "", "Findings:"]
        lines.extend(f"• {finding.title}: {finding.detail}" for finding in response.findings)
        if not response.findings:
            lines.append("• None")
        lines.extend(["", "Limitations:"])
        lines.extend(f"• {limitation}" for limitation in response.limitations)
        self.assistant_output.setPlainText("\n".join(lines))

    def show_workflow_error(self, error: Exception) -> None:
        self._message_box.warning(self, "Workflow action unavailable", str(error))

    def update_workflow_state(self) -> None:
        if self.workflow is None and self.ves_workflow is None:
            self.workflow_state.setText("Select an imported survey to begin.")
            return
        if self.ves_workflow is not None:
            snapshot = self.ves_workflow.snapshot()
            self.workflow_state.setText(
                f"Project: {snapshot.project_name or 'unnamed'} | Survey: {snapshot.survey_name} | "
                f"VES points: {snapshot.point_count} | Processing: {snapshot.processing_state} | "
                f"Inversion: {snapshot.inversion_state}\\n" + " ".join(snapshot.semantics)
            )
            return
        snapshot = self.workflow.snapshot()
        self.workflow_state.setText(
            f"Project: {snapshot.project_name or 'unnamed'} | Survey: {snapshot.survey_name or 'none'} | "
            f"Sources: {snapshot.imported_sources} | Measurements: {snapshot.measurements} | "
            f"Active: {snapshot.active} | Flagged: {snapshot.flagged} | Excluded: {snapshot.excluded} | "
            f"Processing: {snapshot.processing_state} | Inversion: {snapshot.inversion_state}\n"
            + " ".join(snapshot.semantics)
        )

    def refresh_buttons(self) -> None:
        active = self.manager.store is not None
        selected = self.workflow is not None or self.ves_workflow is not None
        ert_selected = self.workflow is not None
        self.add_survey_button.setEnabled(active)
        self.import_dat_button.setEnabled(ert_selected)
        self.qc_button.setEnabled(ert_selected)
        self.process_button.setEnabled(ert_selected)
        self.inspect_measurements_button.setEnabled(ert_selected)
        self.invert_button.setEnabled(ert_selected and self._operation is None)
        self.visualize_button.setEnabled(ert_selected)
        self.visualize_3d_button.setEnabled(ert_selected)
        ves_selected = self.ves_workflow is not None
        self.ves_import_button.setEnabled(ves_selected)
        self.ves_process_button.setEnabled(ves_selected)
        self.ves_invert_button.setEnabled(ves_selected)
        self.cancel_button.setEnabled(self._operation is not None)
        self.report_button.setEnabled(selected)
        self.assistant_query_input.setEnabled(active)

    def closeEvent(self, event) -> None:
        self._cancel_running_operation()
        self._executor.shutdown(wait=True)
        self.manager.close()
        event.accept()

    def refresh(self) -> None:
        selected_id = (
            self.workflow.survey_id if self.workflow is not None
            else self.ves_workflow.survey_id if self.ves_workflow is not None else None
        )
        active = self.manager.store is not None
        self.survey_list.blockSignals(True)
        self.survey_list.clear()
        if not active:
            self.survey_list.blockSignals(False)
            self.project_label.setText("No project open")
            self.workflow = None
            self.ves_workflow = None
            self.update_workflow_state()
            self.refresh_buttons()
            return
        metadata = self.manager.store.load_metadata()
        self.project_label.setText(metadata.name if metadata else "Unnamed project")
        surveys = self.manager.store.list_surveys()
        for survey in surveys:
            self.survey_list.addItem(f"{survey.name}  ·  {survey.survey_type.value}")
        target = next((index for index, survey in enumerate(surveys) if survey.id == selected_id), -1)
        self.survey_list.blockSignals(False)
        if target >= 0:
            self.survey_list.setCurrentRow(target)
            self.select_survey(target)
        else:
            self.workflow = None
            self.ves_workflow = None
            self.update_workflow_state()
        self.refresh_buttons()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

