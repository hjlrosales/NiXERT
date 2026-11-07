# Barugo ABEM Database Forensic Semantic Investigation

## 1. Executive conclusion

The prior `importer_ready = false` decision survives this investigation, but several of its stated reasons do not.

The supplied databases are not semantically opaque. Authoritative ABEM documentation and the official spread/protocol package establish substantially more than the earlier NiX assessment recognized:

- `Tasks.ArrayCode=15` is **Multiple Gradient** and `Tasks.ArrayCode=7` is **Schlumberger** for the relevant Terrameter LS 2 generation.
- The exact official `Gradient_2x21.xml` and `2X21.xml` artifacts reproduce all **518/518** ERT `DP_ABMN` configurations, including A/B current-electrode roles, M/N potential-electrode roles, electrode IDs 1–41, X positions 0–40, switch addresses, and the 2×21 spread.
- The exact official `VES_Schlumberger.xml` reproduces **29/30** VES configurations. The only database-only configuration is `AB/2=300`, `MN/2=27`; the manual explicitly permits temporary VES electrode positions. The 25 linked observations are therefore safely identifiable as Schlumberger VES points.
- Local coordinate scale is supportable for these files: spread coordinates are electrode-spacing steps, the task supplies the true spacing, and the manual describes task/station distances in metres. The ERT mapping is `physical X = stored X × 15 m`; VES uses `× 1 m`.
- Two previously omitted SQLite views identify `Channel=14, DatatypeID=6` as current (`currentView`) and `Channel=13, DatatypeID=7` as transmitter voltage (`voltageView`). The primary receiver `ΔU`, `R`, and `ρapp` rows remain on the same input channel (1 or 2) with `SeqNum=0`.

Those findings falsify the earlier claim that array semantics, electrode roles, local geometry, and primary channel selection are unknowable for these exact files. They do **not** justify import today.

Critical blockers remain:

1. NiX has no neutral/unassessed measurement state, while ABEM `Ready` and status bit meanings are not authoritatively defined. Assigning `ACTIVE`, `EXCLUDED`, or `FLAGGED` would still guess.
2. `DataSDevType`, `N`, `MCycles`, `ADValue`, and `ADRange` lack a field-level vendor definition. Strong mathematical patterns do not qualify an uncertainty or QC mapping.
3. The current `ProjectStore` has no VES-point persistence table; `VESPoint` exists only in memory/text workflows. These 25 VES observations cannot be persisted without an approved NiX schema change.
4. The qualification code has not been updated to ingest or independently verify the newly located official evidence. It still reports the relevant categories as blocked.
5. `DPV.DatatypeID=17` occurs once per transmitter measurement but is absent from the 16-row `Datatype` dictionary. All observed values are zero, but its meaning remains unknown.

Accordingly, the appropriate outcome is **NOT READY**. The result is narrower than before: the databases contain enough evidence for exact-file array, role, local-geometry, and core electrical mappings, but not enough to create fully qualified NiX scientific records under the current target model.

## 2. Scope, evidence standard, and safety

This investigation covered:

- the NiX ABEM inspector, intermediate parser, qualification layer, contract, readiness assessment, vendor checklist/request, tests, roadmap, changelog, and scientific/domain models;
- complete read-only SQLite schema and value profiling of the two original databases;
- the accompanying survey KMZ;
- official ABEM/Guideline Geo manuals and the official November 2024 spread/protocol package;
- deterministic comparison of official protocol geometry to every database `DP_ABMN` row.

Both databases were opened using SQLite URI `mode=ro&immutable=1`. No vendor file was changed, attached, migrated, vacuumed, copied into a NiX project, or used to create a NiX record. No importer was implemented.

The requested evidence hierarchy is used throughout:

| Tier | Meaning in this report |
|---|---|
| Tier 1 | Official ABEM documentation/artifact, controlled vendor-software experiment, vendor confirmation, or explicit metadata whose meaning is established by official documentation |
| Tier 2 | Reproducible behavior or agreement among multiple independent ABEM artifacts |
| Tier 3 | Names, correlations, mathematical patterns, or reverse-engineered inference |
| Tier 4 | Speculation |

`VERIFIED` is used only when an evidence chain is strong enough for the stated, narrowly scoped meaning. `PROVISIONALLY SUPPORTED` is not permission to map a scientifically critical field. No Tier 3 inference is promoted to verified.

## 3. Sources and source identity

| Source | Size | SHA-256 | Key scope |
|---|---:|---|---|
| ERT `Project7/project.db` | 557,056 bytes | `057674127c923842510ee5e8af6082fed88ef152438f3752ca681d5f2f6d47af` | `Gradient_1`, project schema 4/common schema 3 |
| VES `Project8/project.db` | 196,608 bytes | `97eec29b3f9870092f9674e54b560df20f9df2130ac18778ff29161757d09e51` | `VES Schlumberger_1`, project schema 4/common schema 3 |
| `Barugo Survey line & center point.kmz` | 1,139 bytes | `379dbc6791cb3a03b2e7b5a41a71b600e546d085808026bea885fdecec260b50` | Two line strings and one VES point |
| Official November 2024 spread/protocol ZIP | downloaded copy | `39ca2cf06c0ea79822212347b5fbc000f272449d1a297584b79c93e1024ac1cb` | Exact named XML files referenced by both databases |

The database and KMZ facts in this table come from direct read-only inspection; the official ZIP was obtained from Guideline Geo's product resources.[^2][^5][^6][^7]

