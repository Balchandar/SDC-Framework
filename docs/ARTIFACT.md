# Artifact and Release

Status: **FROZEN — `sdc.artifact/1`, `sdc.release/1`.** Governing ADRs:
[ADR-0006](ADR/0006-declarative-artifact-interpreted-runtime.md),
[ADR-0007](ADR/0007-artifact-canonical-json.md),
[ADR-0008](ADR/0008-detached-attestations-release-bundle.md),
[ADR-0016](ADR/0016-wasm-execution-substrate.md),
[ADR-0017](ADR/0017-policy-contract-and-capability-manifest.md).

> **Amendment (2026-09-24, before any implementation).** The artifact gains a
> structured `policy` section (the SDC Policy Contract) that replaces the
> separate `authn` / `authz` blocks, and a `capabilities` section (the
> capability manifest). **The artifact stays the only semantic identity.**
> The Wasm engine that executes it is runtime code, not part of the artifact,
> and is bound to it through the signed statement
> ([WASM-EVALUATION.md §4](WASM-EVALUATION.md#4-artifact-model)).

---

## 1. The artifact

### 1.1 Definition

> An **SDC artifact** is exactly one JSON document that conforms to
> `schemas/artifact/artifact-1.schema.json` and is serialized in SDC canonical
> form (RFC 8785 JCS; no floats, no `null`, ASCII keys, NFC strings). Its
> identity is `artifactHash = "sha256:" + hex(sha256(bytes))`.

There is no directory convention and there are no side files. If it is not in
the document, it is not part of the artifact.

### 1.2 Properties

| Property | How it is guaranteed |
|---|---|
| Immutable | Content-addressed. Any change is a different artifact |
| Content-addressable | `artifactHash` over the canonical bytes; the loader rejects non-canonical bytes (INV-09) |
| Hashable, reproducible | Canonical form; compilation is pure (INV-10) |
| Verifiable | Declarative content, so static checks run over data and dynamic checks run through the runtime ([VERIFICATION.md](VERIFICATION.md)) |
| Signed | Through the provenance statement in the release (§2), never self-signed |
| Traceable to source | `irHash` embedded; `sourceHash` → `irHash` is signed in provenance |
| Traceable to compiler | `compilerHash` in the signed statement |
| Traceable to evidence | Evidence names `artifactHash`; the statement binds both |

### 1.3 What the artifact must never contain (INV-08)

Code in any language (**including WebAssembly**: no per-application Wasm
exists, INV-26), secrets or secret values, fixtures or test data,
timestamps, absolute paths, host or user names, environment values, prose or
descriptions, `sourceHash`, `compilerHash`, or evidence.

Leaving `sourceHash` and `compilerHash` out is deliberate. A comment edit, or a
compiler patch release that produces identical output, yields the **same**
artifact. Existing evidence then stays valid, and "rebuild required" means
exactly "the program changed".

### 1.4 Format v1

```json
{
  "format": "sdc.artifact/1",
  "runtimeContract": 1,
  "requires": ["authn.jwt/1", "authz.policy/1", "http.server/1", "log/1", "metrics/1", "store.sql/1"],
  "irVersion": "1.0",
  "irHash": "sha256:…",
  "application": { "id": "APP-001", "name": "customer-service", "version": "1.0.0" },
  "inputs": {
    "secrets": [ { "name": "JWT_SIGNING_KEY", "derivedFrom": ["AUTHN-001"] } ],
    "settings": [ { "name": "PORT", "type": "integer", "default": 8080, "derivedFrom": ["DEPL-001"] } ]
  },
  "limits": {
    "requestTimeoutMs": 10000, "maxRequestBytes": 1048576, "maxConcurrency": 64,
    "shutdownGraceMs": 10000, "derivedFrom": ["REL-001"]
  },
  "policy": {
    "version": 1,
    "authentication": {
      "scheme": "bearer-jwt", "algorithm": "HS256", "secret": "JWT_SIGNING_KEY",
      "claims": [ { "claim": "role", "mapsTo": "principal.role", "required": true, "derivedFrom": ["AUTHN-003"] }, "…" ]
    },
    "authorization": {
      "model": "rbac-tenant", "default": "deny", "deniedAs": "notFound",
      "roles": ["tenant_admin", "user"],
      "rules": [
        { "id": "AUTHZ-001", "effect": "allow", "role": "user", "action": "read",
          "resource": "DATA-001", "condition": { "kind": "same-tenant" } },
        { "id": "AUTHZ-003", "effect": "deny", "role": "any", "action": "any",
          "resource": "any", "condition": { "kind": "cross-tenant" } }
      ]
    },
    "dataAccess": {
      "entities": [
        { "id": "DATA-001", "name": "Customer", "store": "DEP-001", "key": "id", "tenant": "tenant_id",
          "fields": [ { "name": "email", "type": "string", "classification": "personal", "nullable": false },
                      { "name": "password", "type": "string", "classification": "secret", "nullable": false }, "…" ] }
      ],
      "operations": [
        { "id": "API-001", "entity": "DATA-001", "access": "get",
          "projection": ["email", "id", "name", "tenant_id"] }
      ]
    },
    "audit": { "decisions": "required", "fields": ["authz-decision", "latency", "operation", "requirement-id", "status"],
               "neverLogged": ["personal", "secret"] },
    "network": { "inbound": { "port": 8080 }, "outbound": [ { "dependency": "DEP-001", "purpose": "store" } ], "default": "deny" }
  },
  "capabilities": {
    "granted": [
      { "id": "DEP-010", "capability": "store", "target": "DEP-001", "access": "read", "entities": ["DATA-001"] },
      { "id": "DEP-011", "capability": "http.inbound", "access": "serve" },
      { "id": "DEP-012", "capability": "log", "access": "emit" },
      { "id": "DEP-013", "capability": "metrics", "access": "emit" }
    ],
    "denied": [ { "id": "DEP-020", "capability": "filesystem" } ]
  },
  "outcomes": {
    "success": 200, "unauthenticated": 401, "forbidden": 403, "notFound": 404,
    "invalidRequest": 400, "internalError": 500, "unavailable": 503
  },
  "operations": [
    { "id": "API-001", "method": "GET", "path": "/customers/{id}", "kind": "read-one",
      "resource": "DATA-001", "keyParameter": "id", "authentication": "required",
      "rules": ["AUTHZ-001", "AUTHZ-002", "AUTHZ-003"],
      "derivedFrom": ["API-001", "AUTHN-001", "AUTHZ-001", "AUTHZ-002", "AUTHZ-003", "BEH-001", "DATA-001", "SEC-001"] }
  ],
  "observability": {
    "logs": "structured-json", "metrics": "prometheus", "health": true,
    "fields": ["authz-decision", "latency", "operation", "request-id", "requirement-id", "status", "tenant-id"]
  },
  "requirements": ["API-001", "APP-001", "AUTHN-001", "…"]
}
```

(`"…"` marks elision in this document only. Real artifacts are complete.)

Notes:

- `policy` is the serialized SDC Policy Contract
  ([POLICY.md §2](POLICY.md#2-the-sdc-policy-contract)). Response projection
  lives in `policy.dataAccess.operations[].projection` (`secret` fields are
  never projected), and `operations[].rules` is the pre-selected effective
  policy. The runtime needs no knowledge of the IR.
- `capabilities` is the capability manifest
  ([POLICY.md §4](POLICY.md#4-capability-model)): `granted` is exactly
  `required ∩ declared`, and `denied` lists explicit denials for
  documentation and verification.
- `requires` lists runtime capabilities with major versions. Compatibility
  means the runtime implements every listed capability at that major version
  and implements `runtimeContract`. It says what the runtime must *implement*;
  `capabilities.granted` says what this program may *use*.
- `requirements` indexes every requirement id that has a runtime
  counterpart, which allows audit logs to cite requirement ids.
- **Sub-hashes.** `policyHash = sha256(JCS(artifact.policy))` and
  `capabilityHash = sha256(JCS(artifact.capabilities))`. They are recorded in
  the statement for audit and diff. They are *parts* of `artifactHash`, not
  independent identities.

### 1.5 Loader validation (before any execution)

1. Size is at most 16 MiB. Parse strictly: duplicate keys, floats, `null`, or
   nesting deeper than 64 levels cause rejection.
2. Re-serialize to canonical form. **The result must equal the input bytes**,
   otherwise reject.
3. Validate against the schema for `format`.
4. Check referential integrity: every `resource`, `rules[]` entry and
   `secret` resolves.
5. Recompute `artifactHash` and compare it with the signed statement (§2).

## 2. Release bundle

The **release** is what gets deployed. It is one canonical JSON file named
`<name>-<version>.release.json`:

```json
{
  "format": "sdc.release/1",
  "artifact":  { … the artifact document … },
  "materials": { "ir": { … }, "trace": { … } },
  "evidence":  { … sdc.evidence/1 … },
  "envelope":  {
    "payloadType": "application/vnd.sdc.statement.v1+json",
    "payload": "<base64 of canonical statement>",
    "signatures": [ { "keyid": "sha256:…", "sig": "<base64 Ed25519>" } ]
  }
}
```

- `envelope` is a DSSE envelope. The signature is Ed25519 over
  `PAE(payloadType, payload)`.
- The statement ([PROVENANCE.md](PROVENANCE.md)) binds `artifactHash`,
  `irHash`, `traceHash`, `evidenceHash`, `sourceHash`, `policyHash`,
  `capabilityHash`, `engineHash` and `hostHash`. The runtime recomputes each
  hash from the embedded documents and from the engine component it is about
  to instantiate, and compares:
  - `H(artifact) == statement.subject.digest`
  - `H(materials.ir) == identity.irHash == artifact.irHash`
  - `H(materials.trace) == identity.traceHash`
  - `H(evidence) == verification.verificationId`
  - `H(artifact.policy) == identity.policyHash`, `H(artifact.capabilities) == identity.capabilityHash`
  - `H(engine component bytes) == targetRuntime.engine` (and the engine is in the trust-config allowlist)
- `releaseDigest = sha256(canonical release file)`. It identifies the bundle
  for distribution only; trust derives from the signature.
- **The release does not contain the engine component by default.** The engine
  is part of the runtime distribution, and the statement names it by hash.
  For air-gapped deployment the bundle MAY carry the engine bytes under
  `runtime.engine`; they are then checked exactly as above, and trust still
  derives from the trust-config allowlist, never from the bundle.
- **There is no separate "manifest" file.** The statement's `identity`
  section is the release manifest, so the same facts are never stored twice.
- The IR, trace and evidence travel with the release so that `sdc explain`,
  `sdc diff` and audits work on a deployed release without its source tree.

## 3. Hash summary

| Hash | Over | Defined in |
|---|---|---|
| `sourceHash` | Source-set manifest (paths + per-file sha256 of raw bytes) | [COMPILER.md](COMPILER.md#stage-1-load) |
| `irHash` | `ir.json` | [SEMANTIC-IR.md](SEMANTIC-IR.md#6-hashes) |
| `traceHash` | `trace.json` | [SEMANTIC-IR.md](SEMANTIC-IR.md#6-hashes) |
| `artifactHash` | The artifact document | here |
| `evidenceHash` (= `verificationId`) | The evidence document | [VERIFICATION.md](VERIFICATION.md) |
| `compilerHash`, `configHash`, `lockHash`, `buildId` | Toolchain identity and inputs | [BUILD-REPRODUCIBILITY.md](BUILD-REPRODUCIBILITY.md) |
| `statementHash` | The statement payload | [PROVENANCE.md](PROVENANCE.md) |
| `releaseDigest` | The release file | here |
| `policyHash`, `capabilityHash` | `artifact.policy`, `artifact.capabilities` (sub-hashes of the artifact) | here |
| `engineHash` | The `sdc-engine` Wasm component bytes | [RUNTIME.md §1](RUNTIME.md#1-role) |
| `hostHash` | The host binary (per platform) | [RUNTIME.md §1](RUNTIME.md#1-role) |
| `runtimeHash` | `H({host, engine, wasmtime, hostConfig})` | [RUNTIME.md §1](RUNTIME.md#1-role) |
| `executableId` | `H(JCS({host: hostHash, engine: engineHash, artifact: artifactHash}))` | [BUILD-REPRODUCIBILITY.md](BUILD-REPRODUCIBILITY.md) |

## 4. Format evolution

- `sdc.artifact/1` may gain optional fields only when each one comes with a
  new capability in `requires`. An older runtime then refuses the artifact
  instead of ignoring a field it does not understand.
- **The runtime rejects unknown fields.** "Must understand" is the rule, and
  silent ignoring is forbidden.
- A breaking change is `sdc.artifact/2`, which requires a runtime supporting
  that format.
