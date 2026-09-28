# ADR-0004: Stable requirement ids are declared in source

- Status: Accepted
- Date: 2026-09-24

## Context

Traceability (`sdc explain SEC-014`), semantic diff and evidence all need a
stable identity for each requirement across edits.

- Ids derived from content change whenever the wording changes.
- Positional ids change whenever the file is reordered.
- The MVP used heuristic check names as ids and deduplicated by them, so
  distinct requirements were lost (D3).

## Decision

- Each requirement has an id of the form `PREFIX-NNN`, where the prefix is
  bound to its section. The id is **declared in source** (a table `ID` column
  or a heading `{#ID}`).
- Ids are unique within a project. A missing id is an `ERROR`.
- `sdc check --assign-ids` inserts missing ids deterministically, as a
  visible source edit.
- Ids survive renames and rewording. A deleted id is retired; enforcement of
  non-reuse is decision U3.
- Every downstream element (IR node, artifact element `derivedFrom`,
  obligation, evidence entry, diff change) refers to requirement ids.

## Consequences

- Full lineage is possible: source → IR → artifact → obligation → evidence →
  release.
- Runtime audit logs can cite the rule id behind each authorization decision.
- Authors, or `sdc assist`, must maintain ids. Diagnostics make this
  mechanical.

## Alternatives rejected

- *Content-hash ids*: unstable under edits.
- *Compiler-assigned hidden ids stored in a side file*: the side file becomes
  a second source of truth that humans do not review.
