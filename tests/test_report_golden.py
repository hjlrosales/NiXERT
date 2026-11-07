"""Golden-file regression tests: the exact report bytes are frozen.

`tests/golden/report_fixture.json` is the fixed `ReportData` fixture;
`report_fixture.html` and `report_fixture.csv` are the exact bytes the generator
must keep producing. A failure here means the rendered structure, an escape, or
an export row changed. Regenerate deliberately with::

    python tools/regenerate_report_goldens.py

and review the diff before committing it.
"""

from __future__ import annotations

import json
from pathlib import Path

from nix_ert.reports.generator import (
    ReportData,
    render_csv,
    render_html,
    report_content_sha256,
    report_manifest,
)

GOLDEN = Path(__file__).resolve().parent / "golden"
EXPECTED_DIGEST = "789db33849ab79885efd962b2b9b957c244d247ac8ae2eae48fa7af8e5afa550"


def _fixture() -> ReportData:
    return ReportData(**json.loads((GOLDEN / "report_fixture.json").read_text(encoding="utf-8")))


def test_html_bytes_match_the_golden_file() -> None:
    rendered = render_html(_fixture()).encode("utf-8")
    assert rendered == (GOLDEN / "report_fixture.html").read_bytes()


def test_csv_bytes_match_the_golden_file() -> None:
    rendered = render_csv(_fixture()).encode("utf-8")
    assert rendered == (GOLDEN / "report_fixture.csv").read_bytes()


def test_rendering_is_repeatable_bit_for_bit() -> None:
    assert render_html(_fixture()) == render_html(_fixture())
    assert render_csv(_fixture()) == render_csv(_fixture())


def test_content_digest_is_frozen_across_formats() -> None:
    data = _fixture()
    digest = report_content_sha256(data)
    assert digest == EXPECTED_DIGEST
    assert digest in render_html(data)
    assert digest in render_csv(data)
    assert digest in json.dumps(report_manifest(data))
    assert report_manifest(data)["content_sha256"] == digest


def test_golden_files_have_no_platform_specific_line_endings() -> None:
    for name in ("report_fixture.html", "report_fixture.csv"):
        payload = (GOLDEN / name).read_bytes()
        assert b"\r\n" not in payload, name
    # The row-oriented export is newline-terminated; the HTML document is not.
    assert (GOLDEN / "report_fixture.csv").read_bytes().endswith(b"\n")
