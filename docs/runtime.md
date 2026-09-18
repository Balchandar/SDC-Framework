# Runtime

`sdc_runtime` is the stable substrate that generated services target. It is
standard-library-only and is **inlined** into the standalone artifact, so the
runtime package is the single source of truth while the artifact stays
self-contained.

Provides: `Config`, `StructuredLogger` (with redaction), `Metrics`
(Prometheus text), `App`/`Router`/`Request`/`Response` (threaded HTTP server
with security headers, request IDs, graceful shutdown), `jwt_encode`/
`jwt_verify` (HS256, no dependency), `Principal`, `Policy` (authorization rule
interpreter), `Store`/`InMemoryStore`/`PostgresStore` (parameterized), and
`project_fields` (sensitive-field stripping).

Lifecycle: `App.serve()` installs SIGTERM/SIGINT handlers for graceful
shutdown and exposes `/healthz`, `/readyz`, `/metrics`.
