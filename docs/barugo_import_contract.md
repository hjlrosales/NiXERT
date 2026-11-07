# Barugo ABEM `project.db` semantic inventory and import contract

**Status:** specification only — no importer is implemented. The v0.1 draft is retained; the evidence does **not** justify a v0.2 importer contract.

**Contract version:** `abem-project-db-to-nix-v0.1-draft`

**Resolution review:** 2026-09-14. This review uses only the supplied files,
existing NiX code, existing cited official/public documentation, and
read-only mathematical/structural analysis. It does not use LS2 hardware,
undocumented protocol probing, or reverse engineering.

**Vendor unblock checklist:** see [`barugo_vendor_evidence_checklist.md`](barugo_vendor_evidence_checklist.md) for the concise evidence request that must be satisfied before importer implementation.

The two source files were opened with SQLite `mode=ro` and inspected on
2026-09-14. No source file was copied, migrated, transformed, or written. The
contract below separates facts observed in these files from interpretations
that require an explicit future vendor/import specification.

## 1. Source files and observed facts

| Dataset | Source | SQLite size | SHA-256 | Task | Project/Common schema |
|---|---|---:|---|---|---|
| ERT | `ERT Survey Data/Project7/project.db` | 557,056 bytes | `057674127c923842510ee5e8af6082fed88ef152438f3752ca681d5f2f6d47af` | `Gradient_1` | 4 / 3 |
| VES | `VES Survey Data/Project8/project.db` | 196,608 bytes | `97eec29b3f9870092f9674e54b560df20f9df2130ac18778ff29161757d09e51` | `VES Schlumberger_1` | 4 / 3 |

Both pass SQLite `PRAGMA integrity_check` (`ok`). Both record instrument
serial `LS26186002`, instrument software `2.2.5b(3179)`, and transmitter
software `3.7.2`. These are file metadata, not evidence that NiX ERT
communicated with the instrument.

### ERT facts

- `Tasks`: 1 row; `ArrayCode=15`; `SpacingX=15.0`, `SpacingY=1.0`,
  `SpacingZ=1.0`; task time `2025-06-05 04:08:57`.
- `TaskSettings`: `BaseReference=0;0;0`, `ElectrodeSpacing=15;1;1`,
  `ProtocolMode=15`, `ProtocolFile=/home/root/protocols/Gradient_2x21.xml`,
  `SpreadFile=/home/root/protocols/2X21.xml`.
- `DP_MEASURE`: 401 links, all `Ready=1`.
- `DP_ABMN`: 518 geometry rows; 401 are linked by `DP_MEASURE`; linked geometry
  uses X-only coordinates (`Y=Z=0` for A/B/M/N). The union of linked A/B/M/N
  coordinates contains 37 positions; the full table contains 41 distinct X
  values from 0 through 40.
- `DPV`: 6,007 rows; 401 linked `ρapp` rows; 401 linked primary resistance
  rows; 228 linked channel-1 resistance rows and 173 linked channel-2
  resistance rows. The primary linked electrical channel is not a single
  fixed channel across the file.
- Stored `ρapp` range is `-54243.30588595141` to `20748.435437999226 Ωm`;
  35 of 401 stored primary `ρapp` values are negative.
- Stored data include named `R` (Ω), `I` (A), `ΔU` (V), `SP` (V), temperature
  (°C), IP windows (mV/V), and IP delta voltage (V). `SNR`, chargeability `t`,
  `Avg`, `Signal`, `IPSP`, power `P`, length `l`, and `MinMax` have no DPV rows
  in this file.
- `Measures`: 228 rows, one station, one distinct session ID, timestamps from
  `2025-06-05 04:21:14` through `05:00:05`.
- `Sessions`: 4 rows for the task, timestamps `04:11:28` through `04:21:08`.
- `Log`: 47 rows referring to 37 measurement IDs. `ElectrodeTestData`: 91
  rows. These are operational/audit records and must not be mistaken for the
  401 DP_MEASURE observations.

### VES facts

- `Tasks`: 1 row; `ArrayCode=7`; `SpacingX=1.0`, `SpacingY=1.0`,
  `SpacingZ=1.0`; task time `2025-06-05 07:12:13`.
- `TaskSettings`: `BaseReference=0;0;0`, `ElectrodeSpacing=1;1;1`,
  `ProtocolMode=15`, `ProtocolFile=/home/root/protocols/VES_Schlumberger.xml`,
  `SpreadFile=/home/root/protocols/VES_C1C2P1P2.xml`.
- `DP_MEASURE`: 25 links, all `Ready=1`.
- `DP_ABMN`: 30 geometry rows; 25 are linked. Linked geometry is X-only
  (`Y=Z=0`). The linked VES positions are symmetric: A/B are at `+/-AB/2`
  and M/N are at `+/-MN/2` in the stored X coordinate system. The stored
  values include AB/2 values `1.0, 1.4, 1.9, ...` and several MN/2 groups
  (`0.2`, `1.0`, `5.2`, `27.0`).
- `DPV`: 450 rows; 25 linked primary `ρapp` rows and 25 linked primary
  channel-1 `R` rows. Stored `ρapp` range is `8.55678743779201` to
  `357.91754793064314 Ωm`; no stored primary `ρapp` value is negative.
