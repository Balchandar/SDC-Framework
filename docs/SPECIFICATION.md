# SDC Specification Language (sdc/1)

Status: **FROZEN — language version `sdc/1`.** Governing ADRs:
[ADR-0002](ADR/0002-markdown-controlled-grammar.md),
[ADR-0004](ADR/0004-requirement-identifiers.md),
[ADR-0005](ADR/0005-ambiguity-is-an-error.md),
[ADR-0017](ADR/0017-policy-contract-and-capability-manifest.md).

> **Amendment (2026-09-24, ADR-0017, before any implementation).** sdc/1
> gains: the `search` operation and action (§5.2, §5.4); data
> `Classification` replacing `Sensitive` (§5.5); `Store-Dependency` (§5.5);
> and the **Capabilities** table (§5.13). No sdc/1 document or compiler
> existed before the amendment, so no meaning changed for any existing
> source.

SDC source is ordinary Markdown. A human or an LLM can read and write it
without learning a programming language. Meaning, however, is carried only by
a small set of **structural forms** with a fixed grammar. Prose is always
allowed and never changes meaning.

---

## 1. Source set

A project is a directory containing `sdc.toml` and Markdown files.

**Source-set membership is fixed by this specification and cannot be
configured.** It is exactly the set of files in the project root (not
recursive) whose name is either:

- `<section>.md`, or
- `<section>.<fragment>.md` where `<fragment>` matches `[a-z0-9-]+` (for
  example `api.customers.md` for large APIs),

where `<section>` is one of the 13 section names below. Every other `.md` file
(for example `README.md`) is **not** a source and is listed as `INFO` by
`sdc check`. The `.sdc/` directory holds tool metadata (the AI ledger) and is
never a source.

| File | Section | Id prefix | Required |
|---|---|---|---|
| `application.md` | Application | `APP` | **yes** |
| `api.md` | API | `API` | if any operation is exposed |
| `authentication.md` | Authentication | `AUTHN` | if any operation requires authentication |
| `authorization.md` | Authorization | `AUTHZ` | if authentication is present |
| `data.md` | Data | `DATA` | if any operation references a resource |
| `behavior.md` | Behavior | `BEH` | if `api.md` exists |
| `security.md` | Security | `SEC` | no |
| `performance.md` | Performance | `PERF` | no |
| `reliability.md` | Reliability | `REL` | no |
| `observability.md` | Observability | `OBS` | no |
| `deployment.md` | Deployment | `DEPL` | for `release` builds |
| `testing.md` | Testing | `TEST` | no |
| `dependencies.md` | Dependencies | `DEP` | no |

Fragments of a section are concatenated in byte order of their file names,
after the base file. Because all IR collections are order-independent
(INV-06), the order never changes meaning. It only affects diagnostic
positions.

**Encoding.** Files must be UTF-8. A leading BOM is ignored. CRLF is treated as
LF for parsing. Text values are NFC-normalized. Hashing (`sourceHash`) uses the
**raw bytes**, so projects should commit `.gitattributes` containing
`*.md text eol=lf`.

## 2. Document structure

Every source file has exactly this shape:

```markdown
# <Section Name>

<preamble: Key: Value lines and prose>

<tables, item headings, prose, blockquotes — in any order>
```

- The first heading must be a level-1 heading naming the section of the file
  (case-insensitive, exact name, **no aliases**). A mismatch is an `ERROR`.
- Only one level-1 heading is allowed per file.
- `application.md` must also declare `Language: sdc/1`.

## 3. Semantic carriers

Meaning is carried **only** by these four forms. Anything else is prose.

### 3.1 Key–value lines

`Key: Value` at the start of a line, in the section preamble (before the first
table or item heading) or directly under an item heading.

- Keys are case-insensitive, and each section defines the only valid keys.
  **An unknown key is an `ERROR`**, which catches typos such as `Defualt: deny`.
- A key repeated with the same value gets a `WARNING`. Repeated with a
  different value, it is `AMBIGUOUS`.
- Values come from closed vocabularies wherever a vocabulary is defined. Words
  such as `yes`/`no` are exact tokens; `maybe` or `usually` is `AMBIGUOUS`.

### 3.2 Tables

GitHub pipe tables. A section defines table schemas identified by their exact
header set.

