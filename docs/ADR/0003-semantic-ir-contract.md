# ADR-0003: The Semantic IR is the sole compilation input: versioned, split into semantics and trace

- Status: Accepted
- Date: 2026-09-24

## Context

The IR is the truth model. The planner, the verifier, diff and explain all
depend on it, and releases persist it. The MVP IR was mutable and
stringly-typed, and it hashed prose, so wording changes altered `ir_hash`
(D6). It had no identities or spans, and two different version constants.

## Decision

- Every stage after IR construction consumes only the IR and its derivatives
  (INV-02).
- The IR is emitted as two documents: `ir.json` (meaning, `irHash`) and
  `trace.json` (source mapping and prose, `traceHash`).
- The IR carries a single `irVersion` (`MAJOR.MINOR`), a JSON Schema, frozen
  types, references by id, order-independent collections sorted by id,
  explicit default origins, and canonical form without floats or `null`.
- A MAJOR change requires a pure migration function. Tools reading older IR
  migrate it forward.

## Consequences

- `irHash` identifies meaning, so a trace-only change is detectable as
  `NON_SEMANTIC`.
- The IR schema becomes a public contract (it ships inside releases). That
  makes changes deliberate.

## Alternatives rejected

- *Hash source text as the identity*: conflates formatting with meaning.
- *A single IR document with trace inline*: prose would enter `irHash`.
- *Let stages read Markdown for convenience*: creates bypasses of the IR, and
  two readings of the source that can disagree.
