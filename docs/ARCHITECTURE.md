# SDC Architecture (Frozen)

Status: **FROZEN — architecture v1**, amended 2026-09-24 by
[ADR-0016](ADR/0016-wasm-execution-substrate.md) (Wasm execution substrate)
and [ADR-0017](ADR/0017-policy-contract-and-capability-manifest.md) (policy
contract, capability manifest). Changing anything in this document requires a
superseding ADR ([ADR-0001](ADR/0001-record-architecture-decisions.md)).

> Humans and LLMs describe what the software means. SDC determines how that
> meaning becomes executable. The compiler, not the LLM, is the authority.

---

## 1. What SDC is

SDC (Semantic Definition Compiler) is a **specification compiler**. It turns a
set of human-readable, LLM-friendly Markdown files into one immutable,
content-addressed, signed **artifact**. A fixed, trusted **runtime** executes
that artifact only after it has proved the artifact is intact, compatible and
verified.

SDC is **not**:

- an AI code generator,
- a set of language backends,
- a template engine,
- an autonomous agent,
- a new programming language.

There is no generated source code anywhere in SDC. The artifact is a
declarative program in a closed, versioned vocabulary. The runtime is its
interpreter. The interpreter is a fixed WebAssembly component (`sdc-engine`)
running on Wasmtime inside a host that owns every capability. **SDC defines
the semantics; Wasm is only the execution substrate.** SDC never generates
Wasm per application.

## 2. The six things that must never be confused

| Term | Definition | Mutable? | Identity |
|---|---|---|---|
| **Source** | The project's Markdown files (the *Source Set*) | Yes (human/LLM edited) | `sourceHash` |
| **Semantic IR** | The typed meaning of the source, produced by the compiler | No (derived) | `irHash` (semantics), `traceHash` (source mapping) |
| **Artifact** | The compiled program: one canonical JSON document | **Never** | `artifactHash` |
| **Build** | One execution of the toolchain turning a source set into a release under a specific compiler, configuration and lock | — | `buildId` (deterministic), `invocationId` (per run) |
| **Release** | The artifact plus its materials (IR, trace), evidence, provenance statement and signatures, in one bundle | **Never** | `releaseDigest` |
| **Executable** | A runtime process (host + `sdc-engine` component) that executes one release | — | `executableId` = H(hostHash, engineHash, artifactHash); `executableHash` if packaged |

"Build" is a process and has no bytes of its own. Everything with bytes has a
hash.

## 3. System overview

```text
                 HUMAN / LLM
                      │   (edits Markdown; AI only via reviewed patches)
                      ▼
        ┌──── Source Set (*.md) ─────┐   UNTRUSTED INPUT
        │           sourceHash       │
        └────────────┬───────────────┘
 ═══════════════════ │ ══════════════ TRUST BOUNDARY: compiler TCB ═════
                     ▼
   Load → Parse → Bind/Validate → Normalize → Semantic IR ── irHash / traceHash
                     → Resolve → Analyze (facts, diagnostics)
                     → Plan (lower) → Emit
                     ▼
               ARTIFACT (canonical JSON) ── artifactHash
                     │
         ┌───────────┴────────────┐
         ▼                        ▼
   Verification               Provenance
   (obligations from IR,      (identity of every input,
    executed on the runtime)   compiler, config, lock, AI ledger)
         │ evidenceHash           │
         └───────────┬────────────┘
                     ▼
            Release policy decision
                     ▼
        Statement → DSSE Signature (Ed25519)
                     ▼
             RELEASE BUNDLE  ── releaseDigest
 ═══════════════════ │ ══════════════ TRUST BOUNDARY: runtime TCB ══════
                     ▼
   Host loader: signature → hashes (artifact, engine) → compatibility → policy
                     ▼
   Host: authentication, policy decision point, capability grants
                     ▼   (only granted sdc:runtime interfaces are linked)
   Wasmtime ─► sdc-engine component interprets the artifact
               (no filesystem, sockets, env, or secrets: INV-27, INV-29)
```

## 4. Pipeline

Every stage has one responsibility, a typed input and a typed output. No stage
may skip ahead. In particular, **nothing after "IR construction" reads
Markdown.** Full contracts are in [COMPILER.md](COMPILER.md).

