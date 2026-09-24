# ADR-0002: Markdown is the only source language; meaning comes from a controlled structural grammar

- Status: Accepted
- Date: 2026-09-24

## Context

SDC sources must be human-readable, LLM-friendly, diffable and reviewable,
and must not require learning a new programming language. The MVP accepted
free prose and assigned meaning by substring matching. That led to inverted
negation, dropped requirements and invented statuses (defects D1–D4). Free
natural language cannot be given deterministic meaning without heuristics,
and heuristics are not a compiler.

## Decision

- Source is CommonMark-subset Markdown, one section per file, with a fixed
  membership rule ([SPECIFICATION.md §1](../SPECIFICATION.md#1-source-set)).
- Meaning is carried **only** by four structural forms: key–value lines,
  tables with known schemas, item headings with `{#ID}`, and closed
  vocabularies for values.
- Prose is allowed everywhere and is always non-normative. It goes to the
  trace, never to the IR.
- Normative-looking prose that is not bound to a structural form is
  `UNRESOLVED` (the normative-prose rule).
- There are no section aliases, and no inference from names, plurals or
  words.

## Consequences

- The same text always has the same meaning, and the grammar can be tested
  exhaustively.
- Authors write tables for anything meaningful. `sdc assist structure` helps
  convert prose into tables.
- The grammar is versioned (`sdc/1`), and vocabulary extensions are language
  changes.

## Alternatives rejected

- *Free prose with better NLP or an LLM interpreter*: non-deterministic, or
  deterministic only per model version; not reviewable.
- *YAML/JSON/TOML or a new DSL*: loses readability and "no new language".
  YAML front matter was considered and rejected, because it splits every file
  into two syntaxes.
- *Keep the heuristics with warnings*: warnings do not prevent the wrong
  meaning from being compiled.
