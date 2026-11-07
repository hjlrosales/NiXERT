# Processing and model versions

Version records are immutable snapshots of a processing or inversion state. Each record stores the survey, kind, parent, canonicalized parameter JSON, SHA-256 parameter hash, structured snapshot JSON, notes, and creation timestamp.

Changing a display name or notes does not change the numerical snapshot. `restore_by_copy` creates a new child record instead of mutating or deleting the source version. Comparisons report parameter and snapshot differences. Canonical JSON sorting makes parameter hashes reproducible when mapping insertion order differs.

Version records do not yet store binary figure artifacts or complete raw measurement arrays; those should be added only when their serialization contract is defined.