| # | Stage | Input → Output | Pure? |
|---|---|---|---|
| 1 | Load | project dir → `SourceSet` | yes (reads files) |
| 2 | Parse | `SourceSet` → `DocumentTree` (Markdown CST with spans) | yes |
| 3 | Bind & validate | `DocumentTree` → `SectionStatements` + diagnostics | yes |
| 4 | Normalize | statements → canonical values + recorded defaults | yes |
| 5 | IR construction | → `SemanticIR` + `Trace` | yes |
| 6 | Resolve | symbolic references → ids; `sdc.lock` checked | yes |
| 7 | Analyze | IR → `Facts` (effects, consistency) + diagnostics | yes |
| 8 | Plan (+ optimize slot) | IR + Facts → `ArtifactModel` | yes |
| 9 | Emit | `ArtifactModel` → canonical bytes, `artifactHash` | yes |
| 10 | Verify | artifact + IR → `Evidence` | deterministic methods yes; measured no |
| 11 | Policy | Evidence + policy → decision | yes |
| 12 | Provenance | all identities → `Statement` | identity part yes |
| 13 | Sign | Statement → DSSE envelope | yes (Ed25519 is deterministic) |
| 14 | Release | → Release bundle | yes, given 10–13 |
| 15 | Package (optional) | release + runtime → container / zipapp | best-effort, see [BUILD-REPRODUCIBILITY.md](BUILD-REPRODUCIBILITY.md) |

Stages 1–9 form `sdc compile`. Stages 1–14 form `sdc build`.

## 5. Identity chain

```text
sourceHash ─┐
            ├─(compile, pure)─► irHash ──► artifactHash ──┐
compilerHash┤                   traceHash                 ├─► evidenceHash (= verificationId)
configHash  ┤                                              │      bound to runtimeHash, verifierHash
lockHash    ┘                                              ▼
                                   Statement{identity, verification, ai, metadata}
                                                           ▼
                                               DSSE signature(s) ─► Release (releaseDigest)
                                                           ▼
                                         executableId = H(hostHash, engineHash, artifactHash)
```

