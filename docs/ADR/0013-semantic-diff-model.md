# ADR-0013: Semantic diff runs over IR nodes and effects, keyed by requirement id

- Status: Accepted
- Date: 2026-09-24

## Context

The MVP had two overlapping diffs ("drift" and "semantic diff") at section
granularity. There were no compatibility classes, and the baseline was the
mutable last local build. Text diffs cannot show that a role rename removes
access for every existing user.

## Decision

- One subsystem, `sdc/diff`, with two layers:
  - the **node diff** (IR nodes keyed by id: `ADDED`, `REMOVED`, `MODIFIED`,
    `TRACE_ONLY`);
  - the **effect diff** (permission matrix, exposure, authentication and
    outcome maps from analysis).
- Each change gets one compatibility class (`NON_SEMANTIC`, `NON_BREAKING`,
  `POTENTIALLY_BREAKING`, `BREAKING`) and impact flags (`SECURITY_IMPACT`,
  `PERFORMANCE_IMPACT`, `DATA_MIGRATION_REQUIRED`), from a versioned
  classification table. An unmatched change is `POTENTIALLY_BREAKING`, never
  silently `NON_BREAKING`.
- Per-dimension impact levels are reported, together with `rebuild` (iff
  `irHash` changed) and the affected obligations.
- The baseline is always explicit: a directory or a release bundle.

## Consequences

- Reviewers see what a change does to access, exposure and contracts.
- The diff drives feedback-time test selection, but never weakens release
  verification.

## Alternatives rejected

- *Text/AST diff of Markdown*: not semantic.
- *Section-level change flags*: too coarse to classify impact.
