# Architecture Assessment (pre-freeze)

Status: **Input to the architecture freeze.** Describes the repository as of
commit `8501b56` (the "MVP"). Everything here is *observed*, and every defect
listed under "Verified defects" was reproduced by running the code, not
inferred from reading it.

The target architecture is in [ARCHITECTURE.md](ARCHITECTURE.md). The
implementation order is in [ROADMAP.md](ROADMAP.md).

---

## 1. Summary verdict

The MVP is a well-built demo. It has clean boundaries, a real runnable
end-to-end loop and 50 passing tests. But it is a different system from the
one SDC intends to be:

| Intended SDC | What the MVP actually is |
|---|---|
| Specification compiler with deterministic meaning | Keyword-heuristic prose classifier whose meaning depends on word matches |
| Compiler owns the execution model; no language backends | `CodeBackend` plugin abstraction, `python-stdlib-http` backend, plan fields `language` / `framework` / `backend` |
| AI assists, never controls | `AICompiler` sits in the build path; model failure silently falls back |
| Immutable, signed, verifiable artifact | An unsigned Python script in `dist/`; the manifest is an unsigned side file |
| Runtime executes only verified artifacts | Nothing verifies anything at load; a tampered artifact runs |
| Verification is bound to what ships | The verified bytes are **not** the released bytes |
| Traceability per requirement | No requirement identities; no source spans |
| Semantic diff as a first-class subsystem | Two overlapping section-level set diffs over mutable local state |

The most valuable thing in the MVP is not what its README emphasises (the AI
compiler and the code backend). It is something it does almost by accident.
**The generated service is a fixed, generic runtime plus application-specific
data** (`AUTHZ_RULES`, `BEHAVIOR`, `SENSITIVE`, `TENANT_FIELD`, a route
table), and that runtime already *interprets* authorization rules as data
(`Policy.decide`). The code generator only pastes constants into a fixed
template. That observation drives the central decision of the freeze:
[ADR-0006](ADR/0006-declarative-artifact-interpreted-runtime.md) makes the
artifact the data and the runtime the interpreter, and removes code generation
entirely.

---

## 2. Current architecture (as built)

```text
sdc CLI (sdc_cli.main)
  └─ Toolchain (sdc_cli.pipeline)            orchestration, writes .build/ and dist/
       ├─ load_project (sdc_parser.loader)   all *.md recursively, merged by heading
       │    ├─ parse_blocks (markdown.py)    headings/paragraphs/lists/tables/code
       │    └─ normalize_* (sections.py)     keyword heuristics → typed IR fragments
       ├─ validate_ir (sdc_parser.validate)  a handful of consistency checks
       ├─ AICompiler (sdc_compiler)          provider → "implementation plan" → validate_plan
       │    └─ generate_implementation       sdc_codegen → PythonHttpBackend
       │         └─ service.py = runtime.py source + embedded constants + route glue
       ├─ verify (sdc_verifier)              runs service.py in a subprocess over HTTP
       │    ├─ behavioral.py                 spec test table + auto negative authz cases
       │    ├─ security.py                   dynamic probes + regex scans of generated source
       │    └─ performance.py                300 sequential requests → p99
       └─ build()                            copies service.py (+ shebang) to dist/<dirname>,
                                             writes manifest.json (unsigned)
```

### Component inventory

