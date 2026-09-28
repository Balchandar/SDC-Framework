# Policy Contract and Capability Model

Status: **FROZEN — SDC Policy Contract 1, capability manifest 1,
`sdc:runtime@1.0.0` WIT world (shape).** Governing ADRs:
[ADR-0016](ADR/0016-wasm-execution-substrate.md),
[ADR-0017](ADR/0017-policy-contract-and-capability-manifest.md).

SDC compiles two different kinds of control from the specification, and it
never confuses them:

| | **Authorization** | **Capability security** |
|---|---|---|
| Question | *May this principal do this to this resource?* | *May this program perform this kind of effect at all?* |
| Example | "Clinicians may search patient records." | "This program may read `PatientDB`. It may not touch the filesystem." |
| Subject | A request's principal | The compiled program (the engine instance running this artifact) |
| Decided | Per request, from data (roles, tenant, attributes) | Once, at load (grant set), enforced on every call |
| Source | `authentication.md`, `authorization.md`, `data.md`, `behavior.md` | `dependencies.md` → Capabilities table |
| Compiled to | `artifact.policy` (the SDC Policy Contract) | `artifact.capabilities` (the capability manifest) |
| Enforced by | Host policy decision point (PDP) plus data-access scoping | Host linker (what exists) and capability layer (what is granted) |
| Failure mode | `unauthenticated` / `forbidden` / `notFound` outcome | Instantiation failure, or a `denied` error plus an audit event |

Both are needed. Authorization alone cannot stop a defective program from
reading data outside any request. Capabilities alone cannot express "only
clinicians".

---

## 1. Principles

1. **The SDC Policy Contract is authoritative.** Its semantics are defined by
   SDC, in this document. Any policy engine is an *implementation* of those
   semantics, never their definition.
2. **Policies are compiled from source, never authored in a policy
   language.** Users do not write Rego or Cedar.
3. **Default deny** everywhere: authorization, capabilities and network.
4. **Enforcement lives in the host** (INV-29). The engine component asks and
   the host decides.
5. **There is no policy-backend plugin architecture.** There is one contract,
   one reference evaluator, and verification oracles. The engine choice
   behind the contract is recorded in ADR-0017 and can change only through an
   ADR.

## 2. The SDC Policy Contract