- Header matching is case-insensitive and ignores surrounding whitespace.
- A table whose header set matches no schema **and** that contains a normative
  keyword (see §3.4) is `UNRESOLVED`. Otherwise it is prose.
- A missing required column is an `ERROR`, and so is an unknown column in a
  recognized table. An empty required cell is an `ERROR`. An empty optional
  cell means "absent" and never means a default unless §5 lists one.

### 3.3 Item headings

Level-3 headings that declare an item with attributes:

```markdown
### GET /customers/{id} {#API-001}
Operation: read-one
Resource: Customer
Authentication: required
```

- The `{#ID}` suffix declares the requirement id.
- The key–value lines directly under the heading, up to the next blank-line
  paragraph, table or heading, belong to the item.
- A table that directly follows an item's key–value lines, before any other
  heading, belongs to the item when the section grammar defines an item table
  for it (for example the search **Criteria** table, §5.2).

### 3.4 The normative-prose rule

Prose is non-normative: it goes into the trace as description and never into
the semantic IR. Silence must not hide a requirement, though. Any prose
sentence in a section that contains a **normative keyword**
(case-insensitive: `must`, `must not`, `shall`, `shall not`, `never`,
`always`, `required`, `forbidden`, `may only`, `only`, `cannot`, `should`)
and is not inside a semantic carrier produces:

```text
UNRESOLVED SDC-S010  security.md:7  normative statement is not bound to a requirement
  "Tokens must never appear in URLs."
  hint: add a row to the Requirements table, or mark the sentence non-normative
        by putting it in a blockquote ("> ...").
```

Blockquotes (`> …`), fenced code blocks, HTML comments and link reference
definitions are always non-normative and are exempt. This rule is what stops
an LLM-written sentence from silently becoming, or silently failing to become,
behavior.

## 4. Requirement identifiers

- Format: `^(APP|API|AUTHN|AUTHZ|DATA|BEH|SEC|PERF|REL|OBS|DEPL|TEST|DEP)-[0-9]{3,}$`
- Declared in source: as the `ID` column of a table, or as `{#ID}` on an item
  heading.
- The prefix must match the section, otherwise `ERROR`. Ids are unique across
  the project, otherwise `ERROR`.
- A missing id is an `ERROR`. `sdc check --assign-ids` writes missing ids into
  the source deterministically (the next free number per prefix, in file then
  line order). That is a visible, reviewable edit. The compiler never assigns
  ids silently.
