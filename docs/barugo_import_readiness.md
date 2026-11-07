# ABEM importer implementation-readiness assessment

**Assessment date:** 2026-09-15  
**Decision:** **NOT READY**  
**Contract under review:** `abem-project-db-to-nix-v0.1-draft`  
**Source classification:** `BARUGO SAMPLE DATA — REAL USER-PROVIDED DATA`

This is a read-only implementation gate. No importer, conversion, acquisition,
LS2 communication, or scientific-engine change is included. The original Barugo
files remain outside NiX project state and are not treated as live LS2 data.

## 1. Executive conclusion

**NO-GO for ABEM → NiX persistence implementation.**

The available evidence is sufficient to design a parser that preserves vendor
records as an explicitly versioned intermediate representation. It is not
sufficient to populate the current NiX `ProjectStore` without guessing
scientifically meaningful fields. Implementation must remain blocked until the
blocking evidence below is supplied and accepted.

The existing read-only inspector and fixture validation remain the maximum safe
Barugo workflow.

## 2. Evidence currently verified

The following is established from the two read-only Barugo databases, existing
repository evidence, and structural/arithmetic checks:

| Area | Classification | Verified evidence |
|---|---|---|
| Source provenance | **VERIFIED** | Both files are valid SQLite databases, pass integrity checks, and have stable SHA-256/size records. |
| ABEM schema versions | **VERIFIED** | Both record project schema 4 and common schema 3. |
| ERT/VES dataset distinction | **VERIFIED for supplied files** | Task names and protocol filenames identify the supplied files as `Gradient_1` ERT and `VES Schlumberger_1` VES. This does not decode numeric array codes universally. |
| Observation boundary | **VERIFIED** | `DP_MEASURE` links `DPID` to `MeasureID`; linked rows have matching geometry, measurement metadata, and DPV values in the supplied files. |
| DPV structure | **VERIFIED** | `DPV` is a multi-row value stream keyed by task/measurement/data-point/channel/sequence/datatype, not one complete observation per row. |
| A/B/M/N role columns | **VERIFIED** | `DP_ABMN` explicitly stores separate A, B, M, and N coordinate columns. Numeric electrode numbering is not verified. |
| Datatype labels/units | **VERIFIED** | The `Datatype` table labels `R`, `I`, `ΔU`, `ρapp`, `SP`, `IP`, `IPΔU`, and temperature with displayed units. Channel and polarity semantics remain unresolved. |
| Internal resistivity arithmetic | **VERIFIED as internal consistency** | Stored `ρapp = R × K` is reproducible for 401/401 ERT and 25/25 VES linked rows to floating-point precision. This is not independent instrument or inversion validation. |
| VES geometry pattern | **VERIFIED as structural evidence** | Supplied VES rows are symmetric and support derivation of AB/2 and MN/2. This does not establish a universal vendor VES persistence contract. |
| Source immutability | **VERIFIED** | Original ERT and VES hashes remain unchanged after inspection and fixture testing. |
| NiX compatibility | **VERIFIED: incompatible as-is** | Vendor databases do not contain the NiX `ProjectStore` tables and current NiX persistence has no dedicated VES-point representation. |

## 3. Blocking evidence gaps

Each item below must be resolved before the corresponding field can be
persisted into NiX. “Strong” structural evidence is not sufficient authority for
an importer mapping.