| Component | Files | Assessment |
|---|---|---|
| IR model | `sdc_ir/model.py` | Good section decomposition (13 sections), sensible field choices. **Mutable** dataclasses, stringly-typed enums, free-form `predicate: dict` and `request: dict`, prose (`notes`, `description`) mixed into the hashed semantics. No node identities, no source spans. |
| Canonicalization / hashing | `sdc_ir/hashing.py` | `canonical_json` (sorted keys, compact) is the right idea and is preserved. It is not RFC 8785 (JCS) in general (floats, non-BMP key ordering); `build_id` is truncated to 64 bits and omits configuration and provider. |
| Error taxonomy | `sdc_ir/errors.py` | Good "what / why / spec / component" shape. The `regenerable` flag belongs to the code-generation worldview, and it causes semantic errors to be **non-blocking** (see D5). |
| Markdown reader | `sdc_parser/markdown.py` | Small, deterministic, dependency-free. Preserve it, but add source spans and blockquote / heading-attribute support. |
| Section binding | `sdc_parser/sections.py` (`extract_sections`, `CATEGORY_ALIASES`) | Reasonable. Aliases (`authz`, `telemetry`, `tests`, …) add ambiguity for no benefit. |
| Normalizers | `sdc_parser/sections.py` (`normalize_*`) | **The core architectural problem.** Meaning is decided by substring matches (`"admin" in low and "tenant" in low`). Unmatched normative statements are dropped silently. Several normalizers contain always-true expressions (`"metric" in text or True`). |
| Loader | `sdc_parser/loader.py` | Merge-by-heading means one file can hold several sections. Every `*.md` file, recursively, is a source, including READMEs. |
| Validation | `sdc_parser/validate.py` | The right checks (tenant field required for tenant isolation, role references, auth ⇒ 401 outcome) are worth preserving as analysis rules. |
| AI compiler | `sdc_compiler/aicompiler.py`, `providers.py` | Puts the provider **inside** the build. The plan it produces does not actually drive code generation (D8). Model failure silently falls back (D3). |
| Plan / planner | `sdc_compiler/plan.py`, `planner.py` | `ImplementationPlan{language, framework, backend}` is the language-backend architecture the freeze forbids. `Component.derived_from` (IR sections) is the seed of real traceability. |
| Drift / diff | `sdc_compiler/analysis.py`, `diff.py` | Two overlapping section-level diffs. `diff.py` imports a private table from `analysis.py`. There are no compatibility classes and no impact levels. The baseline is the mutable `.build/application-ir.json`. |
| Code generation | `sdc_codegen/**` | The `CodeBackend` registry plus one Python backend. In practice it is a template whose only variable parts are data. |
| Runtime | `sdc_runtime/runtime.py` | Solid stdlib HTTP substrate: router, deny-precedence `Policy` interpreter, JWT HS256, structured logging with redaction, metrics, security headers, a parameterized Postgres store. It is **inlined into every artifact** (by text copy), so the runtime has no identity of its own. |
| Verifier | `sdc_verifier/**` | Genuinely independent (it runs the service over HTTP), with a good confinement start (loopback, fresh secret, `DATABASE_URL` stripped). Its static checks are regexes over source the compiler generated from a fixed template, so they are tautological. The status model has no `BLOCKED` and an unused `WARN`. |
| CLI | `sdc_cli/**` | Good UX. Commands: `init validate compile verify test build run diff inspect`. `run` executes unverified generated code (D10). |
| Tests | `tests/**` (50) | Good coverage of the happy path and determinism of hashes. No negative tests of parser semantics (negation, dropped statements), no tamper tests, no provenance-truthfulness tests. |
| Docs | `ARCHITECTURE.md`, `docs/*.md` (lowercase) | Accurate for the MVP, but they claim properties the code does not have (e.g. "the IR never silently invents behavior"). The lowercase files collide with the required uppercase deliverables on case-insensitive filesystems. |
| Deployment | `docker-compose.yml`, generated `Dockerfile` | The compose file builds from the mutable `.build/generated` directory, not from a verified artifact. |

---

## 3. Verified defects

Each row was reproduced with the scripts described under "Reproduction".
Severity is judged against the *intended* architecture.

| # | Defect | Observed | Severity | Violates |
|---|---|---|---|---|
| D1 | Explicit status codes on their own line are ignored; defaults are invented | `If the customer does not exist:` / `418` → IR `not_found=404` | Critical | §6 no silent invention |
| D2 | Negation inverts meaning | `Cross-tenant access is not forbidden.` → `forbidden=[cross_tenant_access]`, a `deny` rule | Critical | §6 |
| D3 | Security requirements are silently dropped or misattributed | `Never expose authentication tokens.` dropped (dedup by id). `Tenant names are shown in the UI header.` becomes the `tenant_isolation` requirement | Critical | §6, §14 |
| D4 | Unrecognized normative authorization prose is dropped without a diagnostic | `A clinician may read patients assigned to their ward.` → no rule, no role, no warning | Critical | §6 |
| D5 | Semantic errors do not block compilation | `SemanticError(regenerable=True)` passes the `fatal` filter in `Toolchain.compile` | High | §6 |
| D6 | The IR hash is sensitive to wording, not meaning | Rewording a performance sentence with an identical target changes `ir_hash` (prose `notes` are hashed) | High | §5 hashable semantics, §15 |
| D7 | A forged token is accepted when the signing secret is unset | `jwt_verify(jwt_encode(claims, ""), "")` succeeds. The generated service reads `SDC_JWT_SECRET` with default `""` | Critical (runtime) | §17 |
| D8 | The AI "plan" does not drive code generation | Codegen reads only `plan["backend"]`, `target`, `language`. The components are decorative, and the service is generated twice | High (architecture) | §7, §2 |
| D9 | Provenance records the requested provider, not the provider actually used | `--provider anthropic` without a key → local plan used, manifest says `"provider": "anthropic"` | Critical (provenance) | §7, §12 |
| D10 | Verified bytes ≠ released bytes | `.build/generated/service.py` sha256 `556a…` is verified; `dist/p` sha256 `032a…` ships (shebang prepended). The verification report contains no artifact hash | Critical | §8, §13 |
| D11 | No tamper detection | Appending a byte to `dist/p` → it still starts and serves | Critical | §9 |
| D12 | The production artifact embeds test fixtures and test hooks | `secret-password-c1` fixture rows and the `SDC_SEED_JSON` environment override are in `dist/` | High | §10, §17 |
| D13 | Telemetry identity is overridable from the environment | `SDC_SPEC_HASH`, `SDC_IR_HASH` and `SDC_BUILD_ID` override embedded values | High | §12 |
| D14 | Security defaults fail open | A missing `role` claim defaults to `"user"`. Postgres failure falls back to an in-memory store silently | High | §17, §7 |
| D15 | Security requirements without a check are non-blocking | `UNVERIFIED` checks are emitted with `mandatory=False` | High | §13 |
| D16 | Existence oracle across tenants | The detail handler checks existence before authorization: cross-tenant existing id → 403, non-existent → 404 | Medium | §17 |
| D17 | `sdc run` executes unverified code | `cmd_run` compiles and runs `.build/generated/service.py` with no verification | High | §16 |
| D18 | The artifact name depends on the checkout directory | `dist/<basename(project_dir)>` | Low | §11 |
| D19 | Performance gating is nondeterministic | A local p99 over 300 requests is a mandatory, blocking check | Medium | §11 |