`artifactHash` covers the policy section (`policyHash`) and the capability
manifest (`capabilityHash`), so modifying either invalidates the artifact. The
engine component is runtime code shared by all applications. Its
`engineHash`, together with `hostHash`, is bound to the artifact only through
the signed statement and the evidence ([WASM-EVALUATION.md §4](WASM-EVALUATION.md#4-artifact-model)).

- The artifact embeds `irHash` but **not** `sourceHash`. A whitespace or
  comment edit changes `sourceHash` and `traceHash`, but not the artifact, so
  earlier evidence stays valid. The source-to-artifact link is recorded and
  signed in provenance. ([ADR-0007](ADR/0007-artifact-canonical-json.md))
- Evidence, provenance and signatures are *detached*. They reference the
  artifact by hash and are never part of it. ([ADR-0008](ADR/0008-detached-attestations-release-bundle.md))

## 6. Execution model

The compiler owns the execution model. The artifact is a **declarative
program** made of operations (`read-one`, `read-list`, `search`), the **SDC
Policy Contract** (authentication, authorization, data access, audit, network
and capability policy), entity schemas, outcome mappings, limits and
observability requirements. Each element carries the requirement ids it was
derived from.

The runtime implements a versioned *runtime contract*. It has two parts:

- the **host**: native code embedding Wasmtime. It is the security kernel:
  loader, trust, authentication, secrets, policy decision point, data-access
  scoping, log validation, and every capability;
- the **`sdc-engine` component**: a fixed Wasm component that interprets the
  artifact's vocabulary and imports only the SDC-owned WIT world
  `sdc:runtime@1.0.0`.

Authorization (who may do what) and capability security (what the program may
do at all) are compiled separately and enforced by the host
([POLICY.md](POLICY.md)).

There are no language backends and no per-app Wasm. The Python runtime of the
v1 freeze is the interim reference until the Wasm runtime passes the
identical conformance suite ([RUNTIME-CONFORMANCE.md](RUNTIME-CONFORMANCE.md)).
Decisions: [ADR-0006](ADR/0006-declarative-artifact-interpreted-runtime.md),
[ADR-0016](ADR/0016-wasm-execution-substrate.md). Details:
[RUNTIME.md](RUNTIME.md).

## 7. Trust model (summary)

| Trusted (TCB) | Untrusted |
|---|---|
| Compiler (stages 1–9) | Source files, *including human-authored ones* |
| Verifier + release-policy evaluator | LLMs, AI proposals, prompts |
| Signer + signing keys | External dependencies and services |
| Runtime host (loader, authentication, PDP, capabilities) | Any artifact **before** its signature and hashes verify |
| Wasmtime + Cranelift (pinned LTS) | Runtime inputs (requests, tokens, environment except secret values) |
| `sdc-engine` component: trusted for *correctness*, **not** for authority (confined to granted imports) | `.build/` cache contents; anything in a working directory |
| Runtime trust configuration (trusted keys, engine allowlist, capability ceiling) | Agent integrations and MCP clients; precompiled code not produced by this host |

Details: [SECURITY-MODEL.md](SECURITY-MODEL.md).

## 8. AI boundary (summary)

AI is an authoring assistant. It never runs inside `sdc compile` or
`sdc build`. It produces schema-constrained proposals, which are validated and
rendered into a Markdown patch. A human reviews and applies the patch, and the
compiler then parses it like any other source. Every applied proposal is
recorded in a committed ledger (provider, model, prompt / input / output
hashes). Provider failure behavior is an explicit policy: `FAIL` (the
default), `FALLBACK_LOCAL` or `FALLBACK_CACHED`. Details:
[AI-INTEGRATION.md](AI-INTEGRATION.md).

---

## 9. Architecture invariants

These are the testable truths of SDC. Every one of them has, or must get, an
automated test (see [ROADMAP.md](ROADMAP.md)).

**Meaning**

- **INV-01** The IR is a pure function of the source set and the language
  version. Configuration, environment, time, network and AI cannot influence
  it.
- **INV-02** Only the parser and the semantic binder read Markdown. Every later
  stage consumes the IR or its derivatives. Trace data is used for reporting
  and never for semantics.
- **INV-03** Compilation proceeds only when there are zero `ERROR`,
  `AMBIGUOUS` and `UNRESOLVED` diagnostics. Build profile (`dev` / `release`)
  never changes meaning.
- **INV-04** No default is applied silently. Every applied default is recorded
  in the IR with `origin: "default"` and its rule id. Security-relevant
  outcomes have no defaults.
- **INV-05** Every requirement has an id that is declared in source, unique in
  the project, and prefixed by its section.
- **INV-06** IR collection semantics are independent of order. The canonical
  order is by id.

**Form and identity**

- **INV-07** Every hashed structure uses the SDC canonical form: RFC 8785 (JCS)
  restricted to no floats, no `null`, ASCII keys and NFC strings. Every hash is
  `sha256:<hex>` over canonical bytes.
- **INV-08** The artifact contains no code in any language, and no secrets,
  fixtures, timestamps, absolute paths or host information.
- **INV-09** `artifactHash = sha256(artifact bytes)`. Non-canonical artifact
  bytes are rejected on load, so an artifact has exactly one byte
  representation.
- **INV-10** Compilation is pure. The same (`sourceHash`, `compilerHash`,
  `configHash`, `lockHash`) produces a byte-identical artifact. Any violation
  is a P0 compiler defect.

**AI**

- **INV-11** The compiler and verifier never invoke an AI provider and never
  use the network.
- **INV-12** AI output reaches the compiler only as a source change that goes
  through the same parser as human input. Every applied AI proposal is
  recorded in the ledger.
- **INV-13** Provenance records what actually happened (the provider, model
  and runtime actually used), never what was requested.

**Verification and release**

- **INV-14** Verification obligations are derived from the IR by the verifier,
  independently of the planner.
- **INV-15** Evidence is bound to (`artifactHash`, `runtimeHash`,
  `verifierHash`). Evidence for one artifact is never valid for another.
- **INV-16** A release bundle exists only if the release policy is satisfied. A
  critical requirement that is `FAIL`, `UNVERIFIED` or `BLOCKED` always blocks
  a release.
- **INV-17** The signature covers the provenance statement, which binds
  `artifactHash`, `evidenceHash`, `irHash`, `traceHash`, `sourceHash`,
  `compilerHash`, `configHash` and `lockHash`.

**Runtime**

- **INV-18** The production runtime executes a release only after it has
  verified the signature (by a key configured on the runtime side, never
  taken from the bundle), every hash, compatibility and policy. Any failure
  refuses execution. Production mode has no bypass.
- **INV-19** The runtime fails closed. Authorization defaults to deny. A
  missing claim, secret or capability is refused (per request or at startup).
  There is no silent fallback of stores or providers.
- **INV-20** The runtime does not depend on the toolchain. The toolchain
  depends on the runtime contract.
- **INV-21** Identity values in runtime telemetry come only from the verified
  release, never from the environment.
- **INV-22** Verify mode is structurally unusable for production. It forces the
  fixture store, loopback binding and ephemeral secrets, and refuses real
  secrets and stores.
- **INV-23** `.build/` is an untrusted cache. Trust decisions read only signed
  releases.

**Change**

- **INV-24** Semantic diff, impact classification and `explain` operate on IR
  nodes and derived effects keyed by requirement id, never on text.
- **INV-25** Configuration (`sdc.toml`) cannot change meaning. It selects
  profile, keys, waivers and AI policy only. Source-set membership is fixed by
  the language specification.

**Execution substrate** (added by ADR-0016 and ADR-0017)

- **INV-26** No executable code is produced per application. Every
  application on a given runtime release runs the same `sdc-engine`
  component. The per-application content is only the canonical artifact.
- **INV-27** The engine component's imports are exactly the `sdc:runtime`
  world. It imports no WASI filesystem, sockets, CLI, environment or process
  interface, and the host linker defines nothing else. This is checked
  statically from the component binary.
- **INV-28** Every effect the program performs uses a capability that is
  declared in source, validated by the compiler (`required ⊆ declared`),
  listed in the artifact capability manifest, and granted by the host.
  Anything else is absent or denied.
- **INV-29** Security enforcement (authentication, secrets, policy decisions,
  data-access scoping, `secret`-field removal, log validation) happens in the
  host. The engine holds no secrets and reaches data only through a
  host-issued, policy-scoped decision handle.
- **INV-30** Precompiled native code is never an identity, never
  distributed, and is loaded only from a host-private cache that the same
  host build and configuration produced.
- **INV-31** A runtime implementation replaces another only after passing the
  identical conformance suite and differential parity on every example.

---

## 10. Final repository structure

This is the target. It is reached incrementally ([ROADMAP.md](ROADMAP.md)),
without a big-bang move.

```text
SDC-Framework/
├── README.md  LICENSE  CHANGELOG.md  CONTRIBUTING.md  SECURITY.md  CODE_OF_CONDUCT.md
├── pyproject.toml                 # toolchain distribution (sdc) + interim Python runtime
├── Makefile
├── docs/
│   ├── ARCHITECTURE.md  SPECIFICATION.md  SEMANTIC-IR.md  COMPILER.md
│   ├── ARTIFACT.md  RUNTIME.md  VERIFICATION.md  SECURITY-MODEL.md
│   ├── BUILD-REPRODUCIBILITY.md  PROVENANCE.md  SEMANTIC-DIFF.md  AI-INTEGRATION.md
│   ├── POLICY.md  RUNTIME-CONFORMANCE.md  WASM-EVALUATION.md
│   ├── ASSESSMENT.md  ROADMAP.md
│   └── ADR/
├── schemas/                       # JSON Schema; the machine-checkable contracts
│   ├── ir/  artifact/  evidence/  provenance/  release/
│   ├── proposal/  ledger/  configuration/
├── runtime/                       # production runtime (Rust) — MUST NOT depend on the toolchain
│   ├── wit/                       # sdc:runtime@1.0.0 WIT world (the runtime contract as types)
│   ├── host/                      # Wasmtime embedding: loader, trust, authn, PDP, capabilities, store adapters
│   ├── engine/                    # sdc-engine: vocabulary interpreter → Wasm component (no WASI imports)
│   └── vectors/                   # canonical-form + hash test vectors shared with the Python contract
├── src/
│   ├── sdc_contract/              # canonical JSON, hashing, artifact/release models, DSSE (toolchain side)
│   ├── sdc_runtime/               # INTERIM Python reference runtime; removed from production at switch-over
│   └── sdc/                       # distribution "sdc" — the toolchain
│       ├── ir/                    # Semantic IR types, canonicalization, migrations
│       ├── compiler/
│       │   ├── source/  parser/  semantic/  resolve/  analysis/  planner/  emit/
│       │   └── diagnostics.py
│       ├── verification/
│       │   ├── obligations/  static/  dynamic/  measured/  evidence/  policy/
│       ├── build/                 # orchestration, provenance, signing, release, reproduce, packaging
│       ├── diff/                  # semantic + effect diff, classification
│       ├── explain/               # requirement lineage
│       ├── ai/
│       │   ├── providers/  prompts/  proposals/  render/  ledger/
│       └── cli/                   # init check compile build verify run diff inspect explain assist
├── tests/
│   ├── parser/ semantic/ analysis/ planner/ artifact/ runtime/
│   ├── conformance/               # runtime-agnostic suite (RUNTIME-CONFORMANCE.md) + hostile components
│   ├── verification/ security/ reproducibility/ semantic_diff/ explain/ ai/
│   ├── end_to_end/
│   └── golden/                    # source → IR → artifact golden files
├── examples/
│   ├── hello-world/  crud-api/  secure-api/  healthcare/
├── experiments/                   # isolated PoCs (E1–E6); never production architecture
├── tools/  scripts/
└── .github/workflows/             # test, double-build (artifact R1, engine R5), conformance
```

### Deliberate deviations from the requested layout

| Requested | Decision | Reason |
|---|---|---|
| Top-level `compiler/`, `verification/`, `ai/`, `cli/` | Under `src/sdc/…` | Top-level Python import names like `compiler` collide with other packages. The production runtime is a separate Rust tree, `runtime/`, installable **without** the toolchain (INV-20). |
| `compiler/codegen/` | `compiler/emit/` | There is no code generation. Emit means canonical serialization of the artifact. |
| `compiler/optimizer/` | An optional pass slot in `compiler/planner/` | v1 has no optimizations. Adding a stage because compilers usually have one is explicitly rejected. |
| `compiler/artifact/` | `sdc_contract/` (Python) + `runtime/vectors/` | The artifact model is shared by the compiler, verifier and runtime. The Rust host has its own implementation, checked against shared vectors. |
| `runtime/{loader,verifier,executor,sandbox,io,security}` + `runtime.py` | `runtime/{wit,host,engine}` | Under ADR-0016 the executor is the `sdc-engine` Wasm component; the sandbox is Wasmtime; the loader, security and io are the host. |
| `compiler/build/` | `sdc/build/` | A build orchestrates compilation, verification and signing. It is not a compiler stage. |
| `compiler/diff/` | `sdc/diff/` | The diff also compares releases and artifacts, not only sources. |
| `runtime/verifier/` | `sdc_runtime/loader/` | This avoids confusion with `verification/`. Loading *is* verification of integrity. |
| `verification/{contracts,invariants,api,behavior,security,performance,coverage,reports}` | `verification/{obligations,static,dynamic,measured,evidence,policy}` | Organised by *method*, not topic. Topic is a property of each obligation. Coverage is part of the evidence, and reports are CLI rendering. |
| `schemas/specification/` | Dropped | Markdown is not JSON. The grammar is normative in [SPECIFICATION.md](SPECIFICATION.md). |
| Top-level `spec/` holding 13 app files | Dropped | The framework is not an application. Applications live in `examples/*`. The per-section grammar lives in `SPECIFICATION.md`. |
| Root `sdc.toml` | Only in applications | Configuration belongs to a project, and the framework root is not a project. |
| `tests/semantic-diff` | `tests/semantic_diff` | Python packages cannot contain hyphens. |

No `backends/`, `plugins/`, `languages/` or `*-backend/` directories exist, and
none may be added without an ADR superseding ADR-0006.

---

## 11. Critical design test

**Scenario.** A developer creates `application.md`, `api.md`, `security.md`,
`data.md` and `behavior.md`, builds release R1, and deploys it. An LLM then
modifies `security.md`, the developer builds R2, and it is deployed.

| Question | How SDC answers | Mechanism |
|---|---|---|
| What changed? | `sdc diff R1 .` lists changed files (`sourceHash` per file) and **changed requirements by id** (`SEC-004 MODIFIED: property no-sensitive-logging → custom`) | Source set manifest; IR node diff ([SEMANTIC-DIFF.md](SEMANTIC-DIFF.md)) |
| Why did it change? | If the change came through `sdc assist`, the ledger entry names provider, model, prompt hash and proposal, and records whether the file still equals the accepted output. If the LLM edited the file directly, the change is reported as `UNATTRIBUTED`. Release policy can require attribution for critical sections. | AI ledger ([AI-INTEGRATION.md](AI-INTEGRATION.md)); VCS metadata in the statement |
| Which semantic entities changed? | Requirement ids, with before/after values from the IR | IR diff keyed by id |
| Which executable behavior is affected? | Artifact operations whose `derivedFrom` includes a changed id, plus any operation whose derived **effects** (permissions, exposure, authentication, outcomes) changed | Effect diff over analysis facts; artifact diff |
| Which security properties are affected? | Classification `SECURITY_IMPACT` with per-dimension levels, and the list of critical requirements touched | Classification table ([SEMANTIC-DIFF.md](SEMANTIC-DIFF.md#4-classification)) |
| Which tests must run? | Obligations of changed or effect-affected requirements (fast feedback). A **release always runs the full obligation set.** | Obligation index by requirement ([VERIFICATION.md](VERIFICATION.md)) |
| Is a rebuild mandatory? | Yes if and only if `irHash` changed (or the compiler, configuration or lock changed), because then `artifactHash` changes. A trace-only edit needs no new artifact, but it does need a new statement. | Artifact embeds `irHash`, not `sourceHash` |
| What artifact was produced? | `artifactHash` in R2's signed statement | [ARTIFACT.md](ARTIFACT.md) |
| What compiler produced it? | `compiler.version` + `compilerHash` (the hashes of the toolchain files, Python and Unicode versions) | [PROVENANCE.md](PROVENANCE.md) |
| What verification was performed? | Evidence `verificationId`: every obligation with its method, status and runtime/verifier identity, plus the policy decision | [VERIFICATION.md](VERIFICATION.md) |
| Can the artifact be trusted? | `sdc inspect --verify R2` or the runtime loader checks the signature by a trusted key, every hash, and that the policy decision is `RELEASABLE` | [SECURITY-MODEL.md](SECURITY-MODEL.md) |
| Can the executable be reproduced? | `sdc build --reproduce R2` recompiles from the source set with the recorded compiler, configuration and lock, and requires a byte-identical artifact and identical statement identity. The executable identity is `H(hostHash, engineHash, artifactHash)`. | [BUILD-REPRODUCIBILITY.md](BUILD-REPRODUCIBILITY.md) |
| Can the runtime prove the artifact was not modified? | Yes, for the artifact and release. The loader re-canonicalizes, re-hashes and verifies the signature before executing, and refuses on any mismatch. **Limit:** SDC cannot prove the integrity of the runtime binary or host it runs on. That requires platform attestation, which is out of scope ([ROADMAP.md](ROADMAP.md#risks-and-unresolved-decisions)). | [RUNTIME.md](RUNTIME.md#3-loading-and-verification) |

The execution-substrate design test (patient search: clinician-only
authorization, a declared DB capability, a denied filesystem, a tampered
engine or policy, an unverified security requirement) is worked in
[POLICY.md §7](POLICY.md#7-critical-design-test-patient-search).

All thirteen questions have a mechanism. Two have explicitly documented limits
(attribution of edits made outside SDC, and host integrity). Both are
reported rather than hidden, so the architecture is considered **frozen**.

---

## 12. Document map

| Document | Freezes |
|---|---|
| [SPECIFICATION.md](SPECIFICATION.md) | Source model, Markdown grammar, requirement ids, diagnostics |
| [SEMANTIC-IR.md](SEMANTIC-IR.md) | IR v1 types, canonical form, `irVersion`, hashing |
| [COMPILER.md](COMPILER.md) | Stage contracts, profiles, CLI |
| [ARTIFACT.md](ARTIFACT.md) | Artifact format v1, release bundle |
| [RUNTIME.md](RUNTIME.md) | Runtime contract, capabilities, loading, execution technology |
| [VERIFICATION.md](VERIFICATION.md) | Obligations, methods, statuses, release policy, evidence |
| [SECURITY-MODEL.md](SECURITY-MODEL.md) | TCB, trust boundaries, threats, keys |
| [BUILD-REPRODUCIBILITY.md](BUILD-REPRODUCIBILITY.md) | Reproducibility levels and inputs |
| [PROVENANCE.md](PROVENANCE.md) | Statement format and fields |
| [SEMANTIC-DIFF.md](SEMANTIC-DIFF.md) | Diff model, classes, impact |
| [AI-INTEGRATION.md](AI-INTEGRATION.md) | AI boundary, proposal flow, provider policy, ledger |
| [POLICY.md](POLICY.md) | SDC Policy Contract, capability model, `sdc:runtime` WIT world, OPA/Cedar decision |
| [RUNTIME-CONFORMANCE.md](RUNTIME-CONFORMANCE.md) | Runtime conformance suite and the Python → Wasm switch-over gate |
| [WASM-EVALUATION.md](WASM-EVALUATION.md) | Wasm substrate evaluation, decision, comparison, risks |
| [ASSESSMENT.md](ASSESSMENT.md) | Current state, defects, contradictions, mapping |
| [ROADMAP.md](ROADMAP.md) | Implementation phases, risks, unresolved decisions |
| [ADR/](ADR/README.md) | Irreversible decisions |