- Stored data include `R` (Ω), `I` (A), `ΔU` (V), `SP` (V), temperature (°C),
  four IP windows per linked observation (mV/V), and IP delta voltage (V).
  `SNR`, `t`, `Avg`, `Signal`, `IPSP`, `P`, `l`, and `MinMax` have no DPV rows.
- `Measures`: 25 rows, one station, 25 distinct session IDs, timestamps from
  `2025-06-05 07:16:03` through `09:44:39`.
- `Sessions`: 34 rows for the task, timestamps `07:15:56` through `09:44:33`.
- `Log`: 92 rows; `ElectrodeTestData`: 66 rows. Five `DP_ABMN` rows are not
  linked by `DP_MEASURE` and must not be imported as observations without a
  documented rule.

## 2. Complete table/column inventory

The following is the observed SQLite schema. SQLite declared types are shown
as stored; SQLite does not enforce the semantic units of numeric columns.

| Table | Columns (declared type) |
|---|---|
| `ProjectSchemaVersion` | `Version INTEGER`, `Comment TEXT` |
| `CommonSchemaVersion` | `Version INTEGER`, `Comment TEXT` |
| `TT_EC_SCHEMA` | `VERSION INTEGER`, `COMMENT TEXT` |
| `Tasks` | `ID INTEGER PK`, `Name TEXT`, `Active INTEGER`, `PosX REAL`, `PosY REAL`, `PosZ REAL`, `SpacingX REAL`, `SpacingY REAL`, `SpacingZ REAL`, `ArrayCode INTEGER`, `Time timestamp` |
| `TaskSettings` | `key1 INTEGER PK`, `key2 INTEGER PK`, `Setting TEXT PK`, `Value TEXT`, `Auto INTEGER` |
| `AcqSettings` | `key1 INTEGER PK`, `key2 INTEGER PK`, `Setting TEXT PK`, `Value TEXT`, `Auto INTEGER` |
| `Sessions` | `ID INTEGER PK`, `Time timestamp`, `TaskID INTEGER`, `InstrumentSerial TEXT`, `InstrumentSoftware TEXT`, `TransmitterSerial TEXT`, `TransmitterSoftware TEXT` |
| `Measures` | `ID INTEGER PK`, `StationID INTEGER`, `PosLatitude REAL`, `PosLongitude REAL`, `PosQuality INTEGER`, `Time timestamp`, `IntPowerVolt REAL`, `ExtPowerVolt REAL`, `Temp REAL`, `Light REAL`, `SessionID INTEGER`, `PositionId INTEGER` |
| `Stations` | `ID INTEGER PK`, `TaskID INTEGER`, `SpreadPositionID INTEGER`, `PosX REAL`, `PosY REAL`, `PosZ REAL`, `Time TIMESTAMP` |
| `Positions` | `Id INTEGER PK`, `TaskId INTEGER`, `PositionType INTEGER`, `PosX REAL`, `PosY REAL`, `PosZ REAL`, `IsRemote INTEGER`, `MeasureID INTEGER`, `MeasurePhase INTEGER`, `MeasureTime REAL` |
| `DP_ABMN` | `ID INTEGER PK`, `TaskID INTEGER`, `DPKEY TEXT`, `APosX REAL`, `APosY REAL`, `APosZ REAL`, `BPosX REAL`, `BPosY REAL`, `BPosZ REAL`, `MPosX REAL`, `MPosY REAL`, `MPosZ REAL`, `NPosX REAL`, `NPosY REAL`, `NPosZ REAL`, `FocusX REAL`, `FocusY REAL`, `FocusZ REAL`, `Ready INTEGER`, `Note TEXT`, `Mode INTEGER`, `ModeValue REAL` |
| `DP_MEASURE` | `ID INTEGER PK`, `DPID INTEGER`, `MeasureID INTEGER`, `Ready INTEGER` |
| `DPV` | `ID INTEGER PK`, `TaskID INTEGER`, `MeasureID INTEGER`, `DPID INTEGER`, `Channel INTEGER`, `SeqNum INTEGER`, `DatatypeID INTEGER`, `DataValue REAL`, `DataSDev REAL`, `ADValue INTEGER`, `ADRange INTEGER`, `Status INTEGER`, `N INTEGER`, `MCycles INTEGER`, `DataSDevType INTEGER` |
| `Datatype` | `ID INTEGER PK`, `Name TEXT`, `Unit TEXT`, `Explanation TEXT` |
| `Electrodes` | `ID INTEGER PK`, `SpreadID INTEGER`, `PosX INTEGER`, `PosY INTEGER`, `PosZ INTEGER`, `CurrentElectrode INTEGER`, `PotentialElectrode INTEGER`, `RemoteElectrode INTEGER`, `SwitchNumber INTEGER`, `SwitchAddress INTEGER`, `Cable INTEGER`, `Takeout TEXT` |
| `ElectrodeTestData` | `ID INTEGER PK`, `TaskID INTEGER`, `StationID INTEGER`, `SwitchNumber INTEGER`, `SwitchAddress INTEGER`, `PosX REAL`, `PosY REAL`, `PosZ REAL`, `ResistanceValue REAL`, `CurrentValue REAL`, `TestStatus INTEGER`, `UserSetting INTEGER`, `TxStatus INTEGER`, `Time TIMESTAMP`, `PositionId INTEGER` |
| `GPSPositions` | `Id INTEGER PK`, `PositionID INTEGER`, `GPSSOURCE INTEGER`, `smask INTEGER`, `utc timestamp`, `sig INTEGER`, `fix INTEGER`, `PDOP REAL`, `HDOP REAL`, `VDOP REAL`, `LAT REAL`, `LON REAL`, `ELV REAL`, `SPEED REAL`, `DIRECTION REAL`, `INUSE INTEGER`, `INVIEW INTEGER`, `satinfo TEXT` |
| `ExternalData` | `ID INTEGER PK`, `TaskID INTEGER`, `InstrID TEXT`, `MeasureID INTEGER`, `PhaseID INTEGER`, `PhaseType INTEGER`, `PhasePolarity INTEGER`, `DatatypeID INTEGER`, `DataValue REAL`, `DataSDev REAL`, `Status INTEGER`, `N INTEGER` |
| `Datasets` | `Id INTEGER PK`, `Name TEXT`, `ExcludeSet boolean` |
| `DatasetItems` | `Id INTEGER PK`, `DataSetsId INTEGER`, `MeasureID INTEGER`, `DPID INTEGER` |
| `Log` | `ID INTEGER PK`, `Time timestamp`, `PosLatitude REAL`, `PosLongitude REAL`, `PosQuality INTEGER`, `IntPowerVolt REAL`, `ExtPowerVolt REAL`, `Temp REAL`, `Light REAL`, `SourceTypeID INTEGER`, `SourceID TEXT`, `TaskID INTEGER`, `MeasureID INTEGER`, `WhatEnglish TEXT`, `What TEXT`, `Data BLOB`, `EventClass INT`, `EventClassId TEXT` |
| `EventSources` | `ID INTEGER PK`, `Name TEXT` |
| `TT_EC_LISTS` | `ID INTEGER PK`, `TASKID INTEGER`, `NAME TEXT`, `ALONGCABLE INT` |
| `TT_EC_DATA` | `ID INTEGER PK`, `EC_LIST_ID INTEGER`, `X REAL`, `Y REAL`, `Z REAL` |
| `sqlite_sequence` | SQLite internal autoincrement bookkeeping; not project data |

