# Application IR

The IR (`sdc_ir`) is a strongly typed, deterministic representation of a
specification. Its `to_dict()` produces an ordered structure; `canonical_json`
+ sha256 produce the `ir_hash`.

Top-level sections: `application, api, authentication, authorization, data,
behavior, security, performance, reliability, observability, deployment,
testing, dependencies`.

Authorization rules are **structured and compilable**, e.g.

```json
{ "effect": "deny", "subject": "any", "predicate": {"op": "cross_tenant"} }
{ "effect": "allow", "subject": "user", "predicate": {"op": "same_tenant", "scope": "own"} }
```

Determinism guarantee: identical specifications produce an identical canonical
IR and therefore an identical `ir_hash`.

Provenance hashes: `specification_hash`, `ir_hash`, `build_id`, `artifact_hash`.
