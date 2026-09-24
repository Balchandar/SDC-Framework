# SDC — Semantic Definition Compiler

> Humans and LLMs describe what the software means. SDC determines how that
> meaning becomes executable. **The compiler, not the LLM, is the authority.**

SDC is a **specification compiler**. It turns human-readable, LLM-friendly
Markdown definitions into one immutable, signed, verifiable artifact. A fixed,
trusted runtime executes that artifact only after proving it is intact,
compatible and verified.

SDC is not an AI code generator, not a set of language backends, not a
template engine and not a new programming language.

```text
             HUMAN / LLM
                  │
                  ▼
          Markdown Specification        the source        (sourceHash)
                  │
                  ▼
            Semantic IR                 the truth model   (irHash)
                  │
                  ▼
              Compiler
                  │
                  ▼
          Immutable Artifact            the program       (artifactHash)
                  │
          ┌───────┴────────┐
          ▼                ▼
      Verification      Provenance
          │                │
          └───────┬────────┘
                  ▼
              Signature                 integrity
                  │
                  ▼
      Runtime (verifies, then executes) behavioral trust through evidence
```

## Status

> **Architecture v1 is FROZEN (2026-09-24).** The frozen contracts live in
> [`docs/`](docs/ARCHITECTURE.md). The code in `packages/` is the **legacy
> MVP prototype**. It predates the freeze and contradicts it in documented
> ways ([`docs/ASSESSMENT.md`](docs/ASSESSMENT.md)). It is being replaced
> phase by phase ([`docs/ROADMAP.md`](docs/ROADMAP.md)). **Do not deploy the
> MVP's output.**

## Architecture documents

| Document | Contents |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Final architecture, invariants, repository structure, critical design test |
| [SPECIFICATION.md](docs/SPECIFICATION.md) | The Markdown source language `sdc/1` |
| [SEMANTIC-IR.md](docs/SEMANTIC-IR.md) | IR v1: types, canonical form, `irVersion` |
| [COMPILER.md](docs/COMPILER.md) | Pipeline stage contracts, profiles, CLI |
| [ARTIFACT.md](docs/ARTIFACT.md) | Artifact and release bundle formats |
| [RUNTIME.md](docs/RUNTIME.md) | Runtime contract and execution model |
| [VERIFICATION.md](docs/VERIFICATION.md) | Obligations, evidence, release policy |
| [SECURITY-MODEL.md](docs/SECURITY-MODEL.md) | Trust boundaries, threats, keys |
| [BUILD-REPRODUCIBILITY.md](docs/BUILD-REPRODUCIBILITY.md) | What "reproducible" means |
| [PROVENANCE.md](docs/PROVENANCE.md) | The signed provenance statement |
| [SEMANTIC-DIFF.md](docs/SEMANTIC-DIFF.md) | Meaning-level diff and impact |
| [AI-INTEGRATION.md](docs/AI-INTEGRATION.md) | The AI boundary |
| [ADR/](docs/ADR/README.md) | Architecture decision records |

## An SDC application (target model)

```text
my-application/
├── sdc.toml             # toolchain configuration (never meaning)
├── application.md       # Language: sdc/1, Name, Version
├── api.md               # operations: ### GET /customers/{id} {#API-001}
├── authentication.md    # scheme, claims table
├── authorization.md     # roles and rules tables (default deny)
├── data.md              # entities: field / type / key / tenant / sensitive
├── behavior.md          # outcome → status table
├── security.md          # requirements table with properties
├── performance.md  reliability.md  observability.md
├── deployment.md  testing.md  dependencies.md
└── .sdc/ledger/         # record of AI-assisted edits (committed)
```

```bash
sdc check            # parse, validate, resolve, analyze → diagnostics
sdc compile          # → .build/artifact.json (artifactHash)
sdc verify           # → evidence + release-policy decision
sdc build            # → dist/<name>-<version>.release.json (signed)
sdc run              # run a release through the verifying loader
sdc diff R1 .        # semantic + effect diff with impact classification
sdc explain SEC-002  # requirement lineage: source → IR → artifact → evidence
```

## Legacy MVP quickstart

The prototype still runs, for reference only:

```bash
pip install -e ".[dev]"
make test                         # 50 tests
cd examples/customer-api && sdc build
python scripts/assessment_probe.py   # reproduces the documented MVP defects
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Changes to frozen documents require an
ADR.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
