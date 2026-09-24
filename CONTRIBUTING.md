# Contributing to SDC

SDC's architecture is **frozen** ([docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)).
Contributions implement the frozen contracts in the order of
[docs/ROADMAP.md](docs/ROADMAP.md).

## Setup

```bash
pip install -e ".[dev]"
make test
```

## Rules

1. **Contracts before code.** Do not implement a feature whose contract is not
   frozen in `docs/`. To change a frozen contract, propose an ADR in
   `docs/ADR/` first ([ADR-0001](docs/ADR/0001-record-architecture-decisions.md)).
2. **Invariants are law.** Every change must preserve
   [the architecture invariants](docs/ARCHITECTURE.md#9-architecture-invariants),
   and a PR that implements an invariant adds its test.
3. **No language backends, plugins or code generation**
   ([ADR-0006](docs/ADR/0006-declarative-artifact-interpreted-runtime.md)). New
   behavior means extending the artifact vocabulary and a runtime capability,
   by ADR.
4. **No heuristics in the compiler.** Meaning comes only from the grammar in
   [docs/SPECIFICATION.md](docs/SPECIFICATION.md). Ambiguity is a diagnostic,
   never a guess.
5. **No AI and no network in the build**
   ([ADR-0011](docs/ADR/0011-ai-outside-the-build.md)).
6. **Determinism first.** Everything that is hashed is canonical (no floats,
   no `null`, sorted collections). Stages 1–9 read no clock, environment or
   filesystem order.
7. **The runtime never imports the toolchain.**
8. **Dependencies.** The core is stdlib-only, except `cryptography` for
   signatures ([ADR-0014](docs/ADR/0014-implementation-language-and-packaging.md)).

## Legacy code

`packages/` holds the pre-freeze MVP. Fix only the Phase 0 defects there.
Everything else is replaced in later phases, so do not extend it.

## Tests

```bash
make test
pytest tests/parser
```
