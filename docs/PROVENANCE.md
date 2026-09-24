# Provenance

Status: **FROZEN — statement predicate `sdc.provenance/1`.** Governing ADRs:
[ADR-0008](ADR/0008-detached-attestations-release-bundle.md),
[ADR-0012](ADR/0012-reproducibility-definition.md).

Every release answers the question "where did this executable come from?"
with a signed statement. Provenance records **what actually happened**, never
what was requested (INV-13). The MVP recorded the *requested* provider even
when a fallback was used (D9); that class of defect is ruled out here.

---

## 1. Statement

The statement follows the in-toto Statement v1 layout, so standard
supply-chain tooling can read it. The SDC predicate carries the details.

```json
{
  "_type": "https://in-toto.io/Statement/v1",
  "subject": [ { "name": "customer-service@1.0.0",
                 "digest": { "sha256": "<artifactHash hex>" } } ],
  "predicateType": "urn:sdc:provenance:1",
  "predicate": {
    "identity": {
      "buildId":        "sha256:…",
      "sourceHash":     "sha256:…",
      "irHash":         "sha256:…",
      "traceHash":      "sha256:…",
      "artifactHash":   "sha256:…",
      "irVersion":      "1.0",
      "languageVersion":"sdc/1",
      "compiler":       { "name": "sdc", "version": "1.0.0", "hash": "sha256:…" },
      "configHash":     "sha256:…",
      "lockHash":       "sha256:…",
      "dependencyHash": "sha256:…",
      "runtimeContract": 1,
      "targetRuntime":  { "version": "1.0.0", "hash": "sha256:…" },
      "profile":        "release",
      "sources": [ { "path": "security.md", "sha256": "…" } ]
    },
    "verification": {
      "verificationId": "sha256:…",
      "verifier":       { "version": "1.0.0", "hash": "sha256:…" },
      "runtime":        { "version": "1.0.0", "hash": "sha256:…" },
      "decision":       "RELEASABLE",
      "blocking":       [],
      "waivers":        [],
      "coverage":       { "requirements": 31, "pass": 30, "unverified": 1, "fail": 0, "blocked": 0 }
    },
    "ai": {
      "ledgerHash": "sha256:…",
      "entries": [
        { "id": "prop-2026-…", "provider": "anthropic", "model": "…", "modelVersion": "…",
          "promptHash": "sha256:…", "inputHash": "sha256:…", "outputHash": "sha256:…",
          "configurationHash": "sha256:…", "policy": "FAIL", "outcome": "APPLIED",
          "files": [ { "path": "security.md", "resultSha256": "…", "matchesCurrent": true } ] }
      ],
      "unattributedChanges": [ ]
    },
    "metadata": {
      "invocationId": "…", "startedAt": "2026-09-24T10:00:00Z", "finishedAt": "…",
      "builder": { "os": "linux", "arch": "x86_64", "python": "3.12.4" },
      "vcs": { "commit": "…", "dirty": false }
    }
  }
}
```

## 2. Field reference

| Field | Meaning |
|---|---|
| `identity.*` | Deterministic (R2). Anyone can recompute it from the inputs |
| `sourceHash` / `sources` | The exact source bytes. `sources` lists per-file hashes so a single changed file is identifiable |
| `irHash`, `traceHash` | Meaning, and where it came from |
| `artifactHash` | Also the statement subject. This is what the signature ultimately vouches for |
| `compiler.hash` | `compilerHash` ([BUILD-REPRODUCIBILITY.md §2](BUILD-REPRODUCIBILITY.md#2-compiler-identity)) |
| `dependencyHash` | Equals `lockHash` in v1. It is kept as a separate name so that a future lock format can hash only its dependency section |
| `targetRuntime` | The runtime the lock pins, which is the one verification used |
| `verification.verificationId` | `evidenceHash`, which binds the embedded evidence |
| `verification.runtime` | The runtime evidence was **actually** produced on |
| `ai.entries` | AI proposals from the ledger that touched the current sources |
| `ai.unattributedChanges` | Critical-section changes since the base release that have no ledger entry (when `require-attribution` is configured) |
| `metadata` | The event record. Not reproducible, and never used for trust |

## 3. Signature

- `signature` is **not** a field of the statement, because a signature cannot
  be inside what it signs. It lives in the DSSE envelope of the release
  ([ARTIFACT.md §2](ARTIFACT.md#2-release-bundle)).
- `statementHash = sha256(JCS(statement))`. The signed payload is exactly
  those canonical bytes.

## 4. What provenance never contains

Secrets, API keys or tokens; prompt or response text (only their hashes; the
ledger may keep the full text, see [AI-INTEGRATION.md](AI-INTEGRATION.md#5-ledger));
absolute paths; user names; environment variable values.

## 5. Answering "where did this executable come from?"

Given a running process:

1. Its startup log prints `executableId`, `artifactHash`, `buildId`,
   `runtimeHash` and the signer `keyid`.
2. `sdc inspect --verify <release>` shows the statement and checks every
   hash.
3. `identity.sources` + `vcs.commit` locate the exact source.
4. `identity.compiler` identifies the toolchain, and `sdc build --reproduce`
   proves the path from source to artifact.
5. `verification` shows the evidence, and `ai` shows any machine-authored
   input.
