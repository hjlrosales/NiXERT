"""Regenerate the frozen report HTML/CSV golden bytes.

The golden files pin the exact rendered bytes for a fixed `ReportData`. Changing
them is a deliberate, reviewable act: any diff means the report structure, an
escape, or an export row changed. Run this only after confirming the new output
is correct, then commit the regenerated files together with the change that
caused them.

Usage::

    python tools/regenerate_report_goldens.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:  # allow direct execution from the project root
    sys.path.insert(0, str(_PROJECT_ROOT))

from nix_ert.reports.generator import ReportData, render_csv, render_html, report_content_sha256


FIXTURE = _PROJECT_ROOT / "tests" / "golden" / "report_fixture.json"
HTML_GOLDEN = _PROJECT_ROOT / "tests" / "golden" / "report_fixture.html"
CSV_GOLDEN = _PROJECT_ROOT / "tests" / "golden" / "report_fixture.csv"


def fixture_report() -> ReportData:
    """Build the report data pinned by the golden files."""
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return ReportData(**payload)


def main() -> int:
    data = fixture_report()
    HTML_GOLDEN.write_text(render_html(data), encoding="utf-8", newline="\n")
    CSV_GOLDEN.write_text(render_csv(data), encoding="utf-8", newline="\n")
    print(f"wrote {HTML_GOLDEN.relative_to(_PROJECT_ROOT)} ({HTML_GOLDEN.stat().st_size} bytes)")
    print(f"wrote {CSV_GOLDEN.relative_to(_PROJECT_ROOT)} ({CSV_GOLDEN.stat().st_size} bytes)")
    print(f"content_sha256={report_content_sha256(data)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