### Reproduction

```bash
pip install -e ".[dev]" && pytest -q       # 50 passed (baseline)
python scripts/assessment_probe.py         # prints the observed behavior for D1–D14
```

D16–D19 follow directly from reading the cited code paths
(`make_detail_handler`, `cmd_run`, `Toolchain.build`, `verify_performance`).

---

## 4. Architectural contradictions

These are contradictions *within* the MVP's own claims, or between the MVP and
the SDC vision. The freeze resolves each one.

| # | Contradiction | Resolution in the freeze |
|---|---|---|
| C1 | The docs say "the parser never silently invents behavior"; the normalizers invent statuses, roles and requirements (D1–D4) | Controlled grammar; prose is non-normative; normative prose that is not bound to a requirement is `UNRESOLVED` ([ADR-0005](ADR/0005-ambiguity-is-an-error.md)) |
| C2 | "The IR and plan are language-agnostic" versus a plan containing `language`, `framework` and `backend` | The plan is deleted; the IR is lowered to a declarative artifact ([ADR-0006](ADR/0006-declarative-artifact-interpreted-runtime.md)) |
| C3 | "Model output never becomes an artifact" versus the model choosing the plan in the build path, with silent fallback | AI is removed from the build; its output enters only as reviewed source ([ADR-0011](ADR/0011-ai-outside-the-build.md)) |
| C4 | "Verification is a separate authority" versus verifying a different file from the one shipped | Evidence is bound to `artifactHash` and the runtime identity ([ADR-0008](ADR/0008-detached-attestations-release-bundle.md)) |
| C5 | "Binary reproducibility guaranteed" versus an artifact that inlines whatever `runtime.py` is installed, is named after the directory, and has an unsigned manifest | R1 byte-identical artifact, defined inputs, and a `compilerHash` ([ADR-0012](ADR/0012-reproducibility-definition.md)) |
| C6 | "Generated code is an intermediate, safe to delete" versus generated code being the thing that ships and runs | No generated code exists; the artifact is the compiled program |
| C7 | The error taxonomy has `regenerable`, a retry-the-LLM concept, inside a deterministic compiler | Diagnostics carry a severity; retrying cannot change a deterministic result |
| C8 | Drift analysis (`analysis.py`) and semantic diff (`diff.py`) model the same thing twice | One diff subsystem ([ADR-0013](ADR/0013-semantic-diff-model.md)) |
| C9 | Two sources of IR version truth (`IR_SCHEMA_VERSION` in `__init__`, `schema_version` in the model) | A single `irVersion` constant, schema-backed |
| C10 | Two sources of fixture truth (`_default_seed` in codegen, `build_seed` in the verifier) | Fixtures are declared in `testing.md`; nothing is invented |
| C11 | "Security requirements as executable checks" versus regex scans of compiler-generated text | Static checks run over the declarative artifact; runtime correctness is covered by a conformance suite |

## 5. Dead code and duplicated concepts

- `IR_SCHEMA_VERSION` (unused), `WARN` status (unused), and the `--provider` flag on `sdc diff` (unused).
- `Observability.metrics/health` and `Deployment.container/healthcheck` normalizers are always `True`.
- `Endpoint.authenticated` defaults `True`, and the loader also forces it `True`.
- `AICompiler.compile` generates code, then `Toolchain.compile` regenerates it with metadata. Only the second result is used.
- `ImplementationPlan.components`, `dependencies` and `optimization_strategy` are never read by codegen.
- `check_authorization_enforced` re-runs `check_tenant_isolation`.
- `_seeded_id` / `sid` computation is duplicated in `behavioral.py`, `security.py` and `performance.py`.
- `App.observability_fields` is stored and never used.

