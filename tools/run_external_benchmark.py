"""Headless admission/execution of a benchmark registry manifest.

This tool cannot validate a scientific engine on its own: it refuses every
candidate that lacks licensed dataset bytes, a recorded source digest, stated
acquisition geometry, an independent reference result, and a frozen tolerance
justification. It exists so that evidence *can* be executed and recorded once it
is supplied, without the desktop application.

Exit codes::

    0  every selected protocol was admitted (and, when executing, stayed inside
       its frozen tolerance)
    1  the manifest, a case file, or the case coverage is invalid; nothing ran
    2  at least one selected protocol was refused admission
    3  every selected protocol executed, but at least one stayed outside
       tolerance

Usage::

    python tools/run_external_benchmark.py --manifest registry.json --admit-only
    python tools/run_external_benchmark.py \\
        --manifest registry.json --case candidate=VES.json --json out.json
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:  # allow direct execution from the project root
    sys.path.insert(0, str(_PROJECT_ROOT))

from nix_ert.qualification.benchmark_cli import main


if __name__ == "__main__":
    raise SystemExit(main())
