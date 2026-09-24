# Runtime Contract

Status: **FROZEN — runtime contract 1**, amended before implementation by
[ADR-0016](ADR/0016-wasm-execution-substrate.md) (Wasm substrate) and
[ADR-0017](ADR/0017-policy-contract-and-capability-manifest.md) (policy
contract, capability manifest). Governing ADRs:
[ADR-0006](ADR/0006-declarative-artifact-interpreted-runtime.md),
[ADR-0009](ADR/0009-runtime-executes-only-verified-releases.md),
[ADR-0015](ADR/0015-capability-based-runtime.md). Conformance:
[RUNTIME-CONFORMANCE.md](RUNTIME-CONFORMANCE.md).

The amendment changed *how* the contract is implemented (§12, §13) and made
the capability grant explicit (§6). It did not change the loader chain,
modes, outcomes or fail-closed rules.

The contract is frozen first. The execution technology is chosen from it in
§12.

---

## 1. Role

The runtime is a trusted, fixed program. It loads **one** release, proves the
release is intact, compatible and permitted, and then interprets the artifact.
It contains no application-specific code, and it does not depend on the
toolchain (INV-20).

The runtime ships as its own distribution (`sdc-runtime`). It has two parts:

| Part | What it is | Identity |
|---|---|---|
| **Host** | A native binary (Rust) embedding Wasmtime: loader, trust, authentication, secrets, policy decision point, capability implementations, HTTP termination | `hostHash`: sha256 of the host binary for its platform |
| **Engine** | The `sdc-engine` Wasm component: the interpreter of `sdc.artifact/1`, identical on all platforms | `engineHash`: sha256 of the component bytes |

```text
runtimeHash = sha256(JCS({ host: hostHash, engine: engineHash,
                           wasmtime: "<version>", hostConfig: hostConfigHash }))
```

`hostConfigHash` covers the fixed Wasmtime `Config` of §12.2. These
identities are recorded in evidence, in the signed statement and in startup
logs.

