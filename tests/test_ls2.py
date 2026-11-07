"""Tests for the fail-closed LS2 integration boundary."""

from __future__ import annotations

import unittest

from nix_ert.data.ls2 import LS2IntegrationBlocked, UnsupportedLS2Transport, acquire_read_only


class FixtureTransport:
    def __init__(self, payload: bytes):
        self.payload = payload

    def read_survey(self, survey_id: str) -> bytes:
        return self.payload

    def list_surveys(self) -> tuple[str, ...]:
        return ("survey-1",)


class LS2Tests(unittest.TestCase):
    def test_unsupported_transport_fails_closed(self) -> None:
        transport = UnsupportedLS2Transport()
        with self.assertRaises(LS2IntegrationBlocked):
            transport.list_surveys()
        with self.assertRaises(LS2IntegrationBlocked):
            transport.read_survey("survey-1")

    def test_valid_fixture_uses_same_dat_validation_boundary(self) -> None:
        payload = b"1\n1\n1\n0\n1 2 3 4 25\n"
        result = acquire_read_only(FixtureTransport(payload), "survey-1")
        self.assertEqual(result.dataset.measurements[0].apparent_resistivity, 25)
        self.assertEqual(result.raw_bytes, payload)

    def test_invalid_payload_is_rejected_without_side_effects(self) -> None:
        with self.assertRaises(LS2IntegrationBlocked):
            acquire_read_only(FixtureTransport(b"not a dat"), "survey-1")


if __name__ == "__main__":
    unittest.main()