Only `TT_EC_DATA.EC_LIST_ID → TT_EC_LISTS.ID` is declared in
`PRAGMA foreign_key_list` in these files. The measurement relationships below
are therefore **logical relationships demonstrated by values and joins, not
SQLite-declared foreign keys**.

## 3. Relationship semantics established by the files

For both datasets:

```text
Tasks.ID
  ├── DP_ABMN.TaskID
  ├── DPV.TaskID
  ├── Sessions.TaskID
  ├── Stations.TaskID
  └── Measures → Sessions.TaskID (through Measures.SessionID)

DP_MEASURE.DPID + DP_MEASURE.MeasureID
  ├── DP_ABMN.ID = DPID
  ├── Measures.ID = MeasureID
  └── DPV.DPID + DPV.MeasureID
```

Observed integrity checks:

- zero `DPV` rows without a matching `(DPID, MeasureID)` in `DP_MEASURE`;
- zero `DP_MEASURE` rows without matching `DP_ABMN.ID`;
- zero `DP_MEASURE` rows without matching `Measures.ID`;
- zero duplicate `(DPID, MeasureID)` pairs in `DP_MEASURE`;
- zero task mismatches between linked `DPV` and `DP_ABMN`.

This does not prove that every unlinked vendor row is invalid; it establishes
that the future observation import boundary must begin with `DP_MEASURE` and
not with every row in `DPV` or `DP_ABMN`.

`DPV` is a value stream, not one row per measurement. A single linked
observation has multiple `(Channel, SeqNum, DatatypeID)` values. The importer
must preserve the complete value stream or a lossless source reference; it
must not select a value solely by `DatatypeID` without specifying channel and
sequence semantics.

## 4. Geometry, coordinates, and electrode numbering

### ERT

`DP_ABMN` stores four explicit point coordinates (`APos*`, `BPos*`, `MPos*`,
`NPos*`) for each data point. In the observed ERT file, Y and Z are zero and X
values are integer station-like positions from 0 to 40. `TaskSettings` and
`Tasks` both record X spacing of 15.0. Recalculation of all 401 linked values
shows that multiplying the stored X coordinates by `SpacingX` produces the
correct dimensional geometry for the half-space geometric-factor equation.

This supports the following **contract rule**, subject to importer validation:

```text
physical_x_m = stored_APosX/BPosX/MPosX/NPosX * Tasks.SpacingX
physical_y_m = stored_*PosY * Tasks.SpacingY
physical_z_m = stored_*PosZ * Tasks.SpacingZ
```

It does not establish a global coordinate reference system, an electrode
numbering convention, or that X is a GIS coordinate. `DPKEY` is a serialized
geometry key, not an electrode-number field. There is no direct, trustworthy
mapping from the observed `DP_ABMN` coordinates to NiX electrode integers for
all future ABEM files. A future importer must create a deterministic source
geometry identity (for example, linked-row ID plus role) and only assign NiX
numbers after a validated numbering policy is supplied.

The `Electrodes` table is empty in both supplied files, so its switch/cable
fields cannot be used for these datasets. `ElectrodeTestData` contains test
positions and switch addresses, not measurement electrode numbering.

### VES

The VES geometry is not an electrode-number list. It is a symmetric four-point
layout in a local X coordinate system:

```text
A = +AB/2, B = -AB/2, M = +MN/2, N = -MN/2
```

