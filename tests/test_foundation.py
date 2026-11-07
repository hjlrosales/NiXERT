"""Tests for application configuration and the project database."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from nix_ert.core.config import AppConfig
from nix_ert.data.models import ProjectMetadata, SurveyType
from nix_ert.data.project import ProjectManager, ProjectStore


class ConfigTests(unittest.TestCase):
    def test_config_round_trip_and_recent_project_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = AppConfig.load(directory)
            config.remember_project("first.sqlite3")
            config.remember_project("second.sqlite3")
            config.remember_project("first.sqlite3")
            config.save()
            loaded = AppConfig.load(directory)
            self.assertEqual(len(loaded.recent_projects), 2)
            self.assertEqual(Path(loaded.recent_projects[0]), Path("first.sqlite3").resolve())

    def test_invalid_config_falls_back_to_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("not json", encoding="utf-8")
            self.assertEqual(AppConfig.load(directory).recent_projects, [])


class ProjectStoreTests(unittest.TestCase):
    def test_metadata_and_surveys_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "project.sqlite3"
            with ProjectStore(path) as store:
                metadata = ProjectMetadata(
                    name="Test survey", client="Client", location="Site",
                    survey_date=date(2026, 9, 14), operator="Operator",
                )
                store.save_metadata(metadata)
                survey = store.add_survey("Line 1", SurveyType.ERT, {"spacing": 5.0})
                self.assertEqual(store.load_metadata(), metadata)
                self.assertEqual(store.get_survey(survey.id), survey)
            with ProjectStore(path) as reopened:
                self.assertEqual(reopened.load_metadata(), metadata)
                surveys = reopened.list_surveys()
                self.assertEqual(len(surveys), 1)
                self.assertEqual(surveys[0].metadata["spacing"], 5.0)

    def test_malformed_sqlite_project_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.sqlite3"
            path.write_bytes(b"not a sqlite database")
            with self.assertRaises(ValueError):
                ProjectStore(path).open()

    def test_empty_survey_name_is_rejected_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory, ProjectStore(Path(directory) / "p.sqlite3") as store:
            with self.assertRaises(ValueError):
                store.add_survey("  ", SurveyType.VES)
            self.assertEqual(store.list_surveys(), [])


    def test_manager_create_open_and_recent_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = AppConfig.load(Path(directory) / "config")
            manager = ProjectManager(config)
            project_path = manager.create_project(Path(directory) / "project", ProjectMetadata("Managed"))
            self.assertTrue(project_path.exists())
            manager.close()
            self.assertEqual(manager.open_project(project_path), ProjectMetadata("Managed"))
            self.assertIn(str(project_path.resolve()), config.recent_projects)
            manager.close()


if __name__ == "__main__":
    unittest.main()
