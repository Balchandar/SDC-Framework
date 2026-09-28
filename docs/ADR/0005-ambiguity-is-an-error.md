# ADR-0005: Ambiguity is an error; no silent defaults; profile never changes meaning

- Status: Accepted
- Date: 2026-09-24

## Context

A specification compiler is only valuable if its output means what the
source says. The MVP invented behavior (statuses, roles, fixture principals),
dropped statements silently, and allowed semantic errors through because
they were marked `regenerable` (D5).

## Decision

- Diagnostic severities: `ERROR`, `AMBIGUOUS`, `UNRESOLVED`, `WARNING`,
  `INFO`. **Compilation requires zero `ERROR`, `AMBIGUOUS` and `UNRESOLVED`
  diagnostics** (INV-03).
- Defaults are allowed only where the language specification lists them,
  and every applied default is recorded in the IR with its rule id (INV-04).
  Security-relevant values have no defaults.
- Build profiles (`dev`, `release`) change only the verification policy and
  the signing key. They never change the IR or the artifact.
- `regenerable` is removed from the error model.

## Consequences

- Some specifications that "worked" in the MVP will not compile until they
  are made explicit. This is the intended trade: explicit failure over
  incorrect behavior.
- Warnings never change meaning. The release policy may escalate specific
  warning codes, but that affects only whether a release is allowed.

## Alternatives rejected

- *Best-effort compilation with warnings*: wrong meaning still ships.
- *Stricter rules only in release*: meaning would depend on profile, and dev
  testing would test a different program.
