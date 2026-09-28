# ADR-0011: AI stays outside the build; its output enters only as reviewed source

- Status: Accepted
- Date: 2026-09-24

## Context

In the MVP, an AI provider ran inside the build, and silently fell back to a
deterministic planner when the provider was missing or failed. Provenance
recorded the requested provider, not the one used (D9). The AI "plan" did not
drive code generation anyway (D8). If AI output flowed into the IR directly,
the IR would no longer be a function of source, and neither reproducibility
nor review would hold.

## Decision

- `sdc compile`, `sdc verify` and `sdc build` never invoke AI and never use
  the network.
- AI is used only by `sdc assist`. It produces schema-constrained proposals,
  which are validated, normalized and **rendered deterministically into a
  Markdown patch** for human review. Once applied, the patch is ordinary
  source.
- Provider failure policy is explicit: `FAIL` (the default, and mandatory in
  CI), `FALLBACK_LOCAL` or `FALLBACK_CACHED`. Fallbacks are always printed and
  recorded.
- Every invocation writes a committed ledger entry (provider, model,
  `modelVersion`, `promptHash`, `inputHash`, `outputHash`,
  `configurationHash`, outcome, per-file result hashes). Provenance includes
  `ledgerHash` and per-file attribution.
- The MVP's keyword heuristics become the deterministic local proposer.

## Consequences

- SDC is fully functional without any LLM.
- Machine-authored input is always visible as a diff and attributable.
- A bad proposal can at worst be accepted by a human reviewer; it can never
  bypass the compiler.

## Alternatives rejected

- *Structured proposal validated straight into the IR*: the IR stops being a
  function of source, and reproducibility and review are lost.
- *Silent fallback*: changes behavior invisibly, as happened in the MVP.
