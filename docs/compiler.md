# Compiler

The AI compiler (`sdc_compiler.AICompiler`) is provider-neutral. It:

1. asks an `AIProvider` for a **structured implementation plan** from the IR,
2. **validates** the plan (`validate_plan`),
3. drives the selected **code backend** to generate the implementation.

Model output never becomes an artifact directly. The default provider
(`local`) is deterministic and offline; `anthropic`, `openai`, `google` and
custom providers implement the same interface and degrade gracefully when a
key/SDK is absent.

## Implementation plan

```json
{
  "target": "linux-x86_64",
  "language": "python",
  "framework": "stdlib-http",
  "backend": "python-stdlib-http",
  "components": [{"name": "http-server", "derived_from": ["api"]}, ...],
  "optimization_strategy": {...}
}
```

Each component records the IR sections it is `derived_from`, which powers drift
analysis.

## Drift & semantic diff

- `analyze_drift(old_ir, new_ir, plan)` → changed sections, affected/unaffected
  components, affected endpoints, required verification.
- `semantic_diff(old_ir, new_ir)` → semantic changes plus security /
  performance / data / compatibility impact and required verification.
