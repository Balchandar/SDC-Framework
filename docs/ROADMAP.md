# Implementation Roadmap

Status: **Plan of record after the architecture freeze.** The phases are
ordered by dependency. A phase is done only when its exit criteria are
automated tests in CI.

Amended 2026-09-24 by [ADR-0016](ADR/0016-wasm-execution-substrate.md) and
[ADR-0017](ADR/0017-policy-contract-and-capability-manifest.md): Phase 5 now
starts with the runtime-agnostic conformance suite; Phase W (experiments) is
added; Phase 11 becomes the Wasm execution substrate with a switch-over gate.

Guiding rule: **no feature is implemented before its contract is frozen**
(the frozen documents are the contracts). The MVP stays runnable until
Phase 6 reaches parity; then the legacy packages are deleted in one change.

---

## Phase 0: Quarantine the MVP (small, immediate)

The MVP is not the architecture, but people may run `sdc init` and deploy
what it produces. So the defects that are exploitable today are fixed first,
and nothing else.

- [x] README banner: MVP = legacy prototype; link to this freeze.
- [ ] Runtime refuses to start with an empty or short `SDC_JWT_SECRET` (D7).
- [ ] A missing `role` claim is denied instead of defaulting to `user` (D14).
- [ ] The manifest records the provider actually used (D9).
- [ ] Turn the probes in `scripts/assessment_probe.py` ([ASSESSMENT.md §3](ASSESSMENT.md#3-verified-defects))
      into regression tests under `tests/legacy/`.

Exit: the probes for D7, D9 and D14 pass as tests. The other defects are
fixed by construction in later phases and need no MVP patch.

## Phase 1: Specification model

*Depends on: freeze.* Contract: [SPECIFICATION.md](SPECIFICATION.md).

- Source-set loader with `sourceHash`, limits and the membership rule.
- Markdown CST parser with spans (extend `markdown.py`: blockquotes, heading
  attributes, line/column).
- Section binder and grammar for all 13 sections; the normative-prose rule.
- Diagnostics model and codes; `sdc check`; `sdc check --assign-ids`.
- Rewrite `examples/customer-api` as `examples/secure-api` in sdc/1; add
  `hello-world`.

Exit: golden tests (source → diagnostics) for every grammar production. The
negative tests reproduce D1–D4 and now produce `ERROR` or `UNRESOLVED`. The
compiler contains no keyword heuristics.

## Phase 2: Semantic IR

*Depends on: 1.* Contract: [SEMANTIC-IR.md](SEMANTIC-IR.md).

- Frozen IR types; `ir-1.schema.json`; a CI check that the schema and the
  types agree.
- Canonical-form enforcement (no floats, no `null`, ASCII keys, NFC).
- Normalization and defaults with origin recording; IR construction plus
  trace; resolution; `irHash` and `traceHash`.
- Analysis: effect model plus consistency rules (port `validate.py`).
- `sdc inspect` (IR view).

Exit: golden IR per example. Property tests: shuffling files, rows or
whitespace, or rewording prose, leaves `irHash` unchanged (fixes D6).
Changing any declared value changes `irHash`.

## Phase 3: Artifact model

*Depends on: 2.* Contract: [ARTIFACT.md §1](ARTIFACT.md#1-the-artifact).

- `sdc_runtime/contract`: canonical JSON, hashing, artifact model, schema.
- Planner (lowering) and emitter; `sdc compile`.
- Loader steps 1, 3 (hash only) and 4 in `sdc_runtime` (no signatures yet).

Exit: golden artifacts. **R1 double-build test in CI** (different directory,
`TZ`, user). The loader rejects non-canonical and schema-invalid artifacts.

## Phase 4: Compiler lifecycle

*Depends on: 3.* Contract: [COMPILER.md](COMPILER.md).

- Stage orchestration with isolation (stages receive only their declared
  inputs); `.build/` layout; exit codes; profiles.
- `sdc.toml` parsing; `configHash`; `sdc.lock` and `sdc lock`.

Exit: a stage-isolation test (a stage given a `DocumentTree` after stage 5
fails the build). A malicious-source corpus (size, depth, symlinks, pathological
tables) completes within its limits.

## Phase 5: Conformance suite + Python reference runtime (verify mode)

*Depends on: 3.* Contracts: [RUNTIME.md](RUNTIME.md),
[RUNTIME-CONFORMANCE.md](RUNTIME-CONFORMANCE.md), [POLICY.md](POLICY.md).

Needed before verification, because dynamic verification executes artifacts.

- **5a. Conformance suite first.** Runtime-agnostic, driven only through the
  adapter protocol (process, HTTP, capability trace). This suite is the
  authority for every later runtime.
- **5b. Python reference runtime.** Split `runtime.py` into capabilities.
  Interpreter for `read-one`, `read-list` and `search`. Host-style separation
  *inside* Python (authentication, PDP and store scoping in a "host" layer; the
  interpreter layer receives only principals and decision objects), so its
  behavior matches the Wasm split. Capability trace emission.
- Fixes by construction: D7, D13, D14, D16. No seed or identity environment
  hooks.
- `verify` mode (fixture store, loopback, ephemeral secrets).

Exit: the Python runtime passes every applicable conformance test
(`CAP-DENY-*` are `N/A-substrate`). `verify` mode refuses a real store,
external secrets and a non-loopback bind.

## Phase W: Wasm substrate experiments (parallel with phases 1–6)

*Depends on: freeze.* Specification: [experiments/README.md](../experiments/README.md).

- E1 import-set minimality, E2 engine reproducibility, E3 precompiled-cache
  safety, E4 per-request cost, E5 Cedar fidelity and symbolic proofs, E6
  cross-platform determinism.
- The code lives in `experiments/` only.

Exit: results recorded in ADR-0016 and ADR-0017. **If E1 or E2 fails,
ADR-0016 reverts to DEFER**, and Phase 11 falls back to "Python runtime + OS
sandbox" (the former U6).

## Phase 6: Verification and evidence

*(Amended: adds the capability obligations, the capability-trace
assertions and the Cedar policy oracle, [VERIFICATION.md §9](VERIFICATION.md#9-execution-substrate-verification).)*

*Depends on: 2, 3, 5.* Contract: [VERIFICATION.md](VERIFICATION.md).

- Obligation derivation from the IR. Static checks over the artifact. A
  dynamic harness (port `harness.py`, `behavioral.py` and the dynamic parts
  of `security.py`). Measured obligations with benchmark profiles.
- Evidence document; release-policy evaluation; waivers; `sdc verify`.
- **Parity point: delete `sdc_codegen`, `sdc_compiler`, `sdc_parser` and
  `sdc_verifier`**, and move the CLI to the new pipeline.

Exit: every requirement in the examples has an obligation or an explicit
`UNVERIFIED`. A critical `UNVERIFIED` blocks (D15). A mutation test (flip one
artifact rule) makes verification FAIL.

## Phase 7: Provenance

*Depends on: 6.* Contract: [PROVENANCE.md](PROVENANCE.md).

- Statement builder with `identity`, `verification` and `metadata`;
  `compilerHash`; `buildId`.

Exit: the statement identity is byte-identical across two builds (R2). Every
identity field is recomputable by an independent script.

## Phase 8: Integrity and signing

*Depends on: 7.* Contract: [ARTIFACT.md §2](ARTIFACT.md#2-release-bundle),
[SECURITY-MODEL.md](SECURITY-MODEL.md).

- DSSE + Ed25519 (`cryptography`); key classes; `sdc build` produces the
  release bundle.
- Runtime loader steps 2 and 5, production mode, trust config; `sdc run`
  through the loader (fixes D17).
- `sdc inspect --verify`.

Exit: tamper suite. Flipping any byte of the release makes the runtime refuse
with the right reason (fixes D10 and D11). Dev releases are refused in
production mode. A key missing from the trust config is refused.

## Phase 9: Reproducible builds

*Depends on: 8.* Contract: [BUILD-REPRODUCIBILITY.md](BUILD-REPRODUCIBILITY.md).

- `sdc build --reproduce`; a CI job that reproduces every release candidate;
  deterministic container packaging (R4, best effort); `executableId`.

Exit: `--reproduce` reports `REPRODUCED` in CI for every example. A deliberate
non-determinism injection makes the CI job fail.

## Phase 10: Semantic diff and explain

*Depends on: 2 (7 for release inputs).* Contract: [SEMANTIC-DIFF.md](SEMANTIC-DIFF.md).

- Node diff, effect diff, classification table, impact report; `sdc diff`;
  `sdc explain`; IR migration hooks for older releases.

Exit: a golden diff for every row of the classification table. The
Role:User→Clinician scenario in `examples/healthcare` produces the documented
output.

## Phase 11: Wasm execution substrate and switch-over

*Depends on: 5, 8, W (E1, E2 and E4 accepted).* Contracts: [RUNTIME.md](RUNTIME.md),
[POLICY.md §4.4](POLICY.md#44-the-sdcruntime100-wit-world-shape),
[ADR-0016](ADR/0016-wasm-execution-substrate.md).

- **11a. Freeze the WIT text** of `sdc:runtime@1.0.0` by ADR (the shape is
  already frozen in POLICY.md).
- **11b. `sdc-engine` component** (Rust, `runtime/engine/`): the vocabulary
  interpreter, with no WASI imports. R5 double build in runtime CI. Static
  import check in CI.
- **11c. Host** (Rust, `runtime/host/`): Wasmtime embedding with the fixed
  configuration (RUNTIME §12.2); loader and trust (including `engineHash`
  allowlist); authentication; PDP; store adapters (fixture, SQL); log
  validation; capability trace; limits (memory limiter, fuel/epoch,
  concurrency, body size, graceful shutdown); host-private precompiled cache
  (INV-30); canonical-form implementation checked against the shared vectors.
- **11d. Parity.** The identical conformance suite passes, including
  `CAP-DENY-*` with hostile components. There is differential parity with the
  Python runtime on every example and on the fuzzed artifact corpus
  (VERIFICATION §9.4). Performance meets the declared targets.
- **11e. Switch-over** (the gate in RUNTIME-CONFORMANCE §5): production mode
  exists only on the Wasm runtime. Existing releases are **re-verified** (new
  evidence and statement), never recompiled. The Python runtime's production
  mode is removed. Keeping it as a verify-mode oracle is decision U13.
- The OS-level defense-in-depth profile (RUNTIME §13) is emitted for
  `Packaging: container`.

Exit: switch-over gate satisfied on one commit, and ADR-0016's status is
updated to *Accepted (conditions met)*.

## Phase 12: CLI completion

*Depends on: 4–10.*

- `init` (sdc/1 scaffold), consistent human and JSON output, exit codes,
  documentation.

## Phase 13: AI integration

*Depends on: 1, 2 (proposal validation needs the IR), 10 (attribution in
diffs).* Contract: [AI-INTEGRATION.md](AI-INTEGRATION.md).

- Proposal schema, validation, deterministic rendering, ledger, provider
  policy, the local proposer (the MVP heuristics moved here), `sdc assist`.

Exit: `FAIL` is the default and is tested with an unreachable provider. The
fallbacks are recorded. Proposal rendering is deterministic. Attribution
appears in `sdc diff` and in provenance.

### Dependency graph

```text
0
1 → 2 → 3 → 4
        3 → 5 → 6 → 7 → 8 → 9
        2 ──────→ 6
        2 → 10 (release inputs after 7)
        3 → 5 ────────────────→ 11 ← W (E1, E2, E4)
                            8 → 11
   4..10 → 12
   1,2,10 → 13
```

---

## Risks and unresolved decisions

### Risks

| # | Risk | Likelihood / impact | Mitigation |
|---|---|---|---|
| K1 | **Expressiveness ceiling.** A closed vocabulary (read-one, read-list, rule conditions) cannot express real business logic. Pressure grows to add "just a little" computation until SDC becomes a programming language by accident | High / High | Every vocabulary extension requires an ADR. If computation is unavoidable, admit only a **total, side-effect-free expression sublanguage** (CEL-like: no loops, no recursion, bounded), evaluated by the runtime and never Turing-complete. Write operations (create, update, delete, with transactions and validation) are the next vocabulary step and need their own freeze |
| K2 | **Authoring friction.** A controlled grammar feels less natural than free prose, and users may resist it | Medium / Medium | Prose stays allowed everywhere. `sdc assist structure` converts prose to structure. Diagnostics carry concrete hints. Tables are LLM-friendly by nature |
| K3 | **Common-mode verification failure.** Obligations come from the same IR the compiler produced. A parser misreading passes verification | Medium / High | Author-declared `testing.md` cases with `Verifies`; mandatory review of the semantic diff; a grammar small enough to test exhaustively; golden tests |
| K4 | **Normative-prose rule is noisy** (for example the word "only") | Medium / Low | Blockquote escape hatch; tune the keyword list within sdc/1.x (a minor change, since it only adds or removes diagnostics) |
| K5 | **Runtime performance** versus declared latency targets | Medium / Medium | Measured evidence tells the truth. The Wasm runtime (ADR-0016) is expected to be faster, but that is unmeasured (E4) |
| K6 | **TCB size**: the Python interpreter and `cryptography` are inside the TCB | Low / High | Pin and hash them; recorded in `runtimeHash` and `compilerHash` |
| K7 | **Store equivalence**: verification uses `store.fixture`, production uses `store.sql` | Medium / Medium | Store capability conformance tests run against both, including an optional real Postgres in CI |
| K8 | **Migration effort** from the MVP | Certain / Medium | Phased; the MVP stays runnable until Phase 6 parity |
| K9 | **Component Model tooling churn** (wit-bindgen, wasm-tools, WASI 0.3 async) | Medium / Medium | Import no WASI; SDC-owned WIT; pin tool versions in the runtime lock; E1/E2 |
| K10 | **Host is the security kernel**: all enforcement concentrates in one component | Certain / High | Keep it small; conformance per interface; OS defense-in-depth profile; review policy for host changes |
| K11 | **Wasmtime/Cranelift defect or zero-day** | Low / High | LTS pinning with guaranteed security backports; `runtimeHash` exact match forces re-verification on upgrade; OS profile |
| K12 | **Debuggability** (DWARF is Tier 3 and unmaintained in Wasmtime) | Certain / Medium | Capability trace; Wasm backtraces; native test builds of the engine crate |
| K13 | **Two policy semantics** (the SDC contract vs. the Cedar oracle) drift | Medium / Medium | The contract is authoritative; oracle disagreement is `FAIL`; E5 fidelity test in CI |
| K14 | **Two implementation languages** (Python toolchain, Rust runtime) | Certain / Medium | Shared test vectors for canonical form and hashes; the boundary is the artifact format, which is already language-neutral |

### Unresolved decisions (explicitly *not* frozen)

| # | Decision | Constraint already frozen | Decide by |
|---|---|---|---|
| U1 | The expression sublanguage (if any): CEL subset vs. a bespoke one | Must be total, side-effect-free, and sit inside the artifact as data (ADR-0006) | Before write operations |
| U2 | Key management: local keys vs. KMS vs. Sigstore keyless plus a transparency log | DSSE + Ed25519; trust keys come from runtime config (ADR-0008, ADR-0009) | Phase 8 |
| U3 | Requirement-id retirement enforcement (preventing reuse after deletion) | Ids declared in source, never auto-assigned silently (ADR-0004) | Phase 10 (diff has the history) |
| U4 | Whether missing attribution of critical-section changes **blocks** a release or only reports | Attribution is recorded (ADR-0011) | Phase 13 |
| U5 | Data migrations: SDC flags `DATA_MIGRATION_REQUIRED` but produces no migration artifact | The artifact stays declarative | After write operations |
| ~~U6~~ | ~~Sandbox enforcement technology~~ | **Resolved for the primary layer by ADR-0016** (Wasm confinement). The OS defense-in-depth technology remains a deployment choice | — |
| U7 | Waiver expiry (a time-dependent policy) | Waivers are recorded in the statement; the artifact is unaffected | Phase 6 |
| U8 | Rollback protection defaults (`min-version` in the trust config) | The runtime trust config owns it | Phase 8 |
| U9 | Multi-service systems (several artifacts that call each other) | One process runs one release; no outbound calls in contract 1 | After v1 |
| U10 | Host and runtime attestation (TPM/TEE) so the runtime itself can be proven | Out of scope, and stated so ([SECURITY-MODEL.md §6](SECURITY-MODEL.md#6-out-of-scope-stated-not-hidden)) | Future |
| U11 | Distribution split: one wheel first, or `sdc` + `sdc-runtime` from day one | The dependency direction is frozen (INV-20); the production runtime is a separate Rust tree | Phase 3 |
| U12 | Wasmtime upgrade policy: which LTS, and when to move to the next | Only supported LTS releases (ADR-0016 C7) | Phase 11c |
| U13 | Keep the Python runtime after switch-over as a verify-mode differential oracle, or retire it completely | It is never a production runtime after switch-over | Phase 11e |
| U14 | Composed per-app component (engine ∘ artifact) as an optional packaging form | Never an identity; a derived packaging attestation only | After Phase 11 |
| U15 | Cedar as the runtime PDP (rather than the oracle only) | Requires an ADR and an E5-proven equivalent translation; tied to U1 | With U1 |
| U16 | Production timeout mechanism: epoch only, or epoch plus a fuel ceiling | Verify mode uses fuel (determinism) | Phase 11c |
| U17 | Adopt `wasi:http` for inbound requests instead of the SDC `handler` export | The engine must still import no other WASI interface | Phase 11a |
| U18 | Instance-per-request vs. pooled instance reuse, and artifact decoding per instance vs. a pre-decoded host form | Isolation between requests must be preserved | E4 results |
| U19 | WASI 0.3 / Component Model async for host calls | Not required by contract 1 | After Phase 11 |
| U20 | Host implementation language (Rust assumed as Wasmtime's primary API) | The host must embed Wasmtime with component support and pass conformance | Phase 11c |
