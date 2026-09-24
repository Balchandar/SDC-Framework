# Runtime Contract

Status: **FROZEN — runtime contract 1.** Governing ADRs:
[ADR-0006](ADR/0006-declarative-artifact-interpreted-runtime.md),
[ADR-0009](ADR/0009-runtime-executes-only-verified-releases.md),
[ADR-0015](ADR/0015-capability-based-runtime.md).

The contract is frozen first. The execution technology is chosen from it in
§12.

---

## 1. Role

The runtime is a trusted, fixed program. It loads **one** release, proves the
release is intact, compatible and permitted, and then interprets the artifact.
It contains no application-specific code, and it does not depend on the
toolchain (INV-20).

The runtime ships as its own distribution (`sdc-runtime`). Its identity is
`runtimeHash`: the sha256 of the canonical manifest of its installed files and
their hashes, plus the interpreter version. That identity is recorded in
evidence and in startup logs.

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
  3. hashes    artifactHash, irHash, traceHash, evidenceHash recomputed and equal
               to the signed statement                              → REFUSE_INTEGRITY
  4. compat    format known; runtimeContract supported; every `requires`
               capability implemented at that major version          → REFUSE_INCOMPATIBLE
  5. policy    statement.verification.decision == RELEASABLE;
               profile allowed by mode; runtime match rule (§3.1);
               signer allowed for this application name (optional)    → REFUSE_POLICY
  6. inputs    every declared secret present and non-empty; every setting
               valid; capability providers (e.g. SQL driver) available → REFUSE_INPUTS
  7. freeze    artifact becomes an immutable in-memory structure
  8. serve
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

- `exact` (**default**): the executing `runtimeHash` must equal the evidence
  runtime. After a runtime patch, re-verify: this needs a new evidence
  document and statement, but no recompilation.
- `contract`: any runtime implementing the same contract and capability
  majors is accepted. This is weaker, and it is logged at startup.

## 4. Memory model

- The artifact is immutable after load (§3 step 7). No code path writes to it.
- Each request is processed with request-local state only.
- Process-wide mutable state is limited to capability-owned state (metrics
  counters, connection pools) behind the capability interfaces.
- Metrics storage is bounded, using fixed-bucket histograms instead of the
  MVP's unbounded latency list.

## 5. Concurrency

- Requests are independent and may execute concurrently, up to
  `limits.maxConcurrency`. Excess requests are rejected with the
  `unavailable` outcome.
- The meaning of an artifact never depends on scheduling. There is no shared
  mutable application state, so this holds by construction.
- Data consistency is the store capability's responsibility, as governed by
  the `transactions` flag.

## 6. I/O and capabilities

The artifact performs I/O **only** through capabilities it declares in
`requires` ([ADR-0015](ADR/0015-capability-based-runtime.md)). Capabilities in contract 1:

| Capability | Provides | Notes |
|---|---|---|
| `http.server/1` | Inbound HTTP/1.1 on the configured port | Request size and timeout limits from `limits` |
| `authn.jwt/1` | Bearer JWT verification | `alg` must equal the declared algorithm; `exp`/`nbf` enforced; `iss`/`aud` when declared; an empty or short key refuses startup (fixes D7) |
| `authz.policy/1` | Deny-precedence rule evaluation | Default deny; decision returns the matching rule ids |
| `store.sql/1` | Parameterized reads by key and tenant | No silent fallback (fixes D14); unavailability yields the `unavailable` outcome |
| `store.fixture/1` | In-memory fixtures | **Verify mode only** |
| `log/1` | Structured JSON to stdout | Redaction of sensitive fields is enforced by the capability |
| `metrics/1` | Prometheus text on `/metrics` | Bounded |
| `clock/1`, `random/1` | Time and randomness | Injected, so verification is deterministic |

Not available in contract 1: outbound network, filesystem, subprocesses,
dynamic loading. **Default deny for all of them.**

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

- Authentication and authorization are evaluated by the runtime, from
  artifact data, before any store read that returns data. `read-one` loads the
  row once for authorization, then projects it. `read-list` filters by tenant
  in the query, then applies the policy to each row.
- A missing required claim is `unauthenticated`. **A missing claim never
  defaults to a value** (fixes D14).
- Secrets come from a runtime secret source (environment or mounted files).
  Their names are declared in the artifact, their values are never logged,
  and a missing value refuses startup.
- Identity telemetry (`artifactHash`, `buildId`, name and version) comes from
  the verified release only (INV-21, fixes D13).
- Resource limits are enforced in-process from `limits` (request size,
  timeout, concurrency) and at the OS level from the sandbox profile (§13).

## 12. Execution technology decision

Given the contract above:

- The artifact contains no general computation. It is a closed vocabulary of
  operations, policies and mappings.
- The MVP already demonstrated an interpreter design: `Policy.decide`
  interprets rules as data, and the generated "code" only pasted data into a
  fixed template.

**Decision: a declarative artifact interpreted by a fixed runtime.**

| Alternative | Rejected because |
|---|---|
| Generated source per language (the MVP) | Needs language backends; the generated code becomes an unverifiable TCB; it violates the no-backend principle |
| Custom bytecode / VM | No general computation needs to be executed. A VM would add an instruction set, a verifier and a language by the back door |
| WASM | Designed to isolate untrusted code, and there is no code. It could only be reconsidered if a future extension requires user-supplied computation, which would need a new ADR |
| Native compilation | Same objections as generated source. Performance is not the bottleneck at this vocabulary size |

The reference runtime is Python, preserving the MVP's `runtime.py`
components. A runtime in any other language is only another implementation of
**this contract**. It must pass `tests/conformance` and is identified by its
own `runtimeHash`. It is not a "backend", because the artifact bytes are
identical for every runtime.

## 13. Isolation (sandbox)

The artifact is data, so there is no untrusted code in the process. The
sandbox is defense in depth against defects in the trusted runtime, such as
HTTP parsing bugs. The contract requires the deployment to be able to enforce:

| Control | Derived from |
|---|---|
| Filesystem: read-only, release + trust config + secrets mount only | Fixed |
| Network: listen on the declared port; egress only to declared dependency hosts | `requires` + `dependencies` |
| CPU / memory / process limits | `deployment` resources |
| Secret access: only the declared secret names | `inputs.secrets` |
| No privilege escalation, no new executables | Fixed |

`sdc build` with `Packaging: container` emits a sandbox profile (a seccomp
profile, a network-policy description and resource limits) next to the
package. The enforcing technology (containers, gVisor, Landlock, …) is an open
decision ([ROADMAP.md](ROADMAP.md#risks-and-unresolved-decisions)). The
contract is independent of that choice.
