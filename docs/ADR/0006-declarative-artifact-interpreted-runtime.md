# ADR-0006: No language backends; a declarative artifact interpreted by a fixed runtime

- Status: Accepted. Amended by [ADR-0016](0016-wasm-execution-substrate.md): the
  interpreter runs as a fixed Wasm component. The decision below is unchanged
- Date: 2026-09-24

## Context

The MVP had a `CodeBackend` abstraction, a `python-stdlib-http` backend, and a
plan with `language`, `framework` and `backend`. It promised Rust and other
backends. That turns SDC into a multi-language code generator, which is
explicitly not the goal. Generated code is also hard to verify: the MVP's
static security checks were regexes over its own template.

However, the MVP's generated service was *already* a fixed runtime plus
application data (authorization rules, behavior map, sensitive fields,
tenant fields, a route table). Its `Policy` class interpreted rules as data.
The per-application part of the code carried no logic beyond pasted
constants.

## Decision

- The compiled program (the artifact) is a **declarative document** in a
  closed, versioned vocabulary: operations, policy, entities, outcomes,
  limits and observability, each element carrying `derivedFrom` requirement
  ids.
- A **fixed, trusted runtime** implements a versioned runtime contract and
  versioned capabilities, and interprets the artifact.
- No code is generated in any language. No backend, plugin or language
  abstraction exists. `sdc_codegen`, `ImplementationPlan` and
  `KNOWN_BACKENDS` are deleted.
- Another runtime implementation (any language) is allowed only as a
  conformant implementation of the *same contract*. The artifact bytes are
  identical for every runtime.

## Consequences

- Security and behavior properties become statically checkable over data.
- The artifact is small, canonical, reproducible and diffable.
- **Expressiveness is bounded by the vocabulary** (risk K1). Extending it
  requires an ADR. If computation becomes unavoidable, only a total,
  side-effect-free expression sublanguage may be admitted (U1).
- The runtime is the most security-critical code, and it gets a conformance
  suite.

## Alternatives rejected

- *Keep language backends*: violates the SDC vision; adds an unverifiable
  TCB per language.
- *Bytecode / VM*: introduces an instruction set, and therefore a language,
  for computation SDC does not need.
- *WASM*: its purpose is isolating untrusted code, and there is none.
  **Amended by ADR-0016:** this rejection stands for Wasm *as the artifact
  format* (per-app generated code). It was incomplete as a rejection of Wasm
  *as the substrate for the fixed interpreter*, because the interpreter
  processes untrusted input and benefits from confinement. ADR-0016 adopts
  that use.
- *Native compilation*: the same problems as backends; performance is not the
  constraint at this vocabulary size.
