# Semantic IR (irVersion 1.0)

Status: **FROZEN — `irVersion` 1.0**, amended before implementation by
[ADR-0017](ADR/0017-policy-contract-and-capability-manifest.md) (`search`,
classification, capabilities, derived policy view). Governing ADR:
[ADR-0003](ADR/0003-semantic-ir-contract.md).

The Semantic IR is SDC's truth model: the complete, typed meaning of a source
set. The compiler lowers it, the verifier derives obligations from it, the
diff compares it, and `explain` navigates it. It is a stable, versioned
contract with a JSON Schema in `schemas/ir/ir-1.schema.json`.

---

## 1. Two documents: semantics and trace

The IR is emitted as two canonical JSON documents:

| Document | Contains | Hash | Used for |
|---|---|---|---|
| `ir.json` | Meaning only: typed values, ids, references, default origins | `irHash` | Everything semantic: planning, obligations, diff, artifact identity |
| `trace.json` | Where the meaning came from: file, line span, source text, descriptions, prose | `traceHash` | `explain`, diagnostics, reports. **Never** for semantics (INV-02) |

The split is what makes `irHash` a hash of *meaning*. In the MVP (defect D6),
rewording a sentence changed the IR hash. Under this contract, rewording prose
changes only `traceHash`, and changing a declared value changes `irHash`.

## 2. General rules

1. **Strong typing.** Every field has one type from the schema. Enumerations
   are closed string sets, and there are no free-form dictionaries.
2. **Identity.** Every requirement-bearing node has an `id`, the requirement
   id declared in source. Nodes that are not requirements (for example entity
   fields) are identified by a path from their owner (`DATA-001.fields.email`).
3. **References by id.** Cross-references hold ids (`"resource": "DATA-001"`),
   never names. That makes renaming a `MODIFIED` change instead of a
   delete-plus-add.
4. **Order independence.** Every collection has set semantics and is emitted
   sorted by `id` (or by name where there is no id). No meaning depends on
   order (INV-06). Authorization in particular is deny-precedence, not
   first-match.
5. **Explicit origin.** Every value that can be defaulted carries
   `origin: "source"` or `origin: "default"` plus `rule: "D-xx"` (INV-04).
6. **Immutability.** IR objects are frozen after construction. Stages derive
   new values; they never mutate the IR.
7. **Canonical form** (INV-07):
   - RFC 8785 (JCS) serialization;
   - **no floating-point numbers**: quantities are integers with a unit in the
     field name (`targetMs`, `limitMb`);
   - **no `null`**: an absent optional value means the key is absent;
   - ASCII `camelCase` keys, so JCS key order equals code-point order;
   - NFC-normalized strings;
   - integers in the range ±(2^53 − 1).
8. **No environment.** The IR contains no paths, timestamps, hostnames, user
   names or environment values.

## 3. Root

```text
SemanticIR {
  irVersion:        "1.0"
  languageVersion:  "sdc/1"
  application:      Application
  api:              Api
  authentication:   Authentication
  authorization:    Authorization
  data:             Data
  behavior:         Behavior
  security:         Security
  performance:      Performance
  reliability:      Reliability
  observability:    Observability
  deployment:       Deployment
  testing:          Testing
  dependencies:     Dependencies
}
```

All 13 sections are always present. An absent source section produces the
section's empty value: empty collections, or `enabled: false` where noted.
Absence is itself meaningful and stable.

## 4. Section types

Notation: `T?` = optional (key omitted when absent), `[T]` = set sorted by id,
`Id<P>` = requirement id with prefix `P`, `Ref<P>` = reference to such an id.

```text
Application   { id: Id<APP>, name: string, version: SemVer }

Api           { basePath: Defaultable<string>, operations: [Operation] }
Operation     { id: Id<API>, method: "GET", path: PathTemplate,
                kind: "read-one" | "read-list" | "search",
                resource: Ref<DATA>, keyParameter?: string,
                criteria?: { mode: "at-least-one" | "all",
                             params: [ { parameter, field: FieldName, match: "exact" | "prefix-ci" } ] },
                maxResults?: int,
                authentication: "required" | "none" }

Authentication{ id?: Id<AUTHN>, scheme: "none" | "bearer-jwt",
                algorithm?: "HS256", secret?: SecretName,
                issuer?: string, audience?: string, claims: [Claim] }
Claim         { id: Id<AUTHN>, claim: string, mapsTo: PrincipalField, required: bool }

Authorization { model: "none" | "rbac" | "rbac-tenant", default: "deny",
                audit: bool, roles: [RoleName], rules: [Rule] }
Rule          { id: Id<AUTHZ>, effect: "allow" | "deny",
                role: RoleName | "any", action: "read" | "search" | "any",
                resource: Ref<DATA> | "any", condition: Condition }
Condition     = { kind: "always" } | { kind: "same-tenant" } | { kind: "cross-tenant" }
              | { kind: "attr-contains", principalAttr: string, field: FieldName }

Data          { store: "sql" | "fixture", storeDependency?: Ref<DEP>,
                transactions: Defaultable<bool>, entities: [Entity] }
Entity        { id: Id<DATA>, name: EntityName, fields: [Field] }   # fields sorted by name
Field         { name: FieldName, type: "string" | "integer" | "boolean" | "timestamp",
                key: bool, tenant: bool,
                classification: "standard" | "personal" | "secret", nullable: bool }

Behavior      { outcomes: [Outcome], deniedAs?: "forbidden" | "not-found" }
Outcome       { id?: Id<BEH>, condition: OutcomeCondition, status: int,
                origin: "source" | "default", rule?: string }

Security      { requirements: [SecurityRequirement] }
SecurityRequirement { id: Id<SEC>, property: SecurityProperty, criticality: "critical" }

Performance   { benchmarkProfile?: string, targets: [PerfTarget] }
PerfTarget    { id: Id<PERF>, metric: "latency-p50" | "latency-p99" | "throughput",
                operation: Ref<API> | "all", target: int, unit: "ms" | "rps",
                criticality: "standard" | "advisory" }

Reliability   { requestTimeoutMs, maxRequestBytes, maxConcurrency,
                shutdownGraceMs, storeRetryAttempts : Defaultable<int> }   # each may carry an id

Observability { logs: "structured-json", metrics: "prometheus" | "none",
                health: bool, fields: [ObsField] }

Deployment    { id?: Id<DEPL>, platform: Platform, packaging: Packaging,
                port: int, resources: { cpuMillis?, memoryMb?, processes? } }

Testing       { fixtures: [Fixture], cases: [TestCase] }
Fixture       { entity: Ref<DATA>, rows: [Row] }       # rows sorted by key value
TestCase      { id: Id<TEST>, operation: Ref<API>, principal: Principal,
                target: { key: string, present: bool }, expect: OutcomeCondition,
                verifies: [Ref<*>] }

Dependencies  { dependencies: [Dependency], capabilities: [CapabilityDecl] }
Dependency    { id: Id<DEP>, kind: "runtime" | "store" | "identity-provider",
                name: string, constraint: string }
CapabilityDecl{ id: Id<DEP>, capability: CapabilityName,
                target?: Ref<DEP>, access: "serve" | "read" | "emit" | "none" }

Defaultable<T> = { value: T, origin: "source", id?: Id }
               | { value: T, origin: "default", rule: string }
```

