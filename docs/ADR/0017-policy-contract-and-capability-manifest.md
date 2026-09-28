# ADR-0017: The SDC Policy Contract and capability manifest; Cedar as oracle, no hard-coded policy engine

- Status: Accepted
- Date: 2026-09-24
- Amends: sdc/1 ([SPECIFICATION.md](../SPECIFICATION.md)) and
  `sdc.artifact/1` ([ARTIFACT.md](../ARTIFACT.md)). Both are amended **before
  any implementation exists**, which ADR-0001 permits
- Contract: [POLICY.md](../POLICY.md)

## Context

The v1 freeze expressed authorization as IR sections and an artifact `authz`
block, but it had no single policy abstraction. It had no notion of
*capability* security as distinct from *authorization*. Its data model could
not say "shown to authorized users but never logged" (for example, patient
names). OPA and Cedar were proposed as policy engines.

## Decision

1. **SDC Policy Contract 1**: a typed, lossless view `policyView(ir)` over the
   IR, with six parts: AuthenticationPolicy, AuthorizationPolicy,
   DataAccessPolicy, AuditPolicy, NetworkPolicy and CapabilityPolicy. SDC
   defines its semantics normatively (deny precedence, default deny,
   order-independent, total conditions). It is serialized as
   `artifact.policy`, and its sub-hash is `policyHash`.
2. **Capability manifest**: capabilities are declared in `dependencies.md`
   (Capabilities table). The compiler checks `required ⊆ declared` (otherwise
   `ERROR SDC-R030`) and emits `granted = required ∩ declared` plus explicit
   `denied` rows as `artifact.capabilities` (sub-hash `capabilityHash`).
   Capability rows are critical requirements.
3. **Authorization and capability security are distinct** and both compiled.
   Authorization is enforced by the host PDP per request. Capabilities are
   enforced by the host linker and capability layer per program.
4. **Data classification** `standard | personal | secret` replaces `Sensitive:
   yes|no`. `personal` data is returned to authorized requests but never
   logged. `secret` data never leaves the host.
5. **The sdc/1 vocabulary gains** the `search` operation (an explicit criteria
   table, AND-combined, `Criteria` and `Max-Results` required) and the
   `search` action.
6. **Policy engines**:
   - no engine is hard-coded as the runtime evaluator in contract 1; the host
     reference PDP implements the contract semantics directly;
   - **Cedar is preferred and adopted now as an independent verification
     oracle**: the verifier translates the IR (not the artifact) to Cedar and
     cross-checks the whole permission matrix;
   - Cedar is the designated path for richer conditions (U1), adopted as PDP
     by a future ADR;
   - **OPA is not selected** for application authorization;
   - there is no policy-backend plugin architecture.

## Rationale

- One contract with SDC-defined semantics keeps meaning in SDC, not in an
  engine's version history.
- Cedar's model (default deny, `forbid` overrides `permit`, no external
  effects, bounded evaluation) matches the contract. Its formalization in
  Lean, differential testing and symbolic analysis make it an unusually
  strong *independent* oracle, which addresses the common-mode risk K3.
- OPA's generality (builtins including network and time; a general-purpose
  language) is the unbounded surface SDC avoids. Its Wasm form requires
  host-implemented builtins.
- Capabilities make least privilege computable, reviewable and verifiable per
  artifact, and they map directly onto Component Model imports (ADR-0016).

## Consequences

- New grammar and IR elements (Capabilities table, `Classification`,
  `search`), and new artifact sections (`policy`, `capabilities`).
- The verifier depends on Cedar (a verification-time dependency, not in the
  runtime TCB). A Cedar defect can at worst produce a false disagreement
  (`FAIL`, then investigation) or, together with an identical runtime defect,
  a false agreement.
- A future move to Cedar as PDP requires an ADR, a translation that is
  proved equivalent over contract 1 (E5), and conformance.

## Alternatives rejected

- *Hard-code OPA*: general-purpose, nondeterministic builtins, users pulled
  toward Rego.
- *Hard-code Cedar now as PDP*: a second semantics to synchronize, for no
  expressiveness contract 1 needs. Deferred, not rejected.
- *Support both behind a plugin interface*: explicitly forbidden, and it
  multiplies semantics.
- *Keep `Sensitive: yes/no`*: cannot express "visible but never logged".
