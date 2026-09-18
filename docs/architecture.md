# Architecture (docs)

This page complements the top-level [`ARCHITECTURE.md`](../ARCHITECTURE.md).

The toolchain is a linear pipeline of decoupled stages, each producing a
machine-readable artifact. The two authorities that matter — the **AI
compiler** (generation) and the **verifier** (judgement) — are independent, so
the system that writes the implementation is never the system that certifies
it.

```text
specs → parser → IR → compiler → generated impl → verifier → artifact
```

Key modules:

- `sdc_cli.pipeline.Toolchain` — orchestration (parse/validate/compile/verify/build).
- `sdc_compiler.AICompiler` — provider-neutral generation via a validated plan.
- `sdc_verifier.verify` — runs the artifact and observes behavior.