Both databases report instrument serial `LS26186002`, instrument software `2.2.5b(3179)`, and transmitter software `3.7.2`. The official 2017 Terrameter LS 2 manual is specifically based on application release 2.2.5, making it the closest available version-scoped manual.[^1]

## 4. Current NiX evidence and blocker baseline

The repository contains three distinct layers:

```text
ABEM project.db
  → abem_sample.py          factual summary only
  → abem_intermediate.py    lossless raw/table/relationship representation
  → abem_qualification.py   semantic gate
  → future importer         not implemented
```

The intermediate representation always returns `importer_ready = false`. The qualification layer independently reports `NOT_READY` if any result has `blocks_import=True`. The exact Barugo hashes are already authorized only for ERT/VES classification; that authorization is not a general ABEM mapping.

This baseline is defined by the repository's existing contracts, implementation, domain models, and tests.[^8]

The existing qualification results for both files are:

| Category | Existing result | Blocks import? | Independent review |
|---|---|---:|---|
| Dataset kind | VERIFIED | No | Remains verified; strengthened by official array/protocol evidence |
| Source provenance/integrity | VERIFIED | No | Remains verified |
| Project/survey/measurement identity | VERIFIED | No | Remains verified |
| `DP_MEASURE` relationships | VERIFIED | No | Remains verified |
| Raw `DP_ABMN` and `DPV` relationships | VERIFIED | No | Remains verified |
| Vendor datatype names/units | VERIFIED | No | Remains verified |
| Electrode positions | VERIFIED | No | Strengthened to exact-file local position/number mapping |
| Electrode roles | BLOCKED | Yes | Can be upgraded to VERIFIED for these exact protocol matches |
| Array/protocol semantics | BLOCKED | Yes | Can be upgraded to VERIFIED for these exact files |
| Coordinate reference system | BLOCKED | Yes | Split: local metric geometry VERIFIED; global CRS/line georeferencing UNKNOWN |
| Timestamp records | VERIFIED | No | Remains verified; timezone normalization remains unknown |
| QC/quality semantics | BLOCKED | Yes | Still blocked |
| Uncertainty semantics | BLOCKED | Yes | Stronger evidence, but still not verified |
| VES persistence | UNSUPPORTED | VES: Yes | Still unsupported and blocking |
| Auxiliary raw preservation | VERIFIED | No | Remains verified; planned-vs-observed geometry is now clearer |
| NiX compatibility | BLOCKED | Yes | Still blocked pending target contract and qualification update |

The current tests correctly enforce the current code state. No fail-closed test was weakened or changed.

## 5. Complete SQLite forensic findings

### 5.1 Database-level properties

Both sources report:

- `PRAGMA integrity_check = ok`;
- zero `PRAGMA foreign_key_check` violations;
- UTF-8 encoding;
- `application_id=0` and `user_version=0`;
- 1,024-byte pages and `journal_mode=delete`;
- 24 vendor tables plus SQLite's internal `sqlite_sequence`;
- six explicit indexes, two views, and zero triggers.

The ERT file has 544 pages; the VES file has 192.

### 5.2 Schema and row counts

| Table | Columns (declared SQLite types abbreviated) | ERT rows | VES rows |
|---|---|---:|---:|
| `ProjectSchemaVersion` | `Version`, `Comment` | 1 | 1 |
| `CommonSchemaVersion` | `Version`, `Comment` | 1 | 1 |
| `TT_EC_SCHEMA` | `VERSION`, `COMMENT` | 1 | 1 |
| `Tasks` | `ID`, `Name`, `Active`, `PosX/Y/Z`, `SpacingX/Y/Z`, `ArrayCode`, `Time` | 1 | 1 |
| `TaskSettings` | `key1`, `key2`, `Setting`, `Value`, `Auto` | 5 | 5 |
| `AcqSettings` | `key1`, `key2`, `Setting`, `Value`, `Auto` | 200 | 1,400 |
| `Sessions` | `ID`, `Time`, `TaskID`, instrument/transmitter serial/software | 4 | 34 |
| `Measures` | `ID`, `StationID`, latitude/longitude/quality, `Time`, power, temperature, light, `SessionID`, `PositionId` | 228 | 25 |
| `Stations` | `ID`, `TaskID`, `SpreadPositionID`, `PosX/Y/Z`, `Time` | 1 | 1 |
| `Positions` | `Id`, `TaskId`, `PositionType`, `PosX/Y/Z`, `IsRemote`, `MeasureID`, `MeasurePhase`, `MeasureTime` | 7 | 39 |
| `DP_ABMN` | `ID`, `TaskID`, `DPKEY`, A/B/M/N XYZ, focus XYZ, `Ready`, `Note`, `Mode`, `ModeValue` | 518 | 30 |
| `DP_MEASURE` | `ID`, `DPID`, `MeasureID`, `Ready` | 401 | 25 |
| `DPV` | identity/task/link/channel/sequence/datatype, value/deviation, ADC/status/count/cycle fields | 6,007 | 450 |
| `Datatype` | `ID`, `Name`, `Unit`, `Explanation` | 16 | 16 |
| `Electrodes` | spread/position/role/remote/switch/cable/takeout fields | 0 | 0 |
| `ElectrodeTestData` | task/station/switch/position/resistance/current/status/time fields | 91 | 66 |
| `GPSPositions` | position/source/mask/time/fix/DOP/lat/lon/elevation/speed/satellite fields | 0 | 0 |
| `ExternalData` | task/instrument/measure/phase/datatype/value/deviation/status/count | 0 | 0 |
| `Datasets` | `Id`, `Name`, `ExcludeSet` | 0 | 0 |
| `DatasetItems` | dataset/measure/data-point identifiers | 0 | 0 |
| `Log` | event time/location/environment/source/task/measure/text/BLOB/class fields | 47 | 92 |
| `EventSources` | `ID`, `Name` | 13 | 13 |
| `TT_EC_LISTS` | task/list name/cable-direction | 0 | 0 |
| `TT_EC_DATA` | list and XYZ values | 0 | 0 |

