# WebAssembly Execution Substrate: Evaluation

Status: **Decision record input for [ADR-0016](ADR/0016-wasm-execution-substrate.md)
and [ADR-0017](ADR/0017-policy-contract-and-capability-manifest.md).**
Date: 2026-09-24. Baseline: architecture v1 freeze (commit `6aa1af1`).

This document evaluates whether SDC's trusted runtime should execute on
WebAssembly, using the Wasm Component Model and Wasmtime, instead of a custom
Python runtime. The evaluation is made against the already-frozen SDC
requirements, not against Wasm's general merits.

---

## 1. Decision

> **ADOPT WASM WITH CONDITIONS.**
>
> WebAssembly components on Wasmtime become the production execution
> substrate of the SDC runtime. They run **one fixed, app-independent SDC
> engine component** that interprets the canonical SDC artifact as data,
> inside a host that owns every capability. SDC does **not** generate Wasm
> per application.

The conditions are binding. If any condition cannot be met, the decision
reverts to **DEFER** (Python reference runtime plus OS-level sandboxing):

| # | Condition | How it is checked |
|---|---|---|
| C1 | No per-application Wasm, and no generated source in any language. The canonical JSON artifact stays the sole semantic identity | INV-26; code review; the release format has no per-app binary |
| C2 | The engine component imports exactly the `sdc:runtime` WIT world, and nothing from `wasi:filesystem`, `wasi:sockets`, `wasi:cli` or any other interface | Static import check (verifier + host), INV-27; experiment **E1** |
| C3 | All security enforcement (authentication, secrets, policy decisions, data-access scoping, log redaction) lives in the host. The engine cannot reach data without a host-issued, policy-scoped handle | INV-29; conformance suite `CAP-*` |
| C4 | The engine component builds byte-reproducibly from pinned sources and toolchain | Experiment **E2**; runtime CI double build (R5) |
| C5 | Per-request isolation overhead fits within the declared performance budgets | Experiment **E4** acceptance thresholds |
| C6 | The Wasm runtime replaces the Python runtime only after passing the **identical** conformance suite plus differential evidence on every example | [RUNTIME-CONFORMANCE.md](RUNTIME-CONFORMANCE.md) switch-over gate |
| C7 | Wasmtime is pinned to a supported LTS release, and the host never loads precompiled code it did not produce itself | INV-30; lock file |

Experiments are specified in [`experiments/README.md`](../experiments/README.md).
They are isolated, and none of their code becomes production architecture
automatically.

### Why not the other outcomes

- **ADOPT (unconditionally)**: several load-bearing assumptions are not yet
  demonstrated in *this* design (E1, E2, E4). Adopting without gates would
  freeze on belief.
- **DEFER**: the frozen v1 left runtime isolation as an open decision (U6,
  "sandbox enforcement technology") and admitted that SDC cannot prove "no
  filesystem access" in-process for a Python runtime. Deferring leaves the
  critical design test (§9) only partly provable by the SDC verifier:
  filesystem denial would depend on deployment configuration SDC cannot
  inspect.
- **REJECT**: the reasons ADR-0006 gave for rejecting Wasm apply to Wasm *as
  the artifact format* (per-app generated code). Those reasons still hold and
  are kept (§3). They do not apply to Wasm *as the substrate* for a fixed
  interpreter.

**Correction to the v1 freeze.** ADR-0006 said Wasm was unnecessary because
"there is no untrusted code to isolate". That was incomplete. The runtime's
own complex, evolving code (request parsing, the vocabulary interpreter,
response rendering) processes untrusted input and is the likeliest place for
defects. Confining *that* code, with only typed capabilities as its authority,
is the value Wasm adds.

---

## 2. The critical question

> *Can SDC's declarative artifact be represented as a WebAssembly Component
> without turning SDC into a conventional programming-language compiler?*

**Yes, and the correct representation is not a compiled component per
application.** There are three ways to put an SDC application into Wasm:

| Option | Pipeline | Verdict |
|---|---|---|
| **W1: Generate code, then compile it** | IR → generated Rust/C → rustc/clang → `.wasm` | **Rejected.** This is exactly the "Markdown → Rust" architecture forbidden by the freeze. It reintroduces language backends, puts generated code in the TCB, and makes artifact reproducibility depend on an external compiler per app. No compelling reason exists |
| **W2: Emit Wasm directly** | IR → SDC emits Wasm instructions per app | **Rejected.** SDC would become an instruction-level compiler with its own code generator, register allocation and ABI lowering. That is a conventional compiler in all but name. The artifact becomes opaque bytecode, and static verification over declarative data (VERIFICATION.md §3) is lost |
| **W3: Fixed engine + artifact as data** | IR → canonical artifact (unchanged). A fixed `sdc-engine` component, built once per runtime release by SDC maintainers, loads the artifact bytes through a WIT interface and interprets them | **Adopted** |

Under W3:

- The SDC compiler is **unchanged**. It still emits the canonical artifact
  and never emits Wasm (INV-26).
- The engine component is **runtime code**, just as the Python runtime is
  today. It is written by hand, reviewed, versioned and conformance-tested.
  It is the same bytes for every application.
- "Wasm component per app" exists only as an *optional packaging form*
  (§4, model A′). It is derived, never an identity.

SDC therefore stays a semantic compiler whose output is a constrained,
declarative executable representation. Wasm is the *substrate* that runs the
interpreter of that representation. It is not the representation itself.

---

## 3. Current runtime vs. Wasm + Wasmtime

"Current" means the Python runtime as frozen in v1: one process holding
ambient OS authority, with isolation delegated to an undecided OS sandbox (U6).
"Wasm" means design W3: a Rust host embedding Wasmtime, plus the `sdc-engine`
component.