The task name and protocol filename identify the intended layout as
Schlumberger, and the geometry is consistent with that layout. `AB/2` and
`MN/2` are derived from absolute coordinate magnitudes; this is an evidenced
geometric derivation, not a claim that the vendor numeric `ArrayCode=7` has
been decoded. The file provides no separate VES table containing named
`AB/2`/`MN/2` columns.

`FocusZ` is populated and follows a vendor depth/focus sequence, but its
calculation and scientific meaning are not documented by the database schema.
It must be preserved as vendor metadata and must not be silently mapped to NiX
VES layer depth or electrode elevation.

The VES `TaskSettings.ElectrodeSpacing=1;1;1` is consistent with the stored
coordinates being used at their recorded scale. The database itself does not
provide a units declaration for `DP_ABMN` coordinates; the proposed importer
must require a unit/scale confirmation rather than silently asserting metres.

## 5. Electrical datatypes, units, and independent checks

The `Datatype` table is the authoritative source of the names, displayed units,
and explanations found in these files:

| ID | Name | Unit | Explanation | Mapping status |
|---:|---|---|---|---|
| 1 | `SP` | V | SP | preserve as extra; not NiX voltage without polarity contract |
| 2 | `ρapp` | Ωm | Apparent Resistivity value | direct candidate for NiX apparent resistivity, after validation |
| 3 | `IP` | mV/V | One IP window. Can be recalculated | unsupported by current NiX measurement model; preserve extra |
| 4 | `SNR` | dB | Signal to noice ratio | no rows in supplied files; preserve schema metadata |
| 5 | `R` | Ω | Resistance | direct candidate for NiX resistance, with channel/sequence retained |
| 6 | `I` | A | Current | direct candidate for NiX current, with channel/sequence retained |
| 7 | `ΔU` | V | ResDeltaVoltage | direct candidate for measured voltage only after polarity/channel contract |
| 8 | `t` | ms | Chargeability | no rows; unsupported by current NiX model |
| 9 | `IPΔU` | V | IPDeltaVoltage | preserve extra; not ordinary DC voltage |
| 10 | `Avg` | V | Average | no rows; semantics not sufficient for NiX voltage |
| 11 | `Signal` | V | Intermediary result | no rows; preserve as vendor extra |
| 12 | `IPSP` | V | Sp compensation | no rows; preserve as vendor extra |
| 13 | `Temp` | C | Temperature | preserve as acquisition metadata/extra |
| 14 | `P` | W | Power | no rows; preserve schema metadata |
| 15 | `l` | m | Length | no rows; meaning/role not established |
| 16 | `MinMax` | % | (Max-Min)/Min | no rows; preserve schema metadata |

### Reproduction method

For each linked `DP_MEASURE` row, use the primary resistance and apparent
resistivity values at the same electrical channel and `SeqNum=0`. With physical
coordinates in metres, compute:

```text
K = 2π / (1/|AM| - 1/|BM| - 1/|AN| + 1/|BN|)
ρapp_reproduced = R * K
```

For the ERT file, `physical_coordinate = stored_coordinate * SpacingX` in X
(and equivalent Y/Z scaling if non-zero). For the VES file, the observed
`SpacingX=1` leaves the stored local coordinate values unchanged.

Observed results:

| Dataset | Matched rows | Maximum absolute difference | Maximum relative difference |
|---|---:|---:|---:|
| ERT | 401 / 401 | `1.4551915228366852e-11 Ωm` | `2.682711717269371e-16` |
| VES | 25 / 25 | `2.842170943040401e-14 Ωm` | `1.968607575895177e-16` |

Additionally, for every matched row, `ΔU / I = R` when using the corresponding
channel-14 current record: maximum absolute difference was `0.0 Ω` for 228/228
ERT rows where the required records were present and 25/25 VES rows. The
remaining 173 ERT records lack the required channel-14 current pairing in the
stored value stream and must not be filled by inference.

This validates internal arithmetic consistency of the supplied records. It does
not validate the vendor's acquisition electronics, geometry convention outside
these files, instrument status bit meanings, or inversion results.

## 6. QC, status, and timestamps

`DP_MEASURE.Ready` is a vendor readiness/selection field in these files, but
its semantic equivalence to NiX `ACTIVE`, `EXCLUDED`, or `FLAGGED` is not
established. All linked rows are `Ready=1`; do not map that value to NiX QC
status without vendor documentation.

`DP_ABMN.Ready` is not the same field: ERT linked rows contain values 0, 1, and
17; VES linked rows contain 0 and 1. The numeric meanings of 0, 1, and 17 are
unknown. Preserve both source fields as raw metadata and require an explicit
status mapping before using them for exclusion.

`DPV.Status` is a numeric bitmask or status code candidate, not a NiX quality
label. Values observed include 0, 50,331,648, and 587,202,560. Their bit
meanings are unknown. A future importer must preserve the integer exactly and
must not translate it into QC acceptance, rejection, or suspiciousness.

`DPV.DataSDev` is a stored standard-deviation-like field according to its name,
but the semantics of `DataSDevType`, `N`, `MCycles`, `ADValue`, and `ADRange`
are not established sufficiently to map them to a NiX uncertainty model. Keep
them in a lossless vendor-value record.

Timestamps are present in `Tasks.Time`, `Sessions.Time`, `Measures.Time`,
`Log.Time`, and `ElectrodeTestData.Time`. Their event semantics differ. Preserve
the original text and source table/row; do not collapse them into one survey
date without a defined precedence rule. GPS tables exist but have zero rows in
both files, so the measured lat/lon in `Measures` must not be treated as a
complete coordinate solution or automatic reprojection input.

