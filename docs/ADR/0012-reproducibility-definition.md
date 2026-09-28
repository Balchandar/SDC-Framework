# ADR-0012: Reproducibility is defined as a byte-identical artifact from declared inputs

- Status: Accepted. The `executableId` formula is refined by
  [ADR-0016](0016-wasm-execution-substrate.md) to `H(hostHash, engineHash, artifactHash)`,
  and R5/R6 are added. Nothing is weakened
- Date: 2026-09-24

## Context

The MVP claimed binary reproducibility, but its output depended on the
installed runtime source, the directory name and an unsigned manifest. Its
`build_id` omitted configuration and provider, and was truncated to 64 bits.

## Decision

- Declared build inputs: `sourceHash`, `compilerHash` (the hashes of the
  toolchain files, Python major/minor and Unicode version), `configHash`,
  `lockHash`.
- `buildId = sha256(JCS({sourceHash, compilerHash, configHash, lockHash}))`,
  full length.
- Mandatory levels:
  - **R0**: same source + compiler version ⇒ same `irHash`.
  - **R1**: same declared inputs ⇒ byte-identical artifact.
  - **R2**: identical statement identity.
  - **R3**: identical static and dynamic verification outcomes.
- Best effort: **R4**, byte-identical packaging. Canonical executable
  identity is `executableId = H(runtimeHash, artifactHash)`.
- Statement `metadata` (time, host, invocation) is excluded from all
  comparisons.
- `sdc build --reproduce` checks R0–R2 (and R3 on request). CI runs it for
  every release candidate.

## Consequences

- A compiler that reads the clock, the environment or filesystem order is
  defective by definition.
- Container images are not the identity of an executable. `executableId` is.

## Alternatives rejected

- *Byte-reproducible container images as the definition*: registries
  recompress layers, so that is outside SDC's control.
- *Semantic reproducibility only*: too weak to detect a substituted compiler.
