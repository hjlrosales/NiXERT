# Barugo vendor evidence request

**Request purpose:** qualify the remaining ABEM `project.db` semantics required
for a safe, provenance-preserving NiX import.

**Current decision:** `importer_ready = false` / **NOT_READY**.

This request concerns only file semantics and authorized exported database
fixtures. It does not request or authorize LS2 commands, acquisition, protocol
reverse engineering, instrument configuration, or undocumented USB/Wi-Fi
communication.

## 1. Executive summary

NiX can already read the supplied Barugo files read-only and preserve their raw
SQLite facts, source hashes, table/row/column provenance, and logical
`DP_MEASURE` relationships. It can also preserve vendor datatype labels and
raw electrical values.

The supplied files do not establish the semantics needed to create final NiX
measurements or VES records safely. Structural patterns and internally
reproducible arithmetic are not sufficient vendor authority. Please provide the
minimum evidence listed below for the affected ABEM schema/software versions.

A response may state **NOT APPLICABLE** or **METADATA ONLY**, but must state the
scope, affected versions, and why that treatment is correct.

## 2. Current import blockers

The qualification layer currently keeps these areas blocked:

1. ERT/VES classification for files not covered by exact authorized evidence;
2. electrode roles, numbering, and switch mapping;
3. array/protocol/mode semantics;
4. coordinate units, scale, axes, origin, CRS, and GPS semantics;
5. channel, sequence, phase, polarity, and primary-value selection;
6. QC/status/exclusion semantics;
7. uncertainty, stacking, and ADC-field semantics;
8. VES representation and persistence;
9. lossless handling of auxiliary and unlinked records; and
10. final ABEM-to-NiX persistence compatibility.

Source provenance, raw-value preservation, source-row identity, task identity,
raw datatype labels/units, and structural link presence can already be qualified
narrowly without interpreting vendor semantics.

## 3. Evidence request table