## 7. Evidence-backed NiX mapping table

| ABEM source | Proposed NiX concept | Status | Required condition |
|---|---|---|---|
| file path + SHA-256 + byte count | imported source provenance | **DIRECT** | source is read-only and hash recorded before import |
| `Tasks.Name` | survey name | **DIRECT** | retain original text |
| schema/version rows | source metadata | **DIRECT** | retain numeric versions and comments |
| `DP_MEASURE` linked row | measurement identity boundary | **DIRECT** | use `(DP_MEASURE.ID, DPID, MeasureID)` as source identity |
| `DP_ABMN` A/B/M/N coordinates | measurement geometry | **DIRECT FACT / SCALE CONDITIONAL** | require validated coordinate scale/units; preserve raw coordinates |
| `Datatype.Name=ρapp`, `Unit=Ωm` | NiX apparent resistivity | **DIRECT CANDIDATE** | exactly one selected primary row per linked observation; finite value; arithmetic check passes |
| `Datatype.Name=R`, `Unit=Ω` | NiX resistance | **DIRECT CANDIDATE** | channel/sequence selection is fixed and source row retained |
| `Datatype.Name=I`, `Unit=A` | NiX current | **DIRECT CANDIDATE** | channel/sequence pairing is fixed; absent values remain absent |
| `Datatype.Name=ΔU`, `Unit=V` | NiX voltage | **CONDITIONAL** | polarity and channel semantics are documented; do not confuse with IPΔU |
| `Tasks.SpacingX/Y/Z` + `DP_ABMN` | local scaled coordinates | **CONDITIONAL** | scale/unit contract is accepted and geometry validation passes |
| VES task/protocol name + symmetric ABMN geometry | NiX VES Schlumberger geometry | **CONDITIONAL, ERT-SEPARATE** | geometry symmetry and derived spacings pass; numeric code remains preserved |
| `TaskSettings.ProtocolFile`, `SpreadFile`, `ProtocolMode`, `ArrayCode` | vendor acquisition metadata | **DIRECT AS RAW / UNKNOWN SEMANTICS** | preserve verbatim; no NiX array-name translation for ERT |
| `DPV` complete rows | vendor raw electrical values | **DIRECT AS LOSSLESS EXTRA** | retain channel, sequence, datatype, value, deviation, status, ADC/count fields |
| `Ready`, `Status`, `DataSDev*`, `N`, `MCycles` | NiX QC/status/uncertainty | **NOT MAPPED** | vendor definitions required |
| `FocusZ` | NiX depth/elevation | **NOT MAPPED** | vendor definition required |
| `GPSPositions`, `Measures` coordinates | NiX projected/GIS coordinates | **NOT MAPPED** | CRS, datum, fix semantics, and reprojection contract required |
| `IP`, `IPΔU`, `SP`, `Temp`, other datatypes | NiX measurement extras | **LOSSLESS EXTRA ONLY** | preserve; no scientific reinterpretation |

“DIRECT” means the database field and its syntactic relationship are directly
observed. “CANDIDATE” and “CONDITIONAL” are deliberately not permission to
implement silently; they identify the smallest mapping that can be evaluated by
contract validation.

## 8. Proposed versioned import contract

A future importer may accept only an explicitly selected dataset kind:
`ABEM_ERT` or `ABEM_VES`. It must not infer one common representation from the
presence of ABEM tables.

### Common envelope

1. Open the source in read-only mode and compute SHA-256/byte count before any
   parsing.
2. Verify SQLite integrity and require exactly one supported project/common
   schema version policy. Unknown or newer versions fail closed.
3. Record source path, hash, byte count, schema versions/comments, task ID/name,
   all task settings, instrument/session metadata, and software version.
4. Create one NiX survey only after a user explicitly identifies whether this
   source is ERT or VES. Preserve `BARUGO SAMPLE DATA — REAL USER-PROVIDED DATA`
   as provenance; never represent it as live LS2 acquisition.
5. Preserve each source table/row key and all unmapped DPV fields in a
   lossless `extra`/sidecar record. No silent discard is allowed.
6. Copy bytes to a NiX-managed immutable source area only as an explicit import
   operation. The original remains untouched and is never used as a writable
   project database.

### ERT branch

1. Select only `DP_MEASURE` links for the chosen task; reject links with missing
   `DP_ABMN`, `Measures`, or linked DPV values.
2. Preserve `(DP_MEASURE.ID, DPID, MeasureID)` as the source measurement key.
3. Preserve raw A/B/M/N coordinates and task spacing. Require an explicit unit
   and coordinate-scale confirmation before producing NiX electrode positions.
4. Reject ERT import until a vendor-supported mapping for `ArrayCode=15`,
   `ProtocolMode=15`, `Gradient_2x21.xml`, and `2X21.xml` to a NiX array is
   supplied and tested. The observed names are not enough to decode all
   protocol semantics or electrode numbering.
5. Select one primary DC `R` and `ρapp` pair only through a versioned channel/
   sequence rule. Require finite values and reproduce `ρapp = R*K` within a
   documented tolerance. Keep all alternate channels and IP windows as raw
   extras.
6. Do not import any negative `ρapp` into NiX inversion-ready data. Preserve it
   in the source record and expose it for explicit QC review; the source value
   is not deleted or changed.