*Interim:* until switch-over ([RUNTIME-CONFORMANCE.md §5](RUNTIME-CONFORMANCE.md#5-switch-over-gate-python--wasm)),
the Python reference runtime implements this contract with
`runtimeHash = sha256(manifest of its files + interpreter version)`.

## 2. Modes

| Mode | Accepts | Store | Secrets | Network bind | Used by |
|---|---|---|---|---|---|
| `production` | Signed releases whose policy decision is `RELEASABLE` and whose signer is in the trust config | Declared real store | Real, from the secret source | Configured | Deployments |
| `dev` | Additionally, `profile: dev` releases, only with `--allow-dev` | Real or fixture | Real | Configured; prints a banner and sets the telemetry flag `dev=true` | `sdc run` |
| `verify` | An **unsigned artifact** | **Fixture store only** | **Ephemeral only** (generated per run) | **Loopback only** | The verifier harness |

`verify` mode refuses any real store configuration, any externally supplied
secret, and any non-loopback bind. That makes it structurally useless for
serving production traffic (INV-22). It is the only way an unverified
artifact ever executes, and it does so under confinement.

## 3. Loading and verification

```text
load(release, trustConfig):
  1. parse     strict canonical JSON; size/depth limits          → REFUSE_MALFORMED
  2. signature DSSE envelope; ≥1 valid Ed25519 signature by a key in trustConfig
               (keys come ONLY from trustConfig, never from the bundle)  → REFUSE_SIGNATURE
  3. hashes    artifactHash (which covers policy + capabilities), irHash, traceHash,
               evidenceHash recomputed and equal to the signed statement;
               engineHash of the component about to be instantiated equals
               the statement's engine AND is in trustConfig.engines  → REFUSE_INTEGRITY
  4. compat    format known; runtimeContract supported; every `requires`
               capability implemented at that major version          → REFUSE_INCOMPATIBLE
  5. policy    statement.verification.decision == RELEASABLE;
               profile allowed by mode; runtime match rule (§3.1);
               signer allowed for this application name (optional);
               artifact.capabilities.granted ⊆ trustConfig.capabilityCeiling → REFUSE_POLICY
  6. inputs    every declared secret present and non-empty; every setting
               valid; capability providers (e.g. SQL driver) available → REFUSE_INPUTS
  7. freeze    artifact becomes an immutable in-memory structure
  8. link      the host linker defines ONLY sdc:runtime interfaces; granted effect
               interfaces get real implementations, ungranted ones get deny stubs;
               the component is instantiated once as a check (unknown import → REFUSE_INCOMPATIBLE)
  9. serve
```

- Every refusal exits the process with code 3, before any socket is opened,
  and logs `{event: "load.refused", reason, artifactHash?}`. There is no
  partial start.
- Production mode has no flag that skips steps 2–5 (INV-18).
- A byte modified anywhere in the artifact changes its hash. Step 3 fails, or
  step 1 fails if the modification also breaks canonical form.

### 3.1 Runtime match rule

The evidence records the `runtimeHash` it was produced on. The trust config
sets `runtime-match`:

- `exact` (**default**): the executing `runtimeHash` (host + engine +
  Wasmtime + config) must equal the evidence runtime. After a runtime patch,
  re-verify: this needs a new evidence document and statement, but no
  recompilation.
- `engine`: `engineHash` must be equal, while the host may be any
  conformant host of the same contract (for example the same host version on
  another platform). This is logged at startup. The engine is
  platform-independent, so this mode supports multi-platform fleets.
- `contract`: any runtime implementing the same contract and capability
  majors is accepted. This is weaker, and it is logged at startup.

## 4. Memory model

- The artifact is immutable after load (§3 step 7). No code path writes to it.
- Each request is processed with request-local state only. On the Wasm
  runtime this is structural: **one fresh engine instance per request**, with
  its own linear memory, dropped (and zeroed by Wasmtime) afterwards. A defect
  triggered by one request cannot affect another request's memory.
- Per-instance memory is capped by a Wasmtime resource limiter derived from
  `limits` and `deployment.resources`.
- Process-wide mutable state is limited to capability-owned state (metrics
  counters, connection pools) behind the capability interfaces.
- Metrics storage is bounded, using fixed-bucket histograms instead of the
  MVP's unbounded latency list.

## 5. Concurrency

- Requests are independent and may execute concurrently, up to
  `limits.maxConcurrency`. Excess requests are rejected with the
  `unavailable` outcome.
- The host is asynchronous. Each engine instance is single-threaded (the
  Wasm `threads` proposal is not used). Host capability calls may suspend the
  instance without blocking an OS thread.
- The meaning of an artifact never depends on scheduling. There is no shared
  mutable application state, so this holds by construction.
- Data consistency is the store capability's responsibility, as governed by
  the `transactions` flag.

## 6. I/O and capabilities

The artifact performs I/O **only** through capabilities
([ADR-0015](ADR/0015-capability-based-runtime.md)). Two artifact fields
govern this, and they must not be confused:

- `requires` states what the **runtime must implement** (compatibility, step
  4), e.g. `authn.jwt/1`;
- `capabilities.granted` states what **this program is allowed to use**
  (authority, steps 5 and 8), declared in source
  ([POLICY.md §4](POLICY.md#4-capability-model)).

On the Wasm runtime, each capability is an interface of the `sdc:runtime` WIT
world, implemented by the host. The engine component imports nothing else
(INV-27). Capabilities in contract 1:

| Capability | Provides | Notes |
|---|---|---|
| `http.server/1` | Inbound HTTP/1.1 on the configured port | Request size and timeout limits from `limits` |
| `authn.jwt/1` | Bearer JWT verification | `alg` must equal the declared algorithm; `exp`/`nbf` enforced; `iss`/`aud` when declared; an empty or short key refuses startup (fixes D7) |
| `authz.policy/1` | Deny-precedence rule evaluation | Default deny; decision returns the matching rule ids |
| `store.sql/1` | Parameterized reads by key and tenant | No silent fallback (fixes D14); unavailability yields the `unavailable` outcome |
| `store.fixture/1` | In-memory fixtures | **Verify mode only** |
| `log/1` | Structured JSON to stdout | Closed-vocabulary fields only; `personal` and `secret` values can never be logged (enforced by the capability) |
| `metrics/1` | Prometheus text on `/metrics` | Bounded |
| `clock/1`, `random/1` | Time and randomness | Host-internal only (token expiry, request ids); **not exposed to the engine** in contract 1. Injected in verify mode for determinism |

| Capability | WIT interface | Kind |
|---|---|---|
| Artifact access | `sdc:runtime/artifact` | kernel (always linked, no effect) |
| Authorization decisions | `sdc:runtime/policy` | kernel (host PDP) |
| Data access | `sdc:runtime/store` | effect (requires a `store` grant) |
| Logging | `sdc:runtime/log` | effect (requires a `log` grant) |
| Metrics | `sdc:runtime/metrics` | effect (requires a `metrics` grant) |
| Inbound HTTP | engine export `handler` | effect (requires an `http.inbound` grant) |

Not available in contract 1: outbound network, filesystem, subprocesses,
environment variables, secrets, dynamic loading. **Default deny for all of
them.** On Wasm they are not merely denied but *unrepresentable*: no
interface exists that the engine could import.

## 7. Networking

- Inbound: bind address and port from runtime settings. Verify mode is
  loopback only.
- Outbound: only to endpoints of declared dependencies (the store host), and
  only through the capability. No general egress exists.

## 8. Filesystem

Read-only. The runtime reads the release file, its trust config and, when
configured, secrets from a mounted directory. It writes nothing; logs go to
stdout.

## 9. Process model

- One runtime process executes one release.
- No hot reload: a new release means a new process.
- Graceful shutdown on SIGTERM within `limits.shutdownGraceMs`.
- Health endpoints `/healthz` and `/readyz` are built in. Readiness requires
  every capability to be available.

## 10. Error handling

- Every request failure maps to a declared outcome
  (`unauthenticated`, `forbidden`, `notFound`, `invalidRequest`,
  `unavailable`, `internalError`).
- Unexpected exceptions become `internalError` with a generic body, and the
  details are logged with the request id. Internals never leak.
- A runtime invariant violation (for example an operation referencing an
  unknown rule after load) terminates the request as `internalError`, never as
  an allow.
- Authorization denial of an existing resource returns `outcomes.deniedAs`
  (fixes D16).

## 11. Security boundaries and resource limits

- Authentication and authorization are evaluated by the **host**, from
  artifact data, before any store read that returns data (INV-29). The engine
  receives an opaque principal and obtains data only with a host-issued
  decision handle ([POLICY.md §5](POLICY.md#5-where-each-control-is-enforced)). `read-one` loads the
  row once for authorization, then projects it. `read-list` filters by tenant
  in the query, then applies the policy to each row.
- A missing required claim is `unauthenticated`. **A missing claim never
  defaults to a value** (fixes D14).
- Secrets come from a runtime secret source (environment or mounted files).
  Their names are declared in the artifact, their values are never logged,
  and a missing value refuses startup. Secret values are used only inside the
  host and **never enter the engine component**.
- Access logs never contain query strings, request bodies or row values. They
  contain only the closed-vocabulary fields of POLICY.md §4.4.
- Identity telemetry (`artifactHash`, `buildId`, name and version) comes from
  the verified release only (INV-21, fixes D13).
- Resource limits are enforced by the host from `limits` (request size,
  timeout, concurrency), and per instance by Wasmtime (memory limiter,
  interruption, §12.2).

## 12. Execution technology decision

### 12.1 Decision (amended by ADR-0016)

Given the contract above, the execution design is:

**a declarative artifact, interpreted by a fixed `sdc-engine` WebAssembly
component, running on Wasmtime inside a native host that owns every
capability.** This is ADOPTED WITH CONDITIONS
([WASM-EVALUATION.md](WASM-EVALUATION.md)).

| Alternative | Status |
|---|---|
| Generated source per language (the MVP) | Rejected: needs language backends; generated code becomes an unverifiable TCB |
| Per-app Wasm, generated or emitted by SDC | Rejected: turns SDC into a conventional compiler; the artifact becomes opaque (ADR-0016, W1/W2) |
| Custom bytecode / VM | Rejected: an instruction set is a language by the back door; SDC would own a sandbox. **SDC implements no proprietary instruction set or VM in v1** |
| Native compilation | Rejected: same objections as generated source |
| Python interpreter process (the v1 freeze) | **Interim reference** until switch-over; isolation depends on the OS sandbox |
| **Fixed engine component on Wasmtime** | **Adopted.** The interpreter is confined to typed capabilities; capability denial is provable from the binary; secrets stay in the host |

Wasm is the substrate, not the architecture. The artifact bytes, their
meaning and their identity are exactly the same on the Python runtime and the
Wasm runtime.

### 12.2 Fixed Wasmtime configuration

The host uses exactly this configuration, recorded in `hostConfigHash`:

| Setting | Value | Why |
|---|---|---|
| Component model | enabled | The engine is a component |
| WASI | **not linked** (no `add_to_linker` of any WASI interface) | INV-27 |
| Threads, shared memory | disabled | Determinism; not needed |
| Relaxed SIMD | disabled | Determinism |
| NaN canonicalization | enabled | Determinism |
| Memory | fixed per-instance maximum via a resource limiter | Deterministic growth failure; memory cap |
| Interruption | **fuel** in `verify` mode (deterministic); **epoch** deadline in `production` (wall-clock `requestTimeoutMs`) | Timeouts in production are wall-clock; verify-mode replay stays deterministic |
| Allocation | pooling allocator | Per-request instantiation cost |
| Precompiled code | loaded only from a host-private cache produced by this host build and configuration; never from a release, the network or a shared path (INV-30) | `Component::deserialize` is `unsafe` for untrusted bytes |
| Wasmtime version | a supported LTS release, pinned in the runtime lock | Security backports guaranteed for supported releases |

## 13. Isolation (sandbox)

With the Wasm substrate, isolation has two layers:

| Layer | Provides | Technology |
|---|---|---|
| **In-process (primary)** | Engine confinement: linear-memory isolation, no raw syscalls, type-checked control flow, imports as its complete authority, per-instance memory and CPU limits | Wasmtime (Component Model), fixed configuration §12.2 |
| **Host process (defense in depth)** | Limits the damage if the host or Wasmtime itself has a defect | OS controls: read-only filesystem except the release and trust config, network egress only to granted store hosts, CPU and memory limits, no privilege escalation |

The host-process controls are derived from the artifact as before:

| Control | Derived from |
|---|---|
| Filesystem: read-only; release + trust config + secrets mount + private code cache only | Fixed |
| Network: listen on the declared port; egress only to granted store dependency hosts | `capabilities` + `dependencies` |
| CPU / memory / process limits | `deployment` resources |
| Secret access: only the declared secret names | `inputs.secrets` |
| No privilege escalation, no new executables | Fixed |

The former open decision U6 (sandbox technology) is resolved for the primary
layer by ADR-0016. The OS technology for the defense-in-depth layer remains a
deployment choice, and SDC emits the profile (seccomp and network policy) for
`Packaging: container`.
