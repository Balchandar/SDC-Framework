# ADR-0014: Python is the reference implementation; the runtime is separable; `cryptography` is allowed

- Status: Accepted. The runtime-language clause is superseded by
  [ADR-0016](0016-wasm-execution-substrate.md): the production runtime is a Rust
  host plus a Wasm engine component, and the Python runtime is the interim
  reference. The toolchain clauses are unchanged
- Date: 2026-09-24

## Context

The MVP is Python, stdlib-only, with seven "packages" that share one
`pyproject.toml`. Production hosts should not need the compiler. Signatures
need Ed25519, which the standard library does not provide.

## Decision

- The toolchain and the reference runtime are Python (≥3.11). This is an
  implementation detail of SDC and never visible in artifacts.
- Two import roots in one repository, `src/sdc` (the toolchain) and
  `src/sdc_runtime` (the runtime), eventually published as two distributions.
  **`sdc_runtime` must not import `sdc`** (INV-20). The shared artifact
  contract lives in `sdc_runtime.contract`.
- The core stays stdlib-only, **except** for `cryptography` (pinned and
  hash-locked), which is allowed for signing and verification.
- Optional extras: AI provider SDKs (toolchain only) and the SQL driver
  (runtime `store.sql` capability).

## Consequences

- The runtime can be audited and deployed alone.
- Timing of the distribution split is decision U11. The dependency direction
  is enforced by an import-linter test from Phase 3.

## Alternatives rejected

- *A pure-Python Ed25519*: not constant-time; unacceptable for signing.
- *HMAC signatures*: symmetric keys cannot separate the signer from the
  verifier.
- *Rewriting in another language now*: no architectural benefit before the
  contracts are implemented.