### VES branch

1. Select only the 25 `DP_MEASURE` links for `VES Schlumberger_1`.
2. Derive `AB/2=|A-B|/2` and `MN/2=|M-N|/2` only after verifying the observed
   symmetric ordering and local-coordinate assumptions. Do not use `FocusZ` as
   depth.
3. Require a VES unit/scale declaration; the supplied file is arithmetically
   consistent with its stored scale and `SpacingX=1`, but the schema does not
   itself declare coordinate units.
4. Select the primary channel-1 `R`/`ρapp` pair under a versioned rule and
   reproduce all 25 values within the measured floating-point tolerance.
5. Store VES points in a dedicated VES representation; do not force them into
   the current ERT measurement/electrode-number model.
6. Preserve all four IP windows, SP, temperature, status/count fields, and raw
   geometry as extras.

## 9. Validation and fail-closed rules

The importer must reject the source, without creating a partially valid NiX
survey, if any of the following occurs:

- source cannot be opened read-only, fails SQLite integrity, or changes hash
  during processing;
- required schema/version/table/column policy is not met;
- task selection is ambiguous or requested ERT/VES kind conflicts with task
  metadata;
- a `DP_MEASURE` link lacks geometry, a `Measures` row, or linked DPV values;
- a `(DPID, MeasureID)` pair is duplicated or DPV task IDs disagree;
- coordinates are missing, non-finite, degenerate, or units/scale are not
  explicitly accepted;
- array/protocol code cannot be mapped by an approved versioned mapping;
- no unique primary resistance/apparent-resistivity pair can be selected;
- selected values are non-finite or arithmetic reproduction fails tolerance;
- status flags would need to be translated without documented vendor meanings;
- a value would be silently dropped, overwritten, or converted without a
  recorded rule;
- the source path is also the target project database or target is outside the
  managed import area;
- source is mistaken for a live LS2 transport or hardware acquisition.

Validation must be performed before the single project persistence transaction.
A failed validation must leave the existing NiX project unchanged.

## 10. Unknown and unsupported information

The following remain unknown or unsupported from the supplied databases alone:

- vendor meanings of `ArrayCode`, `ProtocolMode`, `Mode`, `ModeValue`,
  `DP_ABMN.Ready`, `DP_MEASURE.Ready`, and `DPV.Status`;
- the complete Gradient/2x21 protocol and electrode-number semantics;
- whether all DPV channels represent repeated stacks, independent channels, or
  another vendor acquisition structure;
- exact polarity/reference conventions for `SP` and `ΔU`;
- whether `DataSDev`, `N`, `MCycles`, `ADValue`, and `ADRange` can support a
  defensible NiX uncertainty/QC model;
- the semantic relationship of `FocusX/Y/Z` to pseudo-depth or geology;
- CRS, datum, GPS fix quality semantics, and any automatic reprojection;
- a complete VES project metadata model and persistence target in current NiX;
- the source-wide intended treatment of unlinked `DP_ABMN`, logs, tests, and
  auxiliary rows;
- any LS2 USB/Wi-Fi/API/protocol behavior.

## 11. Unknown-resolution review

This section answers whether the remaining unknowns can be resolved without
hardware. Each conclusion is classified as follows:

- **DIRECT:** explicitly represented by a column, declared unit/name, or
  existing cited documentation;
- **DERIVED:** reproduced by a deterministic mathematical or relational check;
- **STRONG:** strongly suggested by repeated structure, names, or configuration,
  but not explicitly documented;
- **UNKNOWN:** the supplied evidence is insufficient to establish the meaning.

`STRONG` and `UNKNOWN` findings are not valid importer mappings by themselves.

### Resolved or partially resolved facts

