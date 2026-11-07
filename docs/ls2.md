# Terrameter LS2 connectivity discovery and safety boundary

## Status

M15 remains **blocked for direct instrument communication**. This investigation
found official evidence for remote connectivity and vendor software, but did
not establish a public, supported, and validated LS2 acquisition API/protocol.

The exact operational rule remains:

> **Protocol unknown — do not implement communication.**

No USB command, serial command, TCP/UDP request, VNC request, project mutation,
measurement trigger, protocol transfer, or instrument configuration operation
has been attempted by NiX ERT.

## Distinguishing local sample data from LS2 connectivity

The local Barugo files are real user-provided ABEM/Terrameter project databases
that can be inspected offline, but they are not a connection to an LS2 and do
not demonstrate LS2 communication. Read-only inspection of those files does not
change the M15 status, does not validate a transport, and does not authorize
acquisition or protocol implementation. See `docs/qualification.md` for the
recorded schema incompatibility and source facts.

## Evidence reviewed

| Source | Official/public evidence | Confidence |
|---|---|---|
| [Guideline Geo ABEM Terrameter LS 2 product page](https://guidelinegeo.com/products/abem/abem-terrameter-ls-2/) | Guideline Geo advertises flexible remote connectivity through Wi-Fi, Ethernet, or mobile connection, including operating, upgrading, downloading, and testing the instrument. The page also identifies Terrameter LS Toolbox, instrument software, manuals, settings files, and spread/protocol tools. | High for the advertised product capabilities; insufficient to infer an API, protocol, or port. |
| [Guideline Geo Downloads / Resources](https://guidelinegeo.com/help-center/resources/) | Official resource listings include the ABEM Terrameter LS 2 User Manual, Terrameter LS Toolbox, instrument software, settings files, protocol tool, protocol-tool manual, VPN certificate update, and technical specifications. | High for availability of official tools and documentation; the public listing does not publish an acquisition SDK or wire protocol. |
| [Guideline Geo Terrameter LS Toolbox update](https://guidelinegeo.com/news/abem-terrameter-ls-toolbox-v2020/) | Guideline Geo describes Terrameter LS Toolbox as software accompanying Terrameter LS, LS 2, and LS VES instruments and identifies version 2.0.2.0 in the 2021 notice. | High for the official companion-software relationship; no public protocol/API contract is stated. |
| [Guideline Geo Active Guidance](https://guidelinegeo.com/news/abem-active-guidance/) | Guideline Geo states that LS 2 UI v2.6.2 introduced Active Guidance and that later instrument software can be downloaded from the support section. | High for the version-specific UI/software statement; unrelated to an acquisition API. |

The product page also says that license upgrades may be transferred to the
instrument by USB and lists USB use for external GNSS integration. This
establishes that USB is used for some vendor-supported transfer/accessories; it
does **not** establish USB mass-storage exclusivity, a COM-port interface, a
serial protocol, or a general-purpose acquisition API.

## USB findings

### Established

- Official material identifies USB as a mechanism for some instrument file or
  accessory workflows, including license transfer and external GNSS-related
  functionality.
- Official resources provide instrument software and manuals for use with
  Terrameter LS 2 and Terrameter LS Toolbox.

### Not established by the reviewed official public material

- USB mass-storage-only behavior.
- A Windows COM port or USB serial interface.
- A vendor/product ID contract suitable for reliable identification.
- A required public driver contract.
- A public USB device protocol, SDK, or acquisition payload format.
- A documented read-only project/task/spread/data-download API.
- A documented acquisition-control interface.

**Conclusion:** USB can be documented as a vendor-supported connection in some
workflows, but the communication mechanism needed by NiX ERT is unknown. No
USB device is opened and no command is sent.

## Wi-Fi, Ethernet, and remote connectivity findings

### Established

- Guideline Geo publicly advertises remote operation/connectivity over Wi-Fi,
  Ethernet, and mobile connectivity, locally or through the internet.
- The official product page describes operation, upgrade, download, and test
  capabilities at a product level.
- Official manuals/resources exist for the instrument and Toolbox.

### Not established by the reviewed official public material

- Wi-Fi Access Point SSID/password behavior as a stable integration contract.
- A guaranteed default IP address or DHCP/static-addressing contract for every
  firmware version and network mode.
- Documented TCP/UDP ports or service names that NiX ERT may safely probe.
- Whether the remote UI uses VNC in all relevant versions/configurations.
- Whether VNC, where present, provides only remote UI access or exposes data
  transfer/control semantics; no VNC channel is used here.
- A public project/task/spread transfer API.
- A public measurement-download API or acquisition-control API.
- A public SDK, authentication contract, or stable wire protocol.

**Conclusion:** Network reachability must not be confused with instrument API
access. NiX ERT does not scan ports, connect to an LS2 IP, attempt VNC, or send
network requests.

## Offline connection/session architecture

`nix_ert.data.ls2_connection` adds explicit offline-ready contracts without
implementing hardware access:

- `USBTransport` and `WiFiTransport` expose only `connect`/`disconnect`;
- `LS2Session` models `disconnected`, `detected`, `connected`, `unsupported`,
  `protocol unknown`, `hardware validation required`, `timeout`, and `error`;
- `LS2Capabilities` distinguishes detection, identification, documented
  service, read-only data, acquisition control, and mutation permission;
- `LS2Status` is suitable for UI display and records whether an observation is
  mock data;
- `UnsupportedUSBTransport` and `UnsupportedWiFiTransport` remain the default
  fail-closed implementations;
- `MockUSBTransport` and `MockWiFiTransport` are explicit `MOCK/TEST` fixtures
  and never access hardware or a network.

The intended first-device sequence is represented but does not automatically
continue to acquisition:

```text
Connect → Detect → Identify → Verify documented communication → Stop
```

The session has no acquisition, upload, settings, or instrument-mutation
methods. A session reaches `connected` only when an injected observation claims
a documented read-only service. The claim is fixture metadata in offline mode,
not real-device validation.

## Desktop connection panel

The desktop now includes an `LS2 Connection` panel showing USB and Wi-Fi state,
user-supplied Wi-Fi address, identity/address details, capability status, and
explicit safety text. `Check USB` and `Check Wi-Fi` use the unsupported
fail-closed transports. `Run MOCK/TEST USB` and `Run MOCK/TEST Wi-Fi` exercise
the complete state sequence using marked fixtures only; they do not represent a
physical LS2 and do not validate a real network or device.

- validates a user-supplied unicast IP address without probing it;
- accepts only externally supplied USB enumeration facts;
- accepts only externally supplied network facts for the exact requested IP;
- reports observed, unavailable, timeout, rejected, and unsupported states;
- rejects malformed observations;
- never scans arbitrary ports or interfaces;
- never opens serial channels;
- never sends commands;
- refuses all service probing until an official service name/port contract is
  supplied and separately validated.

The default USB and network providers fail closed. Mock providers are used in
tests, so the normal test suite never requires a physical LS2.

The existing `nix_ert.data.ls2` adapter remains the only acquisition-shaped
boundary. It accepts a future injected read-only byte transport, validates the
payload through the existing DAT parser, and has no write/control methods.

## Future architecture after the blocker is satisfied

```text
NiX ERT
   │
   ▼
LS2 Manager
   │
   ├── USB observation / officially documented transport
   │
   └── Wi-Fi observation / officially documented transport
          │
          ▼
     LS2 Session
          │
          ▼
   Official protocol/API only
          │
          ▼
 Project / task / measurement bytes
          │
          ▼
 Existing DAT validation boundary
          │
          ▼
 Existing immutable NiX ERT import service
```

The future adapter must be read-only first, preserve the original byte payload,
validate it through the current import boundary, and never modify the
instrument or existing raw/project data.

## Required inputs to unblock M15

1. Official protocol/interface documentation or a vendor-supported SDK that
   explicitly covers read-only survey/data access.
2. Legal/technical authorization for the intended access method.
3. Exact supported OS, driver, transport, authentication, endpoint/service,
   and software/firmware compatibility requirements.
4. A representative LS2 device/export fixture and expected read-only behavior.
5. Validation evidence for project/task/spread transfer and data-download
   payloads, including malformed and unsupported responses.

Until these inputs exist, direct LS2 communication is intentionally blocked.
The offline DAT/import pipeline remains supported independently.