| Dimension | Python runtime (v1 freeze) | Wasm + Wasmtime (W3) | Evidence / basis |
|---|---|---|---|
| **Security surface** | CPython plus runtime code, all with ambient authority. A defect anywhere reaches the OS | Host (Rust, small capability kernel) plus Wasmtime/Cranelift in the TCB for authority. Engine defects are confined to linear memory and granted imports | Wasmtime security doc: "the only thing a WebAssembly instance can do is what is available through interfaces it has been explicitly linked with" |
| **Sandboxing** | External: containers, seccomp and so on, chosen per deployment and not inspectable by SDC | Intrinsic: memory isolation, no raw syscalls, type-checked control flow; plus defense in depth (2 GB guard regions, stack guard pages, memory zeroing, Spectre mitigations) | Wasmtime `docs/security.md` |
| **Capability isolation** | Convention only. Any module may `open()` a file | **Structural.** An interface that is not imported cannot be called; an import the host does not define fails instantiation. Provable from the binary's import list | Component Model semantics; C2/E1 |
| **Determinism** | Python has hash randomization, float formatting and thread scheduling. Achievable with care, but hard to prove | Core Wasm "mostly deterministic", with documented closures: NaN canonicalization, deterministic relaxed-SIMD, bounded memory growth, fuel-based interruption | Wasmtime "Deterministic Wasm Execution" doc |
| **Portability** | Needs a CPython of a matching version on the host | The engine is the same bytes on every platform. The host is a native binary per platform. Tier 1 targets: x86_64 Linux/macOS/Windows. aarch64 has Cranelift component-model support | Wasmtime `stability-tiers.md` |
| **Performance** | Interpreted Python, with a GIL limiting parallelism | Native code via Cranelift. Costs: per-request instantiation and canonical-ABI copying at the boundary. **Unmeasured for SDC** | Experiment E4 (C5) |
| **Startup time** | Python import time | Cranelift compilation of the engine at startup, or a host-owned precompiled cache (INV-30) | E4 |
| **Memory model** | A shared heap. The frozen contract's "request-local state" is enforced only by discipline | Instance-per-request: each request's state lives in a fresh linear memory, and cross-request leakage is impossible without a Wasmtime defect. Memory is capped per instance by a resource limiter | Wasmtime `Store::limiter`; memory zeroing (security doc) |
| **Filesystem** | Available to all code; denial depends on the deployment | Not imported by the engine; the host defines no filesystem interface. **Denial is provable** | C2, INV-27 |
| **Networking** | Available to all code | The engine has no sockets. Inbound HTTP is terminated by the host; outbound exists only as host capabilities (the store driver) | INV-27, INV-29 |
| **Database access** | The Python driver runs inside the runtime | The host runs the driver natively. The engine uses the `sdc:runtime/store` interface through policy-scoped resource handles. There is **no standard WASI SQL interface**: `wasi-sql` is listed as unsupported by Wasmtime, so SDC owns this interface (a feature: it stays semantic, never raw SQL) | Wasmtime tiers: `wasi-sql` "not supported" |
| **Secrets** | In process memory, reachable by any code | **Never enter the engine.** JWT keys and DB credentials are consumed by host capabilities | INV-29 |
| **Concurrency** | Threads plus the GIL | Host async; one engine instance per request; the engine is single-threaded (the Wasm `threads` proposal is only Tier 2 and is not used) | Wasmtime tiers |
| **Observability** | In-process logging | Host-side logging with closed-vocabulary fields; the engine can only emit declared field keys; the host attaches release identity | ADR-0017 |
| **Debugging** | Mature (pdb, tracebacks) | **Weaker.** DWARF debugging is Tier 3, "no active maintainer", with "known shortcomings and bugs". Mitigations: Wasm-level backtraces, host capability trace, native unit tests of the engine crate | Wasmtime tiers footnote |
| **Reproducibility** | Unaffected for artifacts. The runtime is identified by file hashes | Unaffected for artifacts (W3 generates no Wasm). The engine is one reproducible build per runtime release (R5, E2). Precompiled native code is never an identity | BUILD-REPRODUCIBILITY §3 |
| **Artifact integrity** | The loader checks hashes and signature | Same loader, in the host. The engine hash is also verified against the trust config and the signed statement | ARTIFACT §2 |
| **Supply-chain security** | CPython plus pinned wheels | Wasmtime: a monthly major release; **every 12th release is LTS, supported 24 months; security fixes are guaranteed to be backported to all supported releases**. Plus Cargo-locked host dependencies | Wasmtime `stability-release.md` |
| **Runtime maturity** | The SDC runtime is new code either way | Component Model is **Tier 1** in Wasmtime. WASI 0.2 is stable; WASI 0.3 is "the current preview" (async). SDC depends on the Component Model, not on WASI | Wasmtime tiers; WASI README |
| **Operational complexity** | One language (Python) everywhere | **Two languages**: a Python toolchain and a Rust runtime. Deployment gets simpler, though: one static host binary plus the engine plus the release file, with no Python environment | — |
| **Enterprise adoption** | Not a decision criterion. Adoption claims are marketing; the LTS and security-backport policy above is the substantive evidence | — | — |
| **Long-term maintenance** | SDC owns the whole stack, including an undecided sandbox | SDC owns the host kernel, the engine and the WIT contract; Wasmtime maintains the VM, JIT and sandbox. Risk: WIT tooling churn (§8) | — |

**Net assessment.** Wasm is better on the properties the frozen architecture
cares most about: capability isolation, provable denial, secret confinement,
determinism controls, a supply-chain security process, and closing U6. It is
worse on debugging and adds a second implementation language. Performance is
likely better but unmeasured, which is why it is condition C5.

---

## 4. Artifact model

Two models were requested for evaluation. A third variant is noted.

### Model A: per-app Wasm as the production artifact

```text
Release = { manifest, semantic artifact, Wasm component (per app), capability manifest,
            policy bundle, evidence, provenance, signature }
```

- There are two representations of one program: the semantic artifact, and a
  Wasm binary derived from it. Which one is authoritative? If the Wasm, then
  meaning lives in opaque bytecode and the IR/artifact is documentation. If
  the semantic artifact, the Wasm needs a proven derivation, which means a
  code generator (W1/W2, rejected).
- Result: **`artifactHash ≠ wasmHash` with only an asserted relationship.**
  This violates "exactly one authoritative semantic identity".
- **Rejected.**

### Model A′: composed per-app component, as packaging only

