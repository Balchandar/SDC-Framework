# Runtime Conformance Suite

Status: **FROZEN — suite structure and switch-over gate.** Governing ADR:
[ADR-0016](ADR/0016-wasm-execution-substrate.md) (condition C6).

The runtime contract ([RUNTIME.md](RUNTIME.md)) is authoritative. A runtime is
*conformant* if and only if it passes this suite. The suite is
**runtime-agnostic**: the Python reference runtime and the Wasm runtime run
exactly the same test cases, through the same adapter protocol, with the same
expected results.

```text
                 tests/conformance (one suite, one expected-results set)
                               │
               ┌───────────────┴───────────────┐
               ▼                               ▼
   Python reference runtime           Wasm runtime (host + sdc-engine)
        PASS (required)                     PASS (required)
               └──────────── differential ─────┘
                 identical outcomes on every example artifact
```

---

## 1. Adapter protocol

A runtime under test is driven only through its public surface, so the suite
never imports runtime internals:

- **Process interface**: the `sdc-runtime` executable (`run`, `verify`,
  `inspect`), its exit codes (0 / 3 / …), and its stdout JSON log lines.
- **Network interface**: HTTP against the configured port.
- **Test hooks available only in verify mode**: a fixture file, the
  injected clock and random seed, and the **capability trace** (a JSON-lines
  record of every host capability call: interface, function, decision id,
  result class). Both runtimes must emit the trace in the same format.
  (The Python runtime emits it from its capability shims.)

## 2. Inputs

- **Golden artifacts and releases**: `tests/conformance/fixtures/*`, produced
  by the SDC compiler from `examples/*`, plus hand-crafted **invalid** inputs
  (tampered, non-canonical, unknown fields, missing capabilities).
- **Test keys**: a conformance trust config with dev, release and untrusted
  keys.
- **Hostile components** (Wasm runtime only): minimal components that
  import forbidden interfaces or call ungranted ones. For the Python runtime,
  the equivalent cases are marked `N/A-substrate`, with justification (§5).

## 3. Test families

| Family | Ids | Covers (RUNTIME.md section) |
|---|---|---|
| Loader | `LOAD-PARSE-*`, `LOAD-CANON-*`, `LOAD-SIG-*`, `LOAD-TAMPER-ARTIFACT`, `LOAD-TAMPER-POLICY`, `LOAD-TAMPER-CAPS`, `LOAD-TAMPER-EVIDENCE`, `LOAD-TAMPER-ENGINE`, `LOAD-COMPAT-*`, `LOAD-POLICY-UNVERIFIED`, `LOAD-POLICY-DEV`, `LOAD-INPUTS-*` | §3: each refusal with its reason code, before any socket opens |
| Modes | `MODE-VERIFY-REFUSES-REAL-STORE`, `MODE-VERIFY-LOOPBACK`, `MODE-VERIFY-EPHEMERAL-SECRETS`, `MODE-DEV-FLAG` | §2 |
| Authentication | `AUTHN-NO-TOKEN`, `AUTHN-BAD-SIG`, `AUTHN-EXPIRED`, `AUTHN-ALG-MISMATCH`, `AUTHN-MISSING-CLAIM`, `AUTHN-EMPTY-SECRET-REFUSES-START` | §6, §11 |
| Authorization | `AUTHZ-DEFAULT-DENY`, `AUTHZ-DENY-PRECEDENCE`, `AUTHZ-ORDER-INDEPENDENT`, `AUTHZ-COND-*` (each condition), `AUTHZ-DENIED-AS-NOTFOUND` (no existence oracle) | POLICY.md §2.1 |
| Data access | `DATA-PROJECTION-SECRET`, `DATA-TENANT-FILTER`, `DATA-SEARCH-CRITERIA-*`, `DATA-MAX-RESULTS`, `DATA-STORE-UNAVAILABLE` (no fallback) | POLICY.md §2, RUNTIME §6 |
| Capabilities | `CAP-DENY-FS`, `CAP-DENY-NET`, `CAP-DENY-ENV`, `CAP-DENY-PROC`, `CAP-UNGRANTED-STORE`, `CAP-UNGRANTED-LOG`, `CAP-CEILING`, `CAP-STORE-REQUIRES-DECISION`, `CAP-STORE-SCOPE` | POLICY.md §4 |
| Logging and audit | `LOG-VOCABULARY-ONLY`, `LOG-NO-PERSONAL`, `LOG-NO-QUERY-STRING`, `LOG-DECISION-AUDITED`, `LOG-IDENTITY-FROM-RELEASE` | §11, POLICY.md §4.4 |
| Outcomes and errors | `OUT-*` per condition; `OUT-INTERNAL-NO-LEAK` | §10 |
| Limits | `LIM-BODY-SIZE`, `LIM-TIMEOUT`, `LIM-CONCURRENCY`, `LIM-MEMORY` | §11 |
| Determinism | `DET-REPLAY`: in verify mode, the same fixtures, clock and seed give byte-identical responses and capability traces | §2, BUILD-REPRODUCIBILITY R3 |
| Lifecycle | `LIFE-SIGTERM-GRACE`, `LIFE-READY-REQUIRES-CAPS` | §9 |

Every test declares the requirement of the runtime contract it covers. A
contract clause with no test is a conformance-suite defect.

## 4. Pass criteria

- **Conformant**: every applicable test passes. `N/A-substrate` is allowed
  only for the hostile-component cases on the Python runtime, where the
  property is provided by OS-level sandboxing instead and is recorded as such.
- **Differential**: for every golden artifact, the dynamic obligations of
  [VERIFICATION.md](VERIFICATION.md) yield **identical statuses** on both
  runtimes, and identical response bodies and capability traces under
  `DET-REPLAY`.
- The suite result is recorded as `sdc.conformance/1` evidence keyed by
  `runtimeHash`. Release evidence cites it (VERIFICATION.md §9).

## 5. Switch-over gate (Python → Wasm)

The Wasm runtime replaces the Python runtime **as the production runtime**
only when all of the following hold on the same commit:

1. Both runtimes are conformant (§4).
2. Differential parity holds on every example and on the fuzzed artifact
   corpus.
3. Experiments E1–E6 met their acceptance criteria
   ([experiments/README.md](../experiments/README.md)).
4. The `sdc:runtime@1.0.0` WIT text is frozen by ADR.
5. Measured performance of the Wasm runtime meets every example's declared
   targets under the benchmark profile.

Until then, the Python runtime remains the production runtime.
After switch-over, the Python runtime stops being a production runtime
(its production mode is removed). Whether it is kept as a verify-mode
differential oracle is unresolved decision U13.

The substrate-specific cases `CAP-DENY-*` are **strictly stronger** on Wasm
(structural denial). On Python they rely on the deployment sandbox, which is
one reason for the switch.