| Missing evidence | Status | Why it blocks | Smallest evidence required |
|---|---|---|---|
| `ArrayCode`, `ProtocolMode`, `Mode`, `ModeValue` definitions | **BLOCKING** | A numeric vendor code cannot safely become a NiX array/protocol declaration. | Versioned ABEM code table with values, names, scope, and applicable software/firmware versions; include codes 15 and 7. |
| ERT Gradient/2x21 semantics | **BLOCKING** | Task/protocol filenames do not define all electrode and acquisition semantics. | Authoritative description of `Gradient_2x21.xml`/`2X21.xml`, electrode roles, generated configurations, and expected observation records. |
| Electrode numbering and switch mapping | **BLOCKING** | Current NiX measurements require integer A/B/M/N electrode references. | Explicit mapping among `DP_ABMN` roles, coordinate positions, `Electrodes`, switch number/address, cable, takeout, remote electrodes, and any numbering origin/order. |
| Coordinate units, scale, axis, and origin | **BLOCKING** | Arithmetic agreement does not prove metres or universal scaling. | Schema/vendor statement for units and scale of all relevant coordinate and spacing fields, including axis orientation and local-origin rules. |
| CRS/datum/GPS semantics | **BLOCKING when GIS coordinates are imported** | Latitude/longitude columns alone do not establish a usable spatial reference or reprojection rule. | CRS/datum/epoch, axis order, elevation units, GPS fix-quality meanings, and explicit reprojection requirements; or an explicit local-only import decision. |
| Channel and `SeqNum` semantics | **BLOCKING** | Multiple candidate electrical values exist; selecting one by name alone can mix channels or phases. | Authoritative channel/sequence definitions, DC/IP phase rules, repeat/stack behavior, and the primary-value selection rule for each array. |
| Electrical polarity/reference conventions | **BLOCKING for NiX voltage/current fields** | `ΔU/I=R` confirms arithmetic for subsets but not polarity, reference, or sign conventions. | Definitions of electrode polarity, voltage reference, current sign, channel pairing, and treatment of negative values. |
| `Ready`, `Status`, and related flags | **BLOCKING for QC mapping** | Numeric flags cannot be translated to NiX ACTIVE/EXCLUDED/FLAGGED without bit meanings. | Complete enum/bitmask definitions and examples for `DP_MEASURE.Ready`, `DP_ABMN.Ready`, `DPV.Status`, `TestStatus`, `TxStatus`, and related fields. |
| Uncertainty/statistical fields | **BLOCKING for uncertainty/QC mapping** | `DataSDev`, `DataSDevType`, `N`, and `MCycles` cannot be assumed to mean standard deviation, standard error, or stack count. | Definitions, units, formulas, population/sample convention, and ADC scaling for `DataSDev`, `DataSDevType`, `N`, `MCycles`, `ADValue`, and `ADRange`. |
| VES persistence semantics | **BLOCKING for VES import** | Current NiX storage is ERT-oriented and lacks AB/2/MN/2 fields. | Approved NiX VES schema/sidecar representation, observation identity rules, AB/2/MN/2 units, and explicit `FocusX/Y/Z` treatment. |
| Auxiliary/unlinked row policy | **BLOCKING for lossless import** | Silent omission could discard scientifically or operationally relevant source information. | Authoritative inclusion/exclusion rules and preservation requirements for unlinked `DP_ABMN`, logs, sessions, tests, `ExternalData`, datasets, and unknown columns. |
| Version and migration behavior | **BLOCKING for supported-file claims** | A parser cannot safely reinterpret older/newer schema variants without policy. | Supported version matrix, migration/rejection rules, and malformed/incomplete database behavior. |
| Authorized conformance fixtures | **BLOCKING for qualification** | Field meanings need row-level confirmation, not only documentation. | Licensed/authorized ERT and VES copies across clean, repeated, excluded/failed, multi-channel, coordinate/GPS, and auxiliary cases, with expected records and software versions. |

## 4. Non-blocking gaps

These do not prevent a conservative importer if they are preserved as raw
vendor data and not assigned unsupported NiX meaning:

- exact semantics of datatype rows that have no values in the supplied files;
- display-only task settings that are retained verbatim;
- vendor log text and event payloads, if stored losslessly rather than mapped
  to QC;
- instrument/transmitter metadata when retained as provenance only;
- report/UI display formatting;
- internal arithmetic tolerance refinements after a vendor reference procedure
  is supplied;
- performance optimization of parsing, provided validation remains before
  persistence;
- optional LS2 transport evidence when importing an authorized exported
  `project.db` file rather than obtaining it from the instrument.

These become blocking if NiX intends to interpret, filter, alter, or discard the
corresponding information.

## 5. Proposed field and relationship mapping

This is a proposal for the future contract, not an authorization to implement.
Every conditional mapping requires the stated vendor evidence and validation.

| ABEM field/relationship | Intended NiX representation | Current status |
|---|---|---|
| File path, SHA-256, byte count, read-only source | `imported_sources` provenance | **VERIFIED / SAFE** |
| Project/schema/version comments | source metadata or immutable extra | **VERIFIED / SAFE** |
| `Tasks.ID`, `Tasks.Name`, task settings | one explicitly selected NiX survey and metadata | **CONDITIONAL** on task/type selection and version policy |
| `DP_MEASURE.ID`, `DPID`, `MeasureID` | stable source measurement identity | **VERIFIED as source identity** |
| `DP_ABMN` A/B/M/N coordinates | intermediate role-labelled geometry; later NiX electrode references | **CONDITIONAL** on units and numbering evidence |
| `Tasks.SpacingX/Y/Z` | geometry scale metadata and validated coordinate conversion | **CONDITIONAL** |
| `Datatype` definitions | immutable datatype dictionary and raw-value metadata | **VERIFIED as raw metadata** |
| selected `ρapp` | NiX apparent resistivity | **CONDITIONAL** on channel/sequence rule, finite values, and `R×K` validation |
| selected `R` | NiX resistance | **CONDITIONAL** on channel/sequence/polarity rule |
| selected `I` and `ΔU` | NiX current/voltage | **BLOCKED** until pairing and polarity are documented |
| all `DPV` rows | lossless vendor-value sidecar/extra | **VERIFIED as required preservation strategy** |
| `Ready`/`Status`/test flags | NiX QC/status | **BLOCKED** until definitions are supplied |
| `DataSDev`/`N`/`MCycles`/ADC fields | uncertainty/statistics/vendor extras | **BLOCKED for scientific interpretation; safe as raw extras** |
| ERT array/protocol codes | NiX array metadata | **BLOCKED** until authoritative code table exists |
| VES symmetric geometry | dedicated VES points with AB/2 and MN/2 | **BLOCKED** until VES schema and units are approved |
| `FocusX/Y/Z` | vendor metadata only unless documented otherwise | **BLOCKED from depth/elevation mapping** |
| `Measures` lat/lon and `GPSPositions` | GIS coordinate metadata | **BLOCKED** until CRS/fix semantics are documented |
| sessions, logs, tests, datasets, auxiliary tables | preserved source records or explicit documented exclusions | **BLOCKED** until lossless policy is approved |

