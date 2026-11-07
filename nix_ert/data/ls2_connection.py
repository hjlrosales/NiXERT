"""Offline-ready LS2 transport, session, and capability contracts.

This module deliberately contains no USB driver, socket, serial, VNC, or LS2
protocol implementation. Default transports fail closed. The mock transports
are deterministic test fixtures and are marked as such in every observation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from nix_ert.data.ls2_discovery import validate_ip_address


class LS2ConnectionBlocked(RuntimeError):
    """Raised when a transport would require an undocumented LS2 mechanism."""


class LS2TransportKind(str, Enum):
    USB = "USB"
    WIFI = "Wi-Fi"


class LS2ConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    DETECTED = "detected"
    CONNECTED = "connected"
    UNSUPPORTED = "unsupported"
    PROTOCOL_UNKNOWN = "protocol unknown"
    HARDWARE_VALIDATION_REQUIRED = "hardware validation required"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass(frozen=True)
class LS2Capabilities:
    """Capabilities claimed by an injected, separately validated observation."""

    detection: bool = False
    identification: bool = False
    documented_service: bool = False
    read_only_data: bool = False
    acquisition_control: bool = False
    mutation_allowed: bool = False

    @property
    def safe_read_only_ready(self) -> bool:
        return (
            self.detection
            and self.identification
            and self.documented_service
            and self.read_only_data
            and not self.acquisition_control
            and not self.mutation_allowed
        )


@dataclass(frozen=True)
class LS2Observation:
    """Facts returned by an OS/vendor adapter or an explicitly marked mock."""

    transport: LS2TransportKind
    detected: bool
    identity: str | None = None
    address: str | None = None
    documented_service: str | None = None
    read_only_data: bool = False
    software_version: str | None = None
    mock: bool = False
    detail: str = ""

    def __post_init__(self) -> None:
        if self.transport is LS2TransportKind.WIFI and self.address is not None:
            validate_ip_address(self.address)
        if self.documented_service and not self.identity:
            raise ValueError("a documented service requires an identified device")
        if self.read_only_data and not self.documented_service:
            raise ValueError("read-only data requires a documented service")

    @property
    def capabilities(self) -> LS2Capabilities:
        return LS2Capabilities(
            detection=self.detected,
            identification=self.detected and bool(self.identity),
            documented_service=bool(self.documented_service),
            read_only_data=self.read_only_data,
        )


@dataclass(frozen=True)
class LS2Status:
    """Observable session state suitable for a desktop status panel."""

    transport: LS2TransportKind
    state: LS2ConnectionState
    detail: str
    identity: str | None = None
    address: str | None = None
    capabilities: LS2Capabilities = LS2Capabilities()
    mock: bool = False


class LS2Transport(Protocol):
    """Future read-only transport contract; no acquisition/control methods."""

    kind: LS2TransportKind

    def connect(self) -> LS2Observation: ...

    def disconnect(self) -> None: ...


class USBTransport(LS2Transport, Protocol):
    """USB transport slot for a future officially documented adapter."""

    kind: LS2TransportKind


class WiFiTransport(LS2Transport, Protocol):
    """Wi-Fi transport slot for a future officially documented adapter."""

    kind: LS2TransportKind


class UnsupportedUSBTransport:
    """Default USB transport; it performs no device access."""

    kind = LS2TransportKind.USB

    def connect(self) -> LS2Observation:
        raise LS2ConnectionBlocked(
            "USB transport unsupported: official LS2 interface documentation and hardware validation are required"
        )

    def disconnect(self) -> None:
        return None


class UnsupportedWiFiTransport:
    """Default Wi-Fi transport; it performs no socket or service probing."""

    kind = LS2TransportKind.WIFI

    def __init__(self, address: str):
        self.address = validate_ip_address(address)

    def connect(self) -> LS2Observation:
        raise LS2ConnectionBlocked(
            "Wi-Fi transport unsupported: no documented LS2 service/API endpoint is available"
        )

    def disconnect(self) -> None:
        return None


class MockUSBTransport:
    """MOCK/TEST-only USB fixture; never represents a physical LS2."""

    kind = LS2TransportKind.USB

    def __init__(self, observation: LS2Observation | None = None, error: BaseException | None = None):
        self.observation = observation or LS2Observation(
            LS2TransportKind.USB, True, "MOCK LS2 USB device", documented_service="MOCK read-only fixture",
            read_only_data=True, mock=True, detail="MOCK/TEST data only",
        )
        self.error = error

    def connect(self) -> LS2Observation:
        if self.error is not None:
            raise self.error
        return self.observation

    def disconnect(self) -> None:
        return None


class MockWiFiTransport:
    """MOCK/TEST-only Wi-Fi fixture; never opens a real network connection."""

    kind = LS2TransportKind.WIFI

    def __init__(self, address: str = "192.0.2.1", observation: LS2Observation | None = None, error: BaseException | None = None):
        self.address = validate_ip_address(address)
        self.observation = observation or LS2Observation(
            LS2TransportKind.WIFI, True, "MOCK LS2 Wi-Fi device", self.address,
            documented_service="MOCK read-only fixture", read_only_data=True,
            mock=True, detail="MOCK/TEST data only",
        )
        self.error = error

    def connect(self) -> LS2Observation:
        if self.error is not None:
            raise self.error
        return self.observation

    def disconnect(self) -> None:
        return None


class LS2Session:
    """Safe state machine for Connect → Detect → Identify → Verify → Stop.

    ``connect`` calls only the injected transport boundary. ``verify`` checks
    metadata supplied by that boundary; it does not probe a service or request
    data. There is intentionally no acquisition, upload, settings, or command
    method on this session.
    """

    def __init__(self, transport: LS2Transport):
        self.transport = transport
        self.observation: LS2Observation | None = None
        self.status = LS2Status(transport.kind, LS2ConnectionState.DISCONNECTED, "Not connected")

    def connect(self) -> LS2Status:
        try:
            observation = self.transport.connect()
            if not isinstance(observation, LS2Observation):
                raise ValueError("transport returned a malformed LS2 observation")
            self.observation = observation
            if not observation.detected:
                return self._set(LS2ConnectionState.DISCONNECTED, "No LS2 device was detected", observation)
            return self._set(LS2ConnectionState.DETECTED, "LS2 transport connected; identification is pending", observation)
        except TimeoutError:
            return self._set(LS2ConnectionState.TIMEOUT, "LS2 transport connection timed out")
        except LS2ConnectionBlocked as exc:
            return self._set(LS2ConnectionState.UNSUPPORTED, str(exc))
        except (OSError, TypeError, ValueError) as exc:
            return self._set(LS2ConnectionState.ERROR, f"LS2 transport error: {exc}")

    def detect(self) -> LS2Status:
        if self.observation is None:
            return self.status
        if not self.observation.detected:
            return self._set(LS2ConnectionState.DISCONNECTED, "No LS2 device was detected", self.observation)
        return self._set(LS2ConnectionState.DETECTED, "LS2 device detected", self.observation)

    def identify(self) -> LS2Status:
        if self.observation is None:
            return self.status
        if not self.observation.detected:
            return self._set(LS2ConnectionState.DISCONNECTED, "Identify requires a detected LS2 device", self.observation)
        if not self.observation.identity:
            return self._set(
                LS2ConnectionState.HARDWARE_VALIDATION_REQUIRED,
                "Device detected but identity is not officially validated",
                self.observation,
            )
        return self._set(LS2ConnectionState.DETECTED, f"Identified {self.observation.identity}", self.observation)

    def verify_documented_communication(self) -> LS2Status:
        if self.observation is None or not self.observation.detected:
            return self.status
        if not self.observation.identity:
            return self._set(
                LS2ConnectionState.HARDWARE_VALIDATION_REQUIRED,
                "Official device identity is required before communication verification",
                self.observation,
            )
        if not self.observation.documented_service:
            return self._set(
                LS2ConnectionState.PROTOCOL_UNKNOWN,
                "Protocol unknown — do not implement communication",
                self.observation,
            )
        if not self.observation.read_only_data:
            return self._set(
                LS2ConnectionState.HARDWARE_VALIDATION_REQUIRED,
                "Documented service exists, but read-only data behavior is not hardware-validated",
                self.observation,
            )
        return self._set(
            LS2ConnectionState.CONNECTED,
            "Documented read-only communication verified; acquisition was not started",
            self.observation,
        )

    def disconnect(self) -> LS2Status:
        self.transport.disconnect()
        self.observation = None
        return self._set(LS2ConnectionState.DISCONNECTED, "Disconnected")

    def _set(
        self,
        state: LS2ConnectionState,
        detail: str,
        observation: LS2Observation | None = None,
    ) -> LS2Status:
        observation = observation or self.observation
        self.status = LS2Status(
            self.transport.kind,
            state,
            detail,
            observation.identity if observation else None,
            observation.address if observation else None,
            observation.capabilities if observation else LS2Capabilities(),
            observation.mock if observation else False,
        )
        return self.status


__all__ = [
    "LS2Capabilities",
    "LS2ConnectionBlocked",
    "LS2ConnectionState",
    "LS2Observation",
    "LS2Session",
    "LS2Status",
    "LS2Transport",
    "LS2TransportKind",
    "MockUSBTransport",
    "MockWiFiTransport",
    "USBTransport",
    "UnsupportedUSBTransport",
    "UnsupportedWiFiTransport",
    "WiFiTransport",
]