| ID | Semantic question | ABEM fields/tables | Current observed evidence | Why insufficient | Exact evidence requested | Minimum acceptable evidence | NiX validation and unlocked state | Applies to |
|---|---|---|---|---|---|---|---|---|
| E-01 | How is a dataset identified as ERT or VES? | `Tasks.Name`, `Tasks.ArrayCode`, `TaskSettings.ProtocolFile`, `SpreadFile`, schema/version tables | Supplied files are documented as `Gradient_1` ERT and `VES Schlumberger_1` VES; exact source hashes/task/protocol combinations are authorized in the current qualification profile | Names and numeric codes cannot define a general classifier for other files or versions | Versioned authoritative rule identifying dataset kind and precedence among task, protocol, array, and schema metadata | A signed/controlled vendor statement or schema document covering the exact source/software versions, including supplied ERT/VES cases | Match the rule only to the declared versions; unrecognized or conflicting cases remain `blocked` | Both |
| E-02 | What do array, protocol, and mode codes mean? | `Tasks.ArrayCode`, `TaskSettings.ProtocolMode`, `DP_ABMN.Mode`, `ModeValue`, protocol/spread file references | ERT contains code 15 and Gradient/2x21 filenames; VES contains code 7 and Schlumberger filenames | Filenames and numeric patterns do not decode vendor enumerations or all acquisition behavior | Authoritative code tables and protocol-file semantics, including valid combinations, version scope, and whether a code maps to a NiX array label | Documentation/table covering codes 15 and 7, protocol mode 15, mode fields, and the exact Gradient/2x21 and VES files | Assert code/version consistency and map only listed codes; unknown combinations fail `blocked` | Both; ERT especially |
| E-03 | What do A/B/M/N roles map to physically and numerically? | `DP_ABMN.APos*`, `BPos*`, `MPos*`, `NPos*`, `DPKEY`, `Electrodes.*`, `ElectrodeTestData.*` | Role-labelled coordinate columns exist; `DPKEY` repeats coordinates; supplied `Electrodes` tables are empty | Role-column order does not establish stable NiX integer electrodes, switch order, cable, takeout, or remote electrodes | Wiring/geometry specification defining role, electrode number origin/order, switch number/address, cable/takeout, and remote-electrode behavior | Versioned diagram/data dictionary plus row-level examples linking one `DP_ABMN` record to electrode and switch identities | Reconstruct every fixture observation from the documented mapping; verify no collisions, missing electrodes, or role swaps | Both |
| E-04 | What are coordinate units, scale, axes, and origin? | `DP_ABMN` coordinates, `Tasks.SpacingX/Y/Z`, `TaskSettings.ElectrodeSpacing`, `Stations`, `Positions`, `Electrodes` | Coordinate scaling reproduces supplied apparent-resistivity values; linked coordinates are X-only in the supplied files | Arithmetic agreement is not proof of metres, universal scale, axis orientation, or origin rules | Coordinate specification for each relevant field, including units, scale operation, axis direction, origin, local/global status, and elevation meaning | Versioned vendor statement or controlled export specification covering the supplied schema and software versions | Apply only the documented transform; compare reconstructed coordinates to fixture expectations; otherwise retain raw coordinates and keep final geometry `blocked` | Both |
| E-05 | Do coordinates have a CRS/datum and how are GPS fields used? | `Measures.PosLatitude/PosLongitude/PosQuality`, `GPSPositions.*`, task/station positions | Latitude/longitude columns exist; `GPSPositions` is empty in supplied files; no CRS/datum is stored | Column names do not establish CRS, datum, epoch, fix quality, elevation units, or reprojection rules | CRS/datum/epoch, axis order, latitude/longitude/elevation units, fix-quality definitions, and explicit reprojection policy; or an explicit local-only decision | Authoritative coordinate reference specification or written `LOCAL_ONLY / no automatic reprojection` decision | Validate metadata and reject impossible/mismatched coordinates; only GIS-qualified results become `verified` | Both |
| E-06 | Which DPV rows form one primary DC observation? | `DP_MEASURE`, `DPV.Channel`, `DPV.SeqNum`, `Datatype`, `DataValue` | `DP_MEASURE` gives a structural link; `DPV` contains multiple channel/sequence/datatype rows; `ρapp` and `R` are present | Selecting by datatype name alone can mix channels, repeats, phases, or alternate results | Channel/sequence/phase definitions and a primary DC selection rule for each supported array and software version | A vendor data dictionary plus row-level expected selection for representative ERT and VES links | For every fixture link, select exactly the documented primary records, preserve all alternatives, and fail on ambiguity | Both |
| E-07 | What are current, voltage, resistance, polarity, and phase conventions? | `DPV` datatype IDs/names, `Channel`, `SeqNum`, `DataValue`, `ExternalData.Phase*` | Datatype units are displayed; `ΔU/I=R` matches available subsets; negative ERT `ρapp` values exist | Arithmetic consistency does not establish sign, reference electrode, polarity, channel pairing, DC/IP separation, or negative-value treatment | Definitions of `I`, `ΔU`, `R`, `SP`, `IP`, `IPΔU`, phase/window, polarity/reference, stacking, and negative-value handling | Formula/sign convention document plus expected rows containing positive, negative, repeated, and missing pairings | Recompute only under the documented rule, verify pairings/tolerances, and preserve values that cannot be paired; unlocks verified electrical mapping only | Both |
| E-08 | What do readiness/status/test flags mean? | `DP_MEASURE.Ready`, `DP_ABMN.Ready`, `DPV.Status`, `ElectrodeTestData.TestStatus`, `TxStatus`, `Datasets.ExcludeSet` | Numeric flags occur, including several `DPV.Status` values; all supplied linked `DP_MEASURE.Ready` values are 1 | Correlation and numeric patterns cannot define QC acceptance, exclusion, suspiciousness, or test failure | Complete enum/bitmask definitions, precedence, lifecycle, and exclusion rules with examples | Versioned bit table covering all listed fields and representative accepted/rejected/failed records | Decode exact bits, compare expected fixture QC outcomes, and reject unmapped values; unlocks QC mapping | Both |
| E-09 | What do deviation, stack, and ADC fields mean? | `DPV.DataSDev`, `DataSDevType`, `N`, `MCycles`, `ADValue`, `ADRange`, `ExternalData.DataSDev/N` | Fields and numeric ranges are preserved; names suggest statistics but do not define them | They cannot safely support uncertainty, weighting, or QC without formulas and scaling | Definitions, units, formulas, statistical population/sample convention, stack/cycle meaning, ADC conversion and range semantics | Data dictionary plus worked row-level calculations for each field used by NiX | Reproduce vendor expected values and retain fields losslessly; only documented mappings become `verified` | Both |
| E-10 | What is the VES observation and persistence model? | VES `DP_ABMN`, `DP_MEASURE`, `DPV`, `FocusX/Y/Z`, task/protocol settings | Supplied geometry is structurally symmetric and supports observed AB/2/MN/2 derivation; current NiX store has no dedicated VES point model | Structural symmetry does not define persistence, units, focus meaning, repeated readings, or layer-depth semantics | VES schema/export specification covering observation identity, AB/2, MN/2, units, sign/order, repeats, `FocusX/Y/Z`, and whether focus is metadata only | Versioned VES data dictionary plus approved target representation: NiX schema extension or lossless sidecar | Validate all fixture points and round-trip them without loss; `FocusZ` remains metadata unless explicitly defined | VES |
| E-11 | Which unlinked and auxiliary records must be imported or excluded? | Unlinked `DP_ABMN`, `Sessions`, `Measures`, `Stations`, `Positions`, `Electrodes`, `GPSPositions`, `ExternalData`, `Datasets`, `DatasetItems`, `Log`, test tables, unknown tables/columns | ERT and VES contain unlinked geometry and operational/log/test records; parser preserves them | Silent omission can lose scientific or provenance information; automatic inclusion can misclassify operational data | Table-by-table inclusion, exclusion, and lossless-preservation policy, including orphan behavior | Written vendor policy that explicitly handles every table present in the supported versions and unknown future tables | Compare imported/sidecar row sets and hashes against source; any unaccounted row fails closed | Both |
| E-12 | What schema versions and migrations are supported? | `ProjectSchemaVersion`, `CommonSchemaVersion`, `TT_EC_SCHEMA`, all tables | Supplied files report project 4/common 3 and are valid SQLite | One version observation cannot define behavior for older/newer or altered databases | Supported-version matrix, migration/rejection rules, required columns, and malformed/incomplete behavior | Versioned compatibility document plus one fixture per supported branch and explicit rejection cases | Parse each fixture, verify expected schema/field behavior, and reject unsupported versions before persistence | Both |
| E-13 | What source and software metadata are authoritative? | `Tasks.Time`, `Sessions.*`, `Measures.Time`, `Log.Time`, instrument/transmitter fields | Task/session/software/timestamp fields are present and source-addressable | Timestamp precedence, timezone, clock source, and metadata authority are not fully defined | Metadata precedence/timezone/event specification and fields required for survey identity | Written field-precedence and timezone policy; fields may be marked metadata-only | Preserve raw values and validate only the documented normalized subset; otherwise keep raw metadata | Both |
| E-14 | What is the approved ABEM-to-NiX target? | NiX `ProjectStore`, `imported_sources`, `electrodes`, `measurements`, plus future VES representation | Current NiX store is ERT-oriented; no importer or VES target exists | Vendor semantics alone cannot approve a NiX schema/persistence design | Jointly approved mapping/target contract defining required, optional, sidecar, and non-importable fields | Signed target contract with atomic transaction, raw sidecar, provenance, and no-silent-loss rules | Build an intermediate-to-target conformance test; readiness remains blocked until approved | Both |
| E-15 | Which authorized fixtures prove the definitions across versions? | Complete source databases and expected-result manifests | Current Barugo files are real user-provided samples; no authorized conformance package exists | Two internally consistent files cannot cover status, repeats, versions, GPS, failures, or edge cases | Licensed/authorized copies and expected records for clean, repeated, failed/excluded, multi-channel, coordinate/GPS, ERT, and VES cases | Fixtures include software/firmware/settings, permission, row-level expected outputs, and tolerances | Hash fixtures, parse read-only, compare all required fields/relationships, and record success/failure without tuning | Both |