| Question | Classification | Evidence and precise limit |
|---|---|---|
| Which rows define an observation? | **DIRECT / DERIVED** | `DP_MEASURE` supplies `(DPID, MeasureID)` links; every linked pair in both files has matching `DP_ABMN`, `Measures`, and `DPV` rows, with no duplicate pair and no logical orphan. The safe observation boundary is therefore linked `DP_MEASURE`, not every `DP_ABMN` or `DPV` row. This does not define vendor QC acceptance. |
| How are A/B/M/N ordered? | **DIRECT** | `DP_ABMN` has distinct role columns `APos*`, `BPos*`, `MPos*`, and `NPos*`; `DPKEY` contains the same 12 coordinate values in that order followed by a final `-2` token. The role order is known; a numeric electrode-number convention is not. |
| Does `DPKEY` preserve the geometry? | **DERIVED** | All 518 ERT and 30 VES `DPKEY` strings parse to 13 numeric tokens and exactly reproduce the corresponding `DP_ABMN` coordinates plus the final token. `DPKEY` may be retained as a source key, but its final token's meaning is not resolved. |
| How is stored geometry related to the task spacing? | **DERIVED for these files** | ERT uses `Tasks.SpacingX=15` and `TaskSettings.ElectrodeSpacing=15;1;1`; VES uses `1;1;1`. Scaling the stored coordinates by the task spacing yields the geometry factor that reproduces every stored `ρapp` value. This establishes a reproducible scale operation for these files, not a universal ABEM unit or CRS rule. |
| Are the displayed electrical units explicit? | **DIRECT** | `Datatype.Name`, `Datatype.Unit`, and `Datatype.Explanation` explicitly label `R` as Ω, `I` as A, `ΔU` as V, `ρapp` as Ωm, `SP` as V, `IP` as mV/V, `IPΔU` as V, and `Temp` as C. Labels do not by themselves resolve channel, polarity, status, or statistical semantics. |
| Is stored `ρapp` internally reproducible? | **DERIVED** | General four-point half-space `K` and `ρapp=R×K` reproduce 401/401 ERT and 25/25 VES rows. Maximum absolute differences are `1.4551915228366852e-11 Ωm` and `2.842170943040401e-14 Ωm`, respectively. This is internal consistency, not independent validation. |
| Is resistance related to measured voltage/current? | **DERIVED for a subset** | For 228 ERT rows and 25 VES rows with the required channel-14 current and corresponding `ΔU`, `ΔU/I=R` to floating-point precision (maximum absolute difference `0.0 Ω`). The remaining 173 ERT records lack the complete pairing and must not be filled by inference. |
| What does `SeqNum` separate in the supplied data? | **STRONG, not definitive** | `SeqNum=0` contains DC `R`, `ΔU`, and `ρapp`; VES and ERT `SeqNum=1..4` contain four `IP`/`IPΔU` pairs. This repeated structure supports preserving sequence numbers and treating the latter as non-DC extras, but no vendor definition establishes all sequence semantics. |
| What does the VES geometry represent? | **DERIVED / STRONG** | Every linked VES geometry row is symmetric with `A=+|A|`, `B=-|B|`, `M=+|M|`, `N=-|N|`; derived `AB/2=|A-B|/2` and `MN/2=|M-N|/2` reproduce the Schlumberger factor used by the stored values. The task/protocol names strongly identify the intended layout, but `ArrayCode=7` is not decoded from an official code table. |
| Is there a global coordinate reference system? | **UNKNOWN** | ERT/VES linked A/B/M/N coordinates are X-only with Y/Z zero. `Measures` has latitude/longitude column names, but `GPSPositions` is empty and no CRS, datum, axis convention, or reprojection rule is stored. |
| Are the source files provenance-safe? | **DIRECT / DERIVED** | The files have stable recorded SHA-256/byte counts, pass SQLite integrity checks, and were opened read-only. Source hash/path/size and every source row identifier can be preserved without interpreting vendor semantics. |

### Still unresolved

| Question | Classification | Why it remains unresolved |
|---|---|---|
| `Tasks.ArrayCode` 15 for ERT and 7 for VES | **UNKNOWN** for definitive mapping | Task names and protocol/spread filenames are evidence of intended configuration, but the repository's cited official material does not publish an authoritative numeric code table. ERT `ArrayCode=15` must not be translated to NiX `Multiple Gradient` or another array name; VES `ArrayCode=7` must not be treated as a decoded code merely because geometry is Schlumberger-like. |
| `ProtocolMode`, `Mode`, and `ModeValue` | **UNKNOWN** | Values repeat (`ProtocolMode=15`, `Mode=0`, null `ModeValue`), but no documentation establishes enumerations or behavioral meaning. Preserve verbatim. |
| Electrode numbering and switch order | **UNKNOWN** | A/B/M/N role order is explicit, but `Electrodes` is empty; `ElectrodeTestData` contains switch addresses/test positions, not a demonstrated measurement-number mapping. `DPKEY` contains coordinates, not NiX electrode integers. |
| Coordinate units and physical scale outside these files | **UNKNOWN** | The numeric scaling is internally supported and electrical units are named, but no coordinate-unit declaration or vendor rule establishes metres for every ABEM project. Require explicit unit/scale acceptance. |
| `DP_MEASURE.Ready` and `DP_ABMN.Ready` | **UNKNOWN** | `DP_MEASURE.Ready=1` for all linked rows, while `DP_ABMN.Ready` contains ERT 0/1/17 and VES 0/1. Correlation does not identify whether these are ready, selected, quality, or state flags. Do not map to NiX ACTIVE/EXCLUDED/FLAGGED. |
| `DPV.Status` values | **UNKNOWN** | Numeric values 0, 50331648, and 587202560 occur in repeatable patterns, but the files provide no bit definitions. Preserve exact integers; do not derive QC decisions from correlation alone. |
| Channel numbers 0, 1, 2, 13, and 14 | **STRONG for structural grouping; UNKNOWN for vendor meaning** | The datatype/channel matrix repeatedly groups baseline values on channel 0, primary DC values on channels 1/2, additional `ΔU` on 13, and current on 14. This is sufficient to preserve channel identity and avoid mixing rows, not sufficient to assign a definitive instrument-channel model or polarity convention. |
| `DataSDev`, `DataSDevType`, `N`, `MCycles`, `ADValue`, `ADRange` | **UNKNOWN** | Names and numeric ranges are direct facts. The supplied files do not establish whether deviation is standard deviation, standard error, a stack statistic, or an instrument-specific estimate, nor how ADC fields are scaled. Do not map to NiX uncertainty/QC fields. |
| `SP`, `ΔU`, `IPΔU`, and polarity | **DIRECT names / UNKNOWN semantics** | Datatype names/units are explicit, but reference electrode, sign convention, and distinction between DC and IP voltage records are not documented sufficiently for a definitive NiX voltage mapping. |
| `FocusX/Y/Z` | **UNKNOWN** | `FocusZ` varies systematically in VES and is populated in ERT, but no source documentation establishes whether it is a display focus, pseudo-depth, sensitivity location, or another vendor quantity. It is not NiX depth/elevation. |
| VES persistence target | **UNKNOWN / NiX limitation** | The current `ProjectStore` persists ERT-style numbered electrodes and measurements; it has no dedicated VES-point table or AB/2/MN/2 fields. A safe VES import requires a separately approved NiX schema extension or lossless sidecar contract. |
| Unlinked/auxiliary records | **UNKNOWN policy** | ERT has 117 unlinked `DP_ABMN` rows; VES has 5. Both files also contain logs, sessions, electrode-test records, settings, and auxiliary tables. Their source existence is direct, but their intended import inclusion/exclusion policy is not. Preserve or explicitly account for them; do not silently discard them. |

