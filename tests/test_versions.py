"""Tests for immutable processing/model version records."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from nix_ert.data.models import ProjectMetadata, SurveyType
from nix_ert.data.project import ProjectStore
from nix_ert.processing.versions import VersionStore, VersioningError, parameter_hash


class VersionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.store = ProjectStore(Path(self.directory.name) / "project.sqlite3")
        self.store.open()
        self.store.save_metadata(ProjectMetadata("Version test"))
        self.survey = self.store.add_survey("Line 1", SurveyType.ERT)
        self.versions = VersionStore(self.store)

    def tearDown(self) -> None:
        self.store.close()
        self.directory.cleanup()

    def test_canonical_parameter_hash_is_order_independent(self) -> None:
        self.assertEqual(parameter_hash({"b": 2, "a": 1}), parameter_hash({"a": 1, "b": 2}))

    def test_create_list_compare_and_restore_by_copy(self) -> None:
        first = self.versions.create(self.survey.id, "processing", "Raw cleanup", {"threshold": 2}, {"active_rows": [1, 2]})
        second = self.versions.create(self.survey.id, "processing", "Filtered", {"threshold": 3}, {"active_rows": [1]}, parent_id=first.id)
        self.assertEqual(len(self.versions.list(self.survey.id, "processing")), 2)
        comparison = self.versions.compare(first.id, second.id)
        self.assertFalse(comparison["parameter_hash_equal"])
        self.assertIn("threshold", comparison["parameter_changes"])
        copied = self.versions.restore_by_copy(second.id)
        self.assertEqual(copied.parent_id, second.id)
        self.assertEqual(copied.parameters, second.parameters)
        self.assertEqual(copied.snapshot, second.snapshot)

    def test_rename_and_notes_are_persisted_without_changing_snapshot(self) -> None:
        version = self.versions.create(self.survey.id, "model", "Model A", {"lambda": 0.2}, {"cells": [1.0, 2.0]})
        self.versions.rename(version.id, "Preferred model")
        self.versions.update_notes(version.id, "Reviewed by operator")
        loaded = self.versions.get(version.id)
        self.assertEqual(loaded.name, "Preferred model")
        self.assertEqual(loaded.notes, "Reviewed by operator")
        self.assertEqual(loaded.snapshot, {"cells": [1.0, 2.0]})

    def test_invalid_version_operations_are_rejected(self) -> None:
        with self.assertRaises(VersioningError):
            self.versions.create(self.survey.id, "", "x", {}, {})
        with self.assertRaises(VersioningError):
            self.versions.create(self.survey.id, "model", "x", {}, {}, parent_id="missing")
        with self.assertRaises(VersioningError):
            self.versions.restore_by_copy("missing")


if __name__ == "__main__":
    unittest.main()
