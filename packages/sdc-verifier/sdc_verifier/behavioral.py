"""Behavioral and API-contract verification.

Runs explicit test cases from the specification plus auto-generated negative
authorization tests, all against the live service. Each case asserts an
observed HTTP status against the specified status.
"""

from __future__ import annotations

from typing import Any

from sdc_ir import ApplicationIR

from .harness import ServiceHarness
from .report import Check, PASS, FAIL


def _seeded_id(ir: ApplicationIR, entity: str) -> str:
    for e in ir.data.entities:
        if e.name == entity:
            return f"{e.name[0].lower()}1"
    return "1"


def auto_negative_cases(ir: ApplicationIR) -> list[dict[str, Any]]:
    """Generate positive/negative authorization cases from the IR.

    same tenant → allowed; different tenant → denied; missing auth → denied;
    admin same tenant → allowed; unknown id → not found.
    """
    cases: list[dict[str, Any]] = []
    tenant_isolation = "cross_tenant_access" in ir.authorization.forbidden
    has_admin = "tenant_admin" in ir.authorization.roles
    success = ir.behavior.status_for("success") or 200
    unauth = ir.behavior.status_for("unauthenticated") or 401
    forbidden = ir.behavior.status_for("unauthorized") or 403
    not_found = ir.behavior.status_for("not_found") or 404

    for ep in ir.api.endpoints:
        if ep.method != "GET" or not ep.path_params:
            continue
        entity = ep.entity or (ir.data.entities[0].name if ir.data.entities else "Entity")
        sid = _seeded_id(ir, entity)
        concrete = ep.path
        for p in ep.path_params[:-1]:
            concrete = concrete.replace("{%s}" % p, sid)
        detail = concrete.replace("{%s}" % ep.path_params[-1], sid)
        missing = concrete.replace("{%s}" % ep.path_params[-1], "does-not-exist")

        if ir.authentication.required:
            cases.append(
                {"name": f"auth-required::{ep.method} {ep.path}", "endpoint": f"GET {detail}",
                 "principal": None, "expect_status": unauth, "category": "authentication"}
            )
        cases.append(
            {"name": f"same-tenant-allowed::{ep.method} {ep.path}", "endpoint": f"GET {detail}",
             "principal": {"role": "user", "tenant_id": "t1"}, "expect_status": success, "category": "authorization"}
        )
        if tenant_isolation:
            cases.append(
                {"name": f"cross-tenant-denied::{ep.method} {ep.path}", "endpoint": f"GET {detail}",
                 "principal": {"role": "user", "tenant_id": "t2"}, "expect_status": forbidden, "category": "tenant-isolation"}
            )
        if has_admin:
            cases.append(
                {"name": f"admin-same-tenant-allowed::{ep.method} {ep.path}", "endpoint": f"GET {detail}",
                 "principal": {"role": "tenant_admin", "tenant_id": "t1"}, "expect_status": success, "category": "authorization"}
            )
        cases.append(
            {"name": f"missing-not-found::{ep.method} {ep.path}", "endpoint": f"GET {missing}",
             "principal": {"role": "user", "tenant_id": "t1"}, "expect_status": not_found, "category": "error-semantics"}
        )
    return cases


def ir_test_cases(ir: ApplicationIR) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in ir.testing.cases:
        out.append(
            {
                "name": c.name,
                "endpoint": c.request.get("endpoint", ""),
                "principal": c.request.get("principal"),
                "expect_status": c.expect_status,
                "category": "api-behavior",
            }
        )
    return out


def _run_case(harness: ServiceHarness, case: dict[str, Any]) -> Check:
    endpoint = case["endpoint"].strip()
    method, _, path = endpoint.partition(" ")
    principal = case.get("principal")
    token = None
    if principal:
        token = harness.token(
            tenant_id=principal.get("tenant_id", "t1"),
            role=principal.get("role", "user"),
            subject=principal.get("subject", "test"),
            **{k: v for k, v in principal.items() if k not in ("tenant_id", "role", "subject")},
        )
    result = harness.request(method or "GET", path, token=token)
    expected = case["expect_status"]
    ok = result.status == expected
    return Check(
        name=case["name"],
        status=PASS if ok else FAIL,
        detail=f"expected {expected}, observed {result.status}",
        category=case.get("category", "api-behavior"),
        observed={"status": result.status, "body": result.body[:400]},
    )


def verify_behavior(harness: ServiceHarness, ir: ApplicationIR) -> list[Check]:
    checks: list[Check] = []
    seen: set[str] = set()
    for case in ir_test_cases(ir) + auto_negative_cases(ir):
        if not case.get("endpoint"):
            continue
        # de-duplicate identical (endpoint, principal, expect) triples
        key = f"{case['endpoint']}|{case.get('principal')}|{case['expect_status']}"
        if key in seen:
            continue
        seen.add(key)
        checks.append(_run_case(harness, case))
    return checks