## 4. Minimum acceptable evidence by blocker

### ERT minimum

At minimum, an ERT implementation package must include E-02, E-03, E-04,
E-06, E-07, E-08, E-09, E-11, E-12, E-14, and E-15. E-05 is also required if
coordinates are to be presented as GIS/projected data rather than local survey
coordinates.

### VES minimum

At minimum, a VES implementation package must include E-02, E-03, E-04, E-06,
E-07, E-08, E-09, E-10, E-11, E-12, E-14, and E-15. E-05 is required for GIS
coordinates.

### Classification minimum

E-01 is required for any file not already covered by an exact authorized source
entry. It must never be replaced by inference from a task name or numeric
array code.

## 5. Recommended vendor verification procedure

1. Provide document title, revision, publication date, applicable ABEM
   project/common schema versions, instrument software, and firmware versions.
2. Provide clean, authorized copies of one representative ERT and one VES
   database plus permission for automated parser tests. Provide additional
   edge-case fixtures for failed/excluded, repeated, multi-channel, coordinate,
   and auxiliary cases.
3. For each fixture, provide the acquisition settings and a row-level manifest
   keyed by `DP_MEASURE.ID`, `DPID`, and `MeasureID`.
4. Mark the expected dataset kind, array/protocol, coordinate units/reference,
   channel/sequence selection, status interpretation, and VES fields in the
   manifest. Do not provide only a screenshot or a final plot.
