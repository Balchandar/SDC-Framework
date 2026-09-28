# ADR-0016: Wasm Component Model on Wasmtime is the runtime's execution substrate

- Status: **Accepted with conditions** (C1–C7). Reverts to *Deferred* if E1
  or E2 fails.
- Date: 2026-09-24
- Amends: [ADR-0006](0006-declarative-artifact-interpreted-runtime.md) (the
  WASM row of its rejected alternatives), and
  [ADR-0014](0014-implementation-language-and-packaging.md) (the
  reference-runtime language)
- Resolves: open decision U6 (sandbox enforcement technology), for
  in-process isolation
- Evaluation: [WASM-EVALUATION.md](../WASM-EVALUATION.md)

## Problem

Architecture v1 defines a declarative artifact interpreted by a trusted
runtime, specified as a Python process. That runtime:

- holds ambient OS authority, so "the program cannot access the filesystem or
  network" depends on a deployment sandbox that SDC can neither choose (U6 was
  open) nor inspect;
- keeps secrets in the same address space as all request-processing code;
- has no per-request memory isolation and no deterministic interruption.

SDC should not build a proprietary low-level execution engine or sandbox, but
it must keep its semantic model, deterministic compilation, immutable
artifacts, verification, provenance and integrity guarantees.

## Alternatives considered

| Alternative | Summary | Outcome |
|---|---|---|
| A. Python runtime + OS sandbox (status quo) | Keep v1, and choose containers/seccomp/Landlock later | Fallback if the conditions fail |
| B. Generated source → Wasm (W1) | IR → Rust/C → rustc → `.wasm` per app | **Rejected**: language backends; generated code in the TCB; violates ADR-0006 |
| C. SDC emits Wasm directly (W2) | IR → Wasm instructions per app | **Rejected**: SDC becomes an instruction-level compiler; the artifact becomes opaque; static verification over data is lost |
| D. Custom SDC VM / bytecode | A proprietary instruction set | **Rejected**: an instruction set is a language by the back door; SDC would own a sandbox |
| E. **Fixed engine component + artifact as data (W3)** | A hand-written interpreter compiled once to a Wasm component; the host owns all capabilities | **Accepted** |
| F. User-supplied components ("escape hatch") | Let applications ship custom Wasm | **Rejected**: untrusted code with no semantic specification; unverifiable from the IR; unexplainable |
| G. Per-app composed component (A′) as identity | engine ∘ artifact as one `.wasm` | **Rejected as identity**; deferred as packaging only (U14) |

## Decision

1. The production SDC runtime is a **native host** (Rust, embedding Wasmtime)
   plus **one fixed `sdc-engine` component**, per runtime release. The engine
   interprets `sdc.artifact/1` bytes that it receives through the
   `sdc:runtime/artifact` interface.
2. **SDC does not generate Wasm, nor source in any language, per
   application** (INV-26). The compiler is unchanged. The canonical JSON
   artifact remains the **only semantic identity**. `engineHash` and
   `hostHash` are runtime identities, bound to the artifact by the signed
   statement: `executableId = H(host, engine, artifact)`.
3. The engine imports **only** the SDC-owned WIT world
   `sdc:runtime@1.0.0`, and imports **no WASI interfaces**. The host linker
   defines nothing else (INV-27).
4. Security enforcement (authentication, secrets, the policy decision point,
   data-access scoping, log validation and redaction, network) lives in the
   **host**. The engine obtains data only through host-issued,
   policy-scoped resource handles (INV-29).
5. Effect capabilities are declared in source, validated by the compiler,
   listed in the artifact's capability manifest, and granted by the host.
   Everything else is absent or denied (INV-28, [ADR-0017](0017-policy-contract-and-capability-manifest.md)).
6. **SDC implements no proprietary instruction set or virtual machine in v1.**
   That does **not** make SDC a programming-language compiler. SDC remains a
   semantic compiler whose output is a constrained declarative
   representation; Wasm runs the *interpreter* of that representation.
7. Wasmtime is pinned to a supported **LTS** release. Precompiled native code
   is never an identity and is loaded only from a host-private cache that the
   host itself produced (INV-30).
8. The Python runtime remains the production runtime until the Wasm runtime
   passes the **identical** conformance suite plus differential parity
   ([RUNTIME-CONFORMANCE.md](../RUNTIME-CONFORMANCE.md), INV-31).

### Conditions

C1–C7 as listed in [WASM-EVALUATION.md §1](../WASM-EVALUATION.md#1-decision),
gated by experiments E1–E6 ([experiments/README.md](../../experiments/README.md)).

## Rationale

- **Provable capability denial.** In the Component Model, imports are a
  component's complete authority, so "no filesystem access" becomes a fact
  checked from the binary rather than a deployment assumption. The critical
  design test requires exactly this.
- **Secret confinement.** Secrets never enter the code that parses untrusted
  input.
- **Defense in depth from a maintained project.** Wasmtime provides memory
  isolation, guard regions, memory zeroing and Spectre mitigations. Its
  documented release process makes every 12th release LTS, supported 24
  months, with guaranteed security backports. SDC does not build or maintain
  a sandbox.
- **Determinism controls** (NaN canonicalization, relaxed-SIMD handling,
  fuel) strengthen R3 replay in verify mode.
- **WIT resources** give object-capability scoping (decision handles) at the
  type level.
- **ADR-0006's core decision is unchanged**: declarative artifact, fixed
  interpreter, no backends. Only the substrate under the interpreter changes.

## Consequences

- The runtime is implemented in **Rust** (host plus engine). The toolchain
  stays Python. There are two implementation languages. The canonical-form
  implementation exists in both and shares test vectors.
- `runtimeHash` is redefined as `H({hostHash, engineHash, wasmtimeVersion,
  hostConfigHash})`. Evidence and statements name `engineHash` and `hostHash`.
- The artifact gains a `capabilities` section and a structured `policy`
  section (ADR-0017). This is an amendment of `sdc.artifact/1` made before
  any implementation exists.
- Debugging is weaker (DWARF is Tier 3 in Wasmtime). This is mitigated by
  host capability traces, Wasm backtraces and native test builds of the
  engine crate.
- A new public contract, the `sdc:runtime` WIT world, must be frozen
  (phase 11a) and versioned.
- The OS-level sandbox becomes optional defense in depth for the host process
  itself, no longer the primary isolation mechanism.

## Migration implications

See [ROADMAP.md](../ROADMAP.md) phases 5 and 11. In summary:

1. The conformance suite is written first and is runtime-agnostic.
2. The Python reference runtime passes it.
3. The WIT world is frozen.
4. The engine and host are built.
5. The Wasm runtime passes the identical suite, plus differential parity.
6. Switch-over: production mode exists only on Wasm.
7. The Python runtime is retired, or kept as a verify-mode oracle (U13).

No artifact changes at switch-over. Existing releases need **re-verification
only** (new evidence and statement), because `runtime-match: exact` binds
evidence to the runtime.

## Unresolved risks

- Component-model tooling churn (wit-bindgen, wasm-tools) and the WASI 0.3
  transition. Mitigated by importing no WASI.
- Per-request instantiation cost (E4).
- The Wasmtime and Cranelift TCB size; a JIT miscompilation affects all
  applications.
- The monthly major-release cadence of Wasmtime. Mitigated by LTS pinning.
- The host is now the security kernel: its correctness is paramount, and it
  is covered by the conformance suite and review.

Related unresolved decisions: U13–U20 in [ROADMAP.md](../ROADMAP.md#risks-and-unresolved-decisions).
