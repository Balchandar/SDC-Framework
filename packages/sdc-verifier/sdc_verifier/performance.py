"""Performance verification.

The MVP runs an *indicative* local latency benchmark: many sequential
authorized requests against the live service, from which p99 latency is
computed and compared to the specified target. This is explicitly a local
micro-benchmark, not a distributed load test. Throughput targets (e.g. RPS)
are recorded but reported UNVERIFIED because a representative load test is out
of scope for the MVP — SDC never claims a target it did not measure.
"""

from __future__ import annotations

import time

from sdc_ir import ApplicationIR

from .harness import ServiceHarness
from .report import Check, PASS, FAIL, UNVERIFIED


def verify_performance(harness: ServiceHarness, ir: ApplicationIR, iterations: int = 300) -> list[Check]:
    checks: list[Check] = []
    # find an authorized detail path
    path = None
    token = harness.token(tenant_id="t1", role="user")
    for ep in ir.api.endpoints:
        if ep.method == "GET" and ep.path_params:
            entity = ep.entity or (ir.data.entities[0].name if ir.data.entities else "Entity")
            sid = f"{entity[0].lower()}1"
            path = ep.path
            for p in ep.path_params:
                path = path.replace("{%s}" % p, sid)
            break
    if path is None:
        path = "/healthz"
        token = None

    latencies = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        harness.get(path, token=token)
        latencies.append((time.perf_counter() - t0) * 1000.0)
    latencies.sort()
    p99 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.99))]
    p50 = latencies[len(latencies) // 2]

    target = ir.performance.p99_latency_ms
    if target is not None:
        ok = p99 <= target
        checks.append(
            Check(
                "p99_latency",
                PASS if ok else FAIL,
                f"p99={p99:.2f}ms (target <{target}ms), p50={p50:.2f}ms, n={iterations}",
                category="performance",
                observed={"p99_ms": round(p99, 3), "p50_ms": round(p50, 3), "target_ms": target},
            )
        )
    else:
        checks.append(
            Check("p99_latency", UNVERIFIED, f"no target specified; observed p99={p99:.2f}ms",
                  category="performance", mandatory=False)
        )

    if ir.performance.min_rps is not None:
        checks.append(
            Check(
                "throughput",
                UNVERIFIED,
                f"target {ir.performance.min_rps} rps not load-tested in MVP (local micro-benchmark only)",
                category="performance",
                mandatory=False,
                observed={"target_rps": ir.performance.min_rps},
            )
        )
    return checks
