# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Architecture freeze (2026-09-24)

- Froze architecture v1: the source language `sdc/1`, Semantic IR 1.0,
  `sdc.artifact/1`, `sdc.release/1`, `sdc.evidence/1`, the
  `sdc.provenance/1` statement and runtime contract 1.
  See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- Added ADR-0001 to ADR-0015 (`docs/ADR/`).
- Added the assessment of the MVP, with 19 documented defects and a
  reproduction script (`scripts/assessment_probe.py`).
- Added the dependency-ordered implementation roadmap.
- Removed documents superseded by the freeze: root `ARCHITECTURE.md` and the
  lowercase `docs/*.md` files. The lowercase files would also have collided
  with the uppercase deliverables on case-insensitive filesystems.
- The `packages/` MVP is now designated **legacy**. No code behavior changed
  in this entry.

## [0.1.0]

- MVP: Markdown → Application IR → Python stdlib service, with verification
  and a manifest.
