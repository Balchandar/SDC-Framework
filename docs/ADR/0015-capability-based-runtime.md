# ADR-0015: Runtime I/O goes only through declared, versioned capabilities, denied by default

- Status: Accepted
- Date: 2026-09-24

## Context

Runtime isolation (filesystem, network, CPU, memory, processes, secrets) must
be enforceable, and the exact sandbox technology is not yet chosen. Access
must be decidable from the artifact itself.

## Decision

- The artifact lists required capabilities with major versions (`requires`).
  The runtime refuses artifacts that need capabilities it lacks.
- Contract 1 capabilities: `http.server`, `authn.jwt`, `authz.policy`,
  `store.sql`, `store.fixture` (verify mode only), `log`, `metrics`, `clock`
  and `random`.
- There is no filesystem, outbound network, subprocess or dynamic-loading
  capability. Everything not declared is denied.
- Secrets are declared by name. The runtime supplies values from its secret
  source, and a missing value refuses startup.
- A sandbox profile (filesystem, network egress, resource limits, secret
  names) is derived from the artifact and deployment section. The enforcing
  technology is an open decision (U6).

## Consequences

- Least privilege is computable and reviewable per artifact.
- New I/O kinds (outbound HTTP, queues) require a new capability, and
  therefore an ADR plus a conformance suite.

## Alternatives rejected

- *Ambient authority (the process can do anything the OS allows)*: this was
  the MVP; isolation would then depend entirely on the deployment.
- *Choosing the sandbox technology now*: premature. The contract is what
  must be stable.
