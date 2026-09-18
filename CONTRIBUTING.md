# Contributing to SDC

Thanks for your interest. SDC is a proof-of-concept compiler/framework; the bar
is correctness, clear boundaries, and tests.

## Setup

```bash
pip install -e ".[dev]"
make test
```

## Principles

1. **The specification is the source of truth.** Never make generated code
   authoritative. It must remain safe to delete and regenerate.
2. **Keep boundaries clean.** No provider logic in the domain layer; no compiler
   dependency in generated apps; the verifier stays independent of generation.
3. **Determinism first.** Anything that feeds a hash must be canonical.
4. **Write tests before declaring a stage complete.** Each compiler stage has a
   corresponding `tests/` directory.

## Adding a code backend

Implement `sdc_codegen.backends.base.CodeBackend` and register it with
`sdc_codegen.register_backend(...)`. Do not change the specification format or
the IR to accommodate a backend — the IR + plan are the contract.

## Adding an AI provider

Implement `sdc_compiler.providers.AIProvider` and register with
`register_provider(name, cls)`. Providers must produce a **plan**, never code,
and must degrade gracefully (return `available() == False`) when a key/SDK is
missing.

## Style

- Standard library only in the core packages (`sdc-ir`, `sdc-parser`,
  `sdc-compiler`, `sdc-codegen`, `sdc-runtime`, `sdc-verifier`). Third-party
  dependencies belong in optional extras.
- Match the surrounding code's naming and comment density.

## Tests

```bash
make test          # full suite
pytest tests/parser
```
