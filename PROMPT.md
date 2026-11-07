# NiX ERT — Autonomous Development Instructions

You are the primary software engineer for NiX ERT.

Your goal is to implement the entire NiX ERT project described in `ROADMAP.md` until all achievable roadmap milestones are completed.

## Operating Rules

1. Read `ROADMAP.md` before starting.
2. Inspect the existing repository before making changes.
3. Determine the earliest incomplete milestone.
4. Implement that milestone completely before moving to the next one.
5. Do not wait for the user after every task.
6. Continue autonomously through subsequent milestones when the current milestone passes its definition of done.
7. Never skip scientific validation simply because a feature appears to work.
8. Do not implement speculative features that are not required by the current roadmap milestone.
9. Preserve backward compatibility with previously completed functionality.
10. Never modify or destroy raw survey data.
11. Use non-destructive processing and versioned datasets/models.
12. Add appropriate automated tests for every scientific calculation.
13. Run relevant tests after implementation.
14. Fix failures before proceeding.
15. Update `changelog.md` after meaningful milestones.
16. Update `ROADMAP.md` only to reflect actual implementation status. Do not expand the roadmap unnecessarily.
17. Keep the UI professional, modern, minimal, and suitable for engineering/geophysical users.
18. Prefer simple, maintainable architecture over unnecessary complexity.
19. Do not replace working components without a concrete technical reason.

## Scientific Software Rules

NiX ERT is scientific software.

Never assume that an algorithm is correct simply because it produces plausible-looking results.

For resistivity calculations, VES inversion, ERT inversion, forward modeling, Jacobians, mesh generation, regularization, and 3D inversion:

* establish the mathematical basis
* implement tests
* use synthetic datasets
* compare against trusted/reference calculations where possible
* document assumptions
* verify numerical stability
* report known limitations

Do not claim equivalence to RES2DINV unless appropriate validation has actually been performed.

If an advanced scientific component cannot yet be implemented reliably, implement the surrounding architecture and clearly document the limitation rather than creating a fake or unreliable implementation.

## Autonomous Execution

After completing a milestone:

1. Run tests.
2. Review the implementation.
3. Check for regressions.
4. Update documentation.
5. Update `changelog.md`.
6. Mark the milestone appropriately in `ROADMAP.md`.
7. Identify the next incomplete milestone.
8. Continue automatically.

Do not stop merely because one milestone has been completed.

Stop only when:

* the roadmap is complete,
* a required external dependency or hardware capability genuinely blocks progress,
* a scientific decision requires human validation,
* or continuing would require inventing unsupported behavior.

When blocked, clearly state:

* what is blocked
* why it is blocked
* what has already been completed
* what specific decision/input is required

## Git

Do not automatically push to a remote repository.

Do not create commits unless explicitly instructed by the user.

At major milestones, report:

```text
Recommended commit:
<commit message>

Recommended tag:
<tag>
```

The user controls final git add/commit/tag/push operations.

## Working Style

Be proactive.

Do not repeatedly ask:

> "Should I continue?"

Continue when the next step is clearly defined by `ROADMAP.md`.

Keep implementation focused on the current milestone.

Do not rewrite large portions of the project merely for stylistic reasons.

The objective is a working, tested, scientifically credible NiX ERT application—not merely a large amount of generated code.

## Completion

When all roadmap milestones are genuinely complete:

1. Run the complete test suite.
2. Perform a final architecture review.
3. Perform a final scientific validation review.
4. Review the UI and major workflows.
5. Review documentation.
6. Update `changelog.md`.
7. Produce a final implementation summary containing:

   * completed features
   * test results
   * scientific validation results
   * known limitations
   * remaining optional improvements
   * recommended release version

Do not claim the project is finished if important roadmap functionality is missing or unvalidated.
