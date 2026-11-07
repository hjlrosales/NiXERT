# Data QC notes

QC is an inspection and status layer over imported measurements. It never edits the managed raw file and never removes a measurement row.

Current deterministic rules flag:

- missing/non-finite/non-positive apparent resistivity;
- non-finite or non-positive resistance when resistance is present;
- repeated `(A, B, M, N)` tuples;
- gaps in the electrode-number sequence;
- apparent-resistivity outliers in log10 space relative to the dataset median.

Outliers are separated into `potential resistivity noise` and `extreme apparent resistivity` using explicit configurable thresholds. Detection produces reasons; `flag_detected` is an explicit operation that marks rows `FLAGGED`. Users can explicitly set `EXCLUDED` or restore `ACTIVE`, with in-memory undo/redo for the current QC session.

The current missing-electrode rule is a structural heuristic and does not assert that a field survey with intentionally unused electrodes is invalid. It should be reviewed alongside the electrode map in future UI work.
