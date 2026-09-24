# Security Model

Status: **FROZEN.** Governing ADRs:
[ADR-0008](ADR/0008-detached-attestations-release-bundle.md),
[ADR-0009](ADR/0009-runtime-executes-only-verified-releases.md),
[ADR-0011](ADR/0011-ai-outside-the-build.md),
[ADR-0015](ADR/0015-capability-based-runtime.md),
[ADR-0016](ADR/0016-wasm-execution-substrate.md),
[ADR-0017](ADR/0017-policy-contract-and-capability-manifest.md).

> **Amendment (2026-09-24).** The runtime is split into a **host** (the
> security kernel) and the **`sdc-engine` Wasm component** (confined
> interpreter). The TCB, boundaries and threats below are updated
> accordingly.

---

## 1. Trusted computing base

| Component | Why it must be trusted | How trust is earned |
|---|---|---|
| Compiler (stages 1–9) | It decides meaning and emits the program | Deterministic; golden tests; reproducible (a rebuild detects a substituted compiler); `compilerHash` signed |
| Verifier + policy evaluator | It decides whether a program may be released | Independent of the planner; `verifierHash` recorded; obligations are listed, never summarized away |
| Signer + release keys | A signature is the root of runtime trust | Keys held outside the repository (CI secret / KMS); dev keys cannot pass production trust |
| Runtime **host** (loader, trust, authentication, secrets, PDP, capability implementations, store adapters, log validation) | It is the security kernel: every enforcement decision is made here (INV-29) | Conformance suite; `hostHash` in evidence; kept small and stable; no app-specific code |
| **Wasmtime + Cranelift** (pinned LTS) | It enforces engine confinement; a JIT defect could break it | An upstream security process with guaranteed backports to supported releases; fixed configuration (`hostConfigHash`); version in `runtimeHash` |
| Runtime trust configuration | It defines trusted signers, the **engine allowlist** and the **capability ceiling** | Deployed by operators, not shipped in releases |
| The host platform (OS, hardware) | It runs all of the above | **Assumed.** Out of SDC's scope (see §6) |

Trusted for **correctness, but not for authority**:

| Component | Meaning |
|---|---|
| `sdc-engine` component | Its defects can produce wrong *behavior* within the program's grants (caught by dynamic verification), but it cannot exceed its grants. It has no secrets, no filesystem, no sockets, and it reaches data only through host-issued decision handles |

Verification-time dependencies (not in the runtime TCB):

| Component | Effect of a defect |
|---|---|
| Cedar (policy oracle) | A false disagreement produces `FAIL` and an investigation. A false agreement requires an identical runtime defect as well |
| `wasmparser` / `wasm-tools` (import inspection) | A missed import would be caught by the host linker at load anyway (defense in depth) |

Everything else is untrusted, including: source Markdown, LLMs, AI proposals,
agent integrations and MCP clients, external dependencies, the artifact and
the engine component **before** their hashes and signature verify, requests,
and any precompiled code the host did not produce itself.

## 2. Trust boundaries

```text
 UNTRUSTED                          │ TRUSTED
────────────────────────────────────┼──────────────────────────────────────
 Source files (human- or LLM-written)│
 AI providers, prompts, proposals ──┼─► only as reviewed source patches
 sdc.toml (config)                  │  (cannot change meaning, INV-25)
 .build/ cache, dist/ before verify │
                                    │  Compiler → artifact
 B1 ════════════════════════════════╪══ source enters compiler: parsed as hostile input
                                    │  Verifier (runs artifact in verify-mode sandbox)
                                    │  Signer
 B2 ════════════════════════════════╪══ release leaves build: signed statement
 Release in transit / at rest       │
 B3 ════════════════════════════════╪══ host loader: signature, hashes (artifact + engine), compat, policy
                                    │  Host (security kernel)
 Requests, tokens, env values       │
 B4 ════════════════════════════════╪══ runtime inputs: authn, authz, limits (host)
                                    │
 B6 ════════════════════════════════╪══ host ⇄ engine: only sdc:runtime WIT calls; decision handles
                                    │  sdc-engine (Wasm): confined interpreter
 External services (DB, IdP)        │
 B5 ════════════════════════════════╪══ dependency responses: typed, bounded
```

