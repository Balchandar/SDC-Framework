# Experiments

Code under `experiments/` is **never production architecture**. Experiments
exist to settle specific uncertainties behind an architecture decision. Each
experiment has a question, a method and an acceptance criterion. The result
is recorded in the relevant ADR. No production package may import from
`experiments/`, and code is promoted out of here only by rewriting it under a
frozen contract.

Status: **specified, not yet run.** No proof-of-concept was needed to *make*
the decision in [ADR-0016](../docs/ADR/0016-wasm-execution-substrate.md).
These experiments *gate* it (conditions C2, C4, C5).

| Id | Question | Method | Acceptance | Gates |
|---|---|---|---|---|
| **E1** | Can a Rust engine be packaged as a component whose imports are **exactly** the `sdc:runtime` world, with no WASI interfaces pulled in by `std`? | Build a stub engine for `wasm32-unknown-unknown` with `wit-bindgen`, then run `wasm-tools component new`. List the imports with `wasm-tools component wit`. Repeat with `wasm32-wasip2` for comparison | The import set equals the `sdc:runtime` interfaces exactly. A host linker with only those interfaces instantiates it, and a host with no definitions fails with an unknown-import error | C2 |
| **E2** | Is the engine component byte-reproducible? | Build twice with a pinned Rust toolchain, `Cargo.lock`, `wit-bindgen` and `wasm-tools` versions, `--remap-path-prefix` and `SOURCE_DATE_EPOCH`, in different directories, users and machines | Identical sha256 | C4 |
| **E3** | Can precompiled code be cached safely? | A host-private cache keyed by (engineHash, Wasmtime version, config hash), with permissions 0700 and an integrity check of the cache entry against a host-held HMAC | Tampered or foreign entries are rejected before `deserialize`, and a fresh compile happens | INV-30 |
| **E4** | What does per-request isolation cost? | A stub engine that does artifact load, parameter parsing and a response. Measure instantiate + call + drop with the pooling allocator versus a native build of the same engine crate. Also measure artifact reparse per instance vs. a host-provided pre-decoded form | p99 added overhead ≤ 1 ms per request, and startup (compile or cache load) ≤ 2 s, on the reference benchmark profile | C5 |
| **E5** | Does Cedar faithfully encode the contract-1 authorization semantics, and does `cedar-policy-symcc` prove the needed properties? | Translate POLICY.md §2.1 rules and conditions to Cedar plus a schema. Run differential tests against the reference PDP over randomized principals and resources. Try symbolic proofs of "only role X may do Y" | Zero disagreements in at least 10⁶ randomized cases, and a symbolic proof completes for the patient-search example | ADR-0017 oracle |
| **E6** | Is determinism achievable in verify mode? | Configure NaN canonicalization, relaxed SIMD off, a fixed memory maximum and fuel. Replay the conformance `DET-REPLAY` cases 100× across x86_64 and aarch64 | Byte-identical responses and capability traces | R3 on Wasm |

If **E1 or E2 fails**, ADR-0016 reverts to DEFER, and the Python runtime plus
OS sandboxing (the prior open decision U6) continues. If **E4 fails** the
thresholds, the instance-reuse strategy is revisited (U18) before any
decision to revert.
