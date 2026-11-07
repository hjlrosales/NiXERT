"""Tests for structured report output."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from nix_ert.reports.generator import ReportData, render_html, write_html, write_pdf


class ReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = ReportData(
            title="Site <A>", generated_at="2026-09-14T00:00:00+00:00",
            project={"Client": "Acme & Co", "Location": "North"},
            surveys=({"Name": "Line 1", "Type": "ERT"},),
            qc_summary={"Active": 10, "Flagged": 2},
            inversion={"RMS": "3.2%", "Converged": True},
            pseudosection_csv="row,x\n1,2\n",
            interpretation=({"Zone": "Possible target", "Confidence": "Low"},),
        )

    def test_html_contains_structured_sections_and_escapes_values(self) -> None:
        output = render_html(self.data)
        self.assertIn("Project information", output)
        self.assertIn("Acme &amp; Co", output)
        self.assertIn("Site &lt;A&gt;", output)
        self.assertIn("Pseudosection data appendix", output)
        self.assertNotIn("<title>Site <A>", output)

    def test_html_file_is_written(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.html"
            write_html(self.data, path)
            self.assertTrue(path.exists())
            self.assertIn("Data quality control summary", path.read_text(encoding="utf-8"))

    def test_pdf_smoke_when_matplotlib_is_available(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.pdf"
            try:
                write_pdf(self.data, path)
            except RuntimeError as exc:
                if "matplotlib is required" not in str(exc):
                    raise
            else:
                self.assertTrue(path.exists())
                self.assertGreater(path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
