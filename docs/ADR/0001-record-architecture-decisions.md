# ADR-0001: Record architecture decisions; freeze semantics

- Status: Accepted
- Date: 2026-09-24

## Context

The MVP's architecture existed only in code and in prose that had drifted
from the code (see [ASSESSMENT.md](../ASSESSMENT.md) §4). SDC's value depends
on stable contracts: the IR, the artifact, the runtime contract and the
statement format. Contracts that change silently are not contracts.

## Decision

1. Irreversible or expensive decisions are recorded as numbered ADRs in
   `docs/ADR/`.
2. The documents in `docs/` marked **FROZEN** are normative. Changing a frozen
   statement requires a new ADR that supersedes the relevant one. The
   superseded ADR stays in the repository with status `Superseded by
   ADR-NNNN`.
3. Code that contradicts a frozen document is a defect in the code, unless an
   ADR says otherwise.
4. Every invariant in [ARCHITECTURE.md §9](../ARCHITECTURE.md#9-architecture-invariants)
   must have at least one automated test by the end of the roadmap phase that
   implements it.

## Consequences

- Architecture changes are slower and visible, which is intended.
- Reviewers can reject a change by citing an invariant or an ADR.

## Alternatives rejected

- *Architecture in a wiki or issues*: not versioned with the code.
- *Code as the only source of truth*: that is exactly how the MVP's documents
  and behavior drifted apart.
