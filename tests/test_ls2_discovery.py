"""Tests for observation-only, fail-closed LS2 discovery."""

from __future__ import annotations

import unittest

from nix_ert.data.ls2_discovery import (
    DiscoveryStatus,
    LS2DiscoveryBlocked,
    NetworkObservation,
    SafeLS2Discovery,
    USBDeviceObservation,
    validate_ip_address,
)


class USBProvider:
    def __init__(self, value):
        self.value = value

    def observe_usb(self):
        if isinstance(self.value, BaseException):
            raise self.value
        return self.value


class NetworkProvider:
    def __init__(self, value):
        self.value = value
        self.requested: list[str] = []

    def observe_network(self, ip_address: str):
        self.requested.append(ip_address)
        if isinstance(self.value, BaseException):
            raise self.value
        return self.value


class LS2DiscoveryTests(unittest.TestCase):
    def test_default_providers_fail_closed_without_hardware_access(self) -> None:
        discovery = SafeLS2Discovery()
        usb = discovery.inspect_usb()
        network = discovery.inspect_network("192.168.23.1")
        self.assertEqual(usb.status, DiscoveryStatus.UNSUPPORTED)
        self.assertEqual(network.status, DiscoveryStatus.UNSUPPORTED)
        self.assertIn("no documented", network.detail.lower())

    def test_usb_observation_is_reported_without_serial_access(self) -> None:
        provider = USBProvider((USBDeviceObservation("LS2 storage", mounted_paths=("E:/",)),))
        result = SafeLS2Discovery(usb_provider=provider).inspect_usb()
        self.assertEqual(result.status, DiscoveryStatus.OBSERVED)
        self.assertEqual(result.usb_devices[0].description, "LS2 storage")

    def test_usb_empty_timeout_and_malformed_observations_are_safe(self) -> None:
        self.assertEqual(
            SafeLS2Discovery(usb_provider=USBProvider(())).inspect_usb().status,
            DiscoveryStatus.UNAVAILABLE,
        )
        self.assertEqual(
            SafeLS2Discovery(usb_provider=USBProvider(TimeoutError())).inspect_usb().status,
            DiscoveryStatus.TIMEOUT,
        )
        malformed = SafeLS2Discovery(usb_provider=USBProvider(("not an observation",))).inspect_usb()
        self.assertEqual(malformed.status, DiscoveryStatus.REJECTED)

    def test_invalid_ip_is_rejected_without_provider_call(self) -> None:
        provider = NetworkProvider(NetworkObservation("192.168.23.1", True))
        result = SafeLS2Discovery(network_provider=provider).inspect_network("not-an-ip")
        self.assertEqual(result.status, DiscoveryStatus.REJECTED)
        self.assertEqual(provider.requested, [])
        with self.assertRaises(ValueError):
            validate_ip_address("224.0.0.1")

    def test_network_observation_validates_target_and_status(self) -> None:
        provider = NetworkProvider(NetworkObservation("192.168.23.1", True, ssid="LS2-AP"))
        result = SafeLS2Discovery(network_provider=provider).inspect_network("192.168.23.1")
        self.assertEqual(result.status, DiscoveryStatus.OBSERVED)
        self.assertEqual(provider.requested, ["192.168.23.1"])
        unavailable = SafeLS2Discovery(
            network_provider=NetworkProvider(NetworkObservation("192.168.23.1", False))
        ).inspect_network("192.168.23.1")
        self.assertEqual(unavailable.status, DiscoveryStatus.UNAVAILABLE)

    def test_network_timeout_mismatch_and_malformed_response_are_rejected(self) -> None:
        timeout = SafeLS2Discovery(network_provider=NetworkProvider(TimeoutError())).inspect_network("192.168.23.1")
        self.assertEqual(timeout.status, DiscoveryStatus.TIMEOUT)
        mismatch = SafeLS2Discovery(
            network_provider=NetworkProvider(NetworkObservation("192.168.23.2", True))
        ).inspect_network("192.168.23.1")
        self.assertEqual(mismatch.status, DiscoveryStatus.REJECTED)
        malformed = SafeLS2Discovery(network_provider=NetworkProvider({"link_up": True})).inspect_network("192.168.23.1")
        self.assertEqual(malformed.status, DiscoveryStatus.REJECTED)

    def test_documented_service_probe_remains_blocked(self) -> None:
        with self.assertRaisesRegex(LS2DiscoveryBlocked, "Protocol unknown"):
            SafeLS2Discovery.require_documented_service(None, None)
        with self.assertRaises(LS2DiscoveryBlocked):
            SafeLS2Discovery.require_documented_service("unvalidated-service", 1234)


if __name__ == "__main__":
    unittest.main()