The only declared foreign key is `TT_EC_DATA.EC_LIST_ID → TT_EC_LISTS.ID`. Logical measurement relationships are not declared foreign keys.

Composite primary keys exist on `TaskSettings(key1,key2,Setting)` and `AcqSettings(key1,key2,Setting)`. Unique constraints exist on `DP_ABMN(TaskID,DPKEY)` and `DP_MEASURE(DPID,MeasureID)`.

Explicit indexes are:

- `DPV_DPID`;
- `DPV_MEASURE_DPID`;
- `DPV_MEASURE_MEASUREID`;
- `DP_ABMN_TASKFOCUS(TaskID,FocusX,FocusY)`;
- `GPSPositionsIndex(PositionID)`;
- `PositionsIndex(MeasureID)`.

### 5.3 Previously missed views

The earlier table inventory omitted two schema views:

```sql
CREATE VIEW currentView AS
SELECT DataValue AS currentValue, MeasureID
FROM DPV
WHERE Channel = 14 AND DatatypeId = 6
ORDER BY MeasureID;

CREATE VIEW voltageView AS
SELECT DataValue AS voltageValue, MeasureID
FROM DPV
WHERE Channel = 13 AND DatatypeId = 7
ORDER BY MeasureID;
```

These are direct internal semantic evidence. The official manual separately explains that each measurement contains input channels plus a transmitter-monitoring channel, and that the transmitter row contains final measured output current and output voltage.[^1] This establishes channel 14 as transmitter current and channel 13 as transmitter output voltage for these schemas. It also proves that channel-13 voltage must not be confused with the receiver `ΔU` used to calculate resistance.

### 5.4 Observation relationships

For both files:

```text
DP_MEASURE.DPID             → DP_ABMN.ID
DP_MEASURE.MeasureID        → Measures.ID
(DP_MEASURE.DPID,MeasureID) → DPV.(DPID,MeasureID)
```

Observed checks:

- no duplicate `DP_MEASURE(DPID,MeasureID)` pairs;
- no linked row missing geometry, measurement metadata, or DPV values;
- no unlinked `Measures` rows;
- no unlinked `DPV` rows;
- 117 ERT and 5 VES `DP_ABMN` rows are unlinked.

Official protocol comparison changes the meaning of the unlinked geometry. All 518 ERT rows are configurations in the official protocol. The official VES protocol supplies 29 of 30 rows, and the manual permits a temporary position.[^1][^2] The unlinked rows are therefore planned/available configurations, not acquired observations. `DP_MEASURE` is the correct scientific observation boundary for these exact files.

### 5.5 Encodings, BLOBs, and embedded content

Every `DP_ABMN.DPKEY` in both files has 13 semicolon-separated numeric tokens:

```text
A.x;A.y;A.z;B.x;B.y;B.z;M.x;M.y;M.z;N.x;N.y;N.z;-2
```

All 548 keys reproduce their row's 12 coordinate values exactly and contain the terminal `-2`. This proves encoding structure, but not the meaning of the sentinel.

No non-null BLOB payload exists in either file: all `Log.Data` values are null. No embedded JSON or XML was found. Protocol/spread configuration is referenced by path in `TaskSettings`, not embedded.

`DatatypeID=17` is a dictionary orphan: 228 ERT and 25 VES rows use it, always on channel 14, sequence 0, with value/deviation/status/count/cycle/range all zero. It is likely a reserved transmitter datum, but that interpretation is Tier 3 and must not be used.

### 5.6 ERT-specific findings

| Field/pattern | Example or count | Interpretation | Strength |
|---|---|---|---|
| `Tasks.Name` / `ArrayCode` | `Gradient_1` / `15` | Exact Multiple Gradient task | Tier 1 |
| `ProtocolFile` / `SpreadFile` | `Gradient_2x21.xml` / `2X21.xml` | Exact official protocol/spread | Tier 1 + Tier 2 full match |
| `SpacingX` | `15.0` | True X electrode spacing in metres for this task | Tier 1 manual + Tier 2 arithmetic |
| Official geometry match | 518/518 | Database A/B/M/N equals official Tx/Rx configurations | Tier 2 reproducible |
| Linked observations | 401 | Acquired data points | Direct structure + official protocol behavior |
| Measurement groups | 55 with one linked receiver channel; 173 with two | One transmitter injection can yield multiple receiver data points | Tier 1 manual + direct pattern |
| `ρapp` | 401 rows, 35 negative | Stored apparent resistivity, one per link | Tier 1 datatype label/manual |
| `R` / receiver `ΔU` | one same-channel pair per link | Primary receiver resistance and potential difference | Tier 1/Tier 2 |
| Channel-14 `I` | 228 rows, one per `MeasureID` | Final transmitter current shared by that injection's links | Tier 1 + schema view |
| Channel-13 `ΔU` | 228 rows | Transmitter output voltage, not receiver voltage | Tier 1 + schema view |
| `DP_ABMN.Ready` | 0:117 unlinked; 1:334 linked; 17:67 linked | 0 separates unacquired plans; bit 16 meaning unknown | Direct pattern; Tier 3 for bit meaning |
| Negative logs | every negative `ρapp` falls in the `Ready=17` group | `17` is associated with an acquisition warning, but is not decoded | Tier 3 |

