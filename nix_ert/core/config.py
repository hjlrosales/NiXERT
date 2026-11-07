"""Application configuration persisted outside project files."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AppConfig:
    """User-level settings that are safe to recreate when absent."""

    config_dir: Path = field(default_factory=lambda: Path.home() / ".nix-ert")
    recent_projects: list[str] = field(default_factory=list)

    @property
    def config_path(self) -> Path:
        return self.config_dir / "config.json"

    @classmethod
    def load(cls, config_dir: Path | str | None = None) -> "AppConfig":
        directory = Path(config_dir) if config_dir is not None else Path.home() / ".nix-ert"
        path = directory / "config.json"
        if not path.exists():
            return cls(config_dir=directory)
        try:
            payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            recent = payload.get("recent_projects", [])
            if not isinstance(recent, list):
                recent = []
            return cls(config_dir=directory, recent_projects=[str(item) for item in recent])
        except (OSError, ValueError, TypeError):
            # A broken preference file must not prevent the application from starting.
            return cls(config_dir=directory)

    def save(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.config_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"recent_projects": self.recent_projects}, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self.config_path)

    def remember_project(self, project_path: Path | str, limit: int = 10) -> None:
        normalized = str(Path(project_path).resolve())
        self.recent_projects = [
            path for path in self.recent_projects if Path(path).resolve() != Path(normalized)
        ]
        self.recent_projects.insert(0, normalized)
        del self.recent_projects[limit:]
