"""Safe import orchestration for DAT files and project provenance."""

from __future__ import annotations

import hashlib
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from nix_ert.data.dat_import import DATParseError, parse_dat
from nix_ert.data.measurements import ImportedDataset
from nix_ert.data.project import ProjectStore


@dataclass(frozen=True)
class ImportResult:
    source_path: Path
    stored_path: Path
    sha256: str
    dataset: ImportedDataset


def import_dat_into_project(
    store: ProjectStore, survey_id: str, source_path: Path | str,
) -> ImportResult:
    """Parse and copy a DAT source without ever modifying the source file.

    Parsing occurs before copying and persistence. The managed copy is named by
    its digest, preventing same-name collisions and making provenance explicit.
    """
    source = Path(source_path)
    if not source.is_file():
        raise DATParseError(f"DAT source does not exist: {source}")
    raw_bytes = source.read_bytes()
    dataset = parse_dat(raw_bytes.decode("utf-8-sig"), source_name=source.name)
    raw_dir = store.path.parent / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(raw_bytes).hexdigest()
    destination = raw_dir / f"{digest[:16]}-{source.name}"
    if destination.exists():
        if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
            raise OSError(f"Managed raw file collision: {destination}")
    else:
        temporary = raw_dir / f".{uuid.uuid4().hex}.tmp"
        try:
            temporary.write_bytes(raw_bytes)
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != digest:
                raise OSError("Source changed while it was being copied")
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    store.record_import(
        survey_id=survey_id, original_name=source.name, stored_path=destination,
        sha256=digest, byte_count=len(raw_bytes), dataset=dataset,
    )
    return ImportResult(source_path=source, stored_path=destination, sha256=digest, dataset=dataset)