The stored half-space geometric factor reproduces all 401 `ρapp = R × K` values to floating-point precision when ABMN X is multiplied by 15 m. This verifies the exact geometry/value pairing, not instrument accuracy or QC acceptance.

### 5.7 VES-specific findings

| Field/pattern | Example or count | Interpretation | Strength |
|---|---|---|---|
| `Tasks.Name` / `ArrayCode` | `VES Schlumberger_1` / `7` | Exact Schlumberger VES task | Tier 1 |
| `ProtocolFile` / `SpreadFile` | `VES_Schlumberger.xml` / `VES_C1C2P1P2.xml` | Official four-terminal VES protocol | Tier 1 |
| Official geometry match | 29/30, with one extra `300/27` point | Official predefined positions plus a permitted temporary position | Tier 1/Tier 2 |
| Linked observations | 25 | Acquired VES points | Direct structure |
| Coordinates | A=`+AB/2`, B=`−AB/2`, M=`+MN/2`, N=`−MN/2` | Direct VES half-spacing representation | Tier 1 |
| `SpacingX` | `1.0` | One-metre minimum electrode spacing; stored half-spacings are metric here | Tier 1/Tier 2 |
| `FocusZ` | first values `0.370`, `0.527`, `0.721` | Consistent with displayed focus/median penetration depth | Provisionally supported; no DB dictionary ties the column to the UI term |
| `ρapp` | 25 rows, all positive | Stored apparent resistivity | Tier 1 |
| `DP_ABMN.Ready` | 0:5 unlinked; 1:25 linked | Separates unused predefined positions from observations here | Direct exact-file pattern |

The official manual states that VES tasks are created from a VES protocol, electrode positions are saved with data, positions are handled as `MN/2` and `AB/2` multiplied by the selected minimum spacing, and the sounding curve uses focus depth (median depth penetration).[^1] The official XML assigns electrode IDs 1/2 to C1/C2 and 3/4 to P1/P2 and supplies the exact half-spacing sequence.[^2]

All 25 VES `ρapp = R × K` values reproduce to floating-point precision under the Schlumberger factor. This verifies the exact-file AB/2 and MN/2 mapping.

### 5.8 DPV value-stream findings

The relevant repeated pattern is:

| Semantic candidate | Datatype | Channel | `SeqNum` | ERT rows | VES rows | Assessment |
|---|---:|---:|---:|---:|---:|---|
| Self potential | 1 `SP` | 0 | 0 | 228 | 25 | Preserve; not core DC voltage |
| Apparent resistivity | 2 `ρapp` | 1/2 ERT, 1 VES | 0 | 401 | 25 | Exact primary value per link |
| IP windows | 3 `IP` | receiver channel | 1–4 | 1,604 | 100 | Four windows; preserve until sequence/timing contract is qualified |
| Resistance | 5 `R` | receiver channel | 0 | 401 | 25 | Exact primary resistance per link |
| Setup/test current | 6 `I` | 0 | 0 | 228 | 25 | Not the final current |
| Final current | 6 `I` | 14 | 0 | 228 | 25 | Identified by `currentView` |
| Receiver voltage | 7 `ΔU` | receiver channel | 0 | 401 | 25 | Same-channel input potential difference |
| Transmitter output voltage | 7 `ΔU` | 13 | 0 | 228 | 25 | Identified by `voltageView`; retain separately |
| IP delta voltage | 9 `IPΔU` | receiver channel | 1–4 | 1,604 | 100 | Preserve separately from DC voltage |
| Temperature | 13 `Temp` | 0 | 0 | 228 | 25 | Acquisition metadata |
| Unknown zero datum | 17, no dictionary row | 14 | 0 | 228 | 25 | UNKNOWN; preserve only |

All primary scientific rows (`ρapp`, receiver `R`, receiver `ΔU`, final current) have `DPV.Status=0`. Non-zero `DPV.Status` values occur on channel-0 setup/test records: `0x03000000` and `0x23000000`. This reduces the chance of accidentally applying those codes to primary values but does not define the bits.

The exact relations are:

- `receiver ΔU / final channel-14 I = receiver R` for all 401 ERT and 25 VES links, within stored floating-point precision;
- normalized `DataSDev/abs(DataValue)` agrees between `ρapp` and `R` to approximately `1.8×10⁻15` (ERT) and `2.2×10⁻16` (VES);
- the same coefficient agrees between receiver `ΔU` and `R` to approximately `1.0×10⁻6` (ERT) and `2.4×10⁻7` (VES).

The manual defines the displayed normalized standard deviation as the coefficient of variation across repeated stackings.[^1] The database therefore strongly suggests that `DataSDev` is an absolute deviation in the datum's unit from which the displayed coefficient is derived. However, no authoritative database dictionary defines `DataSDevType=0/1/2`, `N`, `MCycles`, or ADC scaling. The uncertainty mapping remains only provisionally supported.

### 5.9 Settings, logs, QC, and timestamps

Both files consistently store acquisition settings including:

- `MeasureMode=1`, `AutoStack=1`;
- `StackLimitsLow=1`, `StackLimitsHigh=3`;
- `ErrorLimit=0.010000`;
- `Acq_DelaySec=0.3`, `Acq_TimeSec=0.5`;
- `BaseFreqHz=60`, `SampleRateHz=1000`;
- four effective IP windows described by `IP_WindowSecList=0.01 0.02 0.02 0.02 0.02` plus off-time settings;
- current, voltage, power, electrode-test, and contact-resistance limits.

