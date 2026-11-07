# M16 advisory AI notes

M16 currently uses a deterministic local provider-neutral assistant over structured NiX ERT artifacts. It does not call a network service or external language model. The service supports project inventory, suspicious measurement identification, QC explanations, log-space resistivity anomaly ranking, model/version comparison, inversion summaries, VES review, 2D/3D model explanations, report drafting, and bounded natural-language queries.

Responses contain traceable findings and explicit limitations. Statistical anomalies and QC flags are review candidates, not geological conclusions. VES/model explanations summarize supplied data and stored metadata; they do not establish uniqueness, resolution, or geological certainty.

The assistant is read-only while analyzing. Mutation support is limited to an explicit exclusion proposal:

```text
propose_exclusion
    ↓
explain_proposal
    ↓
execute_proposal(approved=True)
```

Execution changes only working measurement status through the existing QC engine. It does not delete rows, modify raw files, alter inversion parameters, or change model snapshots. A future generative provider may be added behind the same structured response and approval boundary only after its prompt/data handling and failure behavior are validated.

Direct Terrameter LS2 communication remains independently blocked by the requirements in `docs/ls2.md`; M16 operates on already imported/project-managed artifacts.
