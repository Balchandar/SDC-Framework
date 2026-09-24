# Semantic Diff

Status: **FROZEN — `sdc.diff/1`.** Governing ADR:
[ADR-0013](ADR/0013-semantic-diff-model.md).

A Git text diff shows which characters changed. A semantic diff shows **which
meaning changed, and what that does to the running system.** It is a
first-class subsystem (`sdc/diff`). It replaces both the MVP's `analysis.py`
("drift") and its `diff.py`.

---

## 1. Inputs

`sdc diff <base> [<head>]`. Each side is either:

- a project directory (compiled through stages 1–7; compilation is pure, so
  this is safe), or
- a release bundle (IR, trace and evidence taken from its materials, migrated
  forward if the `irVersion` is older).

The default `head` is the current directory. There is no implicit baseline:
the MVP's mutable `.build/application-ir.json` baseline is gone.

## 2. Two layers

| Layer | Compares | Catches |
|---|---|---|
| **Node diff** | IR nodes keyed by id | What the specification says differently |
| **Effect diff** | Analysis facts: permission matrix, exposure map, authentication map, outcome map | What the system *does* differently, including indirect effects |

Why both are needed: marking `email` as sensitive in `data.md` edits one
`DATA` node, yet it changes the response of every operation on that entity.
Renaming the role `user` to `clinician` edits the authorization table, and it
changes who can call what. The effect diff makes such consequences explicit,
where a node diff alone would leave them to inference.

## 3. Node diff

For each id present on either side:

| Kind | Condition |
|---|---|
| `ADDED` / `REMOVED` | The id exists on one side only |
| `MODIFIED` | Same id, different canonical value, with a field-level `path`, `before` and `after` |
| `TRACE_ONLY` | Same canonical value; the trace differs (wording, position, file) |

Nodes without their own id (entity fields) are diffed as paths under their
owner.

## 4. Classification

Every change gets exactly one **compatibility class** and zero or more
**impact flags**:

- Compatibility: `NON_SEMANTIC` < `NON_BREAKING` < `POTENTIALLY_BREAKING` < `BREAKING`
- Impact flags: `SECURITY_IMPACT`, `PERFORMANCE_IMPACT`, `DATA_MIGRATION_REQUIRED`

Classification rules (v1; versioned with `irVersion`):

| Change | Class | Flags / dimension level |
|---|---|---|
| Any `TRACE_ONLY` | `NON_SEMANTIC` | — |
| Operation added | `NON_BREAKING` | Authorization: MEDIUM (new surface) |
| Operation removed, or method/path/kind changed | `BREAKING` | API contract: HIGH |
| Allow removed or narrowed (effect diff: a cell allow→deny) | `BREAKING` | `SECURITY_IMPACT`; Authorization: HIGH |
| Allow added or widened (a cell deny→allow) | `NON_BREAKING` | `SECURITY_IMPACT`; Authorization: HIGH (privilege expansion) |
| Role renamed or replaced | `BREAKING` | `SECURITY_IMPACT`; Authorization: HIGH |
| Authentication required → none on an operation | `NON_BREAKING` | `SECURITY_IMPACT`; Authentication: HIGH |
| Authentication none → required | `BREAKING` | `SECURITY_IMPACT`; Authentication: MEDIUM |
| Field sensitive yes → no (exposure widened) | `NON_BREAKING` | `SECURITY_IMPACT`; Data: HIGH |
| Field sensitive no → yes (exposure narrowed) | `BREAKING` | `SECURITY_IMPACT`; Data: MEDIUM |
| Field added | `NON_BREAKING` | `DATA_MIGRATION_REQUIRED` |
| Field removed, or type/key/tenant changed | `BREAKING` | `DATA_MIGRATION_REQUIRED` |
| Outcome status changed | `BREAKING` | API contract: HIGH |
| `deniedAs` changed | `POTENTIALLY_BREAKING` | `SECURITY_IMPACT` |
| Security requirement added | `NON_BREAKING` | `SECURITY_IMPACT`; Security: MEDIUM |
| Security requirement removed or property changed | `POTENTIALLY_BREAKING` | `SECURITY_IMPACT`; Security: **HIGH**; always listed under "security weakening" |
| Performance target tightened | `NON_BREAKING` | `PERFORMANCE_IMPACT`; Performance: MEDIUM |
| Performance target loosened | `NON_BREAKING` | `PERFORMANCE_IMPACT`; Performance: LOW |
| Reliability limit changed | `POTENTIALLY_BREAKING` | Reliability: MEDIUM |
| Test case added, removed or modified | `NON_BREAKING` | Verification: REQUIRED |

