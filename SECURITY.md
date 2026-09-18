# Security

## Threat model for the compiler

SDC treats the AI compiler layer as **untrusted or partially trusted**. The
framework never lets model output become an executable artifact directly:

1. A provider produces a **structured implementation plan** (data), not code.
2. The plan is **validated** against a schema before code generation.
3. Generated code is executed **only** by the verifier, under confinement.

### Confinement of generated-code execution

The verifier runs the generated service in a subprocess that is:

- bound to **loopback only** (`127.0.0.1`, ephemeral port);
- given a **fresh, random signing secret** per run (`SDC_JWT_SECRET`);
- **never** passed production credentials (`DATABASE_URL` is stripped; the
  in-memory store is forced);
- **terminated** on teardown, with a kill fallback on timeout.

Filesystem/network/CPU/memory isolation and execution timeouts are the intended
sandbox surface; the MVP applies loopback binding, credential stripping,
subprocess isolation and timeouts. Stronger OS-level sandboxing (cgroups,
seccomp, containers) is a documented extension point.

## Security requirements as executable checks

Security requirements in `security.md` become verification checks where a
machine check exists (see `sdc_verifier/security.py`):

- authentication enforcement, authorization enforcement, tenant isolation
- secret exposure (responses), sensitive logging (logs)
- SQL injection (parameterized queries; whitelisted identifiers)
- unsafe deserialization, path traversal, SSRF
- security headers, insecure configuration, forbidden dependencies

A **mandatory** check that fails **fails the build** — no artifact is produced.
Requirements with no automated check are reported `UNVERIFIED` (visible,
non-blocking) rather than silently passed.

## Properties of the generated artifact

- Sensitive fields (marked in `data.md`) are stripped from all responses and
  redacted from logs.
- Secrets are read from the environment, never embedded.
- Database access uses parameterized queries; table identifiers are validated
  against a safe-identifier allowlist.
- Every response carries baseline security headers.
- Every authorization decision is logged (auditable).

## Reporting

This is a proof-of-concept. Please open an issue for security concerns.