---

## 6. What is preserved

The freeze is not a rewrite for its own sake. These parts carry forward, with
changes limited to what the new contracts require:

| Preserve | Where it goes | Change required |
|---|---|---|
| 13-section decomposition of the IR | `sdc/ir` | Add ids, spans (in trace), typed references, and frozen types |
| `canonical_json` + sha256 `sha256:<hex>` convention | `sdc_runtime/contract/canonical.py` | Enforce the JCS-safe subset (no floats, ASCII keys, no `null`) |
| Markdown block reader | `sdc/compiler/parser` | Add line/column spans, blockquotes and heading attributes |
| Table-driven normalizers (data fields, test cases) | `sdc/compiler/semantic` | Become grammar productions with required columns |
| Keyword heuristics in `sections.py` | `sdc/ai/providers/local.py` | Demoted to the deterministic *local proposal engine* (`FALLBACK_LOCAL`) |
| `validate.py` rules | `sdc/compiler/analysis` | Emit diagnostics with severity and requirement id |
| `runtime.py`: `Router`, `App.handle`, `Policy` (deny precedence), JWT, redaction, metrics, security headers, parameterized `PostgresStore` | `sdc_runtime/*` | Split by capability. Fix D7, D14 and D16. Remove the seed and env-identity hooks |
| Codegen handler factories (`make_detail_handler`, `make_collection_handler`) | `sdc_runtime/interpreter` | Become the `read.one` / `read.list` operation kinds |
| Codegen embedded constants | `sdc/compiler/planner` | Become fields of the artifact |
| `Component.derived_from` | artifact `operations[].derivedFrom` | Requirement ids instead of section names |
| Verifier harness (subprocess, loopback, fresh secret, credential stripping) | `sdc/verification/dynamic` | Runs `sdc-runtime` in verify mode against the artifact |
| Auto-generated negative authorization cases | `sdc/verification/obligations` | Derived per requirement id |
| Dynamic security probes (exposure, isolation, auth, logging, headers) | `sdc/verification/dynamic` | Bound to requirement ids |
| `PASS / FAIL / UNVERIFIED` | `sdc/verification/evidence` | Add `BLOCKED`, remove `WARN` |
| Semantic diff idea + drift → components | `sdc/diff` | Merge into one subsystem, keyed by requirement id |
| CLI look and feel | `sdc/cli` | Commands renamed per [COMPILER.md](COMPILER.md#6-cli) |
| Determinism tests | `tests/reproducibility` | Extended to the byte-identical artifact |

## 7. Current → target mapping

| Current | Target | Action |
|---|---|---|
| `sdc_ir/model.py` | `sdc/ir/model.py` | Rewrite types; keep the section shapes |
| `sdc_ir/hashing.py` | `sdc_runtime/contract/canonical.py`, `sdc/ir/hashing.py` | Move and harden |
| `sdc_ir/errors.py` | `sdc/compiler/diagnostics.py` | Replace with the diagnostic model |
| `sdc_parser/markdown.py` | `sdc/compiler/parser/` | Extend |
| `sdc_parser/loader.py` | `sdc/compiler/source/` | Rewrite (explicit source set, `sourceHash`) |
| `sdc_parser/sections.py` | `sdc/compiler/semantic/` (grammar) + `sdc/ai/providers/local.py` (heuristics) | Split |
| `sdc_parser/validate.py` | `sdc/compiler/analysis/` | Port rules |
| `sdc_compiler/aicompiler.py`, `plan.py`, `planner.py` | — | **Delete** |
| `sdc_compiler/providers.py` | `sdc/ai/providers/` | Repurpose: proposals only; explicit failure policy |
| `sdc_compiler/analysis.py`, `diff.py` | `sdc/diff/` | Merge |
| `sdc_codegen/**` | — | **Delete** (logic moves to planner + interpreter) |
| `sdc_runtime/runtime.py` | `sdc_runtime/{capabilities,security,interpreter}/` | Split and harden |
| `sdc_verifier/**` | `sdc/verification/**` | Restructure around obligations |
| `sdc_cli/**` | `sdc/cli/**` | Adapt commands |
| `examples/customer-api` | `examples/secure-api` | Rewrite in the frozen grammar |
| `docker-compose.yml` | `examples/secure-api/` | Move; build from a release bundle |
| `ARCHITECTURE.md`, `docs/*.md` (lowercase) | `docs/*.md` (this freeze) | Superseded (removed in this change) |