The overall class is the maximum over all changes. The flags are the union.
A change matching no rule is classified `POTENTIALLY_BREAKING` with a
diagnostic, so it is never silently `NON_BREAKING`.

## 5. Impact report

Each impact dimension gets a level `NONE` | `LOW` | `MEDIUM` | `HIGH`:
Authentication, Authorization, API contract, Data, Security, Performance,
Reliability, Observability.

Two further fields:

- `rebuild`: `REQUIRED` if and only if `irHash` differs. It is `NOT_REQUIRED`
  when only the trace changed, but a new statement is still produced.
- `verification`: `REQUIRED` if any obligation is affected, together with the
  affected obligation ids. Selective verification is for feedback only (see
  [VERIFICATION.md §8](VERIFICATION.md#8-selective-re-verification)).

Affected artifact operations are those whose `derivedFrom` contains a changed
id, plus those with a changed effect-diff cell.

## 6. Example

```diff
  | ID        | Effect | Role      | Action | Resource | Condition   |
- | AUTHZ-001 | allow  | user      | read   | Patient  | same-tenant |
+ | AUTHZ-001 | allow  | clinician | read   | Patient  | same-tenant |
```

```text
SEMANTIC CHANGE                                     base R1 → head (working tree)

  AUTHZ-001  MODIFIED  role: user → clinician        authorization.md:18

Effects
  - user       read  API-001 GET /patients/{id}   allow → deny
  - user       read  API-002 GET /patients        allow → deny
  + clinician  read  API-001 GET /patients/{id}   deny  → allow
  + clinician  read  API-002 GET /patients        deny  → allow

Classification   BREAKING, SECURITY_IMPACT

Impact
  Authentication   NONE
  Authorization    HIGH
  API contract     NONE
  Data             NONE
  Security         HIGH
  Performance      NONE
  Verification     REQUIRED  (AUTHZ-001/dynamic/1..2, SEC-003/dynamic/1..4, TEST-004)
  Rebuild          REQUIRED  (irHash changed)

Attribution
  authorization.md  ledger prop-2026-09-24-0007 (anthropic, model …)  matchesCurrent=true
```

## 7. Output format

`sdc diff --json` emits `sdc.diff/1`:

```json
{ "format": "sdc.diff/1",
  "base": { "irHash": "…", "ref": "R1" }, "head": { "irHash": "…" },
  "compatibility": "BREAKING", "flags": ["SECURITY_IMPACT"],
  "impact": { "authentication": "NONE", "authorization": "HIGH", "…": "…" },
  "rebuild": "REQUIRED",
  "verification": { "required": true, "obligations": ["AUTHZ-001/dynamic/1", "…"] },
  "changes": [ { "id": "AUTHZ-001", "kind": "MODIFIED", "path": "role",
                 "before": "user", "after": "clinician",
                 "class": "BREAKING", "flags": ["SECURITY_IMPACT"] } ],
  "effects": [ { "role": "user", "operation": "API-001", "before": "allow", "after": "deny" } ],
  "affectedOperations": ["API-001", "API-002"],
  "attribution": [ { "file": "authorization.md", "ledger": "prop-…", "matchesCurrent": true } ] }
```

## 8. `sdc explain`

`explain` uses the same indexes to show the lineage of one requirement:

```text
sdc explain SEC-002

SEC-002  tenant-isolation  critical
  Source     security.md:9    "Cross-tenant access must never occur."
  IR         security.requirements[SEC-002]  (irHash sha256:…)
  Depends    AUTHZ-003 (deny cross-tenant), DATA-001.tenant_id
  Artifact   authz.rules[AUTHZ-003]; operations API-001, API-002  (artifactHash sha256:…)
  Tests      TEST-003 (declared), SEC-002/dynamic/1..4 (derived)
  Evidence   PASS  (verificationId sha256:…, runtime sdc-runtime 1.0.0)
  Release    customer-service-1.0.0.release.json  signed by keyid sha256:…
  History    added in R1; unchanged since
```
