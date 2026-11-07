"""Fail-closed, observation-only Terrameter LS2 discovery contracts.

The public vendor material reviewed by M15 documents remote connectivity and
vendor tools, but does not publish a stable API, service port, USB serial
contract, or acquisition payload protocol. Consequently this module accepts
only observations supplied by an OS/vendor integration that is separately
validated. It never scans ports, opens serial devices, sends commands, or
accesses an LS2 by default.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Protocol


class LS2DiscoveryBlocked(RuntimeError):
    """Raised when discovery would require an undocumented mechanism."""


class DiscoveryStatus(str, Enum):
    OBSERVED = "observed"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    REJECTED = "rejected"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class USBDeviceObservation:
    """OS/vendor-supplied USB facts; values are not interpreted as a protocol."""

    description: str = ""
    vendor_id: str | None = None
    product_id: str | None = None
    serial_port: str | None = None
    mounted_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class NetworkObservation:
    """Read-only facts observed by an external OS/network integration."""

    ip_address: str
    link_up: bool
    ssid: str | None = None
    service_name: str | None = None
    service_port: int | None = None
    software_version: str | None = None
    notes: str = ""


@dataclass(frozen=True)
class DiscoveryResult:
    transport: str
    status: DiscoveryStatus
    detail: str
    usb_devices: tuple[USBDeviceObservation, ...] = ()
    network: NetworkObservation | None = None


class USBObservationProvider(Protocol):
    """A future OS/vendor adapter that only reports enumerated USB facts."""

    def observe_usb(self) -> Iterable[USBDeviceObservation]: ...


class NetworkObservationProvider(Protocol):
    """A future OS/vendor adapter that only reports a user-selected target."""

    def observe_network(self, ip_address: str) -> NetworkObservation: ...


class UnsupportedUSBObservationProvider:
    """Default provider; no platform-specific USB probing is enabled."""

    def observe_usb(self) -> Iterable[USBDeviceObservation]:
        raise LS2DiscoveryBlocked(
            "USB discovery is unavailable: no officially validated LS2 USB device integration exists"
        )


class UnsupportedNetworkObservationProvider:
    """Default provider; no socket, port scan, or undocumented request is made."""

    def observe_network(self, ip_address: str) -> NetworkObservation:
        raise LS2DiscoveryBlocked(
            "Network discovery is unavailable: no documented LS2 service/API endpoint exists"
        )


def validate_ip_address(value: str) -> str:
    """Validate a user-supplied IP without probing it or making assumptions."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("LS2 IP address is required")
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid LS2 IP address: {value!r}") from exc
    if address.is_unspecified or address.is_multicast or address.is_reserved:
        raise ValueError(f"LS2 IP address is not a usable unicast target: {value!r}")
    return str(address)


def _validate_observation(observation: object, requested_ip: str) -> NetworkObservation:
    if not isinstance(observation, NetworkObservation):
        raise ValueError("network provider returned a malformed observation")
    observed_ip = validate_ip_address(observation.ip_address)
    if observed_ip != requested_ip:
        raise ValueError("network observation IP does not match the requested target")
    if not isinstance(observation.link_up, bool):
        raise ValueError("network observation link_up must be boolean")
    if observation.service_port is not None and not (
        isinstance(observation.service_port, int) and 1 <= observation.service_port <= 65535
    ):
        raise ValueError("network observation service port is invalid")
    if observation.service_name is None and observation.service_port is not None:
        raise ValueError("network observation cannot report a port without a documented service")
    return NetworkObservation(
        ip_address=observed_ip,
        link_up=observation.link_up,
        ssid=observation.ssid,
        service_name=observation.service_name,
        service_port=observation.service_port,
        software_version=observation.software_version,
        notes=observation.notes,
    )


class SafeLS2Discovery:
    """Run only injected, observation-only diagnostics.

    The default providers fail closed. Supplying a provider does not authorize
    commands or acquisition: its output must be an observation object and is
    rejected if it is malformed. No result from this class is an acquisition
    payload or a claim that an instrument API exists.
    """

    def __init__(
        self,
        *,
        usb_provider: USBObservationProvider | None = None,
        network_provider: NetworkObservationProvider | None = None,
    ) -> None:
        self.usb_provider = usb_provider or UnsupportedUSBObservationProvider()
        self.network_provider = network_provider or UnsupportedNetworkObservationProvider()

    def inspect_usb(self) -> DiscoveryResult:
        try:
            devices = tuple(self.usb_provider.observe_usb())
            if not all(isinstance(device, USBDeviceObservation) for device in devices):
                raise ValueError("USB provider returned a malformed observation")
        except TimeoutError:
            return DiscoveryResult("USB", DiscoveryStatus.TIMEOUT, "USB observation timed out")
        except LS2DiscoveryBlocked as exc:
            return DiscoveryResult("USB", DiscoveryStatus.UNSUPPORTED, str(exc))
        except (OSError, ValueError, TypeError) as exc:
            return DiscoveryResult("USB", DiscoveryStatus.REJECTED, f"USB observation rejected: {exc}")
        if not devices:
            return DiscoveryResult("USB", DiscoveryStatus.UNAVAILABLE, "No USB device observation was reported")
        return DiscoveryResult(
            "USB", DiscoveryStatus.OBSERVED,
            "USB facts observed without opening a serial channel or sending commands",
            usb_devices=devices,
        )

    def inspect_network(self, ip_address: str) -> DiscoveryResult:
        try:
            target = validate_ip_address(ip_address)
        except ValueError as exc:
            return DiscoveryResult("Wi-Fi/Ethernet", DiscoveryStatus.REJECTED, str(exc))
        try:
            observation = _validate_observation(
                self.network_provider.observe_network(target), target
            )
        except TimeoutError:
            return DiscoveryResult("Wi-Fi/Ethernet", DiscoveryStatus.TIMEOUT, "Network observation timed out")
        except LS2DiscoveryBlocked as exc:
            return DiscoveryResult("Wi-Fi/Ethernet", DiscoveryStatus.UNSUPPORTED, str(exc))
        except (OSError, ValueError, TypeError) as exc:
            return DiscoveryResult(
                "Wi-Fi/Ethernet", DiscoveryStatus.REJECTED,
                f"Network observation rejected: {exc}",
            )
        if not observation.link_up:
            return DiscoveryResult(
                "Wi-Fi/Ethernet", DiscoveryStatus.UNAVAILABLE,
                "The selected target reports no active network link", network=observation,
            )
        return DiscoveryResult(
            "Wi-Fi/Ethernet", DiscoveryStatus.OBSERVED,
            "Network facts observed; no undocumented service or instrument command was tested",
            network=observation,
        )

    @staticmethod
    def require_documented_service(service_name: str | None, service_port: int | None) -> None:
        """Reject service probing until vendor documentation identifies it."""
        if not service_name or service_port is None:
            raise LS2DiscoveryBlocked(
                "Protocol unknown — do not implement communication; no documented LS2 service endpoint is available"
            )
        raise LS2DiscoveryBlocked(
            f"Documented service validation is not implemented for {service_name}:{service_port}"
        )


__all__ = [
    "DiscoveryResult",
    "DiscoveryStatus",
    "LS2DiscoveryBlocked",
    "NetworkObservation",
    "NetworkObservationProvider",
    "SafeLS2Discovery",
    "USBDeviceObservation",
    "USBObservationProvider",
    "UnsupportedNetworkObservationProvider",
    "UnsupportedUSBObservationProvider",
    "validate_ip_address",
]
