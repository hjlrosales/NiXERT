"""Tests for report deliverables: numbered structure, provenance, and exports."""

from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from nix_ert.app.workflow import ERTWorkflow
from nix_ert.data.models import ProjectMetadata, SurveyType
from nix_ert.data.project import ProjectStore
from nix_ert.reports.generator import (
    ReportData,
    render_csv,
    render_html,
    render_json,
    report_content_sha256,
    report_manifest,
    section_titles,
    write_report,
)
from nix_ert.reports.project_report import build_project_report

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


def _data(**overrides) -> ReportData:
    payload = dict(
        title="Site <A>",
        generated_at="2026-09-14T00:00:00+00:00",
        project={"Client": "Acme & Co", "Location": "North"},
        surveys=({"Name": "Line 1", "Type": "ERT"},),
        qc_summary={"Active": 10, "Flagged": 2},
        inversion={"RMS": "3.2%", "State fingerprint": "abc123"},
        pseudosection_csv="row,x\n1,2\n",
        interpretation=({"Zone": "Possible target", "Confidence": "Low"},),
        provenance={"Software": "NiX ERT 0.1.0", "State fingerprint": "abc123"},
        limitations=("Pseudosection depth is a display proxy, not inversion depth.",),
    )
    payload.update(overrides)
    return ReportData(**payload)


class ReportStructureTests(unittest.TestCase):
    def test_every_section_is_numbered_and_listed_in_the_contents(self) -> None:
        data = _data()
        output = render_html(data)
        titles = section_titles(data)
        self.assertIn("<h2>Contents</h2>", output)
        for index, title in enumerate(titles, start=1):
            self.assertIn(f'<section id="section-{index}">', output)
            self.assertIn(f"<h2>{index}. {title}</h2>", output)
            self.assertIn(f'<a href="#section-{index}">', output)
        self.assertEqual(len(set(titles)), len(titles))

    def test_unsupplied_sections_state_that_nothing_was_invented(self) -> None:
        data = _data(provenance={}, limitations=())
        output = render_html(data)
        self.assertIn("No conclusions supplied", output)
        self.assertIn("No recommendations supplied", output)
        self.assertIn("No limitations statement supplied", output)
        self.assertIn("No provenance supplied", output)

    def test_provenance_values_are_escaped(self) -> None:
        data = _data(provenance={"Software": "<script>alert(1)</script>"})
        output = render_html(data)
        self.assertNotIn("<script>alert(1)</script>", output)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", output)
        self.assertIn("Provenance and report identity", output)

    def test_content_digest_is_stable_and_content_dependent(self) -> None:
        first = report_content_sha256(_data())
        self.assertEqual(first, report_content_sha256(_data()))
        self.assertEqual(len(first), 64)
        self.assertNotEqual(first, report_content_sha256(_data(title="Site <B>")))
        self.assertNotEqual(first, report_content_sha256(_data(provenance={})))

    def test_digest_appears_in_the_rendered_report(self) -> None:
        self.assertIn(report_content_sha256(_data()), render_html(_data()))


class ReportManifestTests(unittest.TestCase):
    def test_manifest_lists_sections_and_matches_the_digest(self) -> None:
        data = _data()
        manifest = report_manifest(data)
        self.assertEqual(manifest["content_sha256"], report_content_sha256(data))
        self.assertEqual(
            [entry["title"] for entry in manifest["sections"]], list(section_titles(data))
        )
        self.assertEqual(manifest["report_format_version"], "nix-ert-report-v2")
        self.assertEqual(manifest["provenance"]["State fingerprint"], "abc123")

    def test_json_rendering_is_deterministic(self) -> None:
        data = _data()
        self.assertEqual(render_json(data), render_json(data))
        self.assertEqual(json.loads(render_json(data)), report_manifest(data))

    def test_manifest_contains_every_supplied_section(self) -> None:
        manifest = report_manifest(_data(conclusions=({"Statement": "Baseline only"},)))
        self.assertEqual(manifest["conclusions"], [{"Statement": "Baseline only"}])
        self.assertEqual(manifest["limitations"][0][:12], "Pseudosectio")


