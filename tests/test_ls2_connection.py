"""Offline LS2 transport/session state-machine tests."""

from __future__ import annotations

import unittest

from nix_ert.data.ls2_connection import (
    LS2ConnectionState,
    LS2Observation,
    LS2Session,
    LS2TransportKind,
    MockUSBTransport,
    MockWiFiTransport,
    UnsupportedUSBTransport,
    UnsupportedWiFiTransport,
)


class LS2ConnectionTests(unittest.TestCase):
    def test_mock_usb_sequence_is_explicitly_mock_and_stops_before_acquisition(self) -> None:
        session = LS2Session(MockUSBTransport())
        self.assertEqual(session.connect().state, LS2ConnectionState.DETECTED)
        self.assertEqual(session.detect().state, LS2ConnectionState.DETECTED)
        self.assertEqual(session.identify().state, LS2ConnectionState.DETECTED)
        status = session.verify_documented_communication()
        self.assertEqual(status.state, LS2ConnectionState.CONNECTED)
        self.assertTrue(status.mock)
        self.assertTrue(status.capabilities.safe_read_only_ready)
        self.assertEqual(session.disconnect().state, LS2ConnectionState.DISCONNECTED)

    def test_mock_wifi_sequence_uses_user_supplied_address(self) -> None:
        session = LS2Session(MockWiFiTransport("192.0.2.10"))
        session.connect()
        session.detect()
        session.identify()
        status = session.verify_documented_communication()
        self.assertEqual(status.state, LS2ConnectionState.CONNECTED)
        self.assertEqual(status.address, "192.0.2.10")
        self.assertTrue(status.mock)

    def test_unsupported_default_transports_are_visible_not_executed(self) -> None:
        usb = LS2Session(UnsupportedUSBTransport()).connect()
        wifi = LS2Session(UnsupportedWiFiTransport("192.0.2.1")).connect()
        self.assertEqual(usb.state, LS2ConnectionState.UNSUPPORTED)
        self.assertEqual(wifi.state, LS2ConnectionState.UNSUPPORTED)

    def test_protocol_unknown_stops_before_connection(self) -> None:
        observation = LS2Observation(
            LS2TransportKind.WIFI, True, "Observed device", "192.0.2.20",
            documented_service=None, read_only_data=False, mock=True,
        )
        session = LS2Session(MockWiFiTransport("192.0.2.20", observation=observation))
        session.connect()
        session.identify()
        status = session.verify_documented_communication()
        self.assertEqual(status.state, LS2ConnectionState.PROTOCOL_UNKNOWN)
        self.assertIn("Protocol unknown", status.detail)

    def test_hardware_validation_required_when_identity_is_missing(self) -> None:
        observation = LS2Observation(LS2TransportKind.USB, True, mock=True)
        session = LS2Session(MockUSBTransport(observation=observation))
        self.assertEqual(session.connect().state, LS2ConnectionState.DETECTED)
        self.assertEqual(session.identify().state, LS2ConnectionState.HARDWARE_VALIDATION_REQUIRED)

    def test_timeout_and_malformed_transport_responses_fail_closed(self) -> None:
        self.assertEqual(
            LS2Session(MockUSBTransport(error=TimeoutError())).connect().state,
            LS2ConnectionState.TIMEOUT,
        )
        self.assertEqual(
            LS2Session(MockUSBTransport(error=ValueError("malformed response"))).connect().state,
            LS2ConnectionState.ERROR,
        )

    def test_detected_but_unidentified_device_requires_validation(self) -> None:
        observation = LS2Observation(LS2TransportKind.USB, True, mock=True)
        session = LS2Session(MockUSBTransport(observation=observation))
        self.assertEqual(session.connect().state, LS2ConnectionState.DETECTED)
        self.assertEqual(session.detect().state, LS2ConnectionState.DETECTED)
        status = session.identify()
        self.assertEqual(status.state, LS2ConnectionState.HARDWARE_VALIDATION_REQUIRED)
        self.assertEqual(session.verify_documented_communication().state, LS2ConnectionState.HARDWARE_VALIDATION_REQUIRED)

    def test_transport_returning_malformed_object_fails_closed(self) -> None:
        class MalformedTransport:
            kind = LS2TransportKind.USB

            def connect(self):
                return {"detected": True, "identity": "not trusted"}

            def disconnect(self):
                return None

        status = LS2Session(MalformedTransport()).connect()
        self.assertEqual(status.state, LS2ConnectionState.ERROR)
        self.assertIn("malformed", status.detail)

    def test_transport_contract_has_no_acquisition_or_mutation_capability(self) -> None:
        session = LS2Session(MockUSBTransport())
        self.assertFalse(hasattr(session.transport, "acquire"))
        self.assertFalse(hasattr(session.transport, "start_measurement"))
        self.assertFalse(hasattr(session.transport, "write_settings"))
        self.assertFalse(hasattr(session, "acquire"))
        self.assertFalse(hasattr(session, "start_measurement"))


if __name__ == "__main__":
    unittest.main()
