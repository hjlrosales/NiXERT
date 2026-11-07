# Reports

`ReportData` is the structured report contract. A report is a fixed, numbered
section sequence rendered from structured data only; no section is composed from
free text supplied at render time.

## Structure

Every report contains these numbered sections, in this order:

1. Project information
2. Survey methodology and organization
3. Data quality control summary
4. Inversion parameters and convergence
5. VES models
6. Interpretation
7. Conclusions
8. Recommendations
9. Limitations and scientific scope
10. Provenance and report identity
11. Pseudosection data appendix (only when pseudosection data is supplied)
12. Appendices (only when appendices are supplied)

The HTML artifact carries a cover block, a generated table of contents that links
to exactly the sections present, numbered headings with anchors
(`#section-N`), and a footer with the report content digest. Sections whose data
was not supplied render an explicit note — for example *"No conclusions supplied.
This report does not invent geological conclusions."* — rather than being dropped
or inferred. All inserted values are HTML-escaped.

## Provenance and identity

`ReportData.provenance` is rendered as its own section. Project-bound reports
populate it with the software version, project, survey identity and type, selected
version and parameter hash, source SHA-256 values, the persisted state
fingerprint, the dataset-match statement, the qualification scope, and the
raw-data handling statement. The state fingerprint matches
`ReportData.inversion["State fingerprint"]`, so a report and its audit record can
be cross-checked.

`report_content_sha256(data)` digests the canonical content — independent of the
output format — and `report_manifest(data)` returns the machine-readable form:
report format version, title, generation time, section list with anchors, the
digest, and every section's data. Rendering the same data twice produces
identical bytes.

## Exports

`write_report(data, path)` dispatches on the suffix and rejects anything else
rather than silently writing HTML:

| Suffix | Writer | Contents |
|---|---|---|
| `.html`, `.htm` | `write_html` | Canonical report: cover, contents, numbered sections, provenance, footer digest |
| `.json` | `write_json` | `report_manifest` with sorted keys and the content digest |
| `.csv` | `write_csv` | Flat `section,record,item,value` rows covering every section, the pseudosection CSV, appendices, and a final `Report identity` row with the digest |
| `.pdf` | `write_pdf` | Simple multi-page text rendering; HTML/JSON remain authoritative |

All text exports are written as UTF-8 with `\n` line endings, so repeated exports
of identical data are byte-identical.

HTML is the canonical report artifact and requires no network or GUI. The PDF is
a text flattening only: tables become text and images are not embedded.

The desktop shell offers all four formats: the *Interpret / Report* tab has an
**Export format** selector (`HTML report`, `PDF report`, `CSV data export`,
`JSON manifest`) whose choices come from
`nix_ert.app.report_export.REPORT_EXPORT_FORMATS`. The save dialog uses the same
filter list, suggests a file name with the selected extension, and the shell
reports the written path, the format's role, and the content digest. A typed
supported extension wins over the selector (the writer dispatches on it); a
typed unsupported extension is refused instead of being silently replaced.

## Frozen output

`tests/golden/report_fixture.json` is a fixed report fixture and
`tests/golden/report_fixture.html` / `.csv` are the exact bytes the generator
must keep producing, including the frozen content digest. `tests/test_report_golden.py`
compares bytes, so any change to structure, escaping, row order, or line endings
fails the suite. Regenerate deliberately with
`python tools/regenerate_report_goldens.py` and review the diff.

## Project-bound assembly

`nix_ert.reports.project_report` assembles reports from the currently open
persisted project and selected survey. It validates project metadata, survey
identity, managed raw-source paths and SHA-256 hashes, QC statistics, and
optional selected model/version ownership before writing. A report run is
appended to the project provenance table with source hashes, version ID, output
path, and a state fingerprint covering the persisted
project/survey/import/measurement/QC/model state; this audit record does not alter
raw bytes, measurements, statuses, or model snapshots. The format is chosen by
the requested output path (`.html`, `.json`, `.csv`, or `.pdf`).

The report explicitly marks missing selected models, stale/unlinked versions, and
missing interpretations rather than inventing them. Reports generated without a
selected model are valid project-state summaries but are not model reports.
Reports fail closed if a managed source is missing, changed, unreadable, or points
outside the project's managed raw-data directory.

## Scope

Reports are deliverables, not scientific evidence. A report states the recorded
qualification scope (`NOT VALIDATED` for external reference comparison,
RES2DINV equivalence not claimed), the numerical baseline limitations of the 2D/3D
models, and the blocked status of direct LS2 communication. It does not assert
geological certainty and does not replace professional interpretation.
