"""Verification engine.

Orchestrates behavioral, security, and performance verification against the
live generated service and assembles the verification report. This is a
separate authority from the compiler: it only observes the artifact.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from sdc_ir import ApplicationIR

from .harness import ServiceHarness
from .report import VerificationReport, Check, PASS, FAIL, UNVERIFIED
from . import behavioral, security, performance


def build_seed(ir: ApplicationIR) -> dict:
    """Deterministic verification fixtures, independent of codegen defaults."""
    seed: dict[str, list[dict]] = {}
    for ent in ir.data.entities:
        prefix = ent.name[0].lower()
        rows = []
        for n, tenant in ((1, "t1"), (2, "t1"), (3, "t2")):
            rid = f"{prefix}{n}"
            row = {}
            for f in ent.fields:
                if f.name == "id":
                    row["id"] = rid
                elif f.name == ent.tenant_field:
                    row[f.name] = tenant
                elif f.sensitive:
                    row[f.name] = f"secret-{f.name}-{rid}"
                else:
                    row[f.name] = f"{f.name}-{rid}"
            row.setdefault("id", rid)
            if ent.tenant_field:
                row.setdefault(ent.tenant_field, tenant)
            rows.append(row)
        seed[ent.name] = rows
    return seed


@dataclass
class VerifyResult:
    report: VerificationReport
    logs: str = ""


def verify(
    ir: ApplicationIR,
    service_path: str,
    specification_hash: str = "",
    ir_hash: str = "",
    run_performance: bool = True,
) -> VerifyResult:
    report = VerificationReport(specification_hash=specification_hash, ir_hash=ir_hash)

    with open(service_path, "r", encoding="utf-8") as fh:
        source = fh.read()

    seed = build_seed(ir)
    harness = ServiceHarness(service_path, seed=seed)
    try:
        harness.start()
    except Exception as exc:
        report.add(Check("service-start", FAIL, f"generated service failed to start: {exc}", category="runtime"))
        return VerifyResult(report=report)

    try:
        # IR <-> implementation consistency: does the service expose the routes
        # the IR declares? (contract check)
        for ep in ir.api.endpoints:
            if ep.path_params:
                continue  # detail routes are exercised behaviorally
            r = harness.get(ep.path, token=harness.token(tenant_id="t1", role="user"))
            report.add(
                Check(
                    f"contract::{ep.method} {ep.path}",
                    PASS if r.status < 500 and r.status != 404 else FAIL,
                    f"route responds ({r.status})",
                    category="api-contract",
                )
            )

        for c in behavioral.verify_behavior(harness, ir):
            report.add(c)
        for c in security.verify_security(harness, ir, source):
            report.add(c)
        if run_performance:
            for c in performance.verify_performance(harness, ir):
                report.add(c)

        logs = harness.read_logs()
    finally:
        harness.stop()

    return VerifyResult(report=report, logs=logs)