The official manual explains those user-facing settings, stacking, error limit, measurement modes, and IP windows.[^1] It does not map the SQLite setting integers or DPV statistical/status fields one-for-one.

Logs provide direct human-readable events:

- ERT: measurement starts, failed and accepted electrode tests, four excluded electrodes, negative-resistivity warnings with Tx/Rx labels, a “skip all similar and continue” action, and completion;
- VES: one-point starts, electrode-test OK/fail summaries, and completion events.

Contact-test correlations suggest `TestStatus=4` means OK, `3` means bad, and `2` means fail. This is useful Tier 3 evidence but not an enum definition. Likewise, all 35 negative ERT `ρapp` values occur among the 67 `DP_ABMN.Ready=17` links, but 32 positive values also have 17. The bit cannot safely become `FLAGGED` without vendor definition or a controlled experiment.

All `Measures.PosQuality` values are 3. The built-in GNSS manual says position is saved with measurements, and the lat/lon ranges are geographically consistent with the accompanying KMZ.[^1] Nevertheless, `GPSPositions` is empty, the meaning of quality 3 is not documented, and the KMZ has no database task/measure identifier. The KMZ cannot authoritatively rotate or translate local electrode geometry.

Timestamps are stored without timezone offsets. Terrameter Toolbox allows the instrument timezone and clock to be configured, but the database does not preserve the timezone choice alongside these timestamps.[^3] Normalize none of them to UTC without external survey metadata.

## 6. External ABEM evidence

| Official source | Exact claim used | Blocker addressed | Strength | Sufficient? |
|---|---|---|---|---|
| Terrameter LS 2 User Manual, 2017-08-14, based on release 2.2.5 | Array codes: 7 Schlumberger, 15 Multiple Gradient; protocol positions are current A/B then potential M/N; spread X is electrode-spacing steps; VES uses AB/2/MN/2 times minimum spacing; input/transmitter channel display; normalized standard deviation; VES focus depth | Array, roles, scale, channel model, VES, partial uncertainty | Tier 1 | Yes for exact array/role/local-scale/VES concepts; no for DB status/statistical field codes |
| Official November 2024 spread/protocol package | Exact `Gradient_2x21.xml`, `2X21.xml`, `VES_Schlumberger.xml`, and `VES_C1C2P1P2.xml` definitions | Exact protocol, electrode ID/switch map, planned geometry | Tier 1 artifact + Tier 2 database match | Yes for these exact task configurations; not a general schema/version contract |
| Terrameter LS Protocol Tool Manual, release 1.0[^4] | Spread XML defines physical layout/electrical connections; true spacing is set in instrument UI; protocol assigns current and potential electrodes; X/Y are step coordinates; switch-address behavior | Geometry, role, numbering, switching | Tier 1 | Yes for XML semantics; exact-file applicability is established by full geometry match |
| Terrameter LS Toolbox Manual, release 2.0.1.2 | Toolbox reads project databases, filters/shows data points, exports visible data, edits topography in metres, and configures instrument timezone | Auxiliary/QC behavior, coordinates, time | Tier 1 | No field-level mapping to `Ready`, status bits, or timezone values |
| Guideline Geo product resource page | Publishes the manuals, Toolbox, Protocol Tool, and protocol update package as ABEM resources | Provenance of external artifacts | Tier 1 | Yes for source authenticity |

The protocol package post-dates the recorded application version, so it is not used alone as proof of database schema compatibility. Its evidentiary force for these exact files comes from the combination of exact filenames, the release-2.2.5 manual's format/array definitions, and the deterministic 518/518 and 29/30 geometry matches.

One terminology caveat is preserved: the VES construction-kit README calls generic Res2DInv code 7 “Wenner-Schlumberger,” while the version-matched instrument manual calls code 7 “Schlumberger” and the exact official XML is named/described “VES Schlumberger.” The exact symmetric geometry is unambiguous; NiX should retain the vendor label `VES Schlumberger` and avoid claiming a universal code-name table beyond this scope.

## 7. Software and controlled-experiment findings

No installed ABEM/Terrameter application or exact protocol XML was identified by the targeted search of common local Program Files, ProgramData, Documents, and Downloads locations. No vendor software was installed, modified, launched against the original databases, or used to create a project. Consequently, no controlled UI-save/database-diff experiment was performed.

The official protocol comparison is an artifact-conformance experiment, not a controlled software experiment:

| Dataset | Official configurations | Database configurations | Exact multiset matches | Missing official | Database-only |
|---|---:|---:|---:|---:|---:|
| ERT | 518 | 518 | 518 | 0 | 0 |
| VES | 29 | 30 | 29 | 0 | 1 (`AB/2=300`, `MN/2=27`) |

This comparison was performed by parsing official spread electrode IDs/XYZ, applying each protocol `<Tx>` and `<Rx>` pair, applying VES `<Move>` selections, and comparing the resulting 12-value A/B/M/N tuple multiset to `DP_ABMN`.

## 8. Blocker-by-blocker evidence matrix

### 8.1 Resolved or narrowed blockers

