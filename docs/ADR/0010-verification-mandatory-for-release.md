# ADR-0010: Verification is mandatory for release, under the obligation model and release policy

- Status: Accepted
- Date: 2026-09-24

## Context

In the MVP, verification was independent (good), but security requirements
without a check were non-blocking (D15). The status model lacked `BLOCKED`,
the checks were not tied to requirements, and performance gating was
nondeterministic (D19).

## Decision

- Obligations are derived from the IR by the verifier, independently of the
  planner. Every requirement yields obligations, or an explicit `UNVERIFIED`
  record.
- Methods: `static` (over artifact data), `dynamic` (runtime in verify mode),
  `measured` (under a declared benchmark profile), and `attested` (reserved).
- Statuses: `PASS`, `FAIL`, `UNVERIFIED`, `BLOCKED`. Aggregation precedence
  is `FAIL` > `BLOCKED` > `UNVERIFIED` > `PASS`.
- Criticality: `critical` (every SEC, AUTHN and AUTHZ requirement, and
  sensitive or tenant data; cannot be lowered), `standard`, `advisory`.
- Release policy: a critical requirement that is not `PASS` always blocks.
  A `standard` requirement blocks unless it has an explicit waiver.
  `advisory` requirements are reported only.
- Releases always run the full obligation set, or reuse complete evidence for
  an identical artifact, runtime and verifier.

## Consequences

- A security requirement cannot ship unverified.
- Performance evidence counts only when measured in a declared environment.

## Alternatives rejected

- *Pass/fail only*: hides the difference between "checked and fine" and "not
  checked".
- *Diff-driven selective verification for releases*: a diff bug would weaken
  a release.
