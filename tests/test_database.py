"""M17 database migration and recovery tests."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from nix_ert.data.models import ProjectMetadata, SurveyType
from nix_ert.data.project import ProjectStore, SCHEMA_VERSION


class DatabaseQualificationTests(unittest.TestCase):
    def test_supported_v2_database_migrates_additively_to_v3(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.sqlite3"
            store = ProjectStore(path)
            store.open()
            store.save_metadata(ProjectMetadata("Legacy"))
            survey = store.add_survey("Line", SurveyType.ERT)
            store.connection.execute("DROP TABLE report_runs")
            store.connection.execute(
                "UPDATE schema_info SET value = '2' WHERE key = 'schema_version'"
            )
            store.connection.commit()
            store.close()

            reopened = ProjectStore(path)
            reopened.open(initialize=False)
            self.assertEqual(
                reopened.connection.execute(
                    "SELECT value FROM schema_info WHERE key = 'schema_version'"
                ).fetchone()[0],
                str(SCHEMA_VERSION),
            )
            self.assertEqual(reopened.list_surveys()[0].id, survey.id)
            self.assertEqual(reopened.list_report_runs(survey.id), [])
            reopened.close()

    def test_newer_schema_is_rejected_without_reinterpretation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "future.sqlite3"
            store = ProjectStore(path)
            store.open()
            store.connection.execute(
                "UPDATE schema_info SET value = '999' WHERE key = 'schema_version'"
            )
            store.connection.commit()
            store.close()
            with self.assertRaisesRegex(ValueError, "newer"):
                ProjectStore(path).open(initialize=False)

    def test_incomplete_schema_is_rejected_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "incomplete.sqlite3"
            connection = sqlite3.connect(path)
            try:
                connection.execute("CREATE TABLE schema_info (key TEXT PRIMARY KEY, value TEXT)")
                connection.execute("INSERT INTO schema_info VALUES ('schema_version', '2')")
                connection.commit()
            finally:
                connection.close()
            project = ProjectStore(path)
            with self.assertRaisesRegex(ValueError, "missing required"):
                project.open(initialize=False)
            project.close()


if __name__ == "__main__":
    unittest.main()