| Semantic question | Fields/tables | Previously examined and why insufficient | New evidence | Verdict | Proposed NiX consequence |
|---|---|---|---|---|---|
| Are the exact files ERT or VES? | `Tasks`, `TaskSettings`, hash | Names plus exact hash authorization | Official array table and exact protocols | VERIFIED | ERT → `SurveyType.ERT`; VES → `SurveyType.VES` |
| What do array codes 15 and 7 mean? | `Tasks.ArrayCode`, `ProtocolMode`, protocol path | Names were treated as non-authoritative | Release-2.2.5 array table and exact official XML | VERIFIED for these files | `Multiple Gradient`; `VES Schlumberger`. `ProtocolMode=15` remains raw/unknown |
| Which electrodes are A/B/M/N? | `DP_ABMN`, protocol/spread | Column names alone did not prove protocol mapping | Manual defines current A/B then potential M/N; full official tuple match | VERIFIED | Use role columns directly |
| How are ERT electrodes numbered/wired? | `DP_ABMN`, empty `Electrodes`, tests | Empty table prevented numbering inference | Official spread maps IDs 1–41 to X 0–40 and switch addresses; full match | VERIFIED for exact ERT | NiX electrode number = step X + 1; retain switch metadata from official evidence, not inferred from empty table |
| What is local coordinate scale? | `Spacing*`, `ElectrodeSpacing`, ABMN, station | Arithmetic alone did not prove metres | Manual and Protocol Tool define step coordinates and true task spacing; exact arithmetic | VERIFIED for local exact-file geometry | ERT X metres = step ×15; VES half-spacing metres = stored value ×1; Y/Z zero |
| Which rows are observations? | `DP_MEASURE`, `DP_ABMN`, `DPV` | Link integrity established but unlinked policy unclear | Official protocol accounts for all planned geometry | VERIFIED for exact files | Import only `DP_MEASURE` links as observations; preserve original source for plans |
| Which DPV rows contain core DC values? | `DPV`, `Datatype`, views | Channel semantics considered unknown | Schema views, manual channel model, unique same-channel rows, exact equations | VERIFIED for these exact files | `ρapp/R/receiver ΔU`: linked receiver channel, seq 0; final I: channel 14 by `MeasureID`; channel 13 voltage is transmitter metadata |
| What are VES AB/2 and MN/2? | VES ABMN/protocol/spacing | Symmetry was only structural | Versioned manual and exact official VES XML | VERIFIED | `ab2=abs(APosX)×1 m`, `mn2=abs(MPosX)×1 m`; validate opposite B/N coordinates |
| What is `FocusZ`? | `DP_ABMN.FocusZ` | Pattern only | Manual labels VES plot axis as focus/median penetration depth | PROVISIONALLY SUPPORTED | Preserve as `vendor_focus_depth_m`; do not map to electrode elevation or layer depth without DB field confirmation |

### 8.2 Remaining blockers and unknowns

| Semantic question | Fields/tables | Evidence examined | Why still insufficient | Verdict | Minimum evidence required |
|---|---|---|---|---|---|
| What do readiness/status values mean? | `DP_MEASURE.Ready`, `DP_ABMN.Ready`, `DPV.Status`, test/Tx status | Exact distributions, logs, value signs, manual UI behavior | Correlation does not define bits, precedence, or NiX state | UNKNOWN — BLOCKING | Vendor enum/bit table scoped to schema 4/software 2.2.5b, or controlled known-state save/diff plus vendor confirmation |
| Can records be assigned a NiX QC state? | Above plus `MeasurementStatus` | All primary DPV statuses are zero; no Datasets filters | NiX requires ACTIVE/EXCLUDED/FLAGGED and has no UNASSESSED | UNSUPPORTED — BLOCKING | Add an approved neutral raw/unassessed state or obtain authoritative ABEM→NiX state mapping |
| What exactly is stored uncertainty? | `DataSDev`, `DataSDevType`, `N`, `MCycles`, ADC fields | Manual CV definition; exact ratio propagation; settings | No field dictionary defines type codes, sample/stack formulas, or ADC scaling | PROVISIONALLY SUPPORTED — BLOCKING if mapped | Versioned field definitions and worked row examples; otherwise preserve only |
| What is datatype 17? | `DPV.DatatypeID=17` | 253 zero rows, channel 14, missing dictionary row | No name/unit/explanation or manual reference | UNKNOWN | Vendor dictionary or controlled experiment; always preserve and never map meanwhile |
| Can acquisition lat/lon georeference electrodes? | `Measures`, `GPSPositions`, KMZ | Geographic agreement and manual GNSS behavior | Instrument position is not a line transform; quality/datum/link unknown | UNKNOWN — BLOCKING only for GIS mapping | Survey control-point/line assignment and CRS/datum/axis/elevation metadata |
| What timezone applies? | all timestamp columns | Toolbox timezone behavior | No stored offset/zone/clock authority | UNKNOWN | Field/timezone policy or field notes; raw timestamps may be preserved without normalization |
| Can the VES points be persisted? | `VESPoint`, `ProjectStore` schema | In-memory VES model and CSV parser | No VES table, source identity, QC, or sidecar persistence | UNSUPPORTED — BLOCKING | Approve an additive VES schema with source ID, row identity, AB/2, MN/2, units, stored rho/R, QC state, and raw extras |
| Can auxiliary rows be losslessly retained? | logs/tests/settings/unlinked plans | Intermediate parser snapshots all rows; original file hash | Future importer has no approved ABEM sidecar contract | PROVISIONALLY SUPPORTED | Mandate immutable raw source retention plus a versioned raw-record/metadata sidecar or explicit source-reference policy |
| Are other ABEM versions supported? | schema/software/version fields | Only two schema-4/common-3 files | No version matrix or fixtures | UNKNOWN; nonblocking only for exact-hash scope | Reject every non-authorized hash/version until separately qualified |
| Is the current qualification layer updated? | `abem_qualification.py`, tests | Current code still returns blockers | New evidence is not encoded or independently checked | UNSUPPORTED — BLOCKING | Add evidence objects and deterministic checks in a separate qualification change; do not implement persistence yet |

