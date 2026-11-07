"""Safe boundary for future direct Terrameter LS2 communication.

No protocol is implemented here. The adapter is deliberately read-only and
must produce the same validated DAT/import input accepted by the offline path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from nix_ert.data.dat_import import DATParseError, parse_dat
from nix_ert.data.measurements import ImportedDataset


class LS2IntegrationBlocked(RuntimeError):
    """Raised until an officially documented protocol is available."""


class ReadOnlyLS2Transport(Protocol):
    """Minimal contract for a future read-only device transport."""

    def list_surveys(self) -> tuple[str, ...]: ...

    def read_survey(self, survey_id: str) -> bytes: ...


@dataclass(frozen=True)
class LS2Acquisition:
    survey_id: str
    raw_bytes: bytes
    dataset: ImportedDataset


class UnsupportedLS2Transport:
    """Fail-closed placeholder; it cannot access hardware or write data."""

    def list_surveys(self) -> tuple[str, ...]:
        raise LS2IntegrationBlocked(
            "Direct LS2 communication is unavailable: official protocol documentation and a validated device fixture are required"
        )

    def read_survey(self, survey_id: str) -> bytes:
        raise LS2IntegrationBlocked(
            "Direct LS2 communication is unavailable: official protocol documentation and a validated device fixture are required"
        )


def acquire_read_only(transport: ReadOnlyLS2Transport, survey_id: str) -> LS2Acquisition:
    """Read bytes, validate them through the DAT parser, and return no write handle."""
    raw_bytes = transport.read_survey(survey_id)
    if not isinstance(raw_bytes, bytes) or not raw_bytes:
        raise LS2IntegrationBlocked("LS2 transport returned no byte payload")
    try:
        dataset = parse_dat(raw_bytes.decode("utf-8-sig"), source_name=f"ls2:{survey_id}")
    except (UnicodeDecodeError, DATParseError) as exc:
        raise LS2IntegrationBlocked("LS2 payload is not a validated supported DAT export") from exc
    return LS2Acquisition(survey_id=survey_id, raw_bytes=raw_bytes, dataset=dataset)
