# Observability

Record the following for every request:

- request ID
- tenant ID
- authenticated principal
- endpoint
- latency
- status code
- authorization decision

Emit structured logs. Expose a metrics endpoint and a health endpoint. Include
the specification hash, build id, and artifact version in telemetry so that
production behavior can be traced back to the exact specification.
