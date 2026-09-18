# Verification

The verifier (`sdc_verifier`) is an independent authority. It runs the actual
generated service over real HTTP and observes behavior; it never trusts the
compiler's claim of correctness.

## Suites

- **API contract** — declared routes respond.
- **Behavioral** — spec test cases plus auto-generated positive/negative
  authorization cases (same-tenant allowed, cross-tenant denied, unauthenticated
  denied, admin allowed, missing → not found).
- **Security** — static scans (SQL injection, unsafe deserialization, path
  traversal, SSRF, hardcoded secrets, forbidden deps) and dynamic checks
  (authentication enforced, tenant isolation, secret exposure, sensitive
  logging, security headers, auditable decisions).
- **Performance** — an indicative local p99 latency benchmark vs the target.

## Honesty about performance

The MVP performs a **local micro-benchmark**, not a distributed load test.
Latency (`p99_latency`) is checked against the target and is blocking.
Throughput targets (RPS) are recorded but reported `UNVERIFIED` because a
representative load test is out of scope for the MVP. SDC never claims a target
it did not measure.

## Build gating

A **mandatory** check that fails **fails the build**; no artifact is produced.
Checks with no automated implementation are `UNVERIFIED` (visible,
non-blocking).
