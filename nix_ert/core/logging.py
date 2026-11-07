"""Central logging setup for the desktop application and scientific modules."""

from __future__ import annotations

import logging
from pathlib import Path

LOGGER_NAME = "nix_ert"


def configure_logging(log_directory: Path | str | None = None, level: int = logging.INFO) -> logging.Logger:
    """Configure application logging once and return the package logger.

    A stream handler is always installed. A file handler is installed when a
    directory is supplied, which keeps library use and tests side-effect free.
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    if not any(getattr(handler, "_nix_ert_stream", False) for handler in logger.handlers):
        stream = logging.StreamHandler()
        stream.setFormatter(formatter)
        stream._nix_ert_stream = True  # type: ignore[attr-defined]
        logger.addHandler(stream)

    if log_directory is not None and not any(
        getattr(handler, "_nix_ert_file", False) for handler in logger.handlers
    ):
        directory = Path(log_directory)
        directory.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(directory / "nix-ert.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler._nix_ert_file = True  # type: ignore[attr-defined]
        logger.addHandler(file_handler)

    return logger
