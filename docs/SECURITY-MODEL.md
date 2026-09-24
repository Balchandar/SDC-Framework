# Security Model

Status: **FROZEN.** Governing ADRs:
[ADR-0008](ADR/0008-detached-attestations-release-bundle.md),
[ADR-0009](ADR/0009-runtime-executes-only-verified-releases.md),
[ADR-0011](ADR/0011-ai-outside-the-build.md),
[ADR-0015](ADR/0015-capability-based-runtime.md).

---

## 1. Trusted computing base

| Component | Why it must be trusted | How trust is earned |
|---|---|---|
| Compiler (stages 1–9) | It decides meaning and emits the program | Deterministic; golden tests; reproducible (a rebuild detects a substituted compiler); `compilerHash` signed |
| Verifier + policy evaluator | It decides whether a program may be released | Independent of the planner; `verifierHash` recorded; obligations are listed, never summarized away |
| Signer + release keys | A signature is the root of runtime trust | Keys held outside the repository (CI secret / KMS); dev keys cannot pass production trust |
| Runtime (loader, interpreter, capabilities) | It executes and enforces | Conformance suite; `runtimeHash` recorded in evidence; small, with no app-specific code |
| Runtime trust configuration | It defines which signers are trusted | Deployed by operators, not shipped in releases |
| The host platform (OS, Python, hardware) | It runs all of the above | **Assumed.** Out of SDC's scope (see §6) |

Everything else is untrusted.

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
 B3 ════════════════════════════════╪══ runtime loader: signature, hashes, compat, policy
                                    │  Runtime interpreter
 Requests, tokens, env values       │
 B4 ════════════════════════════════╪══ runtime inputs: authn, authz, limits
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
- Logs redact every field marked sensitive, and the `log/1` capability
  enforces this, not the artifact.

## 6. Out of scope (stated, not hidden)

- The integrity of the host, OS, Python interpreter and runtime installation.
  Remote attestation (TPM/TEE) is a future extension.
- The correctness of external services (the IdP issuing tokens, the database).
- Denial of service beyond the per-process limits.
- The judgment of human reviewers approving source changes.