## 12. Revised proposed mappings

The previous v0.1 mapping table remains valid only as a staged contract, with
these stricter statuses:

- **Allowed as lossless source metadata now:** file hash/size/path, schema rows,
  task row, all settings, all source table/row keys, all raw DPV columns,
  `DPKEY`, raw A/B/M/N/Focus coordinates, timestamps, and auxiliary records.
- **Conditionally reproducible but not yet safe as final NiX semantics:** linked
  observation identity, scaled local geometry, `R`, `I`, `ΔU`, and `ρapp`.
  These require an approved channel/sequence rule, coordinate-unit acceptance,
  polarity policy, and complete pre-persistence validation.
- **VES-specific and not an ERT mapping:** derived AB/2 and MN/2 from symmetric
  linked geometry, subject to a dedicated VES representation and unit/scale
  acceptance.
- **Not allowed to map without external evidence:** array names from numeric
  codes, electrode numbers, QC statuses, uncertainty estimates, CRS/automatic
  reprojection, `FocusZ` depth, or any NiX interpretation of IP/status flags.

The exact NiX `Measurement` fields (`a`, `b`, `m`, `n`) therefore cannot be
populated safely from these databases yet: the source provides role-labelled
coordinates but not the required stable integer electrode-number mapping. A
future intermediate representation may retain coordinates and role identities
without pretending they are NiX electrode numbers.

## 13. Revised fail-closed decision

Importer validation must stop before any `ProjectStore` transaction when:

1. the selected source/task/type is ambiguous;
2. the source hash changes, SQLite integrity fails, or the read-only source
   cannot be reopened;
3. schema/version policy or required columns are unsupported;
4. any linked `DP_MEASURE` row has missing geometry, measurement metadata, or
   DPV records;
5. geometry scaling or coordinate units are not explicitly accepted;
6. a unique channel/sequence selection for the requested DC values is not
   specified by the contract;
7. `ρapp=R×K` validation fails, or a non-finite value is encountered;
8. a vendor status/uncertainty flag would have to be translated without a
   documented mapping;
9. an ERT numeric array/protocol code lacks an approved code-table mapping;
10. a VES source lacks a dedicated VES persistence target and explicit
    Schlumberger geometry/unit policy;
11. any vendor value or auxiliary row would be silently dropped; or
12. the operation would write the original source or represent it as live LS2
    acquisition.

A rejected import must leave the NiX project unchanged. Passing the arithmetic
checks alone is not sufficient to proceed.

## 14. Importer justification conclusion

**Answer: NO. NiX cannot safely import these Barugo ERT and VES databases into
the current `ProjectStore` without guessing scientifically meaningful fields.**

The supplied data resolve the observation linkage, role-labelled geometry,
source provenance, displayed electrical units, and internal `ρapp` arithmetic.
They do not resolve the array-code table, electrode numbering, coordinate units/
CRS, channel/polarity/status/uncertainty semantics, or a VES persistence target.
Those gaps affect the identity and scientific meaning of imported measurements,
so importer implementation remains blocked. No `abem-project-db-to-nix-v0.2-draft`
is created.

Minimum evidence required to unblock a future importer:

1. an authorized ABEM schema/reference for project schema 4/common schema 3;
2. an authoritative table for `ArrayCode`, `ProtocolMode`, channel, sequence,
   `Ready`, `Status`, `Mode`, and `ModeValue` meanings;
3. the supported coordinate unit/scale, axis, CRS/datum, and electrode-number /
   switch-address relationship;
4. a documented VES representation including AB/2, MN/2, and `FocusZ` meaning
   (or an explicit decision that `FocusZ` is metadata only);
5. an approved lossless mapping for auxiliary, log, test, and unlinked rows;
6. a NiX VES persistence contract; and
7. copied/authorized fixtures plus expected records for parser validation.

## 15. Scientific limitations and exact next step

The arithmetic check is an internal consistency qualification, not an
independent benchmark and not evidence of geological validity, inversion
accuracy, RES2DINV equivalence, or LS2 communication. Negative ERT values and
multiple channel/status patterns demonstrate why automatic QC translation
would be unsafe.

**Exact next implementation step:** obtain a legally usable, vendor-authorized
ABEM schema/protocol reference (including array/protocol code tables, channel/
sequence/status definitions, coordinate units/numbering, and VES semantics),
then implement a read-only parser/validator that emits a versioned intermediate
ABEM record set. Run it first against copied fixtures, require the validation
rules above, and only then add a user-approved persistence adapter into NiX
`ProjectStore`. Until that evidence exists, importer implementation remains
blocked and the current read-only inspector is the maximum supported Barugo
workflow.

This document does not implement acquisition, LS2 communication, or conversion.
M15 remains fail-closed and physically unvalidated.
