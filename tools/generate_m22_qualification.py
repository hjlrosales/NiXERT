"""Regenerate the deterministic M22 qualification artifacts.

Qualification evidence is produced outside project state. Running this script
re-executes every bounded M22 study and rewrites the machine-readable and
human-readable artifacts. Identical engines, environment, and configuration
produce identical artifact bytes; the recorded report hash is deterministic too.

Usage::

    python tools/generate_m22_qualification.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:  # allow direct execution from the project root
    sys.path.insert(0, str(_PROJECT_ROOT))

from nix_ert.qualification.m22 import run_m22_qualification


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", default="docs/m22_scientific_hardening.json")
    parser.add_argument("--markdown", default="docs/m22_scientific_hardening_report.md")
    arguments = parser.parse_args()

    report = run_m22_qualification()
    json_path = Path(arguments.json)
    markdown_path = Path(arguments.markdown)
    json_path.write_text(report.to_json(), encoding="utf-8", newline="\n")
    markdown_path.write_text(report.to_markdown(), encoding="utf-8", newline="\n")
    print(f"wrote {json_path} ({json_path.stat().st_size} bytes)")
    print(f"wrote {markdown_path} ({markdown_path.stat().st_size} bytes)")
    print(f"report_sha256={report.report_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
