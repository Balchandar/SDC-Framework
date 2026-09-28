# Compiler

Status: **FROZEN.** Governing ADRs:
[ADR-0003](ADR/0003-semantic-ir-contract.md),
[ADR-0005](ADR/0005-ambiguity-is-an-error.md),
[ADR-0006](ADR/0006-declarative-artifact-interpreted-runtime.md),
[ADR-0011](ADR/0011-ai-outside-the-build.md),
[ADR-0016](ADR/0016-wasm-execution-substrate.md),
[ADR-0017](ADR/0017-policy-contract-and-capability-manifest.md).

The compiler is the trusted, deterministic component that turns a source set
into an artifact. It never calls an AI provider, never touches the network,
and never reads the clock, the environment or anything outside the source set
and the lock file (INV-01, INV-10, INV-11). **It never emits WebAssembly or
source code in any language** (INV-26). The Wasm execution substrate
(ADR-0016) does not change the compiler: its output is still exactly one
canonical artifact.

---

## 1. Stage contracts

Each stage is a pure function from its input to its output. Each stage also
emits diagnostics, which are accumulated. A stage never raises exceptions for
user errors; exceptions are reserved for compiler defects.

### Stage 1: Load

`load(projectDir) → SourceSet`

- Applies the membership rule of [SPECIFICATION.md §1](SPECIFICATION.md#1-source-set).
  Nothing else is read except `sdc.toml` (configuration) and `sdc.lock`.
- `SourceSet = { format: "sdc.sources/1", files: [{ path, sha256, bytes }] }`,
  sorted by path. Paths are relative and POSIX-style.
- `sourceHash = sha256(JCS({format, files: [{path, sha256}]}))`, computed over
  raw bytes.
- Limits: at most 256 files, 1 MiB per file, 8 MiB in total. Exceeding a limit
  is an `ERROR`, because a hostile source must not exhaust the compiler.
- Symlinks are rejected, which also prevents reading outside the project.

### Stage 2: Parse

`parse(SourceSet) → DocumentTree`

- A CommonMark-subset reader (the MVP's `markdown.py` plus spans): headings
  with `{#id}` attributes, paragraphs, lists, pipe tables, fenced code,
  blockquotes and HTML comments.
- Every node carries `{file, line, column}` spans.
- No semantics: the parser does not know what "Authorization" means.

### Stage 3: Bind and validate

`bind(DocumentTree) → SectionStatements`

- Checks the H1 against the file name, then matches key–value lines, tables
  and item headings against the section grammar.
- Applies the normative-prose rule (`UNRESOLVED SDC-S010`).
- Output: typed but unnormalized statements, each carrying its span and
  declared id.

### Stage 4: Normalize

`normalize(SectionStatements) → NormalizedStatements`

- Case folding of vocabulary tokens, NFC text, integer parsing with range
  checks, and path-template normalization (no trailing slash; parameters
  extracted).
- Applies the defaults listed in [SPECIFICATION.md §7](SPECIFICATION.md#7-defaults),
  recording each one with its origin.
- **No inference.** Nothing is derived from names, words or plurals.

### Stage 5: IR construction

`construct(NormalizedStatements) → (SemanticIR_unresolved, Trace)`

- Builds frozen IR objects. Symbolic references (entity names, role names)
  are kept for stage 6.
- Separates meaning (IR) from provenance of meaning (trace).

### Stage 6: Resolve

`resolve(IR_unresolved, sdc.lock) → SemanticIR`

- Replaces names with ids (`Resource: Customer` → `DATA-001`). An unknown name
  is `UNRESOLVED`, and a name that matches more than one declaration is
  `AMBIGUOUS`.
- Checks `dependencies.md` against `sdc.lock`. The lock pins the runtime
  version, its `runtimeHash`, and the capability versions used for
  verification. A missing or stale lock is an `ERROR` in the `release`
  profile, and `sdc lock` regenerates it. **Resolution never touches the
  network.** Creating the lock is a separate, explicit command.
- Computes `irHash` and `traceHash`.

### Stage 7: Analyze

`analyze(SemanticIR) → Facts`

Facts are derived and deterministic, and they are *not* part of `irHash`
(they are a function of it):

- **Effect model:** the permission matrix (role × operation × condition →
  allow or deny), the exposure map (operation → fields returned), the
  authentication map (operation → required), and the outcome map.
- **Consistency rules** (ported from the MVP's `validate.py` and extended):
  - authentication required ⇒ `unauthenticated` outcome declared (`ERROR`);
  - `rbac-tenant` ⇒ every resource entity has a tenant field (`ERROR`);
  - a rule referencing an undeclared role (`UNRESOLVED`);
  - an operation with no possible `allow` path (`WARNING SDC-A010 unreachable
    operation`);
  - a deny rule that makes an allow rule dead (`WARNING SDC-A011`);
  - a `secret` field in the exposure map (`ERROR`, since no operation may
    return one);
  - `Denied-As` absent under `rbac-tenant` (`WARNING SDC-A021`);
  - a `security.md` property whose preconditions are missing, e.g.
    `tenant-isolation` without `rbac-tenant` (`ERROR`);
  - a capability the program requires that is not declared in the
    Capabilities table (`ERROR SDC-R030`), or a declared grant it does not use
    (`WARNING SDC-A030`, which is not emitted);
  - a grant of a capability that runtime contract 1 does not have
    (`filesystem`, `network.outbound`, …) (`ERROR`);
  - a `search` operation without a criteria table (`ERROR SDC-S031`), or a
    criteria field that is `secret` (`ERROR`).
- Analysis reports diagnostics only. It never modifies the IR.

### Stage 8: Plan

`plan(SemanticIR, Facts) → ArtifactModel`

- Lowering: one artifact operation per API operation, with its effective
  policy (the applicable rules pre-selected by resource and action), its
  response projection (declared fields minus `secret` fields), its outcome
  map, its limits and its observability fields.
- Serializes the **Policy Contract** (`policyView(ir)`) as `artifact.policy`
  and the **capability manifest** (`capabilityView(ir)`) as
  `artifact.capabilities` ([POLICY.md](POLICY.md)). Response projections
  exclude `secret` fields.
- Every artifact element records `derivedFrom: [requirement ids]`.
- **Optimization slot.** This is an ordered list of passes that each preserve
  semantics. **It is empty in v1.** Adding a pass requires an ADR and a
  differential test: the artifact with the pass must produce identical
  evidence outcomes to the artifact without it.

### Stage 9: Emit

`emit(ArtifactModel) → (bytes, artifactHash)`

- Canonical JCS serialization, validated against
  `schemas/artifact/artifact-1.schema.json` before it is written.
- `artifactHash = sha256(bytes)`.

Stages 10–14 (verification, policy, provenance, signing, release) belong to
the build ([VERIFICATION.md](VERIFICATION.md), [PROVENANCE.md](PROVENANCE.md),
[ARTIFACT.md](ARTIFACT.md#2-release-bundle)).

## 2. Stage isolation rules

- Stage *n* may consume only the outputs of stages before it. It never reads
  files directly, except stage 1 (and stage 6, which reads `sdc.lock`).
- Stages 6–9 consume only `SemanticIR`, `Facts` and each other's outputs.
  **They do not receive the `DocumentTree`, and they receive `Trace` only to
  attach positions to diagnostics** (INV-02).
- The verifier receives `SemanticIR` and the artifact bytes. It never receives
  the planner's internal structures (INV-14).

## 3. Build directory

`.build/` is an **untrusted cache** (INV-23). It exists for inspection and
incremental speed, and nothing reads it to make a trust decision.

```text
.build/
├── sources.json       # SourceSet manifest (paths + sha256), sourceHash
├── diagnostics.json
├── ir.json            # irHash
├── trace.json         # traceHash
├── facts.json
├── artifact.json      # THE artifact; artifactHash
├── evidence.json      # verificationId
└── statement.json     # unsigned statement (signed copy lives in the release)
dist/
└── <name>-<version>.release.json    # the only trusted output
```

File names are fixed. The output name comes from `application.md`, never from
the directory name (fixes D18).

## 4. Profiles

| | `dev` | `release` (default for `sdc build`) |
|---|---|---|
| Meaning (IR, artifact) | identical | identical (INV-03) |
| Verification runs | yes | yes |
| Release-policy failures | reported; a release is still produced, marked `profile: dev` | block the release |
| Signing key | ephemeral local dev key, label `dev` | a release key from `sdc.toml [signing]` |
| Runtime acceptance | only with `--allow-dev`; never in production mode | per runtime trust policy |
| `sdc.lock` required | no (a warning) | yes |

## 5. Diagnostics and errors

- User-caused problems are diagnostics ([SPECIFICATION.md §6](SPECIFICATION.md#6-diagnostics)).
- Compiler defects (a violated internal invariant) are `InternalError`s. They
  abort the build with exit code 70, and a bug report must include the
  `sourceHash` and `compilerHash`.
- The MVP's `regenerable` flag is removed: a deterministic compiler gives the
  same answer every time, so retrying cannot help.

Exit codes: `0` success, `1` diagnostics blocked compilation, `2` verification
or policy blocked release, `3` integrity or signature failure, `64` usage
error, `70` internal error.

## 6. CLI

| Command | Stages | Output |
|---|---|---|
| `sdc init [dir]` | — | A scaffolded project in the sdc/1 grammar |
| `sdc check [--assign-ids]` | 1–7 | Diagnostics; with `--assign-ids`, a source edit adding missing ids |
| `sdc compile` | 1–9 | `.build/artifact.json` and `artifactHash` |
| `sdc verify` | 1–11 | `.build/evidence.json` and the policy decision (no signing) |
| `sdc build [--profile dev\|release] [--reproduce <release>]` | 1–14 | `dist/<name>-<version>.release.json` |
| `sdc run [<release>]` | runtime | Runs a release through the **production loader path** of `sdc-runtime` (the Wasm host after switch-over; the Python reference runtime before it). With no argument, builds a `dev` release first and runs it with `--allow-dev`. A critical `FAIL` is refused even in dev. |
| `sdc diff <base> [<head>]` | 1–7 on both | Semantic + effect diff. Each side is a project directory or a release bundle |
| `sdc inspect <dir\|artifact\|release> [--verify] [--json]` | — | Human or JSON view. `--verify` checks a release chain offline |
| `sdc explain <REQ-ID> [--release <r>]` | 1–7 (+ evidence) | Requirement lineage |
| `sdc lock` | 6 | Writes `sdc.lock` (the only command that may use the network) |
| `sdc assist …` | AI | Proposals → Markdown patch; never compiles ([AI-INTEGRATION.md](AI-INTEGRATION.md)) |

Removed MVP commands: `validate` (replaced by `check`) and `test` (replaced by
`verify --only TEST-*`).

`sdc build` conceptually runs: Parse → Validate → Resolve → Normalize →
Analyze → Plan (→ Optimize) → Emit → Verify → Evidence → Policy → Provenance →
Hash → Sign → Release.