The Policy Contract is a **typed, lossless view over the Semantic IR**. It is
computed by a pure function `policyView(ir)` and is **not stored twice** in
`ir.json` ([SEMANTIC-IR.md §10](SEMANTIC-IR.md#9-derived-views-policy-contract-and-capability-manifest)).
The planner serializes it into `artifact.policy`. The verifier recomputes it
independently from the IR and compares.

```text
PolicyContract {
  version: 1
  authentication: AuthenticationPolicy
  authorization:  AuthorizationPolicy
  dataAccess:     DataAccessPolicy
  audit:          AuditPolicy
  network:        NetworkPolicy
  capability:     CapabilityPolicy          # = the capability manifest (§4)
}

AuthenticationPolicy {
  scheme: "none" | "bearer-jwt", algorithm?: "HS256", secret?: SecretName,
  issuer?, audience?,
  claims: [ { claim, mapsTo, required, derivedFrom } ]   # missing required claim ⇒ unauthenticated
}

AuthorizationPolicy {
  model: "rbac" | "rbac-tenant", default: "deny",
  roles: [RoleName],
  rules: [ { id, effect: "allow"|"deny", role|"any", action: "read"|"search"|"any",
             resource: EntityId|"any", condition: Condition } ],
  deniedAs: "forbidden" | "notFound"
}

DataAccessPolicy {
  entities: [ { id, store: DependencyId, key: FieldName, tenant?: FieldName,
                fields: [ { name, classification: "standard"|"personal"|"secret" } ] } ],
  operations: [ { id, entity, access: "get"|"list"|"search",
                  criteria?: [ { parameter, field, match: "exact"|"prefix-ci" } ],
                  maxResults?: int, projection: [FieldName] } ]
}

AuditPolicy {
  decisions: "required" | "none",
  fields: [ObsField],                         # closed vocabulary (SPECIFICATION §5.10)
  neverLogged: ["personal", "secret"]         # fixed in contract 1; not configurable
}

NetworkPolicy {
  inbound:  { port: int },
  outbound: [ { dependency: DependencyId, purpose: "store" } ],   # nothing else
  default: "deny"
}
```

### 2.1 Authorization semantics (normative)

For a request with principal *p*, action *a* and resource *r* (an entity
instance, or an entity scope for `list` / `search`):

```text
match(rule) ≡ (rule.role = "any" ∨ rule.role = p.role)
            ∧ (rule.action = "any" ∨ rule.action = a)
            ∧ (rule.resource = "any" ∨ rule.resource = entityOf(r))
            ∧ cond(rule.condition, p, r)

allowed(p, a, r) ≡ ¬∃ deny rule d: match(d)  ∧  ∃ allow rule l: match(l)
```

Conditions (contract 1):

| Condition | `cond` | For list/search scopes |
|---|---|---|
| `always` | true | true |
| `same-tenant` | `p.tenant = r[tenantField]` | the store query is filtered to `tenantField = p.tenant` |
| `cross-tenant` | `p.tenant ≠ r[tenantField]` | a deny that can never match a same-tenant-filtered row, and is asserted per row |
| `attr-contains(a, f)` | `r[f] ∈ p.attr[a]` | filter `f IN p.attr[a]` |

Properties: evaluation is order-independent, terminating and side-effect free,
and a missing attribute makes a condition **false** (it never defaults).
Decisions return the ids of the matching rules for audit.

### 2.2 Data classification (amends sdc/1 `Sensitive`)

| Classification | Returned by operations | Logged / in metrics | Enters the engine |
|---|---|---|---|
| `standard` | Yes, to authorized requests | Only via closed-vocabulary fields (never raw values) | Yes |
| `personal` | Yes, to authorized requests | **Never** | Yes (projected rows only) |
| `secret` | **Never** | **Never** | **Never.** The host drops the field before the row reaches the engine |

The sdc/1 `Sensitive: yes` of the v1 freeze corresponds to `secret`. The
`personal` level is new: healthcare and similar domains need data that
authorized users see but that must never reach logs. v1 could not express
that distinction ([ADR-0017](ADR/0017-policy-contract-and-capability-manifest.md)).

## 3. Policy engines: OPA and Cedar

Each was evaluated independently against the contract above.

| Criterion | OPA (Rego) | Cedar |
|---|---|---|
| Authorization model | General-purpose policy over arbitrary JSON input and data (Datalog-inspired) | Purpose-built: principal / action / resource / context, RBAC + ABAC, `permit` / `forbid` |
| Fit to SDC semantics | Must *encode* deny-precedence and default deny as Rego conventions | **Native**: default deny, and `forbid` overrides `permit`, match §2.1 exactly |
| Expressiveness | Very high (comprehensions, many builtins). A general computation surface: a risk for SDC (K1) | Deliberately bounded. Enough for RBAC/ABAC conditions and set membership |
| Embedding model | Go library, a sidecar service, or a compiled Wasm module that needs host-implemented builtins | A Rust crate (`cedar-policy`) that embeds directly in a Rust host. `cedar-wasm` also exists |
| Wasm support | `opa build -t wasm`: "The core language is supported fully but there are a number of built-in functions that are not, and probably won't be natively supported in Wasm (e.g., `http.send`)", which must then be host-implemented | Native Rust, so it compiles to Wasm (`cedar-wasm`), or runs natively in the host |
| Performance | Fast for typical policies; depends on policy structure | "Designed to be indexed … bounded latency" (Cedar README) |
| Determinism | Nondeterministic builtins exist (`time.now_ns`, `http.send`, `rand.*`) and would have to be banned | No I/O and no clock in the language; evaluation over supplied entities is deterministic |
| Policy portability | Rego is widely used across infrastructure domains | Cedar is used for application authorization and is open source (Apache-2.0) |
| Auditability / analysis | Testing and coverage tooling; limited formal analysis | **Analyzable by design**: a schema validator, plus a symbolic compiler (`cedar-policy-symcc`) that proves properties with counterexamples. Formal model in Lean with differential randomized testing against the Rust implementation (`cedar-spec`) |
| Versioning | Rego v0 → v1 syntax migration history; builtin set changes by version | Versioned language and crates; schema-validated |
| Security model | Powerful builtins (network, crypto) must be controlled by the embedder | No builtins with external effects |
| Operational complexity | Bundles, a data API and a server are optional but typical | A library call; no services |

### Decision

1. **Neither engine is hard-coded as the runtime evaluator in contract 1.**
   The contract-1 semantics (§2.1) are small, total and fully specified. The
   host's reference PDP implements them directly: an evaluator of roughly a
   hundred lines, conformance-tested. Adding an engine now would add a second
   semantics to keep in sync, without adding expressiveness that contract 1
   uses.
2. **Cedar is the preferred engine**, and it is adopted **now as an
   independent verification oracle**. The verifier translates the *IR*
   (independently of the planner) into Cedar policies and a Cedar schema,
   validates them with Cedar's validator, and evaluates the full permission
   matrix with Cedar. Any disagreement with the runtime's decisions is `FAIL`.
   Symbolic property checks (for example, "no request with role ≠
   `clinician` is permitted `search` on `Patient`") run through
   `cedar-policy-symcc` if experiment E5 confirms fitness. This is SDC's
   strongest mitigation of the common-mode risk K3 for authorization.
3. **Cedar is the designated path for richer conditions** (U1). When the
   vocabulary needs ABAC conditions beyond contract 1, SDC adopts Cedar's
   condition semantics, and the Cedar evaluator becomes the host PDP by
   ADR, instead of inventing an SDC expression language.
4. **OPA is not selected** for SDC application authorization. Its generality
   is exactly the unbounded surface SDC must avoid, and its Wasm form requires
   host-implemented builtins and bans on nondeterministic ones. OPA remains a
   reasonable choice **outside SDC** (for example, cluster admission control
   that checks SDC release statements), and the in-toto statement format
   supports that without SDC depending on OPA.

Answer to the five options asked: (1) OPA: no. (2) Cedar: yes, as the
verification oracle now and the future PDP. (3) Prefer Cedar. (4) Not both.
(5) Neither hard-coded into the runtime yet.

## 4. Capability model

### 4.1 Source declaration

Capabilities are declared in `dependencies.md` (sdc/1 amendment; see
[SPECIFICATION.md §5.13](SPECIFICATION.md#513-dependencies-dep)):

```markdown
## Capabilities

| ID      | Capability       | Target    | Access |
|---------|------------------|-----------|--------|
| DEP-010 | store            | PatientDB | read   |
| DEP-011 | http.inbound     | -         | serve  |
| DEP-012 | log              | -         | emit   |
| DEP-013 | metrics          | -         | emit   |
| DEP-020 | filesystem       | any       | none   |
| DEP-021 | network.outbound | any       | none   |
```

| Capability | Legal `Access` in contract 1 | Host interface |
|---|---|---|
| `http.inbound` | `serve` | Host HTTP server → engine `handler` export |
| `store` | `read` (`write` reserved) | `sdc:runtime/store` |
| `log` | `emit` | `sdc:runtime/log` |
| `metrics` | `emit` | `sdc:runtime/metrics` |
| `filesystem`, `network.outbound`, `process`, `environment`, `clock`, `random`, `secrets` | **`none` only.** A grant is an `ERROR`, because no such capability exists in runtime contract 1 | *none* |

Capability rows are **critical** requirements: they are always verified and
never waivable ([VERIFICATION.md §6](VERIFICATION.md#6-criticality-and-release-policy)).

### 4.2 Compilation

```text
required(program)  = { http.inbound  if api has operations,
                       store(D, read) for each store D read by an operation,
                       log           if observability.logs,
                       metrics       if observability.metrics = prometheus }
declared(source)   = grant rows of the Capabilities table
denied(source)     = rows with Access = none

required ⊄ declared            → ERROR   SDC-R030 capability required but not declared
declared \ required ≠ ∅        → WARNING SDC-A030 unused grant (not emitted: least privilege)
artifact.capabilities.granted  = required ∩ declared
artifact.capabilities.denied   = denied(source)   (documentation + verification obligations)
```

The compiler never infers a grant. A required capability that is missing is
an error, so the author must state it and the reviewer sees it.

### 4.3 Runtime grant

```text
grant = artifact.capabilities.granted ∩ trustConfig.capabilityCeiling
if grant ≠ artifact.capabilities.granted  → REFUSE_POLICY (the operator ceiling forbids a declared grant)
```

- The **host linker defines only the `sdc:runtime` interfaces**. It never
  calls `wasmtime_wasi::add_to_linker` or any equivalent. A component
  importing anything else fails to instantiate.
- The engine imports every `sdc:runtime` effect interface (it is one fixed
  component). For effect interfaces that are **not granted**, the host links a
  **deny implementation**: every call returns `error(denied)` and emits the
  audit event `capability.denied{capability, requirement}`. In verify mode,
  such an event fails the run, because a correct engine never calls an
  ungranted capability.
- The `store` grant is further scoped by target: the host opens connections
  only to granted store dependencies, and only for the entities bound to
  them.

### 4.4 The `sdc:runtime@1.0.0` WIT world (shape)

This shape is frozen here. The exact WIT text is frozen in roadmap phase 11a,
before any implementation, and changes to it require an ADR.

```wit
package sdc:runtime@1.0.0;

interface types {
  type operation-id = string;          // "API-001"; host validates ∈ artifact
  record param { name: string, value: string }
  record request-context { request-id: string, operation: operation-id, params: list<param>, body: list<u8> }
  record response { outcome: outcome, body: list<u8> }
  enum outcome { success, unauthenticated, forbidden, not-found, invalid-request, unavailable, internal-error }
  variant field-value { str(string), int(s64), %bool(bool) }
  record row { fields: list<tuple<string, field-value>> }   // already projected by the host
}

interface artifact {                    // kernel: always linked, no effect
  bytes: func() -> list<u8>;            // the verified canonical artifact
}

interface policy {                      // kernel: host PDP; always linked
  use types.{operation-id};
  resource principal;                   // opaque; created by host authentication
  resource decision;                    // unforgeable proof of an allow, scoped to (principal, operation, target)
  variant target { entity-key(string), entity-scope }
  variant denial { unauthenticated, denied }   // host applies deniedAs; no existence oracle
  authorize: func(p: borrow<principal>, op: operation-id, t: target) -> result<decision, denial>;
}

interface store {                       // effect: requires a store grant
  use types.{row, param};
  use policy.{decision};
  enum store-error { denied, unavailable, invalid-criteria }
  get:    func(d: borrow<decision>) -> result<option<row>, store-error>;
  list:   func(d: borrow<decision>) -> result<list<row>, store-error>;
  search: func(d: borrow<decision>, criteria: list<param>) -> result<list<row>, store-error>;
}

interface log {                         // effect: requires the log grant
  use types.{operation-id, outcome};
  variant log-field {                   // closed vocabulary; no free-form keys or values
    operation(operation-id), outcome(outcome), authz-rules(list<string>),
    requirement(string), latency-us(u64)
  }
  emit: func(event: string, fields: list<log-field>);   // event ∈ fixed set; host validates
}

interface metrics {                     // effect: requires the metrics grant
  use types.{operation-id, outcome};
  observe: func(op: operation-id, o: outcome, latency-us: u64);
}

world engine {
  import artifact;
  import policy;
  import store;
  import log;
  import metrics;
  export handler: interface {
    use types.{request-context, response};
    use policy.{principal};
    handle: func(p: option<principal>, ctx: request-context) -> response;
  }
}
```

Notable properties:

- **No secrets interface.** The JWT key and DB credentials are consumed by the
  host. The engine never sees a secret.
- **No clock or random interfaces.** Contract 1 does not need them in the
  engine. Timestamps and request ids are host-generated.
- **Logging cannot carry patient data.** Keys are a closed variant. Values
  are ids and enums that the host validates against the artifact, plus an
  integer latency. There is no free-text field.
- **Rows arrive projected.** `secret` fields never leave the host.
- **The request id, principal id and tenant** are attached to log records by
  the host, not by the engine.

## 5. Where each control is enforced

| Control | Compiled into | Enforced by | Engine can bypass? |
|---|---|---|---|
| Authentication | `policy.authentication` | Host (before the engine is invoked) | No: the engine receives an opaque principal or none |
| Authorization | `policy.authorization` | Host PDP (`policy.authorize`) | No: data is reachable only with a `decision` |
| Tenant scoping, projection, classification | `policy.dataAccess` | Host store capability | No: filters and projection are applied host-side |
| Existence hiding (`deniedAs`) | `policy.authorization.deniedAs` | Host (`denial` never reveals existence) | No |
| Audit logging | `policy.audit` | Host log capability (validation and redaction) | No: closed vocabulary |
| Network | `policy.network` | Host (no sockets in the engine; drivers connect only to granted stores) | No |
| Effect capabilities | `capabilities` | Host linker plus deny stubs | No |
| Outcome mapping, parameter validation, response rendering | Artifact operations | Engine | Yes, but only within its grants. A defect here is caught by dynamic verification, not by enforcement |

## 6. Integrity

The policy and capability manifest are **sections of the artifact**, so
changing either one changes `artifactHash` and the release is refused
(`REFUSE_INTEGRITY`). Their sub-hashes (`policyHash`, `capabilityHash`)
appear in the signed statement to make audits and diffs precise. Derived
encodings (the Cedar translation used by the verifier) are hashed into the
evidence and never executed by the runtime.

---

## 7. Critical design test: patient search

### 7.1 Source (sdc/1 as amended)

`api.md`:

```markdown
# API

### GET /patients {#API-001}
Operation: search
Resource: Patient
Authentication: required
Max-Results: 50
Criteria: at-least-one

| Parameter | Field       | Match     |
|-----------|-------------|-----------|
| mrn       | mrn         | exact     |
| name      | family_name | prefix-ci |
```

The prose "Search supports MRN and name" alone would **not** compile. A
`search` operation without a criteria table is `ERROR SDC-S031`, because the
combination rule and match semantics would otherwise be guesses. The table
makes them explicit: supplied parameters are combined with AND, at least one
is required, and `name` is a case-insensitive prefix match on `family_name`.

`authorization.md`:

```markdown
# Authorization

Model: rbac-tenant
Default: deny
Audit: required

| Role         | Description             |
|--------------|-------------------------|
| clinician    | Licensed clinical staff |
| receptionist | Front-desk staff        |

| ID        | Effect | Role      | Action | Resource | Condition    |
|-----------|--------|-----------|--------|----------|--------------|
| AUTHZ-001 | allow  | clinician | search | Patient  | same-tenant  |
| AUTHZ-002 | deny   | any       | any    | any      | cross-tenant |
```

`data.md`:

```markdown
# Data

Store: sql
Store-Dependency: DEP-001

### Patient {#DATA-001}

| Field         | Type   | Key | Tenant | Classification | Nullable |
|---------------|--------|-----|--------|----------------|----------|
| id            | string | yes | no     | standard       | no       |
| tenant_id     | string | no  | yes    | standard       | no       |
| mrn           | string | no  | no     | personal       | no       |
| family_name   | string | no  | no     | personal       | no       |
| given_name    | string | no  | no     | personal       | no       |
| date_of_birth | string | no  | no     | personal       | no       |
| ssn           | string | no  | no     | secret         | yes      |
```

`behavior.md`: the Outcomes table maps `unauthenticated` → 401,
`forbidden` → 403, `invalid-request` → 400 and `success` → 200.

`security.md`:

```markdown
| ID      | Requirement                                     | Property               |
|---------|-------------------------------------------------|------------------------|
| SEC-001 | Only clinicians may search patient records.     | authorization-enforced |
| SEC-002 | Patient information must not be logged.         | no-sensitive-logging   |
| SEC-003 | Patient records never cross tenants.            | tenant-isolation       |
```

`dependencies.md`: `| DEP-001 | store | PatientDB | postgres >=15 |`, plus the
Capabilities table of §4.1. The sentences "The application may access the
patient database" and "may not access arbitrary filesystem paths" become rows
`DEP-010` and `DEP-020`. Left as prose, they would trigger `UNRESOLVED
SDC-S010` (the normative-prose rule).

### 7.2 Compiled outputs

IR (excerpt): `api.operations[API-001] = {kind: search, resource: DATA-001,
criteria: [...], maxResults: 50}`,
`authorization.rules = [AUTHZ-001, AUTHZ-002]`,
`dependencies.capabilities = [DEP-010 … DEP-021]`.

`artifact.policy.authorization`:

```json
{ "model": "rbac-tenant", "default": "deny", "deniedAs": "forbidden",
  "roles": ["clinician", "receptionist"],
  "rules": [
    { "id": "AUTHZ-001", "effect": "allow", "role": "clinician", "action": "search",
      "resource": "DATA-001", "condition": { "kind": "same-tenant" } },
    { "id": "AUTHZ-002", "effect": "deny", "role": "any", "action": "any",
      "resource": "any", "condition": { "kind": "cross-tenant" } } ] }
```

`artifact.capabilities`:

```json
{ "granted": [
    { "id": "DEP-010", "capability": "store", "target": "DEP-001", "access": "read", "entities": ["DATA-001"] },
    { "id": "DEP-011", "capability": "http.inbound", "access": "serve" },
    { "id": "DEP-012", "capability": "log", "access": "emit" },
    { "id": "DEP-013", "capability": "metrics", "access": "emit" } ],
  "denied": [
    { "id": "DEP-020", "capability": "filesystem" },
    { "id": "DEP-021", "capability": "network.outbound" } ] }
```

`artifact.policy.dataAccess.operations[API-001].projection =
[date_of_birth, family_name, given_name, id, mrn, tenant_id]` (`ssn` is
excluded as `secret`).

Release: the artifact, IR and trace, evidence, and a statement naming
`artifactHash`, `policyHash`, `capabilityHash`, `engineHash`, `hostHash`, …,
signed.

### 7.3 Runtime

```text
Engine instance (sdc-engine, engineHash E)
 ├── policy / artifact (kernel)        LINKED
 ├── store  → PatientDB (read)         ALLOWED   (DEP-010)
 ├── log                               ALLOWED   (DEP-012)
 ├── metrics                           ALLOWED   (DEP-013)
 ├── patient search (API-001)          ALLOWED   for role clinician, same tenant (AUTHZ-001)
 └── filesystem / sockets / env        DENIED    not imported by the engine; not defined by the host
```

Request `GET /patients?name=smi` by a receptionist:

1. The host authenticates the JWT with its secret, creates `principal
   {role: receptionist, tenant: t1}` and invokes `handle`.
2. The engine validates the parameters against `criteria`. OK.
3. The engine calls `policy.authorize(p, API-001, entity-scope)`. The host PDP
   finds no allow for `receptionist` and returns `denial::denied`.
4. The engine maps the result to the `forbidden` outcome (403). The host logs
   `{operation: API-001, outcome: forbidden, authz-rules: []}` plus the host
   fields, and **no query values**.

The same request by a clinician: `authorize` yields a `decision` scoped to
tenant t1 with the projection above. `store.search(decision, [name=smi])`
makes the host run its fixed parameterized template (`WHERE tenant_id = $1
AND lower(family_name) LIKE lower($2) || '%' LIMIT 50`) and return projected
rows. The engine renders them with outcome 200.

### 7.4 Verification (independent)

| Obligation | Method | Demonstrates |
|---|---|---|
| `AUTHZ-001/dynamic/1..2` | dynamic | A clinician in the same tenant gets `success`; a clinician in another tenant gets rows only from their own tenant |
| `SEC-001/dynamic/1..n` | dynamic | **Every** other role (receptionist, unknown role, no role claim) gets `forbidden`; no token gets `unauthenticated` |
| `SEC-001/oracle/1` | static (Cedar) | The verifier's own Cedar translation of the IR agrees with the runtime on the full matrix. Where E5 confirms fitness, `symcc` proves that no permitted `search` has role ≠ clinician |
| `SEC-002/dynamic/1` | dynamic | After searches that use fixture PHI values (`mrn`, names), none of those values appear in captured logs or metrics |
| `SEC-002/trace/1` | dynamic (trace) | Every `log.emit` call in the capability trace used vocabulary fields only |
| `SEC-003/dynamic/*` | dynamic | Cross-tenant fixtures are never returned |
| `DATA-001/static/1` | static | The projection excludes `secret` (`ssn`); `personal` fields are marked never-logged in `policy.audit` |
| `DEP-010/static/1` | static | The store grant equals the required set recomputed from the IR |
| `DEP-010/trace/1` | dynamic (trace) | Every store call carried a host-issued decision; no store call occurred for denied requests |
| `DEP-020/static/1`, `DEP-021/static/1` | static | The engine component's import list contains no filesystem, socket, CLI or environment interface. `engineHash` is in the allowlist |
| `DEP-020/conformance`, `DEP-021/conformance` | cited | Runtime conformance `CAP-DENY-FS` and `CAP-DENY-NET` passed for this `runtimeHash` (a hostile component that imports them fails to instantiate) |
| Integrity | cited | Conformance `LOAD-TAMPER-ENGINE`, `LOAD-TAMPER-POLICY` and `LOAD-TAMPER-ARTIFACT` passed for this `runtimeHash` |
| Release gate | policy | If any `SEC-*` or `DEP-*` row is `UNVERIFIED` → `NOT_RELEASABLE`. The production loader refuses it (`LOAD-POLICY-UNVERIFIED`) |
