# ADR-0007: The artifact is one canonical JSON document, content-addressed

- Status: Accepted
- Date: 2026-09-24

## Context

The artifact must be immutable, hashable, reproducible and tamper-evident,
and it must be defined exactly, not as a directory convention. The MVP's
artifact was a Python file in `dist/`, named after the checkout directory,
whose bytes differed from the verified file (D10, D18).

## Decision

- An artifact is exactly one JSON document conforming to
  `artifact-1.schema.json`, serialized in SDC canonical form: RFC 8785 JCS
  restricted to no floats, no `null`, ASCII keys and NFC strings.
- `artifactHash = sha256(bytes)`. The loader re-canonicalizes and rejects any
  input whose bytes differ.
- The artifact embeds `irHash`. It does **not** embed `sourceHash`,
  `compilerHash`, timestamps, paths, fixtures or secrets.
- Unknown fields are rejected ("must understand"). New fields come with a new
  capability in `requires`.

## Consequences

- One program has exactly one byte representation and one hash.
- Trace-only edits and compiler patches with identical output keep the same
  artifact, so earlier evidence stays reusable.
- The source → artifact link is carried by the signed provenance statement,
  not by the artifact.

## Alternatives rejected

- *Tar/zip bundle*: needs its own canonicalization (mtimes, ordering,
  compression) for no gain.
- *CBOR / protobuf*: less reviewable, and determinism rules are still needed.
- *Embedding `sourceHash`*: any whitespace edit would force re-verification
  of an unchanged program.
