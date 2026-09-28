# ADR-0008: Evidence, provenance and signature are detached and bound by hash in a release bundle

- Status: Accepted
- Date: 2026-09-24

## Context

Evidence is produced after the artifact, and a signature cannot be inside
what it signs. The MVP's manifest was unsigned, and its verification report
did not name the artifact it verified.

## Decision

- Evidence (`sdc.evidence/1`) names `artifactHash`, `runtimeHash` and
  `verifierHash`.
- The provenance statement (in-toto Statement v1 layout, predicate
  `urn:sdc:provenance:1`) has the artifact as its subject and binds `irHash`,
  `traceHash`, `sourceHash`, `evidenceHash`, `compilerHash`, `configHash` and
  `lockHash`.
- The statement is signed with Ed25519 in a DSSE envelope.
- The **release bundle** (`sdc.release/1`) is one canonical JSON file that
  contains the artifact, the materials (IR, trace), the evidence and the
  envelope. It is the only trusted build output.

## Consequences

- Re-verifying on a new runtime needs a new evidence document and statement,
  but no recompilation.
- Standard supply-chain tooling can read the statement.
- Deployed releases are self-describing for `explain`, `diff` and audit.

## Alternatives rejected

- *Signature embedded in the artifact*: circular.
- *Signing the artifact alone*: evidence and provenance would be unbound and
  forgeable.
- *Separate files in a directory*: an informal convention that is easy to
  mix up.