## 6. Remaining semantic ambiguity

### ERT versus VES

The supplied files can be classified by task/protocol names, but a general
importer must not infer dataset type solely from a filename, array code, or table
presence. It should require explicit task/type selection and validate the
selection against vendor metadata.

### Measurements and observations

`DP_MEASURE` is the demonstrated observation boundary for these files. `DPV` is
a value stream, and multiple rows may represent channels, sequences, or phases.
The vendor must define which records form one primary NiX observation and how
repeated values are retained.

### Geometry and electrodes

A/B/M/N role columns are explicit, but stable integer electrode numbering and
switch wiring are not. Coordinates can be retained as role-labelled vendor
geometry; they cannot yet populate NiX `a`, `b`, `m`, `n` integer fields safely.

### Arrays and protocols

The names `Gradient_2x21`, `2X21`, and `VES_Schlumberger` are useful metadata,
but do not decode numeric fields or establish all acquisition semantics. No
commercial-software equivalence follows from these names.

### Project metadata

Task, session, software, and timestamp fields are available, but precedence,
timezone, and event meaning are not fully defined. They should initially be
preserved verbatim rather than collapsed into one inferred project date.

### Units and reference systems

Electrical datatype units are explicit. Coordinate units, CRS, datum, axis
orientation, and GPS quality semantics are not. The observed scale reproduces
stored resistivity but does not establish a universal metre or GIS mapping.

### Quality and QC

The presence of `Ready`, `Status`, deviations, counts, and test fields does not
establish their meanings. NiX must not mark, exclude, or accept measurements
based on correlations in the two sample files.

### Vendor-specific fields

`FocusX/Y/Z`, IP windows, SP, logs, tests, ADC fields, and auxiliary records need
lossless preservation or explicit vendor-approved exclusion. Unknown fields must
never be silently dropped.

## 7. Minimum vendor response to remove the gate

The smallest complete unblock package is:

1. An authorized schema/data dictionary for project schema 4/common schema 3,
   including relationships and supported-version policy.
2. Code tables and semantic definitions for array/protocol/mode/channel/
   sequence/status fields, specifically covering the supplied ERT and VES cases.
3. Coordinate and wiring specification covering units, scale, axes, origin,
   CRS/datum, electrode numbering, and switch mapping.
4. VES specification covering observation identity, AB/2, MN/2, `FocusZ`,
   units, and an approved NiX persistence representation.
5. QC/statistics specification covering status bits, exclusion rules, negative
   apparent resistivity, uncertainty fields, stacking, and timestamps.
6. Lossless handling rules for auxiliary/unlinked records and unknown columns.
7. Authorized copied fixtures with row-level expected outputs and tolerances.

A response may explicitly mark a field **not applicable** or **metadata only**,
but must state that decision for the affected software/firmware versions.

## 8. Readiness decision and next milestone

**Decision: NOT READY.** No `abem-project-db-to-nix-v0.2-draft` is justified and
no importer should be implemented yet.

The recommended next milestone is **ABEM evidence acquisition and intermediate
parser qualification**, after an authorized vendor evidence package is
available. That milestone should first implement only a read-only parser and
validator producing a versioned intermediate record set. It should run against
copied fixtures, preserve all source identifiers/raw fields, and fail before
any `ProjectStore` transaction on unresolved or invalid semantics. A separate,
user-approved persistence adapter may follow only after the parser passes the
fixture acceptance matrix.

This assessment does not change the M15 status. LS2 hardware communication
remains fail-closed and physically unvalidated.
