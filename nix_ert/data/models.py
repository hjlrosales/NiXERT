"""Stable domain values shared by project management and future importers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any


class SurveyType(str, Enum):
    ERT = "ERT"
    VES = "VES"
    ERT_3D = "3D ERT"


@dataclass
class ProjectMetadata:
    name: str
    client: str = ""
    location: str = ""
    survey_date: date | None = None
    operator: str = ""
    instrument: str = ""
    notes: str = ""


@dataclass
class Survey:
    id: str
    name: str
    survey_type: SurveyType
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
