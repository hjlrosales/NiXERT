# Barugo semantic qualification

## Purpose

`nix_ert.data.abem_qualification` evaluates the factual
`ABEMIntermediateProject` against the currently authorized evidence. It is a
qualification report, not an importer. It does not access SQLite, calculate
scientific values, create NiX records, or communicate with LS2.

The controlled pipeline is:

```text
ABEM SQLite → intermediate facts → semantic qualification → readiness gate → importer
```

The final importer stage remains unimplemented.

## Inputs and evidence rule

The layer consumes only:

- raw facts, source locations, relationship checks, and parser status from
  `ABEMIntermediateProject`; and
- the explicit allow-list `DOCUMENTED_BARUGO_EVIDENCE`, which contains the two
  previously documented Barugo source hash/task/protocol combinations.

The allow-list is source-specific evidence, not a general ABEM classifier. A
file is not classified from table names, filenames, numeric patterns, task-name
similarity, array codes, or assumptions about ABEM products or versions.

For the supplied files, exact evidence entries are:

- ERT SHA-256 `057674127c923842510ee5e8af6082fed88ef152438f3752ca681d5f2f6d47af`,
  task `Gradient_1`, protocol `/home/root/protocols/Gradient_2x21.xml`;
- VES SHA-256 `97eec29b3f9870092f9674e54b560df20f9df2130ac18778ff29161757d09e51`,
  task `VES Schlumberger_1`, protocol `/home/root/protocols/VES_Schlumberger.xml`.

A copied or generic fixture that does not match an authorized entry remains
unclassified even if its task text appears obvious.

## Qualification states

Each `QualificationResult` records a name, observed fact, source locations,
interpretation (only when qualified), status, evidence explanation, import
impact, and required additional vendor evidence.

- **`verified`** — the fact or narrow interpretation is directly supported by
  the intermediate representation and authorized evidence.
- **`unknown`** — evidence is insufficient, and the item is retained only as an
  unresolved/non-interpreted fact.
- **`unsupported`** — this layer intentionally does not provide the operation
  or interpretation, such as scientific calculations, LS2 communication, or
  NiX VES persistence.
- **`invalid`** — the intermediate representation reports a structural/source
  failure, such as a broken logical link.
- **`blocked`** — the semantic is required for safe import but is not verified.
  This is the fail-closed state for unresolved scientific meaning.

The layer never promotes `unknown` or `unsupported` to `verified` based on
appearance or correlation.

## Qualified categories

The report covers:

- project and survey identity;
- source provenance;
- dataset kind;
- measurement identity and DP_MEASURE relationships;
- DP_ABMN and DPV relationship facts;
- raw electrode positions;
- electrode roles/numbering;
- array and protocol semantics;
- vendor-declared units;
- coordinate reference system and units;
- timestamp records and optional normalization;
- QC/status and uncertainty semantics;
- observed raw vendor values;
- calculated scientific values;
- VES persistence;
- auxiliary raw preservation and auxiliary semantics;
- NiX compatibility.

A verified relationship means only that the logical source link is present and
valid. It does not qualify electrode numbering, array geometry, QC status, or
scientific interpretation.

## Blocking rules and current result

Overall readiness is deterministic:

```text
READY       if no result blocks import
NOT_READY   if any result blocks import
```

For the current authorized Barugo evidence, the result is **`NOT_READY`**.
Even the two exact supplied source entries can verify their source-specific
ERT/VES classification, provenance, task identity, raw units, raw values, and
structural relationships, but import remains blocked by:

- array/protocol/mode code semantics;
- electrode numbering and switch mapping;
- coordinate units, axis/origin, CRS, datum, and GPS rules;
- channel/sequence/polarity interpretation needed by a final importer;
- QC/status and uncertainty semantics;
- VES persistence representation;
- approved handling of vendor-specific and auxiliary records;
- the absence of a final approved ABEM-to-NiX mapping.

Unknown timestamp normalization, auxiliary semantics, and scientific
calculation support are explicitly non-blocking when raw values remain
losslessly preserved and no unsupported interpretation is attempted. If a
future importer needs to normalize, filter, or discard those fields, their
status becomes a blocking requirement for that operation.

Invalid intermediate results always produce `invalid` qualification results and
`NOT_READY`. Invalid relationships are not repaired or reinterpreted.

## Provenance and safety

Qualification preserves the intermediate source hash and source locations in
every result. It has no dependency on `ProjectStore` and performs no persistence
calls. It cannot create measurements, surveys, projects, model versions, or
report records.

The layer does not modify the original Barugo databases, use them as live LS2
sources, or open USB, Wi-Fi, serial, VNC, or other instrument interfaces.

## Remaining vendor evidence

The minimum evidence remains the package listed in:

- [`barugo_vendor_evidence_checklist.md`](barugo_vendor_evidence_checklist.md)
- [`barugo_import_readiness.md`](barugo_import_readiness.md)
- [`barugo_import_contract.md`](barugo_import_contract.md)

In particular, NiX still needs authoritative definitions for schema/version
compatibility, numeric array/protocol/channel/status fields, electrode and
switch mapping, coordinate units/CRS, polarity and stacking, uncertainty
fields, VES representation, auxiliary-row policy, and authorized conformance
fixtures with expected records.

## Next milestone

The next implementation milestone is semantic qualification against an
authorized vendor evidence package, followed by read-only parser conformance
fixtures. Only after all scientifically meaningful required results become
`verified` should a separate user-approved ABEM-to-NiX persistence adapter be
considered.

**ABEM → NiX importer: NOT READY.**
