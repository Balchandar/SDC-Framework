# Security

## Security model

SDC's trust boundaries, trusted computing base, threat model and key handling
are specified in [docs/SECURITY-MODEL.md](docs/SECURITY-MODEL.md). Runtime
isolation is in [docs/RUNTIME.md](docs/RUNTIME.md).

## Status of the legacy MVP

The code in `packages/` predates the architecture freeze and has **known
security defects**, documented and reproducible in
[docs/ASSESSMENT.md](docs/ASSESSMENT.md#3-verified-defects). Among them:

- tokens forged with an empty key are accepted when `SDC_JWT_SECRET` is
  unset;
- a missing role claim defaults to `user`;
- artifacts are not integrity-checked before execution.

**Do not deploy artifacts produced by the MVP.** Roadmap Phase 0 fixes the
directly exploitable defects; the rest are removed by construction in the new
architecture.

## Reporting a vulnerability

Please report suspected vulnerabilities privately through GitHub Security
Advisories on this repository ("Report a vulnerability") rather than in a
public issue. Include the SDC version, `compilerHash` / `runtimeHash` if
available, and a minimal reproduction.