- An id identifies a requirement for its whole life. Renaming the entity or
  changing the wording keeps the id. Deleting a requirement retires its id,
  and ids must not be reused ([ROADMAP.md](ROADMAP.md#risks-and-unresolved-decisions)
  covers enforcement of this).

## 5. Section grammar

`R` = required, `O` = optional. Vocabularies are closed in `sdc/1`, and
extending them is a language change (`sdc/1.x`).

### 5.1 Application (`APP`)

| Key | R/O | Value |
|---|---|---|
| `Language` | R | `sdc/1` |
| `Name` | R | `[A-Za-z][A-Za-z0-9-]{0,63}` |
| `Version` | R | SemVer 2.0 |
| `Id` | R | `APP-NNN` (the application requirement) |
| `Description` | O | prose (trace only) |

### 5.2 API (`API`)

Preamble keys: `Base-Path` (O, default `/`).

Items: `### <METHOD> <path-template> {#API-NNN}`

| Key | R/O | Value |
|---|---|---|
| `Operation` | R | `read-one` \| `read-list` \| `search` (sdc/1) |
| `Resource` | R | an entity name declared in `data.md`. **Never inferred from the path.** |
| `Authentication` | R | `required` \| `none` |
| `Key-Parameter` | R for `read-one` | a path parameter name that maps to the resource key |
| `Criteria` | R for `search` | `at-least-one` \| `all` (whether each request must supply at least one, or all, criteria parameters) |
| `Max-Results` | R for `search` and `read-list` | integer, 1–1000 |
| `Summary` | O | prose (trace) |

Item table **Criteria** (required for `search`) — `| Parameter | Field | Match |`

- `Parameter`: a query parameter name `[a-z][a-z0-9_]*`
- `Field`: a field of the resource entity
- `Match` ∈ `exact` \| `prefix-ci` (case-insensitive prefix)
- The supplied criteria are combined with **AND**. Unknown query parameters
  yield `invalid-request`.
- A `search` operation without this table is `ERROR SDC-S031`. Prose such as
  "search supports MRN and name" never defines search semantics.

The METHOD must be consistent with the operation: `read-*` and `search` ⇒
`GET`. Path parameters are `{name}` with `name` matching `[a-z][a-z0-9_]*`.

### 5.3 Authentication (`AUTHN`)

| Key | R/O | Value |
|---|---|---|
| `Id` | R | `AUTHN-NNN` |
| `Scheme` | R | `bearer-jwt` \| `none` |
| `Algorithm` | R if `bearer-jwt` | `HS256` (sdc/1); `RS256`/`EdDSA` reserved |
| `Secret` | R if `HS256` | the name of a runtime secret, e.g. `JWT_SIGNING_KEY` |
| `Issuer`, `Audience` | O | string; enforced when present |

Table **Claims** — `| ID | Claim | Maps-To | Required |`

- `Maps-To` ∈ `principal.id` \| `principal.tenant` \| `principal.role` \|
  `principal.attr.<name>`
- `Required` ∈ `yes` \| `no`. A missing required claim yields the
  `unauthenticated` outcome. **A missing claim never defaults to a value.**

### 5.4 Authorization (`AUTHZ`)

| Key | R/O | Value |
|---|---|---|
| `Model` | R | `rbac-tenant` \| `rbac` |
| `Default` | R | `deny` (the only legal value in sdc/1; `allow` is an `ERROR`) |
| `Audit` | O | `required` \| `none` |

Table **Roles** — `| Role | Description |`: declares role names
(`[a-z][a-z0-9_]*`).

Table **Rules** — `| ID | Effect | Role | Action | Resource | Condition |`

- `Effect` ∈ `allow` \| `deny`
- `Role` is a declared role, or `any`
- `Action` ∈ `read` \| `search` \| `any` (`read-one` and `read-list` are `read`; `search` is `search`)
- `Resource` is a declared entity, or `any`
- `Condition` ∈ `always` \| `same-tenant` \| `cross-tenant` \|
  `attr-contains(<principal attr>, <entity field>)`

**Semantics (order-independent).** A request is allowed if and only if no
`deny` rule matches and at least one `allow` rule matches. Rule order has no
meaning.

Example (replaces the MVP's prose-only authorization):

```markdown
# Authorization

Model: rbac-tenant
Default: deny
Audit: required

A normal user sees their own tenant's customers; administrators see all of
their tenant's customers. Nothing crosses tenants.

| Role         | Description              |
|--------------|--------------------------|
| user         | Ordinary tenant member   |
| tenant_admin | Tenant administrator     |

| ID       | Effect | Role         | Action | Resource | Condition    |
|----------|--------|--------------|--------|----------|--------------|
| AUTHZ-001| allow  | user         | read   | Customer | same-tenant  |
| AUTHZ-002| allow  | tenant_admin | read   | Customer | same-tenant  |
| AUTHZ-003| deny   | any          | any    | any      | cross-tenant |
```

The prose paragraph uses no normative keyword, so it is accepted as a
description.

### 5.5 Data (`DATA`)

| Key | R/O | Value |
|---|---|---|
| `Store` | R | `sql` \| `fixture` (`fixture` is `WARNING` in release) |
| `Store-Dependency` | R if `sql` | the `DEP-NNN` id of a `store` dependency (§5.13) |
| `Transactions` | O | `required` \| `none` |

Items: `### <EntityName> {#DATA-NNN}` followed by the table
`| Field | Type | Key | Tenant | Classification | Nullable |`

- `Type` ∈ `string` \| `integer` \| `boolean` \| `timestamp`
- `Key`, `Tenant`, `Nullable` ∈ `yes` \| `no`, **all required**
- `Classification` ∈ `standard` \| `personal` \| `secret`, **required**
  ([POLICY.md §2.2](POLICY.md#22-data-classification-amends-sdc1-sensitive)):
  - `standard`: returned to authorized requests;
  - `personal`: returned to authorized requests, **never logged**;
  - `secret`: never returned, never logged, never passed to the engine.
- Exactly one `Key: yes` per entity. At most one `Tenant: yes`.
- A field whose name suggests a secret (`password`, `token`, `secret`, …)
  but is not classified `secret` gets a `WARNING`. It is never silently
  upgraded.

### 5.6 Behavior (`BEH`)

Table **Outcomes** — `| ID | Condition | Status |`

- `Condition` ∈ `success` \| `unauthenticated` \| `forbidden` \| `not-found` \|
  `invalid-request` \| `internal-error` \| `unavailable`
- `Status`: an integer HTTP status. A 2xx status is valid only for `success`,
  and a 4xx or 5xx status only for the other conditions.

Defaults (§7) exist only for `success` (200), `invalid-request` (400),
`internal-error` (500) and `unavailable` (503). `unauthenticated`, `forbidden`
and `not-found` are security-relevant and **must be declared** when reachable,
otherwise `ERROR`.

Key `Denied-As` (O): `forbidden` \| `not-found`. This is the outcome returned
when authorization denies access to a resource that exists. `not-found` avoids
cross-tenant existence disclosure. When it is absent and
`Model: rbac-tenant`, the compiler emits `WARNING SDC-A021 existence
disclosure`.

### 5.7 Security (`SEC`)

Table **Requirements** — `| ID | Requirement | Property | Criticality |`

- `Requirement`: prose (trace).
- `Property` ∈ `no-sensitive-exposure` (no `secret` field returned) \|
  `no-sensitive-logging` (no `personal` or `secret` value logged) \|
  `tenant-isolation` \| `authentication-enforced` \| `authorization-enforced` \|
  `authorization-audit` \| `injection-safe` \| `security-headers` \|
  `secrets-from-runtime` \| `custom`
- `Criticality` (O) ∈ `critical` only. Security requirements are always
  critical and cannot be lowered.
- `custom` requirements are `UNVERIFIED` unless a `testing.md` case lists them
  in `Verifies`. Because they are critical, an unverified custom requirement
  blocks a release.

### 5.8 Performance (`PERF`)

Table **Targets** — `| ID | Metric | Operation | Target | Unit | Criticality |`

- `Metric` ∈ `latency-p50` \| `latency-p99` \| `throughput`
- `Operation`: an `API-NNN` id, or `all`
- `Target`: an integer. `Unit` ∈ `ms` \| `rps`.
- `Criticality` ∈ `standard` (default) \| `advisory`

Key `Benchmark-Profile` (O): the name of the environment in which measured
evidence counts ([VERIFICATION.md](VERIFICATION.md#5-measured-evidence)).

### 5.9 Reliability (`REL`)

Table **Properties** — `| ID | Property | Value |`

- `Property` ∈ `request-timeout-ms` \| `max-request-bytes` \|
  `max-concurrency` \| `shutdown-grace-ms` \| `store-retry-attempts`
- `Value`: an integer

### 5.10 Observability (`OBS`)

| Key | R/O | Value |
|---|---|---|
| `Logs` | R | `structured-json` |
| `Metrics` | R | `prometheus` \| `none` |
| `Health` | R | `yes` \| `no` |

Table **Fields** — `| ID | Field |` with `Field` ∈ `request-id` \|
`tenant-id` \| `principal` \| `operation` \| `latency` \| `status` \|
`authz-decision` \| `requirement-id`

The release identity (`artifactHash`, `buildId`, application name and version)
is **always** emitted and is not configurable (INV-21).

### 5.11 Deployment (`DEPL`)

| Key | R/O | Value |
|---|---|---|
| `Id` | R | `DEPL-NNN` |
| `Platform` | R | `linux-x86_64` \| `linux-arm64` |
| `Packaging` | R | `container` \| `zipapp` \| `none` |
| `Port` | R | integer |

Table **Resources** — `| Resource | Limit |` with `Resource` ∈ `cpu-millis` \|
`memory-mb` \| `processes`

### 5.12 Testing (`TEST`)

Items: `### Fixtures: <EntityName>` followed by a table whose columns are
exactly the entity's fields. **Fixtures are never invented.** Dynamic
verification uses only declared fixtures.

Table **Cases** — `| ID | Operation | Principal | Target | Expect | Verifies |`

- `Operation`: `API-NNN`
- `Principal`: `anonymous`, or space-separated `role=<r> tenant=<t>
  [attr.<a>=<v>]`
- `Target`: a fixture key, or `absent:<key>` for a key that does not exist
- `Expect`: a behavior condition (`success`, `forbidden`, …), not a raw
  status code, so tests follow the outcome mapping
- `Verifies`: a comma-separated list of requirement ids. This is the
  explicit link from test to requirement.

### 5.13 Dependencies (`DEP`)

Table **Dependencies** — `| ID | Kind | Name | Constraint |`

- `Kind` ∈ `runtime` \| `store` \| `identity-provider`
- In SDC, a dependency is an **external service or runtime capability
  provider**, never a code library. Artifacts cannot import code.
- These are resolved into `sdc.lock` ([COMPILER.md](COMPILER.md#stage-6-resolve)).

Table **Capabilities** — `| ID | Capability | Target | Access |`
([POLICY.md §4](POLICY.md#4-capability-model))

- `Capability` ∈ `http.inbound` \| `store` \| `log` \| `metrics` \|
  `filesystem` \| `network.outbound` \| `process` \| `environment` \|
  `clock` \| `random` \| `secrets`
- `Access`: `serve` (`http.inbound`), `read` (`store`; `write` is reserved),
  `emit` (`log`, `metrics`), or `none` (an explicit denial). Every capability
  from `filesystem` onwards accepts **only `none`** in sdc/1. A grant is an
  `ERROR`, because runtime contract 1 has no such capability.
- `Target`: for `store`, the `Name` of a `store` dependency; otherwise `-` or
  `any`.
- Every capability the compiled program needs must be granted here, otherwise
  `ERROR SDC-R030`. **Nothing is granted implicitly.** An unused grant is
  `WARNING SDC-A030` and is not emitted.
- Capability rows are always **critical** requirements.

## 6. Diagnostics

Every diagnostic has:
`{code, severity, message, span: {file, line, column}, requirement?, hint?}`.

| Severity | Meaning | Blocks compile |
|---|---|---|
| `ERROR` | The source violates the grammar or a semantic rule | yes |
| `AMBIGUOUS` | The source has more than one valid interpretation | yes |
| `UNRESOLVED` | A reference, or a normative statement, cannot be bound | yes |
| `WARNING` | Valid but risky, or likely unintended | no (reported; release policy may escalate specific codes) |
| `INFO` | Informational (ignored files, applied defaults) | no |

Code ranges: `SDC-P0xx` parse, `SDC-S0xx` structure and grammar, `SDC-R0xx`
resolution, `SDC-A0xx` analysis. Codes are stable once published.

## 7. Defaults

A default is allowed only if it is listed here. Every applied default is
recorded in the IR (`origin: "default"`, `rule: "D-xx"`) and printed by
`sdc check` as `INFO` (INV-04).

| Rule | Default |
|---|---|
| D-01 | `API.Base-Path` = `/` |
| D-02 | `BEH` `success` = 200 |
| D-03 | `BEH` `invalid-request` = 400 |
| D-04 | `BEH` `internal-error` = 500 |
| D-05 | `BEH` `unavailable` = 503 |
| D-06 | `REL` `request-timeout-ms` = 10000; `max-request-bytes` = 1048576; `max-concurrency` = 64; `shutdown-grace-ms` = 10000; `store-retry-attempts` = 0 |
| D-07 | `DATA.Transactions` = `none` |
| D-08 | `PERF` `Criticality` = `standard` |

There are no defaults for identity, authentication, authorization, outcomes of
denial, sensitivity, tenancy, or anything else that is security-relevant.

## 8. Project configuration (`sdc.toml`)

`sdc.toml` configures the *toolchain*, never the meaning (INV-25):

```toml
[build]
profile = "release"              # or "dev"

[signing]
key = "env:SDC_SIGNING_KEY"      # reference only; never the key itself

[policy]
waive = [ { requirement = "PERF-002", reason = "load test env pending" } ]
require-attribution = ["SEC", "AUTHZ", "AUTHN"]   # see AI-INTEGRATION.md

[ai]
provider = "none"                # none | anthropic | openai | google | local
policy = "FAIL"                  # FAIL | FALLBACK_LOCAL | FALLBACK_CACHED
```

## 9. Language versioning

- `sdc/1.x` minor versions may add vocabulary values, optional keys and new
  tables. A valid `sdc/1.0` document keeps exactly the same meaning under
  `sdc/1.x`.
- Anything else is `sdc/2`. The compiler supports one major version.
  Migrating source across majors is done by a tool that rewrites Markdown,
  whose output is reviewed like any other edit.
