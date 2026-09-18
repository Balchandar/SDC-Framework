# SDC Architecture

## Principle

SDC separates three responsibilities that conventional development conflates:

- **Human responsibility** — *what* the software does: behavior, APIs, business
  rules, data, security, authorization, performance, reliability,
  observability, deployment, invariants.
- **AI / compiler responsibility** — *how* it is implemented: language, internal
  architecture, data access, HTTP layer, optimization, generated tests and code.
- **Verification responsibility** — *whether* the implementation satisfies the
  specification. This is a **separate authority**. The generation process is
  never the sole judge of its own output.

## Pipeline

```text
CLI
 │
 ▼
Project Loader ── reads all *.md
 │
 ▼
Markdown Parser ── blocks
 │
 ▼
Semantic Model ── section normalizers
 │
 ▼
Application IR ── typed, canonical, hashed
 │
 ├───────────────┐
 ▼               ▼
AI Compiler    Verifier
 │  (plan)        │  (runs the artifact)
 ▼               │
Code Generator   │
 │               │
 ▼               │
Artifact ────────┘
```

Every stage emits a machine-readable artifact under `.build/`:

```text
.build/
├── specification.json        # raw spec file set (for spec hash)
├── application-ir.json       # canonical IR
├── implementation-plan.json  # validated plan
├── generated/                # generated implementation (marked, deletable)
├── verification-report.json
├── security-report.json
├── benchmark-report.json
├── semantic-diff.json        # present when specs changed vs last build
└── manifest.json
dist/
└── <project-name>            # standalone executable
```

## Boundaries (enforced by package structure)

- No UI/CLI code controls compilation internals — the CLI orchestrates via
  `Toolchain`, which calls decoupled stages.
- No model provider is embedded in the domain layer — `sdc_compiler.providers`
  is the only place providers live, behind the `AIProvider` interface.
- No generated application depends on the compiler — generated services depend
  only on the inlined `sdc_runtime` substrate (in fact they are fully
  standalone: the runtime source is inlined into the artifact).
- The verifier depends on the IR and the built artifact, not on the compiler's
  internal claims.

## Determinism & reproducibility

- **Canonical IR**: `sdc_ir.canonical_json` (sorted keys, compact) is the single
  source of determinism. `ir_hash` is the sha256 of the canonical IR.
- **Semantic reproducibility**: identical specs → identical IR → equivalent
  behavior. Guaranteed.
- **Binary reproducibility**: guaranteed for the deterministic `local` provider
  (same spec + compiler → identical bytes). **Not** claimed when a model
  provider is used — recorded honestly in the manifest.

## Extensibility

- **New code backends**: implement `sdc_codegen.backends.base.CodeBackend` and
  register it. The IR and plan are backend-agnostic — no spec change needed.
- **New AI providers**: implement `sdc_compiler.providers.AIProvider` and
  `register_provider(...)`.
- **New verification engines/targets/deployment targets**: additive, behind
  their own interfaces.

## Error taxonomy

All failures are one of: `SPECIFICATION_ERROR`, `SEMANTIC_ERROR`,
`COMPILER_ERROR`, `GENERATION_ERROR`, `VERIFICATION_ERROR`, `SECURITY_ERROR`,
`PERFORMANCE_ERROR`, `BUILD_ERROR`, `RUNTIME_ERROR`. Every error names what
failed, why, which specification caused it, which component is affected, and
whether regeneration can help. See `sdc_ir.errors`.

## Security of the compilation process

The AI compiler is treated as partially trusted:

- Model output is constrained to a **validated plan**, never executed as code.
- Generated code is executed **only** by the verifier, in a confined subprocess
  bound to loopback, with a fresh per-run signing secret and **no production
  credentials**, and is killed on teardown.
- The generated artifact itself uses parameterized queries, redacts sensitive
  fields from responses and logs, and reads secrets from the environment.

See [`SECURITY.md`](SECURITY.md).