The engine component composed with a tiny data component that exports the
artifact bytes, giving one `.wasm` per app. The relationship is explicit:
`packageHash = H(compose_vN(engineHash, artifactHash))`, and it is
deterministic only if the composition tool is pinned and deterministic.

- Allowed later as a **packaging form**, like a container image, recorded in
  provenance as derived. **Never an identity and never trusted by itself**:
  the runtime still verifies `engineHash` and `artifactHash` separately.
- **Deferred** (U14).

### Model B: canonical artifact is the sole identity; the engine is runtime (ADOPTED)

```text
                    ┌──────────────── Release bundle (sdc.release/1) ──────────────┐
                    │ artifact     canonical JSON: program + policy + capabilities │ artifactHash
                    │ materials    ir.json, trace.json                              │ irHash, traceHash
                    │ evidence     sdc.evidence/1                                   │ evidenceHash
                    │ envelope     DSSE(statement) — Ed25519                        │ signature
                    └──────────────────────────────────────────────────────────────┘
                                           │ statement names
                                           ▼
   Runtime distribution:  host binary (hostHash)  +  sdc-engine.wasm (engineHash)
                          runtimeHash = H({host, engine, wasmtime, hostConfig})
```

| Object | Definition | Identity | Authoritative for |
|---|---|---|---|
| **SDC Artifact** | Canonical JSON (`sdc.artifact/1`) containing the operations, the **policy** section (the SDC Policy Contract) and the **capabilities** section (the capability manifest) | `artifactHash` | **The program's meaning. The only semantic identity** |
| **Policy Bundle** | The `policy` section of the artifact. It is not a separate file; derived engine encodings such as Cedar are verification materials only (ADR-0017) | `policyHash = H(JCS(artifact.policy))`, a sub-hash for audit | Authorization, authentication, data-access, audit and network policy |
| **Capability Manifest** | The `capabilities` section of the artifact | `capabilityHash = H(JCS(artifact.capabilities))`, a sub-hash | What the host may grant |
| **Wasm Component** | `sdc-engine`, the fixed interpreter of `sdc.artifact/1`, identical for every application | `engineHash = sha256(component bytes)` | Executing the vocabulary (never meaning) |
| **Manifest** | There is **no separate manifest file**. The release manifest *is* the provenance statement's `identity` section, so the same facts are never stored twice | (part of `statementHash`) | — |
| **Provenance** | The in-toto statement ([PROVENANCE.md](PROVENANCE.md)) binding every hash above plus the compiler, config, lock and engine | `statementHash` | "Where did this come from" |
| **Signature** | DSSE Ed25519 over the canonical statement | `keyid` | Integrity and origin |
| **Release Bundle** | The single file combining artifact, materials, evidence and envelope | `releaseDigest` | Distribution unit |

Why the sub-hashes are sub-hashes and not independent identities: the policy
and capability manifest are *parts of the program*. A policy separated from
its operations has no meaning. Keeping them inside the artifact means that
modifying the policy *is* modifying the artifact, and it fails
`REFUSE_INTEGRITY` with no extra mechanism. The sub-hashes exist so that
`sdc diff`, audits and the statement can show *which part* changed.

### Identity chain (final)

```text
Source ─► sourceHash
  │ compile (pure; compilerHash, configHash, lockHash)
  ▼
Semantic IR ─► irHash (+ traceHash)
  │ lower
  ▼
SDC Artifact ─► artifactHash      ⊃ policyHash, capabilityHash
  │ executed by (not compiled into)
  ▼
Engine component ─► engineHash    (one per runtime release, reproducible: R5)
Host binary      ─► hostHash
  │
  ▼
executableId = H({ host: hostHash, engine: engineHash, artifact: artifactHash })
  │
  ▼
Statement (identity + verification + ai + metadata) ─► DSSE signature
```

**The signed statement must contain:** `sourceHash`, `irHash`, `traceHash`,
`artifactHash`, `policyHash`, `capabilityHash`, `compilerHash`, `configHash`,
`lockHash`, `engineHash`, `hostHash`, the Wasmtime version, `evidenceHash`,
and `verifier.hash`.