class ReportCsvTests(unittest.TestCase):
    def test_csv_rows_cover_sections_provenance_and_identity(self) -> None:
        data = _data()
        rows = list(csv.reader(io.StringIO(render_csv(data))))
        self.assertEqual(rows[0], ["section", "record", "item", "value"])
        body = rows[1:]
        sections = {row[0] for row in body}
        self.assertIn("Project information", sections)
        self.assertIn("Provenance and report identity", sections)
        self.assertIn("Limitations and scientific scope", sections)
        identity = [row for row in body if row[0] == "Report identity"]
        self.assertEqual(identity[0][3], report_content_sha256(data))

    def test_csv_is_deterministic_and_quotes_embedded_commas(self) -> None:
        data = _data(project={"Client": "Acme, Inc.", "Location": "North"})
        self.assertEqual(render_csv(data), render_csv(data))
        rows = list(csv.DictReader(io.StringIO(render_csv(data))))
        client = [row for row in rows if row["item"] == "Client"]
        self.assertEqual(client[0]["value"], "Acme, Inc.")


class ReportExportTests(unittest.TestCase):
    def test_write_report_dispatches_by_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for suffix in (".html", ".csv", ".json"):
                path = write_report(_data(), root / f"report{suffix}")
                self.assertTrue(path.is_file(), suffix)
                self.assertGreater(path.stat().st_size, 0, suffix)
            payload = json.loads((root / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["content_sha256"], report_content_sha256(_data()))
            header = (root / "report.csv").read_text(encoding="utf-8").splitlines()[0]
            self.assertEqual(header, "section,record,item,value")

    def test_unknown_export_suffix_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.docx"
            with self.assertRaises(ValueError):
                write_report(_data(), path)
            self.assertFalse(path.exists())


class ProjectReportDeliverableTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.source = root / "line.dat"
        self.source.write_text(DAT, encoding="utf-8")
        self.store = ProjectStore(root / "project.sqlite3")
        self.store.open()
        self.store.save_metadata(ProjectMetadata("M24 project", location="Test site"))
        self.survey = self.store.add_survey("Line 1", SurveyType.ERT)
        self.workflow = ERTWorkflow(self.store)
        self.workflow.select_survey(self.survey.id)

    def tearDown(self) -> None:
        self.store.close()
        self.directory.cleanup()

    def test_report_carries_provenance_and_limitations(self) -> None:
        self.workflow.import_dat(self.source)
        result = self.workflow.invert_2d(max_iterations=1)
        data = build_project_report(
            self.store, self.survey.id, version_id=self.workflow.selected_version_id
        )
        self.assertEqual(
            data.provenance["State fingerprint"], data.inversion["State fingerprint"]
        )
        self.assertEqual(len(data.provenance["Source SHA-256"][0]), 64)
        self.assertIn("NOT VALIDATED", data.provenance["Qualification scope"])
        self.assertTrue(any("geological certainty" in item for item in data.limitations))
        output = render_html(data)
        self.assertIn("Provenance and report identity", output)
        self.assertIn(result.message, output)
        self.assertIn("NOT VALIDATED", output)

    def test_machine_readable_export_records_a_report_run(self) -> None:
        self.workflow.import_dat(self.source)
        self.workflow.invert_2d(max_iterations=1)
        path = Path(self.directory.name) / "report.json"
        data = self.workflow.report(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["content_sha256"], report_content_sha256(data))
        runs = self.store.list_report_runs(self.survey.id)
        self.assertEqual(len(runs), 1)
        self.assertEqual(Path(runs[0]["output_path"]).name, "report.json")

    def test_csv_export_is_written_and_records_a_report_run(self) -> None:
        self.workflow.import_dat(self.source)
        path = Path(self.directory.name) / "report.csv"
        self.workflow.report(path)
        self.assertIn("section,record,item,value", path.read_text(encoding="utf-8"))
        self.assertEqual(len(self.store.list_report_runs(self.survey.id)), 1)


if __name__ == "__main__":
    unittest.main()
