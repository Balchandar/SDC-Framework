# ADR-0009: The runtime executes only verified releases and fails closed

- Status: Accepted
- Date: 2026-09-24

## Context

In the MVP, a modified artifact still ran (D11), `sdc run` executed
unverified code (D17), an unset secret allowed forged tokens (D7), missing
claims defaulted to a role and a database failure fell back to memory (D14),
and telemetry identity could be overridden from the environment (D13).

## Decision

- The loader chain (parse → signature → hashes → compatibility → policy →
  inputs) runs before any socket opens. Any failure exits with code 3.
- Trusted keys come only from the runtime trust configuration, never from
  the bundle.
- Modes: `production` (signed, `RELEASABLE`), `dev` (also dev-profile
  releases, only with `--allow-dev`), and `verify` (an unsigned artifact, but
  forced to fixture store, loopback and ephemeral secrets).
- Fail-closed semantics: default-deny authorization; missing claims and
  secrets are refused; no fallback between stores; identity telemetry comes
  only from the release.
- The default runtime match rule is `exact`: the executing `runtimeHash` must
  equal the one the evidence was produced on.

## Consequences

- `sdc run` goes through the same loader as production.
- A runtime patch requires re-verification of deployed artifacts (no
  recompilation).

## Alternatives rejected

- *A skip-verification flag*: every such flag is eventually set in
  production.
- *Trust-on-first-use of the embedded key*: allows self-signed forgeries.
- *Contract-level runtime match by default*: weaker than what the evidence
  actually proves.