No investigated source relationship is `INVALID`. The two databases are structurally valid. “Unknown” describes meaning, not data corruption.

## 9. Evidence chains for verified results

### 9.1 ERT array and electrode mapping

```text
Tasks.ArrayCode=15 + TaskSettings.ProtocolFile=Gradient_2x21.xml
→ release-2.2.5 manual: code 15 = Multiple Gradient
→ official Gradient_2x21.xml: code 15, 2×21, seven Rx/TX pair
→ official 2X21.xml: IDs 1–41, X steps 0–40, switch addresses
→ 518/518 official A/B/M/N tuples equal DP_ABMN
→ NiX: Multiple Gradient ERT, electrode_id = X_step + 1
```

### 9.2 ERT local coordinates

```text
official spread/manual: X is electrode-spacing steps
→ Tasks.SpacingX = TaskSettings.ElectrodeSpacing.X = 15
→ manual: true task spacing and station distance are in metres
→ rhoapp = R × K for 401/401 only when X is scaled by 15 m
→ NiX local x_m = stored X × 15; local origin at first spread electrode/station 0
```

### 9.3 Core electrical rows

```text
Datatype dictionary: rhoapp Ωm, R Ω, I A, ΔU V
→ manual: receiver rows contain measured voltage, R, rhoapp; Tx row contains final I/output V
→ currentView selects channel 14 I; voltageView selects channel 13 ΔU
→ each linked DPID has exactly one seq-0 rhoapp/R/receiver-ΔU tuple on its receiver channel
→ receiver ΔU / channel-14 I = R; R × K = rhoapp for every link
→ NiX exact-file candidate: stored rhoapp, R, receiver ΔU, and final transmitter I
```

### 9.4 VES mapping

```text
Tasks.ArrayCode=7 + VES_Schlumberger.xml
→ manual: code 7 Schlumberger; VES uses AB/2 and MN/2 × minimum spacing
→ official XML: C1/C2 at ±AB/2; P1/P2 at ±MN/2; code 7
→ 29 predefined tuples match, plus one manual-permitted temporary tuple
→ 25 DP_MEASURE links reproduce Schlumberger rhoapp exactly
→ NiX VESPoint candidate: ab2, mn2, resistance, stored apparent_resistivity
```

## 10. Proposed exact-file NiX mappings

These are proposed qualification inputs, not importer instructions and not authorization to persist.

### 10.1 Common envelope

| Source | Proposed NiX mapping | State |
|---|---|---|
| Original bytes/path/size/hash | immutable imported-source provenance | VERIFIED |
| Schema rows, session software/serial | vendor metadata | VERIFIED as raw metadata |
| `Tasks.ID/Name` | selected survey source identity/name | VERIFIED |
| `DP_MEASURE.ID,DPID,MeasureID` | source observation identity | VERIFIED |
| Complete original database | lossless preservation of all auxiliary/unknown rows | REQUIRED |
| Timestamps | original text only | VERIFIED raw; normalization UNKNOWN |
| `Measures.PosLatitude/Longitude/PosQuality` | acquisition-position metadata only | raw only; no line georeferencing |

### 10.2 ERT candidate mapping

| NiX concept | Exact source rule | Validation |
|---|---|---|
| Survey type | `ERT` | hash, task, array, protocol match |
| Array | `Multiple Gradient` | code 15 + exact official protocol |
| Electrode number | `int(stored_step_x)+1`, 1–41 | official spread ID/X mapping |
| Electrode local X | `stored_step_x × 15 m` | task spacing + official step semantics |
| A/B/M/N | matching numbered electrode for each role coordinate | exact official tuple membership |
| Measurement identity | `DP_MEASURE.ID`, retaining DPID/MeasureID | uniqueness and link checks |
| Apparent resistivity | linked datatype 2, receiver channel, seq 0 | exactly one; finite; `R×K` equality |
| Resistance | linked datatype 5, same receiver channel, seq 0 | exactly one; finite |
| Receiver voltage | linked datatype 7, same receiver channel, seq 0 | `ΔU/I=R` equality |
| Current | datatype 6, channel 14, seq 0, joined by `MeasureID` | `currentView`; exactly one per transmitter measurement |
| Tx output voltage | datatype 7, channel 13 | raw extra, never NiX receiver voltage |
| IP/SP/temperature/statistics/status | complete raw extras | no scientific/QC mapping until separately qualified |
| NiX status | none currently safe | BLOCKING |

### 10.3 VES candidate mapping

| NiX concept | Exact source rule | Validation |
|---|---|---|
| Survey type | `VES` | hash, task, array, protocol match |
| Array | `VES Schlumberger` | code 7 + exact XML/geometry |
| `VESPoint.ab2` | `abs(APosX) × 1 m`, require `BPosX=-APosX` | all 25 links |
| `VESPoint.mn2` | `abs(MPosX) × 1 m`, require `NPosX=-MPosX` | all 25 links |
| Apparent resistivity/resistance | same linked seq-0 receiver rules as ERT | one each; exact `R×K` equality |
| Current/receiver voltage | same roles as ERT | exact `ΔU/I=R` equality |
| `FocusZ` | `vendor_focus_depth_m` raw metadata | provisional only; not layer depth |
| Persistence | new dedicated VES table/sidecar | BLOCKING; absent today |
| NiX status | none currently safe | BLOCKING |