Every section except `Application` is implicitly `enabled` exactly when it
has content. There is no `enabled` flag that can disagree with the content.

## 5. Trace

```text
Trace {
  irVersion: "1.0",
  sourceHash: Hash,
  nodes: { <nodeId>: { file, startLine, endLine, sourceText, description? } },
  prose: [ { file, startLine, endLine, text } ],     # non-normative prose, in file order
  defaults: [ { nodeId, rule } ]
}
```

`nodeId` is a requirement id or a node path. `traceHash` is computed over
this document. The trace is the only place where source order and positions
are kept.

## 6. Hashes

- `irHash = sha256(JCS(ir.json))`
- `traceHash = sha256(JCS(trace.json))`
- Both use the `sha256:<lowercase hex>` form.
- `irHash` is computed on the **resolved** IR, after stage 6 of
  [COMPILER.md](COMPILER.md).

## 7. Versioning and evolution

`irVersion` is `MAJOR.MINOR`.

| Change | Version bump | Rule |
|---|---|---|
| New optional field whose absence means exactly the old meaning | MINOR | Old IR stays valid and hashes identically |
| New enum value | MINOR | Old IR never contains it |
| Any change of meaning, required field, rename, removal, or type change | MAJOR | Requires a pure, tested migration `migrate_ir(N → N+1)` |

- A compiler emits exactly one `irVersion`.
- Tools that read IR from older releases (`diff`, `explain`) migrate it
  forward. They never interpret an old IR with new semantics.
- Because the IR is persisted in release bundles, it is a public contract. The
  JSON Schema and the Python types are checked against each other in CI.

## 8. Semantic diff support

Because nodes have stable ids, typed values and order-independent
collections, the diff of two IRs is a structural comparison keyed by id with
no heuristics. See [SEMANTIC-DIFF.md](SEMANTIC-DIFF.md).

## 9. Derived views: Policy Contract and capability manifest

Two stable, typed views are defined over the IR as **pure functions**. They
are contracts in their own right ([POLICY.md](POLICY.md)), but they are *not*
additional sources of truth. They are never stored in `ir.json` and never
contribute to `irHash`:

| View | Function | Consumed by | Serialized as |
|---|---|---|---|
| SDC Policy Contract 1 | `policyView(ir)` over `authentication`, `authorization`, `data`, `behavior.deniedAs`, `observability`, `deployment`, `dependencies` | Planner (lowering); verifier (independent recomputation); Cedar oracle translation | `artifact.policy` (`policyHash`) |
| Capability manifest 1 | `capabilityView(ir) = { granted: required(ir) ∩ declared(ir), denied: explicit none rows }` | Planner; verifier; host grant | `artifact.capabilities` (`capabilityHash`) |

`required(ir)` is computed from the program: which operations exist, which
stores they read, and whether logs or metrics are enabled. It is never taken
from configuration. The planner and the verifier each implement these
functions, and agreement between them is a static verification obligation
([VERIFICATION.md §9](VERIFICATION.md#9-execution-substrate-verification)).

## 10. Relationship to the MVP IR

| MVP (`sdc_ir.model`) | IR 1.0 |
|---|---|
| `schema_version: "0.1"` (and a separate unused `IR_SCHEMA_VERSION`) | `irVersion: "1.0"` (single constant, schema-backed) |
| Mutable dataclasses | Frozen types |
| `Endpoint.entity` inferred by singularizing the path | `Operation.resource` declared, `Ref<DATA>` |
| `AuthorizationRule.predicate: dict` | Closed `Condition` union |
| `notes`, `description` in hashed IR | In `trace.json` only |
| `SecurityRequirement.id` = heuristic check name | Declared `SEC-NNN` + closed `property` |
| `Field.sensitive: bool` | `Field.classification: standard \| personal \| secret` |
| No capabilities | `Dependencies.capabilities` + derived capability manifest |
| `BehaviorRule(condition, status)` with invented defaults | `Outcome` with `origin` and default rule |
| `TestCase.request: dict`, invented `tenant t1 / role user` | Typed `Principal`, declared fixtures, `verifies` links |
| `Performance.p99_latency_ms`, `min_rps` | `PerfTarget` set with ids and criticality |
