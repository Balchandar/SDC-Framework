# SDC — Markdown-Native Application Compiler

> Humans specify software. Machines implement it. Verification establishes that
> the implementation satisfies the specification.

SDC is a proof-of-concept software-development model in which developers
describe an application's **behavior, APIs, data, security, authorization,
performance, and deployment** in human-readable Markdown. SDC transforms those
specifications into a strongly typed **Application IR**, uses a
provider-neutral **AI compiler** to produce a validated implementation plan and
a generated implementation, **verifies** the implementation against the
specification by running it, and produces a deployable artifact plus a signed
manifest.

**The specification files are the source of truth. Generated code is an
intermediate artifact — safe to delete and regenerate, never the authoritative
project source.**

```text
Markdown Specs → Parser → Application IR → AI Compiler → Implementation
                                              ↓
                            Verification ← (independent) → Optimization → Artifact
```

## Quickstart

```bash
pip install -e .

# scaffold a new project
sdc init my-service

# or use the bundled example
cd examples/customer-api

sdc validate     # parse + validate the specs
sdc inspect      # show the Application IR
sdc compile      # generate the implementation
sdc verify       # run the implementation and check it against the spec
sdc build        # validate + compile + verify + produce dist/<name>
sdc run          # run the generated service locally
sdc diff A B     # semantic diff between two spec versions
```

A successful `sdc build` in `examples/customer-api` produces `dist/customer-api`
— a self-contained, standalone HTTP service (Python stdlib only) implementing
`GET /customers/{id}` and `GET /customers` with authentication, authorization,
tenant isolation, structured logging, metrics, health checks, graceful
shutdown, and automated security + behavioral verification.

```bash
SDC_JWT_SECRET=dev-secret PORT=8080 ./dist/customer-api
```

## The MVP loop

1. Write the specs (`project.md`, `api.md`, `authentication.md`,
   `authorization.md`, `data.md`, `behavior.md`, `security.md`,
   `performance.md`, …).
2. `sdc build` → produces `dist/customer-api` and `.build/*.json` reports.
3. Change **only** `authorization.md`.
4. `sdc build` again → SDC detects the semantic change, maps it to affected
   components, regenerates, re-verifies, emits a **semantic diff** and a new
   artifact + manifest.

## Why this is not just an LLM wrapper

- The **AI compiler is provider-neutral** (`local`, `anthropic`, `openai`,
  `google`, custom) and defaults to a **deterministic local planner** so the
  MVP is fully reproducible and offline.
- Model output never becomes an artifact directly — the provider produces a
  **structured plan** that is **validated** before code generation.
- **Verification is a separate authority.** The compiler never declares its own
  output correct; the verifier runs the actual generated service over real HTTP
  and observes behavior.
- The **IR is deterministic**: identical specs → identical `ir_hash`.

## Packages

| Package | Responsibility |
|---|---|
| `sdc-ir` | Strongly typed Application IR, canonicalization, hashing, error taxonomy |
| `sdc-parser` | Markdown → sections → semantic normalization → IR → validation |
| `sdc-compiler` | Provider-neutral AI compiler, planning, drift analysis, semantic diff |
| `sdc-codegen` | Backend abstraction; Python-stdlib HTTP backend |
| `sdc-runtime` | Stable runtime substrate targeted by generated services |
| `sdc-verifier` | Independent behavioral, security, and performance verification |
| `sdc-cli` | The `sdc` command-line compiler and orchestrator |

See [`ARCHITECTURE.md`](ARCHITECTURE.md) and [`docs/`](docs/) for details.

## Status

This is a serious proof-of-concept, not a throwaway demo, but it is an MVP:

- The first realized code backend is `python-stdlib-http` (chosen for
  reproducibility and zero-dependency verification anywhere). The IR and plan
  are language-agnostic; a native backend (e.g. Rust/axum) implements the same
  contract without any specification change.
- PostgreSQL is supported via a generated, parameterized adapter; verification
  uses a deterministic in-memory store.
- Performance verification is an **indicative local latency benchmark**;
  throughput targets are recorded but reported `UNVERIFIED` (SDC never claims a
  target it did not measure). See [`docs/verification.md`](docs/verification.md).

## License

Apache-2.0. See [`LICENSE`](LICENSE).