With those, the runtime can prove the chain the requirements ask for: this
Wasm (`engineHash`, checked at load) executed this SDC artifact (`artifactHash`,
recomputed at load), which came from this IR (`irHash`, embedded in the
artifact and in the statement), which came from this source (`sourceHash`)
and was produced by this compiler (`compilerHash`). The source → IR →
artifact step is *reproducible* by anyone (`sdc build --reproduce`), so the
chain is checkable as well as asserted.

---

## 5. Capability model (summary)

Full contract: [POLICY.md §4](POLICY.md#4-capability-model).

```text
source: dependencies.md "Capabilities" table          (declared, reviewed)
   ↓  compiler: required(program) ⊆ declared, else ERROR SDC-R030
artifact.capabilities                                  (signed, inside artifactHash)
   ↓  host loader: grant set = manifest ∩ runtime trust-config ceiling
host linker: defines only granted sdc:runtime interfaces; everything else absent
   ↓
engine instance: can call only what was linked; data only through
                 policy-scoped resource handles
```

The Component Model is an appropriate abstraction, for three reasons:

1. **Imports are the complete authority of a component.** An interface that
   is not imported cannot be invoked, and an import the host does not define
   is an instantiation error. This is "everything not granted is denied",
   enforced by the runtime rather than by convention.
2. **WIT resources are unforgeable handles.** A `store` reader can be
   obtained only from a host-issued `decision`, which gives SDC
   object-capability scoping ("this request may read `Patient` rows of tenant
   T, projected to fields F") at the type level.
3. **WIT is a typed, versioned interface contract** (`sdc:runtime@1.0.0`).
   The runtime contract becomes machine-checkable at the boundary.

What the Component Model does **not** provide, and SDC therefore defines
itself: an SQL or database interface (none standard; `wasi-sql` is
unsupported), a policy interface, and closed-vocabulary logging. These are
SDC WIT interfaces implemented by the host. SDC deliberately imports **no**
WASI interfaces into the engine. That avoids WASI 0.2 → 0.3 churn and keeps
the engine's authority minimal.

---

## 6. Declarative vocabulary: what SDC can and cannot express

Wasm must not become an excuse for arbitrary computation. Wasm can run
anything; SDC artifacts still express only the closed vocabulary below.

| Concept | Definition in SDC | Examples (sdc/1) | Who implements it |
|---|---|---|---|
| **Primitive** | An operation kind with fixed, specified semantics | `read-one`, `read-list`, `search` | Engine (interpreter) |
| **Composition** | A *fixed* per-operation pipeline. Authors cannot sequence or combine operations | authenticate → validate → authorize → access → project → respond → audit | Engine + host |
| **Capability** | A typed, host-provided interface granting one class of effect, declared in source and scoped by the manifest | `store` (read), `log`, `metrics`, `http.inbound` | Host |
| **Expression** | A closed, total, side-effect-free predicate form. No variables, loops, recursion or user functions | Authorization conditions (`same-tenant`, `attr-contains(...)`), search matches (`exact`, `prefix-ci`) | Host (policy decisions) / engine (matching via host query) |
| **Side effect** | Any interaction beyond the instance. **Only** through capability calls, all enumerated in the manifest | Reading rows, emitting a log record, incrementing a metric | Host |

**SDC cannot express:** arbitrary algorithms, loops, user-defined functions,
free-form SQL, calls to undeclared services, background jobs or schedules,
multi-step workflows, stateful sessions, file I/O, or "custom code" escape
hatches, including "drop in your own Wasm component". The last is the
specific temptation Wasm creates, and it is **rejected** for v1 (ADR-0016).
A user-supplied component would be untrusted code with no semantic
specification: it could not be verified from the IR or explained by
`sdc explain`.

**How the vocabulary grows without becoming a language:**

1. A new primitive or capability requires an ADR, a grammar change (sdc/1.x),
   an artifact capability tag, engine plus host support, and conformance
   tests.
2. If richer *conditions* are needed (authorization attributes, validation
   rules), the preferred path is to adopt an existing **bounded, analyzable
   expression semantics** (Cedar's condition language: purpose-built,
   terminating, formally modelled in Lean) as the *meaning* of those
   conditions, rather than invent an SDC expression language (ADR-0017;
   resolves the direction of U1).
3. Turing-complete computation is out of scope for SDC. A need for it is a
   signal that the requirement belongs outside SDC.

---

## 7. Verification with Wasm (summary)

Full changes: [VERIFICATION.md §9](VERIFICATION.md#9-execution-substrate-verification).
The independence rule is unchanged: obligations are derived from the IR, and
the verifier trusts neither the compiler nor the engine.

| Layer | What the verifier inspects independently |
|---|---|
| Artifact | Static checks over data, as in v1, now including the policy and capability sections recomputed from the IR |
| Capabilities | `required(IR) ⊆ declared(IR) == artifact.capabilities`; explicit denials have no grant |
| Wasm component | `engineHash` is in the trust-config allowlist; its **import list equals the `sdc:runtime` world** (no filesystem, sockets, CLI or environment); its exports equal the handler interface |
| Policy | The permission matrix is tested dynamically on the runtime, **and** cross-checked against an independent oracle: the verifier's own translation of the IR policy into Cedar, evaluated by Cedar |
| Runtime behavior | Dynamic obligations in verify mode, with a host capability trace. Every store, log and metrics call is recorded, and assertions run over the trace (e.g. no log field outside the vocabulary; every store access carries a decision) |
| Security invariants | Host properties (deny unlinked imports, secret confinement, handle scoping, integrity refusal) are proved **once per runtime release** by the conformance suite, and cited by `runtimeHash` in the evidence |
| Performance | Measured on the Wasm runtime under a declared benchmark profile |

---

## 8. Risks

| Area | Risk | Severity | Mitigation |
|---|---|---|---|
| Wasm limitations | No threads in the engine (Tier 2, unused); 32-bit linear memory; boundary copying | Low | Instance-per-request needs no threads; request and response sizes are bounded by `limits` |
| Component Model maturity | Tier 1 in Wasmtime, but the tooling (wit-bindgen, wasm-tools, cargo-component) is pre-1.0 and churns. WASI 0.3 changes async | Medium | Depend only on the Component Model and SDC-owned WIT; import **no** WASI; pin the tool versions in the runtime lock; E1/E2 |
| Host interface complexity | The `sdc:runtime` WIT world is a new public contract, and mistakes are expensive | Medium | Keep it minimal (6 interfaces); version as `@1.0.0`; conformance per interface; freeze via ADR before implementation (roadmap phase 11a) |
| Database access | No standard; the host must implement drivers, pooling, retries and query shaping | Medium | The host builds SQL only from fixed templates plus the artifact entity schema; the engine never sends SQL; store conformance runs against both fixture and SQL |
| Networking | Inbound HTTP is terminated by the host (not `wasi:http`), so off-the-shelf `wasmtime serve` is lost | Low | Accepted: a narrower surface. Adopting `wasi:http` is revisitable (U17) |
| Debugging | DWARF is Tier 3 and unmaintained | Medium | The engine crate is also unit-tested natively (test-only builds, never released); Wasm backtraces; host capability trace in verify mode |
| Performance | Instantiation and ABI copying per request; Cranelift compile at startup | Medium | E4 thresholds; pooling allocator; a host-owned precompiled cache (INV-30) |
| Determinism | NaN, relaxed SIMD, memory growth and interruption are nondeterministic unless configured | Low | Fixed host `Config`: NaN canonicalization on, relaxed SIMD off, fixed memory limits, **fuel** in verify mode (deterministic) and **epoch** in production (wall-clock timeouts). This difference is documented (RUNTIME §12) |
| Supply chain | Wasmtime plus Cranelift is a large TCB, and a Cranelift miscompilation affects everything | Medium | LTS pinning; guaranteed security backports; `cargo-vet`/`cargo-audit`; `wasmtime` version in `runtimeHash`; conformance on every bump |
| Precompiled code | `Component::deserialize` is `unsafe`: arbitrary bytes "can trivially be used to execute arbitrary code" | High if misused | INV-30: never load precompiled code from a release, the network or a shared path; only a host-private cache keyed by (engineHash, Wasmtime version, config hash) |
| Policy engine integration | Two semantics (SDC contract vs. Cedar) could drift | Medium | Cedar is a *verification oracle* only in v1; the SDC contract is authoritative; disagreement is `FAIL` |
| Operational complexity | Two languages; per-platform host builds; Wasmtime upgrade cadence (monthly majors) | Medium | Upgrade only between LTS releases; runtime CI builds all Tier 1 platforms |

## 9. Critical design test

Worked in full, from Markdown to runtime, in
[POLICY.md §7](POLICY.md#7-critical-design-test-patient-search). Summary of
results:

| Required property | Mechanism | Verified by |
|---|---|---|
| Non-clinician search fails | Host PDP: default deny; only `AUTHZ-001` allows role `clinician`, action `search`, `Patient` | Dynamic obligations `AUTHZ-001/dynamic/*`, `SEC-001/*` + Cedar oracle agreement |
| DB access only through the declared capability | The engine has no sockets; `store.search` requires a `decision` handle; the grant comes from `DEP-010` | Static import check + capability trace (every store call has a decision) + conformance `CAP-STORE-*` |
| Patient DB capability ALLOWED; search ALLOWED; logging ALLOWED | Manifest grants `store:PatientDB:read`, `log`, `metrics`, `http.inbound` | Static manifest ⟷ IR recomputation |
| Filesystem DENIED | The engine does not import any filesystem interface; the host defines none; `DEP-020 filesystem none` is a verified negative requirement | Static import proof (per build) + conformance `CAP-DENY-FS` (hostile component fails to instantiate) |
| Undeclared network DENIED | Same, for sockets and outbound (`DEP-021`) | Static import proof + `CAP-DENY-NET` |
| Patient information not logged | `personal` classification; the log interface accepts only closed-vocabulary field keys; the host never logs query strings or bodies | Dynamic: fixture PHI absent from captured logs + trace assertion |
| Modified Wasm binary fails | `engineHash` mismatch against the statement and the trust config → `REFUSE_INTEGRITY` | Conformance `LOAD-TAMPER-ENGINE` |
| Modified policy bundle fails | The policy is inside the artifact → `artifactHash` mismatch → `REFUSE_INTEGRITY` | Conformance `LOAD-TAMPER-POLICY` |
| UNVERIFIED security requirement cannot run in production | Release policy blocks (`NOT_RELEASABLE`); a production-mode loader refuses non-`RELEASABLE` | Conformance `LOAD-POLICY-UNVERIFIED` |

The architecture passes the test. Every property has a mechanism and an
independent verification path. One property (filesystem and network denial)
is proved **statically from the binary**, which the Python runtime could not
do.

## 10. Sources

Primary sources, read from the projects' repositories on 2026-09-24:

- Wasmtime security model: `bytecodealliance/wasmtime/docs/security.md`
- Wasmtime release process and LTS: `bytecodealliance/wasmtime/docs/stability-release.md`
- Wasmtime deterministic execution: `bytecodealliance/wasmtime/docs/examples-deterministic-wasm-execution.md`
- Wasmtime tiers (Component Model Tier 1, DWARF Tier 3, `wasi-sql` unsupported): `bytecodealliance/wasmtime/docs/stability-tiers.md`
- `Module::deserialize` / `Component::deserialize` safety contract: `bytecodealliance/wasmtime/crates/wasmtime/src/runtime/module.rs`, `.../component/component.rs`
- WASI status (0.2 stable collection; 0.3 current preview): `WebAssembly/WASI/README.md`
- Rust `wasm32-wasip2` (Tier 2): `rust-lang/rust/src/doc/rustc/src/platform-support/wasm32-wasip2.md`
- OPA Wasm (core language supported; builtins such as `http.send` require the host): `open-policy-agent/opa/docs/docs/wasm.md`
- Cedar (RBAC/ABAC, analyzable, `cedar-policy-symcc`, `cedar-wasm`): `cedar-policy/cedar/README.md`
- Cedar formalization in Lean and differential randomized testing: `cedar-policy/cedar-spec/README.md`
