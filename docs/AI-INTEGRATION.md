# AI Integration

Status: **FROZEN.** Governing ADR: [ADR-0011](ADR/0011-ai-outside-the-build.md).

AI assists the *author*. It is not part of the compiler. The compiler, not the
LLM, is the authority.

---

## 1. Boundary

```text
        AI provider (untrusted)
               │ structured proposal (JSON, schema-constrained)
               ▼
        Validate  ── schema, vocabulary, referential checks against current IR
               │
               ▼
        Normalize ── canonical values, ids assigned or preserved
               │
               ▼
        Render    ── deterministic proposal → Markdown patch
               │
               ▼
        Human review + apply      ← the only way in
               │
               ▼
        Source set (Markdown) ── same parser as human input
               │
               ▼
        Deterministic SDC (compile, verify, sign)
```

Rules:

- **The build never calls AI** (INV-11). `sdc compile`, `sdc verify` and
  `sdc build` are fully functional with no provider configured, and that is
  the default.
- **AI output enters only as source** (INV-12). A proposal is rendered into a
  Markdown patch and applied only after review. The IR is always a function of
  source, so it stays reproducible and reviewable. A proposal never modifies
  the IR, the artifact, evidence or provenance directly.
- The MVP's `AICompiler`, its AI-chosen "implementation plan" and the
  provider-inside-build path are **removed**.

## 2. What AI is for

| Command | Proposal |
|---|---|
| `sdc assist structure <file>` | Convert prose into the sdc/1 structural forms (tables, item headings) |
| `sdc assist resolve` | Propose fixes for `AMBIGUOUS` / `UNRESOLVED` diagnostics |
| `sdc assist tests` | Propose `testing.md` cases and fixtures for `UNVERIFIED` requirements |
| `sdc assist ids` | Deterministic, no AI needed; same as `sdc check --assign-ids` |

Each command outputs a patch (`--write` applies it to the working tree, and
the default prints it) plus a ledger entry.

## 3. Proposal schema

`schemas/proposal/proposal-1.schema.json`. A proposal is a list of typed
operations on *source structure*, never free text to paste:

```json
{ "format": "sdc.proposal/1",
  "operations": [
    { "op": "add-row", "file": "authorization.md", "table": "Rules",
      "row": { "ID": "AUTHZ-004", "Effect": "allow", "Role": "clinician", "Action": "read",
               "Resource": "Patient", "Condition": "attr-contains(ward, ward_id)" },
      "rationale": "…", "sourceSpan": { "file": "authorization.md", "line": 9 } } ] }
```

Validation rejects: unknown operations, values outside the vocabularies,
references that do not resolve against the current IR plus the proposal,
reuse of existing ids, and edits to files outside the source set. A rejected
proposal is recorded in the ledger with outcome `REJECTED` and changes
nothing.

**Rendering is deterministic.** The same proposal applied to the same source
set produces the same patch bytes.

## 4. Provider policy

Configured in `sdc.toml [ai]`:

| Policy | On provider failure (unreachable, timeout, invalid output after validation) |
|---|---|
| `FAIL` (**default**; mandatory in CI) | The command fails with the provider error. Nothing is proposed |
| `FALLBACK_LOCAL` | Use the deterministic local proposer (the MVP's keyword heuristics, demoted to here). The ledger records `provider: local`, `fallbackFrom: <provider>` |
| `FALLBACK_CACHED` | Use a previously recorded proposal with the same `inputHash` and `promptHash` from the ledger. If none exists, fail |

- A fallback is **never** silent. It is printed and recorded (INV-13).
- `SDC_PROVIDER` and similar environment overrides are removed. The provider
  comes from `sdc.toml` or an explicit `--provider` flag.
- Because AI is outside the build, provider behavior can never change
  application architecture. The worst case is a bad *proposal*, and a human
  sees it as a diff.

## 5. Ledger

Every `sdc assist` invocation appends one entry to `.sdc/ledger/<id>.json`.
The ledger is committed with the sources. It is never part of the source set,
and it is hashed into provenance as `ledgerHash`.

```jsonc
{ "format": "sdc.ledger-entry/1",
  "id": "prop-2026-09-24-0007",
  "command": "assist structure authorization.md",
  "provider": "anthropic", "model": "…", "modelVersion": "…",
  "policy": "FAIL", "fallbackFrom": null,
  "promptTemplate": "structure/authorization@3", "promptHash": "sha256:…",
  "inputHash": "sha256:…",            // hash of the IR + source slices sent
  "outputHash": "sha256:…",           // hash of the raw provider output
  "proposalHash": "sha256:…",         // hash of the validated, normalized proposal
  "configurationHash": "sha256:…",    // temperature, max tokens, etc. (no keys)
  "outcome": "APPLIED" | "PROPOSED" | "REJECTED" | "FAILED",
  "files": [ { "path": "authorization.md", "beforeSha256": "…", "resultSha256": "…" } ],
  "text": { "prompt": "…", "output": "…" }   // optional; off by default (privacy)
}
```

The example is annotated (`jsonc`). Real entries are canonical JSON, so absent
values are omitted rather than written as `null`.

**Attribution.** For each file in the current source set, the build checks
whether its `sha256` equals the `resultSha256` of a ledger entry:

- equal: attributed to the entry, `matchesCurrent: true`;
- changed afterwards: `matchesCurrent: false`, meaning the file was modified
  after the proposal;
- no entry: unattributed.

With `sdc.toml [policy] require-attribution = ["SEC", "AUTHZ", …]`, changes to
those sections since the base release must be attributed, either to a ledger
entry or to a human commit, otherwise the change is reported under
`unattributedChanges`. Whether this blocks is an open decision
([ROADMAP.md](ROADMAP.md#risks-and-unresolved-decisions)).

## 6. Prompts

Prompt templates live in `sdc/ai/prompts/` and are versioned (`name@N`). The
template text is part of the toolchain distribution, and `promptHash` is the
hash of the rendered prompt. Prompts send IR slices and the relevant source
spans, never secrets and never files outside the source set.

## 7. Operating without an LLM

Everything except `sdc assist` works with no provider. `sdc assist
--provider local` uses the deterministic local proposer. SDC is complete
without AI; AI makes authoring faster.
