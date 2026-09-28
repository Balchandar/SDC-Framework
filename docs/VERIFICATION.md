# Verification

Status: **FROZEN — `sdc.evidence/1`**, amended before implementation by
[ADR-0016](ADR/0016-wasm-execution-substrate.md) and
[ADR-0017](ADR/0017-policy-contract-and-capability-manifest.md) (§9: the
Wasm substrate, capabilities, and the Cedar oracle). Governing ADR:
[ADR-0010](ADR/0010-verification-mandatory-for-release.md).

Verification is a stage of the build, not an optional add-on. A release
exists only when the evidence satisfies the release policy (INV-16):

```text
compile → verify → evidence → policy → provenance → sign → release
```

---

## 1. Independence

- The **verifier derives obligations from the Semantic IR**, not from the
  planner or the artifact (INV-14). A lowering bug in the planner therefore
  shows up as a disagreement between IR-derived expectations and artifact
  behavior.
- The verifier executes the artifact on the **same runtime distribution** that
  production uses, in `verify` mode ([RUNTIME.md §2](RUNTIME.md#2-modes)).
  What is verified is the artifact on a specific `runtimeHash`.
- The verifier has its own identity, `verifierHash`, recorded in evidence.
- **Known limit (common-mode failure).** If the compiler misreads the source,
  producing a wrong IR, the obligations inherit the misreading. Two things
  mitigate this: author-written test cases in `testing.md`, which are
  independent of IR derivation, and human review of `sdc inspect` output and
  the semantic diff for every change. See [ROADMAP.md](ROADMAP.md#risks-and-unresolved-decisions).

## 2. Obligations

An **obligation** is one checkable claim about the artifact, derived from one
requirement:

```text
Obligation {
  id:          "<REQ-ID>/<method>/<n>"        e.g. "SEC-002/dynamic/1"
  requirement: "<REQ-ID>"
  method:      "static" | "dynamic" | "measured" | "attested"
  property:    string                          e.g. "tenant-isolation"
  required:    bool                            counts toward the requirement status
  inputs:      { … }                           fixtures, principals, operation ids
}
```

Every requirement id in the IR yields at least one obligation, or an explicit
`UNVERIFIED` record that says why none exists. Nothing is silently skipped.

### 2.1 Derivation (v1)

| Requirement | Obligations |
|---|---|
| `API-*` | static: the operation exists with the declared method, path, kind and resource. dynamic: the route responds; a `read-one` on an absent key returns `notFound` |
| `AUTHN-*` | static: `authn` matches. dynamic: no token, bad signature, expired token, wrong `alg`, missing required claim → `unauthenticated` |
| `AUTHZ-*` rule | dynamic: one positive and one negative case per rule, derived from the permission matrix. static: the default is deny |
| `DATA-*` | static: the projection excludes `secret` fields; `personal` fields are in `policy.audit.neverLogged`; the tenant field is present when tenant-scoped |
| `BEH-*` | dynamic: each reachable condition yields its declared status |
| `SEC-*` `no-sensitive-exposure` | static: no projection contains a `secret` field. dynamic: fixture `secret` values are absent from every response |
| `SEC-*` `no-sensitive-logging` | dynamic: fixture `personal` and `secret` values are absent from captured logs and metrics. trace: every `log.emit` used closed-vocabulary fields only |
| `SEC-*` `tenant-isolation` | dynamic: every cross-tenant principal/target pair is denied, with no data leaked in the body |
| `SEC-*` `authentication-enforced` / `authorization-enforced` | Composed of the AUTHN / AUTHZ obligations for every operation |
| `SEC-*` `authorization-audit` | dynamic: every decision is logged with its rule ids |
| `SEC-*` `injection-safe` | static: the store capability used is parameterized-only (a runtime capability property, established by the conformance suite) |
| `SEC-*` `security-headers` | dynamic: headers present on every response |
| `SEC-*` `secrets-from-runtime` | static: the artifact contains no secret values and only secret names |
| `SEC-*` `custom` | Only the `testing.md` cases that list the id in `Verifies`; otherwise `UNVERIFIED` |
| `PERF-*` | measured ([§5](#5-measured-evidence)) |
| `REL-*` | dynamic: request size limit, timeout and concurrency limit enforced |
| `OBS-*` | dynamic: declared fields present in the logs; `/metrics` and `/healthz` respond |
| `TEST-*` | dynamic: the case, exactly as declared |
| `APP-*`, `DEPL-*`, `DEP-*` (dependencies) | static: artifact header and inputs consistent; lock matches the runtime used |
| `DEP-*` capability grant | static: `artifact.capabilities.granted` equals `capabilityView(ir)`, recomputed by the verifier. trace: every call to the capability was scoped (store calls carry a decision), and no `capability.denied` event occurred |
| `DEP-*` capability denial (`none`) | static: the engine component imports no interface that could provide it (INV-27). cited: the runtime conformance `CAP-DENY-*` result for this `runtimeHash` |
| `AUTHZ-*` (all rules, together) | static (oracle): the verifier's own Cedar translation of the IR policy agrees with the runtime's decisions over the full permission matrix (§9.3) |

The MVP's regex scans of generated Python source (SQL injection, `pickle`,
`open(req…)`) are **removed**. There is no generated source to scan. The
runtime's own security properties are established once per runtime release by
`tests/conformance`, and each capability property check refers to them.

## 3. Methods

| Method | Runs on | Deterministic | Notes |
|---|---|---|---|
| `static` | Artifact bytes vs IR | yes | Proofs over declarative data, possible because the artifact is data (ADR-0006) |
| `dynamic` | Runtime in `verify` mode, fixture store, injected clock and random, loopback | yes (outcome) | Obligation outcomes are reproducible. Only timings vary |
| `measured` | Runtime under a declared benchmark profile | **no** | Evidence carries environment and `reproducible: false` |
| `attested` | A signed human attestation | — | Reserved; not in v1 |

## 4. Status model

Obligation status:

| Status | Meaning |
|---|---|
| `PASS` | The check ran and the claim holds |
| `FAIL` | The check ran and the claim does not hold |
| `UNVERIFIED` | No method exists or was configured for this claim |
| `BLOCKED` | The check could not run: a prerequisite failed, the runtime did not start, or the environment is missing (e.g. no benchmark profile) |

A requirement's status is aggregated over its **required** obligations, in
this precedence: `FAIL` > `BLOCKED` > `UNVERIFIED` > `PASS`. A requirement
with no required obligations is `UNVERIFIED`.

`WARN` from the MVP is removed. A warning is a diagnostic, not a verification
result.

## 5. Measured evidence

- Measured obligations count only when run under the performance section's
  `Benchmark-Profile`, which is a named environment described in
  `sdc.toml [benchmark.<name>]`. Anywhere else they are `BLOCKED`.
- Measured results record hardware, OS, runtime, concurrency, sample count,
  warm-up and raw percentiles.
- This replaces the MVP's blocking p99 over 300 sequential local requests
  (D19), which made build results depend on laptop load.

## 6. Criticality and release policy

Criticality comes from the source:

| Criticality | Applies to |
|---|---|
| `critical` | All `SEC`, `AUTHN`, `AUTHZ`; `DATA` entities that have `personal`, `secret` or tenant fields; every **capability** row in `dependencies.md`. Cannot be lowered |
| `standard` | Everything else (the default) |
| `advisory` | `PERF`, `OBS` only, when declared explicitly |

**Release policy (`release` profile):**

| Requirement status | critical | standard | advisory |
|---|---|---|---|
| `PASS` | release | release | release |
| `FAIL` | **block** | **block** | release, reported |
| `UNVERIFIED` | **block** | block, unless waived | release, reported |
| `BLOCKED` | **block** | block, unless waived | release, reported |

- **Waivers** live in `sdc.toml [policy].waive`. Each has a requirement id and
  a reason. They apply only to `standard` requirements. A waiver naming a
  critical requirement is an `ERROR`. Applied waivers are copied into the
  evidence and the signed statement.
- **`dev` profile:** the same table is evaluated and printed, and the release
  is produced with `decision: NOT_RELEASABLE, profile: dev`. The runtime
  accepts it only in `dev` mode, and `sdc run` refuses a critical `FAIL` even
  in dev.

The policy decision is `RELEASABLE` or `NOT_RELEASABLE`, with reasons (the
blocking requirement ids).

## 7. Evidence document

```json
{
  "format": "sdc.evidence/1",
  "artifactHash": "sha256:…",
  "irHash": "sha256:…",
  "runtime":  { "name": "sdc-runtime", "version": "1.0.0", "hash": "sha256:…",
                "host": "sha256:…", "engine": "sha256:…", "wasmtime": "…",
                "conformance": "sha256:…" },
  "verifier": { "version": "1.0.0", "hash": "sha256:…" },
  "profile": "release",
  "environment": { "platform": "linux-x86_64", "benchmarkProfile": "ci-perf-1" },
  "obligations": [
    { "id": "SEC-002/dynamic/1", "requirement": "SEC-002", "method": "dynamic",
      "property": "tenant-isolation", "required": true, "status": "PASS",
      "detail": "principal tenant=t2 → API-001 key=c1: notFound (expected notFound)",
      "reproducible": true }
  ],
  "requirements": [ { "id": "SEC-002", "criticality": "critical", "status": "PASS" } ],
  "coverage": { "requirements": 31, "pass": 30, "fail": 0, "unverified": 1, "blocked": 0 },
  "policy": { "decision": "RELEASABLE", "blocking": [], "waivers": [] }
}
```

- `verificationId = evidenceHash = sha256(JCS(evidence))`.
- Evidence is detached from the artifact and bound to it by `artifactHash`
  (INV-15).
- **Evidence reuse.** Evidence may be reused for a new build only if
  `artifactHash`, `runtime.hash`, `verifier.hash` and `profile` are all equal
  and it contains no measured obligations. Otherwise verification re-runs.

## 8. Selective re-verification

The semantic diff ([SEMANTIC-DIFF.md](SEMANTIC-DIFF.md)) computes the
obligations affected by a change, for fast feedback in `sdc verify
--changed`. **Releases never use selective verification.** A release always
runs the full obligation set, or reuses complete evidence under the rule
above. A defect in diff classification must never weaken a release.

## 9. Execution-substrate verification

Added by ADR-0016 and ADR-0017. The rule of §1 is unchanged: the verifier
trusts neither the compiler nor the runtime's claims. The Wasm substrate adds
things to inspect. It removes none of the earlier checks.

### 9.1 What the verifier inspects, independently

| Object | Check | Method |
|---|---|---|
| Artifact | As in §2, including the `policy` and `capabilities` sections, each recomputed from the IR by the verifier's own `policyView` and `capabilityView` | static |
| Engine component | `engineHash` is in the trust-config engine allowlist; its import list is exactly the `sdc:runtime@1.0.0` world, with no WASI filesystem, sockets, CLI, environment or process interface; its export is exactly `handler` | static (parses the component binary; independent of the host) |
| Runtime behavior | All dynamic obligations, executed by the real host + engine in verify mode | dynamic |
| Capability use | The host **capability trace** (every capability call, with interface, decision id and result class) is asserted against the manifest and the policy: no ungranted call, no store call without a decision, log fields only from the vocabulary | dynamic (trace) |
| Authorization | The permission matrix is exercised dynamically **and** cross-checked against the Cedar oracle (§9.3) | dynamic + static |
| Security invariants of the host | Denial of unlinked imports, secret confinement, handle scoping, integrity refusals: established once per runtime release by the conformance suite, and **cited by `runtimeHash`** | cited evidence |

### 9.2 Cited conformance evidence

Some properties belong to the runtime, not to the application. Examples are
"a component that imports `wasi:filesystem` cannot be instantiated" and "a
tampered engine is refused". They are proved by
[RUNTIME-CONFORMANCE.md](RUNTIME-CONFORMANCE.md) for a specific
`runtimeHash`, and application evidence **cites** that result
(`runtime.conformance`). A citation counts as `PASS` only if the cited
conformance evidence exists, is signed by a trusted key, and matches the
exact `runtimeHash` used for the dynamic obligations. Otherwise the obligation
is `BLOCKED`. Because capability rows are critical, a `BLOCKED` citation blocks
the release.

### 9.3 Policy oracle (Cedar)

The verifier translates the **IR**, not the artifact, into Cedar policies and
a schema. That keeps it independent of the planner. It then:

1. validates the Cedar policies against the schema;
2. evaluates every (role, action, resource, condition-case) cell of the
   permission matrix with Cedar and compares the results with the runtime's
   observed decisions;
3. where supported (experiment E5), proves symbolic properties such as "no
   principal whose role is not in {R} is permitted action A on resource E".

Any disagreement is `FAIL`. The oracle is a verification dependency. It is not
part of the runtime TCB and is never executed at runtime.

### 9.4 Differential verification during migration

Until the Python → Wasm switch-over
([RUNTIME-CONFORMANCE.md §5](RUNTIME-CONFORMANCE.md#5-switch-over-gate-python--wasm)),
each example's release candidate is verified on **both** runtimes. Obligation
statuses must be identical. A difference is `FAIL` for the Wasm runtime until
it is explained and fixed.