5. Include expected raw and interpreted records separately. Raw values must
   remain byte/value-preserving; interpreted values must cite the definition
   used.
6. Include worked calculations for any selected `R`, `I`, `ΔU`, or `ρapp`, with
   formula, sign convention, tolerance, and treatment of missing/negative
   values.
7. Include explicit handling for every unlinked/auxiliary row class and every
   unknown column in the supported schema.
8. NiX will run the read-only intermediate parser, compare hashes and row-level
   manifests, and record both successful and unsuccessful comparisons.
9. Only after all required semantic results become `verified` will a separate
   importer design be reviewed. No test parameter will be changed merely to
   obtain agreement.

## 6. Evidence acceptance criteria

Evidence is accepted only when it is:

- attributable to an authorized Guideline Geo/ABEM technical source or an
  explicitly authorized technical representative;
- versioned and scoped to the relevant ABEM schema/software/firmware;
- precise enough to define field units, enumerations, relationships, and
  precedence rather than merely naming a column;
- accompanied by fixtures or worked examples where a mapping affects data;
- reproducible by read-only parser tests;
- consistent across the supplied fixtures without undocumented exceptions; and
- compatible with lossless provenance, atomic persistence, and fail-closed
  behavior.

The following are **not** sufficient on their own:

- column or table names;
- numeric pattern matching;
- a visually plausible plot;
- internal `ρapp = R × K` arithmetic consistency;
- conventions from unrelated ABEM software/products;
- third-party reverse engineering;
- a screenshot without row-level source identity; or
- network connectivity or VNC access to an LS2.

## 7. Qualification states unlocked

| Evidence outcome | Qualification state |
|---|---|
| Raw field/table/relationship is present and source-addressable | `verified` for factual preservation only |
| Vendor meaning is not supplied but raw evidence is retained | `unknown` |
| NiX layer intentionally does not implement the operation | `unsupported` |
| Source or relationship violates parser invariants | `invalid` |
| Required semantic lacks accepted evidence | `blocked` |
| All required ERT/VES semantics, target contract, and fixtures pass | Candidate for `READY` review; not automatic production approval |

Evidence for one field does not automatically qualify related fields. For
example, defining `Datatype.Name=R` does not define channel selection, polarity,
QC status, uncertainty, electrode numbering, or VES persistence.

## 8. Remaining risks

Even after semantic evidence is supplied, the following remain separate
qualification questions:

- parser behavior on versions not covered by the evidence package;
- lossless preservation of unknown future tables/columns;
- numerical tolerance and independent reference validation;
- handling of negative or invalid measurements;
- coordinate/GIS correctness when GPS is absent or low quality;
- VES scientific model validity and persistence round-tripping;
- inversion and geological interpretation validity;
- commercial-solver equivalence, including RES2DINV equivalence; and
- LS2 hardware/API behavior and acquisition safety.

This request does not ask for or establish any geological certainty, production-
grade inversion claim, commercial-solver equivalence, or LS2 communication
capability.

## 9. Final status

**ABEM → NiX importer: NOT READY.**

Do not implement the importer until the mandatory evidence for the affected
ERT/VES path is accepted and the authorized fixture acceptance matrix passes.
Until then, NiX supports read-only factual inspection, intermediate parsing, and
semantic qualification only. The original Barugo databases remain read-only,
and M15 LS2 communication remains fail-closed and physically unvalidated.

**Requested vendor response format:** for each ID, reply `SUPPORTED`, `NOT
APPLICABLE`, or `UNKNOWN/UNSUPPORTED`, attach the document/fixture reference,
and include title, revision, date, applicable versions, license/permission, and
technical contact.
