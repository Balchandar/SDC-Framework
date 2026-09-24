# Build Reproducibility

Status: **FROZEN.** Governing ADR:
[ADR-0012](ADR/0012-reproducibility-definition.md).

"Reproducible" in SDC is a set of precise, testable claims at defined levels.
It is not an aspiration.

---

## 1. Build inputs

A build is fully determined by:

| Input | Identity | Definition |
|---|---|---|
| Source | `sourceHash` | Source-set manifest over raw file bytes ([COMPILER.md](COMPILER.md#stage-1-load)) |
| Compiler version and identity | `compiler.version`, `compilerHash` | §2 |
| Compiler configuration | `configHash` | `sha256(JCS(effective config))`: profile, waivers, policy. Signing key *references* only; AI settings are excluded, because they cannot affect the build |
| Dependency lock | `lockHash` | `sha256(sdc.lock bytes)`: runtime version and `runtimeHash`, capability versions |
| Target runtime | `runtimeContract`, `runtimeHash` | From the lock |

```text
buildId = sha256(JCS({ sourceHash, compilerHash, configHash, lockHash }))
```

`buildId` is deterministic (the full 256 bits, not the MVP's truncated 64). A
per-run `invocationId` (random) and timestamps exist only in the statement's
`metadata` section, which is excluded from every reproducibility comparison.

## 2. Compiler identity

```text
compilerHash = sha256(JCS({
  name: "sdc", version,
  files: [ {path, sha256} … ]        # every file of the installed sdc.ir, sdc.compiler,
                                      # and sdc_runtime.contract packages, sorted
  python: { implementation, major, minor },
  unicode: unicodedata.unidata_version
}))
```

Python and the Unicode database version are included because NFC
normalization and case folding depend on them. An editable or dirty install
yields a distinct `compilerHash`, so such builds are identifiable and never
mistaken for a released compiler.

## 3. Reproducibility levels

| Level | Claim | Status |
|---|---|---|
| **R0 Semantic** | Same `sourceHash` + same `compiler.version` ⇒ same `irHash` | **Mandatory.** Tested |
| **R1 Artifact** | Same (`sourceHash`, `compilerHash`, `configHash`, `lockHash`) ⇒ **byte-identical artifact** (same `artifactHash`) | **Mandatory.** A violation is a P0 compiler defect. CI builds twice in different directories, users and `TZ` settings, and compares |
| **R1′ Artifact across compiler patches** | A compiler patch release promises an identical `artifactHash` for identical `irHash` unless its changelog says otherwise | Expected; checked by golden tests |
| **R2 Statement identity** | Same inputs ⇒ identical `statement.predicate.identity` object | **Mandatory** |
| **R3 Verification outcome** | Same `artifactHash` + `runtimeHash` + `verifierHash` ⇒ identical status for every static and dynamic obligation | **Mandatory** for static and dynamic; measured obligations are exempt and marked `reproducible: false` |
| **R4 Executable package** | Same release + same runtime package + same packaging recipe ⇒ byte-identical package | **Best effort** (§5) |

**The SDC definition of "reproducible build":** R0, R1, R2 and R3 hold. In
particular, anyone with the source set, the recorded compiler and the lock can
regenerate a byte-identical artifact and an identical statement identity.

What is deliberately **not** byte-reproducible, and why:

- The **statement `metadata`** (timestamps, builder host, invocation id)
  describes the event, not the product.
- **Evidence of measured obligations**: physical measurements vary.
- The **evidence document as a whole** when it contains measured
  obligations, because timings are part of it. `verificationId` then differs
  between runs, but the per-obligation statuses of R3 do not.
- **Signatures**: Ed25519 is deterministic, so the same key and payload give
  the same signature. The payload includes `metadata`, however, so envelopes
  differ between builds. Trust never depends on envelope equality.

## 4. Enabling rules (what makes R1 true)

1. The compiler reads only the source set, `sdc.toml` and `sdc.lock`
   (INV-01).
2. No clock, randomness, environment variables, locale, hostname, user,
   working directory or absolute path is read by stages 1–9.
3. Canonical JSON everywhere (INV-07). No floats. Sets are sorted.
4. Iteration order never comes from filesystem listing order (the source set
   is sorted by path), and never from hash-map order (collections are sorted
   by id).
5. The artifact excludes `sourceHash` and `compilerHash`, so trace-only edits
   and compiler patches with identical output do not change it.
6. Text is NFC-normalized, and the Unicode version is part of the compiler
   identity.
7. Line endings are normalized for parsing, while `sourceHash` uses raw bytes.
   Therefore a Windows CRLF checkout has a different `sourceHash` but the same
   `irHash` and `artifactHash`, and provenance shows exactly that.

## 5. Executable packaging (R4)

For `Packaging: container`:

- The base image is pinned by digest, recorded in the lock.
- Layers are built with `SOURCE_DATE_EPOCH=0`, sorted tar entries, uid/gid 0,
  fixed mtimes and fixed permissions.
- The contents are the runtime distribution (pinned wheel hashes), the release
  file and the trust config *template*.

Registries may recompress layers, so R4 is best effort. The **canonical
executable identity** is therefore defined independently of packaging:

```text
executableId = sha256(JCS({ runtime: runtimeHash, artifact: artifactHash }))
```

The runtime logs `executableId` at startup. Two deployments with the same
`executableId` execute the same program on the same runtime, whatever their
image digest.

## 6. Checking reproducibility

`sdc build --reproduce <release>`:

1. Reads the release statement's identity (`sourceHash`, `compilerHash`,
   `configHash`, `lockHash`).
2. Refuses if the current source set or compiler differs, and prints which
   input differs.
3. Recompiles, then compares `irHash`, `traceHash`, `artifactHash` and the
   identity object byte for byte.
4. Optionally (`--with-verification`) re-runs verification and compares the
   R3 statuses.

Output: `REPRODUCED` or `NOT_REPRODUCED` with the first differing field. CI
runs this against every release candidate.