## 11. Remaining uncertainties and risk boundaries

The following must not be silently inferred:

- `Ready=17` as `FLAGGED`, even though it contains all negative ERT values;
- `DPV.Status=0` as blanket scientific acceptance;
- `TestStatus` and `TxStatus` numeric meanings from log correlation;
- `DataSDev` as a specific sample/population standard deviation, or `N`/`MCycles` as stack/sample counts, without field definitions;
- datatype 17's name or unit;
- `FocusZ` as geological depth, layer depth, or electrode elevation;
- measurement GNSS positions as electrode coordinates or as a rotation/origin for the KML lines;
- timezone/UTC conversion;
- support for any database other than these exact hashes;
- equivalence to a vendor TXT/DAT/USF export, because no controlled export of these tasks was available;
- any inversion, geological interpretation, hardware communication, or acquisition behavior.

## 12. Final recommendation

Keep `importer_ready = false` and do not implement or enable the importer yet.

The qualification layer should eventually be updated to recognize the newly verified exact-file evidence, but that update should still return `NOT_READY` until the remaining gates close. In particular, the report does not recommend retaining obsolete blockers merely because tests currently encode them; it recommends replacing them with narrower, evidence-accurate blockers.

The minimum readiness conditions are:

1. Authoritative field definitions or controlled-and-confirmed experiments for `DP_MEASURE.Ready`, `DP_ABMN.Ready`, `DPV.Status`, `TestStatus`, `TxStatus`, `DataSDevType`, `N`, `MCycles`, `ADValue`, `ADRange`, and datatype 17.
2. An approved NiX neutral/unassessed QC state or an authoritative ABEM-to-NiX ACTIVE/EXCLUDED/FLAGGED rule.
3. An approved, source-addressable VES persistence schema with raw-value sidecar/provenance.
4. Qualification code and fixtures that independently verify the official manual/XML evidence, exact hashes, geometry multiset, primary DPV row uniqueness, arithmetic invariants, and fail-closed behavior before any persistence layer runs.

## 13. Exact next action

Send Guideline Geo/ABEM a narrowed, version-scoped evidence request containing the two exact hashes and asking for the enum/bit/statistical definitions listed above plus sanctioned TXT (ERT) and USF/TXT (VES) exports of these exact tasks. In parallel, prepare—but do not implement—an additive NiX design proposal for (a) `UNASSESSED` imported measurements and (b) source-addressable VES points. Once the response and exports are available, encode them as qualification evidence and rerun the exact-file gate.

No JSON summary was created because the repository has no existing convention for JSON documentation artifacts.

## Sources

[^1]: Guideline Geo/ABEM. “[Terrameter LS 2 User Manual](https://www.guidelinegeo.com/wp-content/uploads/2017/08/Terrameter-LS-2-User-Manual-2017-08-14-1.pdf).” 2017-08-14, based on application release 2.2.5. Relevant sections: task creation; receiver settings; measurement results; VES; measurement modes; spread/protocol formats; array codes.
[^2]: Guideline Geo/ABEM. “[Terrameter LS, LS 2 — Spread and Protocol Update, November 2024](https://guidelinegeo.com/wp-content/uploads/2016/03/Spread-and-Protocol-Update-Nov2024.zip).” Exact artifacts used: `x21/2x21/Gradient_2x21.xml`, `x21/2x21/2X21.xml`, `VES/VES_Schlumberger.xml`, and `VES/VES_C1C2P1P2.xml`.
[^3]: Guideline Geo/ABEM. “[Terrameter LS Toolbox User Manual](https://www.guidelinegeo.com/wp-content/uploads/2016/03/ABEM-Terrameter-LS-Toolbox-v2.0.1-User-Manual-1.pdf).” Release 2.0.1.2.
[^4]: Guideline Geo/ABEM. “[Terrameter LS Protocol Tool User Manual](https://guidelinegeo.com/wp-content/uploads/2019/08/Terrameter-LS-Protocol-Tool-User-Manual-20190809.pdf).” 2019-08-09, release 1.0.
[^5]: Guideline Geo. “[ABEM Terrameter LS 2 resources](https://guidelinegeo.com/products/abem/abem-terrameter-ls-2/).” Official product/resource index.
[^6]: Local evidence: original Barugo ERT and VES `project.db` files; read-only access on 2026-09-15. Paths and hashes are recorded in Section 3.
[^7]: Local evidence: `Barugo Survey line & center point.kmz`; read-only inspection on 2026-09-15; SHA-256 recorded in Section 3.
[^8]: NiX repository evidence: `docs/barugo_import_contract.md`, `docs/barugo_import_readiness.md`, `docs/barugo_semantic_qualification.md`, `docs/barugo_vendor_evidence_checklist.md`, `docs/barugo_vendor_evidence_request.md`, `nix_ert/data/abem_sample.py`, `nix_ert/data/abem_intermediate.py`, `nix_ert/data/abem_qualification.py`, domain models, and ABEM tests.

## Final answer

**Can NiX now safely import these exact Barugo ABEM `.db` files without making scientifically unsupported assumptions?**

**NO.** The exact arrays, electrode roles, local metric geometry, observation links, VES half-spacings, and primary electrical rows are now supportable without guessing. NiX still cannot assign a scientifically justified QC state, fully interpret the uncertainty/status fields, or persist VES points in its current schema, and its qualification layer does not yet verify the new evidence. Importing now would therefore require unsupported assumptions or an unapproved target-model change.
