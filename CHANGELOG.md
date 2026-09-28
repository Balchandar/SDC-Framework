# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Wasm execution substrate & policy architecture (2026-09-24)

- **Decision: ADOPT WASM WITH CONDITIONS** ([ADR-0016](docs/ADR/0016-wasm-execution-substrate.md)).
  The runtime becomes a Rust host that embeds Wasmtime and runs one fixed
  `sdc-engine` component, which interprets the canonical artifact as data.
  There is no per-application Wasm and no generated code. The canonical
  artifact remains the only semantic identity. The decision is gated by
  experiments E1–E6 (`experiments/README.md`).
- **SDC Policy Contract and capability manifest**
  ([ADR-0017](docs/ADR/0017-policy-contract-and-capability-manifest.md),
  `docs/POLICY.md`). Authorization and capability security are compiled
  separately and enforced by the host. Cedar is adopted as an independent
  verification oracle; OPA is not selected; no engine is hard-coded.
- Pre-implementation amendments: sdc/1 (the `search` operation,
  `Classification` replacing `Sensitive`, the Capabilities table), IR 1.0,
  `sdc.artifact/1` (`policy` and `capabilities` sections), runtime contract 1
  (host/engine split, fixed Wasmtime configuration), provenance (engine, host,
  policy and capability hashes), reproducibility (R5/R6), verification (§9).
- New invariants INV-26 to INV-31. New documents: `WASM-EVALUATION.md`,
  `POLICY.md`, `RUNTIME-CONFORMANCE.md`. Roadmap: conformance suite first,
  Phase W experiments, Phase 11 switch-over gate.
- Status notes added to ADR-0006 (the WASM rejection refined) and ADR-0014
  (runtime language superseded). No code changed.

### Architecture freeze (2026-09-24)

- Froze architecture v1: the source language `sdc/1`, Semantic IR 1.0,
  `sdc.artifact/1`, `sdc.release/1`, `sdc.evidence/1`, the
  `sdc.provenance/1` statement and runtime contract 1.
  See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- Added ADR-0001 to ADR-0015 (`docs/ADR/`).
- Added the assessment of the MVP, with 19 documented defects and a
  reproduction script (`scripts/assessment_probe.py`).
- Added the dependency-ordered implementation roadmap.
- Removed documents superseded by the freeze: root `ARCHITECTURE.md` and the
  lowercase `docs/*.md` files. The lowercase files would also have collided
  with the uppercase deliverables on case-insensitive filesystems.
- The `packages/` MVP is now designated **legacy**. No code behavior changed
  in this entry.

## [0.1.0]

- MVP: Markdown → Application IR → Python stdlib service, with verification
  and a manifest.
