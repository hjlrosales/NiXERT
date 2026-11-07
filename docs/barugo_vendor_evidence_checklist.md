# Vendor evidence checklist — ABEM `project.db` importer

**Purpose:** provide the minimum authoritative evidence required before NiX ERT can implement an ABEM `project.db` importer. This checklist concerns file interoperability only; it does not authorize LS2 acquisition or undocumented communication.

**Detailed request package:** see [`barugo_vendor_evidence_request.md`](barugo_vendor_evidence_request.md) for blocker-specific questions, minimum acceptable evidence, validation procedures, and qualification states.

## Required evidence

### 1. Schema and version contract

- [ ] Authoritative schema documentation for `ProjectSchemaVersion=4`, `CommonSchemaVersion=3`, and `TT_EC_SCHEMA`.
- [ ] Complete table/column data dictionary, including declared types, units, nullability, enumerations, defaults, and lifecycle meaning.
- [ ] Authoritative primary-key and foreign-key/relationship definitions for `Tasks`, `TaskSettings`, `Sessions`, `Measures`, `DP_ABMN`, `DP_MEASURE`, `DPV`, `Datatype`, `Stations`, `Positions`, `Electrodes`, `GPSPositions`, `ExternalData`, `Datasets`, `DatasetItems`, `Log`, and test/auxiliary tables.
- [ ] Version-compatibility policy: supported versions, migration rules, and behavior for newer, older, malformed, or incomplete databases.

### 2. ERT acquisition semantics

- [ ] Official numeric code tables for `Tasks.ArrayCode`, `ProtocolMode`, `DP_ABMN.Mode`, and `ModeValue`.
- [ ] Definitions for the observed Gradient/2x21 configuration and its protocol/spread files.
- [ ] Exact A/B/M/N role, electrode numbering, switch-number, switch-address, cable, takeout, and remote-electrode relationship.
- [ ] Rules for repeated channels and `SeqNum`, including the authoritative DC resistance/voltage/current/`ρapp` selection rule.
- [ ] Channel, polarity, reference-electrode, stacking, and phase/window definitions for `R`, `I`, `ΔU`, `SP`, `IP`, and `IPΔU`.

### 3. VES semantics

- [ ] Authoritative definition of the VES array/protocol code and Schlumberger geometry representation.
- [ ] Exact meaning, units, sign convention, and derivation rules for AB/2, MN/2, electrode positions, and `FocusX/Y/Z`.
- [ ] Rules for VES observation identity, repeated readings, spacing changes, unlinked geometry, and auxiliary records.
- [ ] Recommended lossless VES export/persistence representation suitable for NiX.

### 4. Coordinates and units

- [ ] Units and scale for `DP_ABMN`, `Tasks.SpacingX/Y/Z`, `Stations`, `Positions`, and `Electrodes`.
- [ ] Axis origin/orientation and whether coordinates are local station coordinates, physical distances, elevations, or another reference system.
- [ ] Electrode numbering and coordinate-to-switch mapping for both inline ERT and VES.
- [ ] CRS, datum, latitude/longitude/elevation semantics, GPS fix-quality meanings, and any required reprojection rules.

### 5. QC, uncertainty, and timestamps

- [ ] Complete bit definitions/enumerations for `DP_MEASURE.Ready`, `DP_ABMN.Ready`, `DPV.Status`, `DataSDevType`, `Mode`, and related status fields.
- [ ] Exact meanings, units, and statistical definitions for `DataSDev`, `N`, `MCycles`, `ADValue`, and `ADRange`.
- [ ] Rules for exclusion, invalid measurements, negative apparent resistivity, failed tests, and operational/log records.
- [ ] Timestamp timezone, clock source, and event meaning for task, session, measurement, log, and electrode-test timestamps.

### 6. Conformance fixtures and expected results

- [ ] Authorized copies of representative ERT and VES databases, including clean, excluded/failed, multi-channel, repeated-stack, coordinate/GPS, and auxiliary-record cases.
- [ ] For every fixture: ABEM software/firmware version, acquisition settings, array/protocol description, coordinate units/CRS, and license/permission to use it for development and automated tests.
- [ ] Row-level expected records for selected `DP_MEASURE` links, including geometry, channel/sequence/datatype values, QC/status interpretation, and derived `ρapp`.
- [ ] Expected handling of unlinked `DP_ABMN`, orphan/invalid rows, logs, tests, IP data, and unknown columns.
- [ ] Tolerance and independent calculation procedure for checking `K`, `R`, `ΔU/I`, and `ρapp`.

### 7. Optional protocol evidence

Protocol evidence is required only if NiX will obtain databases through LS2 rather than through an authorized file export:

- [ ] Officially supported USB/Wi-Fi/API/SDK interface and supported software/firmware versions.
- [ ] Read-only export/download workflow, endpoint/service details, authentication requirements, payload/file format, and error behavior.
- [ ] Explicit confirmation that the interface permits survey/project data export without acquisition or instrument mutation.
- [ ] Vendor-supported test procedure and a validated device or vendor fixture. No undocumented commands, port scans, or reverse engineering will be used.

## Unblock criteria

The importer may move to implementation only when all mandatory sections above have an authoritative answer, the VES persistence target is approved, and authorized fixtures with expected results are available. Otherwise NiX will retain the read-only inspector and fail closed on the unresolved field or version.

A successful internal arithmetic match alone is insufficient: it does not decode vendor semantics, validate QC/status interpretation, establish coordinate meaning, or validate inversion/geology.

## Vendor response format

Please return, for each checklist item, one of:

- **SUPPORTED** — attach the authoritative definition or fixture reference;
- **NOT APPLICABLE** — explain why;
- **UNKNOWN/UNSUPPORTED** — identify the limitation and affected versions.

Include document title/version, publication date, applicable instrument/software versions, licensing/permission terms, and contact for clarification.

## Current NiX boundary

Until this evidence is supplied, NiX will not implement ABEM conversion, LS2 acquisition, or protocol communication. The original Barugo databases remain read-only and are not treated as live LS2 data.
