# Barugo read-only intermediate parser

## Purpose

`nix_ert.data.abem_intermediate` provides a factual layer between an ABEM
`project.db` file and any future semantic qualification or NiX importer.

The parser is intentionally **not** an importer. It opens a local SQLite file in
read-only mode, records raw vendor facts, preserves source locations, checks the
observed logical links, and records unresolved semantic boundaries explicitly.
It does not write, migrate, copy, transform, calculate, classify, or persist a
NiX project.

The pipeline remains:

```text
ABEM project.db
    → read-only intermediate representation
    → vendor/semantic qualification
    → future NiX import (not implemented)
```

## Scope

The parser safely records:

- source path, byte count, and SHA-256;
- SQLite integrity result;
- table names and declared column types;
- complete table rows and raw field values, including BLOBs;
- deterministic source row identities where an `ID` field exists;
- field-level observed/invalid status;
- logical `DP_MEASURE` links to `DP_ABMN`, `Measures`, and `DPV`;
- missing, duplicate, and invalid link conditions;
- raw task names, array/protocol codes, settings, geometry, measurements,
  timestamps, datatype labels, and vendor status/count fields;
- explicit semantic facts whose status is `unknown` or `unsupported`.

Every raw field has a `SourceLocation` containing the resolved source path,
table, row identity, and column. Relationship and semantic records also carry
their source evidence locations.

## Intermediate representation

The public representation consists of:

- `ABEMIntermediateProject`: one read-only factual parse result;
- `TableSnapshot`: table name, declared columns, and ordered raw records;
- `RawRecord`: table row identity and all raw fields;
- `RawField`: value, `FactStatus`, and exact `SourceLocation`;
- `RelationshipCheck`: logical link result and source/target locations;
- `SemanticFact`: an explicitly bounded semantic assertion;
- `FactStatus`: `observed`, `unknown`, `unsupported`, or `invalid`.

`ABEMIntermediateProject.importer_ready` is always false. The representation is
not shaped as `Measurement`, `Electrode`, `ImportedDataset`, or any other NiX
scientific/persistence model.

`to_dict()` provides a deterministic diagnostic form. BLOB values are represented
as hexadecimal data, and no output operation writes to the source or a project.

## Status semantics

### `observed`

The value or relationship is present in the database and can be reported
without interpreting its scientific meaning. Examples include a raw `ArrayCode`
integer, a `Datatype.Unit` string, a `DPV.DataValue`, or a valid
`DP_MEASURE` linkage.

### `unknown`

The source value exists, but available evidence does not establish its meaning.
The current parser marks dataset kind, array/protocol code meaning, electrode
numbering/switch mapping, coordinate units/CRS, and QC/uncertainty semantics as
unknown. It retains the raw evidence and does not guess.

### `unsupported`

The current layer deliberately does not provide the requested interpretation or
operation. This includes NiX VES persistence and LS2 communication. Unsupported
does not mean that the vendor value is invalid; it means this layer will not
perform that conversion or access path.

### `invalid`

The source or relationship violates a factual parser invariant, such as a
failed SQLite integrity check, a missing required ABEM table, a non-numeric value
in a declared numeric field, a duplicate `(DPID, MeasureID)` link, missing linked
geometry/measurement/DPV data, or invalid linked geometry. Invalid results are
returned as a factual parse with issues where possible, but are never promoted
to importable data.

## Relationship checks

The parser treats `DP_MEASURE` as the observed link boundary for the supplied
schema. For each link it checks, without assigning scientific meaning:

```text
DP_MEASURE.DPID      → DP_ABMN.ID
DP_MEASURE.MeasureID → Measures.ID
(DPV.DPID, DPV.MeasureID) matches the link
```

It also detects duplicate links and invalid linked geometry. These are logical
value checks; they are not presented as declared SQLite foreign keys. Unlinked
vendor records remain in their complete table snapshots and are not silently
discarded or reclassified.

## What is deliberately not interpreted

The intermediate parser does not decide:

- whether a file is ERT or VES from names, tables, or numeric codes;
- what `ArrayCode`, `ProtocolMode`, `Mode`, or `ModeValue` mean;
- electrode roles, integer numbering, switch wiring, or cable semantics;
- coordinate units, scale, CRS, datum, axis, or reprojection;
- which channel/sequence is the primary electrical observation;
- polarity, phase, stacking, or the meaning of `R`, `I`, `ΔU`, `SP`, `IP`, or
  `IPΔU` beyond retaining their vendor labels and values;
- QC, exclusion, uncertainty, or status meanings;
- VES AB/2, MN/2, focus/depth, or NiX persistence semantics;
- any geometric factor, apparent-resistivity, inversion, or other scientific
  calculation;
- the meaning or safe omission of logs, tests, auxiliary, or unlinked records;
- NiX schema compatibility;
- LS2 USB, Wi-Fi, serial, network, acquisition, or instrument control.

The existing semantic contract remains the authority for what evidence is
verified versus unresolved. The parser does not upgrade `unknown` or
`unsupported` states into mappings.

## Fail-closed behavior

The parser raises `ABEMIntermediateError` when the source cannot be read or
opened read-only. For readable SQLite sources, structural failures are retained
in the result with `status=invalid` and explanatory `issues`, allowing tests and
inspection tools to report the failure without reinterpretation.

A future importer must reject any intermediate result that is invalid, has
unresolved required semantics, or would drop raw records. No `ProjectStore`
transaction is part of this layer, so a failed parse cannot partially modify a
NiX project.

## Qualification evidence

Offline fixtures verify:

- source bytes remain unchanged;
- raw values, including BLOBs, are retained;
- table/row/column provenance is retained;
- logical relationships are represented;
- missing, duplicate, and invalid links are marked fail-closed;
- unknown and unsupported semantics are not guessed;
- ERT/VES task text does not strengthen into a semantic classification;
- repeated parsing produces the same factual diagnostic representation.

The supplied Barugo files remain read-only user data. Their previously recorded
SHA-256 values are unchanged:

- ERT: `057674127c923842510ee5e8af6082fed88ef152438f3752ca681d5f2f6d47af`
- VES: `97eec29b3f9870092f9674e54b560df20f9df2130ac18778ff29161757d09e51`

## Current limitations and eventual importer boundary

This layer does not make the ABEM importer ready. Vendor evidence is still
required for numeric code tables, channel/sequence semantics, electrode
numbering, coordinate units/CRS, QC/status/uncertainty meanings, VES
representation, auxiliary-record policy, supported-version rules, and
conformance fixtures. See:

- [`barugo_import_contract.md`](barugo_import_contract.md)
- [`barugo_vendor_evidence_checklist.md`](barugo_vendor_evidence_checklist.md)
- [`barugo_import_readiness.md`](barugo_import_readiness.md)

The exact next stage is semantic qualification against an authorized vendor
evidence package and copied fixtures. Only after that stage succeeds may a
separate, user-approved persistence adapter be designed. **ABEM → NiX importer
implementation remains NOT READY.**