| Boundary | What crosses it | Enforcement |
|---|---|---|
| B1 source → compiler | Markdown bytes | Size/count limits; no symlinks; a strict grammar; no code execution; no includes; no network |
| B2 build → world | Release bundle | DSSE signature over a statement binding every hash |
| B3 world → runtime | Release bundle | The loader chain ([RUNTIME.md §3](RUNTIME.md#3-loading-and-verification)); keys from runtime config only |
| B4 client → runtime | HTTP requests | JWT verification, default-deny policy, request limits, and outcome mapping that never leaks internals |
| B5 dependency → runtime | Store responses | Parameterized queries; typed projection; unavailability becomes the `unavailable` outcome |
| B6 host ⇄ engine | Typed WIT values and resource handles | The engine can call only linked `sdc:runtime` interfaces. Arguments are validated by the host against the artifact (operation ids, requirement ids, criteria). Data flows only through decision handles. `secret` fields never cross. Per-instance memory and CPU limits apply |

**The artifact before verification is untrusted data.** The verifier runs it
only in `verify` mode, which uses loopback, the fixture store, ephemeral
secrets and the sandbox. Human-written source is untrusted too. SDC's
guarantees do not depend on who wrote the Markdown.

## 3. Threats and mitigations

| Threat | Mitigation | Residual |
|---|---|---|
| Artifact modified after build | Hash + signature checked at load (INV-18) | None within scope |
| Release swapped for an older signed one (rollback) | Optional `min-version` per application in the trust config | Needs operator configuration |
| Evidence forged or detached from its artifact | Evidence hash inside the signed statement; evidence names `artifactHash` | — |
| Compiler substituted or tampered | `compilerHash` in the statement; independent reproduction (`--reproduce`) | Requires someone to reproduce |
| LLM injects weakened security into `security.md` | Semantic diff flags `SECURITY_IMPACT`; AI ledger attribution; `require-attribution` policy; human review | A human approves a bad change |
| Prompt injection through source content into `sdc assist` | Proposals are schema-constrained data; never executed; rendered to a patch for review; never auto-applied to critical sections | Reviewer fatigue |
| Ambiguous prose silently becomes behavior | Normative-prose rule; no heuristics in the compiler (INV-03) | — |
| Missing security requirement goes unnoticed | Critical `UNVERIFIED` blocks release | — |
| Forged token when the secret is unset (D7) | Runtime refuses to start without a non-empty secret; the length is checked | — |
| Privilege by default (D14) | A missing claim is `unauthenticated`; default deny | — |
| Cross-tenant existence oracle (D16) | `deniedAs` outcome; analysis warning | Opt-in to `forbidden` remains possible |
| Silent downgrade (DB → in-memory, model → local) | No fallback in the runtime; AI policy defaults to `FAIL` | — |
| Telemetry spoofing (D13) | Identity comes from the release only | — |
| Malicious Markdown exhausting the compiler | Stage 1 limits; linear-time parser; no regex backtracking on unbounded input | — |
| Secret leakage through artifact or provenance | The artifact holds secret names only; provenance stores hashes of AI config, never keys | — |
| Engine compromised by crafted input (memory corruption inside Wasm) | Confinement: no filesystem, sockets or secrets; data only with host decisions; fresh instance per request | The attacker can return wrong-but-authorized data for *that* request only |
| Engine binary tampered or substituted | `engineHash` checked against the statement **and** the trust-config allowlist before instantiation | — |
| Engine gains an unintended import (build/tooling mistake) | Static import check by the verifier; the host linker defines only `sdc:runtime` (unknown import → refuse) | — |
| Precompiled code injection (`deserialize` of foreign bytes executes arbitrary code) | INV-30: host-private cache only, integrity-checked; never from a release, the network or a shared path | — |
| Wasmtime / Cranelift defect (sandbox escape, miscompilation) | LTS pinning with guaranteed security backports; OS-level defense-in-depth profile on the host process; conformance on every bump | Residual: an upstream zero-day |
| Capability over-grant slipped in by an LLM edit to `dependencies.md` | Capability rows are critical; semantic diff flags `SECURITY_IMPACT`; operator capability ceiling; attribution policy | A human approves it |
| Modified policy | The policy is inside the artifact, so the hash fails (`REFUSE_INTEGRITY`); `policyHash` in the statement | — |
| Agent / MCP client submits requests or source edits | Treated like any other untrusted client (B4) or author (B1). SDC grants no special trust to agent tooling | — |

## 4. Keys and signatures

- The algorithm is Ed25519 inside a DSSE envelope. Verification needs one
  vetted dependency, `cryptography` ([ADR-0014](ADR/0014-implementation-language-and-packaging.md)).
- `keyid = sha256(raw public key)`.
- Three key classes:
  - `dev`: generated locally per machine, stored in the user's config
    directory, and never accepted in production mode.
  - `release`: held by CI or a KMS and referenced from `sdc.toml` as
    `env:` or `file:`. The key is never in the repository.
  - `attestation`: reserved for human attestations.
- The runtime trust config lists accepted `keyid`s. Optionally it restricts a
  key to specific application names.
- Revocation is done by removing a key from the trust config. Transparency
  logs and keyless signing (Sigstore) are an open decision
  ([ROADMAP.md](ROADMAP.md#risks-and-unresolved-decisions)).

## 5. Secrets policy

- Sources, IR, artifacts, evidence and provenance never contain secret values.
- The artifact declares secret **names**. The runtime obtains values from its
  secret source, and a missing value refuses startup.
- AI provider keys are read from the environment by `sdc assist` only. Only
  `configurationHash` is recorded; the key is not.
- Logs never contain `personal` or `secret` values (only closed-vocabulary fields), and the `log/1` capability
  enforces this, not the artifact.

## 6. Out of scope (stated, not hidden)

- The integrity of the host, OS, Python interpreter and runtime installation.
  Remote attestation (TPM/TEE) is a future extension.
- The correctness of external services (the IdP issuing tokens, the database).
- Denial of service beyond the per-process limits.
- The judgment of human reviewers approving source changes.
