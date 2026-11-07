# DAT import notes

The current import milestone supports text DAT files with:

- data count, positive electrode spacing, and array type headers;
- numeric array codes 1–6 and common textual array names;
- canonical `A B M N apparent_resistivity` rows;
- explicit indexed rows `index A B M N apparent_resistivity [resistance] [current] [voltage]`;
- optional topography count followed by distance/elevation pairs;
- `#`, `;`, and `!` comment lines.

The parser rejects count mismatches, unsupported array types, malformed numeric values, and invalid electrode identifiers. Parsed zero and negative apparent-resistivity values are retained and reported so QC can make a visible, non-destructive decision. The parser does not calculate apparent resistivity from resistance, because geometric-factor processing has not yet been independently validated.

Rows with optional electrical fields can overlap the indexed-row width. Auto-detection rejects those ambiguous widths rather than silently shifting electrode identifiers; callers with a known export convention must pass `row_format="canonical"` or `row_format="indexed"`.

Every successful project import copies the original bytes into a project `raw/` directory under a digest-qualified name and records the source SHA-256, byte count, and parsed facts in SQLite. Re-importing the same bytes into the same survey is rejected.

Real LS2 exports vary by firmware and export option. Additional variants should be added only with representative files and regression tests; no equivalence to RES2DINV has been established.
