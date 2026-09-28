# Architecture Decision Records

An ADR records one decision that is expensive or impossible to reverse. The
architecture freeze of 2026-09-24 accepted ADR-0001 to ADR-0015. The Wasm
execution-substrate evaluation of the same date added ADR-0016 and ADR-0017.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions; freeze semantics | Accepted |
| [0002](0002-markdown-controlled-grammar.md) | Markdown is the only source language; meaning comes from a controlled structural grammar | Accepted |
| [0003](0003-semantic-ir-contract.md) | The Semantic IR is the sole compilation input: versioned, split into semantics and trace | Accepted |
| [0004](0004-requirement-identifiers.md) | Stable requirement ids are declared in source | Accepted |
| [0005](0005-ambiguity-is-an-error.md) | Ambiguity is an error; no silent defaults; profile never changes meaning | Accepted |
| [0006](0006-declarative-artifact-interpreted-runtime.md) | No language backends; a declarative artifact interpreted by a fixed runtime | Accepted (amended by 0016) |
| [0007](0007-artifact-canonical-json.md) | The artifact is one canonical JSON document, content-addressed | Accepted |
| [0008](0008-detached-attestations-release-bundle.md) | Evidence, provenance and signature are detached and bound by hash in a release bundle | Accepted |
| [0009](0009-runtime-executes-only-verified-releases.md) | The runtime executes only verified releases and fails closed | Accepted |
| [0010](0010-verification-mandatory-for-release.md) | Verification is mandatory for release, under the obligation model and release policy | Accepted |
| [0011](0011-ai-outside-the-build.md) | AI stays outside the build; its output enters only as reviewed source | Accepted |
| [0012](0012-reproducibility-definition.md) | Reproducibility is defined as a byte-identical artifact from declared inputs | Accepted |
| [0013](0013-semantic-diff-model.md) | Semantic diff runs over IR nodes and effects, keyed by requirement id | Accepted |
| [0014](0014-implementation-language-and-packaging.md) | Python is the reference implementation; the runtime is separable; `cryptography` is allowed | Accepted (runtime language superseded by 0016) |
| [0015](0015-capability-based-runtime.md) | Runtime I/O goes only through declared, versioned capabilities, denied by default | Accepted |
| [0016](0016-wasm-execution-substrate.md) | Wasm Component Model on Wasmtime is the execution substrate for a fixed engine; no per-app Wasm; no custom VM | **Accepted with conditions** (C1–C7) |
| [0017](0017-policy-contract-and-capability-manifest.md) | SDC Policy Contract and capability manifest; Cedar as verification oracle; OPA not selected; no hard-coded engine | Accepted |

Template: Context → Decision → Consequences → Alternatives rejected.
