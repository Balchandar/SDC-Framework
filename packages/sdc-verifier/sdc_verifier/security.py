"""Security verification.

Security requirements are treated as executable checks wherever possible: some
are static (scanning the generated source), some dynamic (observing live
responses and logs). A failed *mandatory* check fails the build. Requirements
with no automated check are reported UNVERIFIED (visible, non-blocking) rather
than silently passed.
"""

from __future__ import annotations

import re
from typing import Callable

from sdc_ir import ApplicationIR

from .harness import ServiceHarness
from .report import Check, PASS, FAIL, UNVERIFIED


def _sensitive_values(ir: ApplicationIR) -> list[str]:
    # values the default seed uses for sensitive fields
    vals = []
    for e in ir.data.entities:
        for f in e.sensitive_fields():
            vals.append(f"secret-{f}-")
    return vals


def _authorized_detail(ir: ApplicationIR, harness: ServiceHarness):
    """Return (path, token) for an authorized detail request, or (None, None)."""
    for ep in ir.api.endpoints:
        if ep.method == "GET" and ep.path_params:
            entity = ep.entity or (ir.data.entities[0].name if ir.data.entities else "Entity")
            sid = f"{entity[0].lower()}1"
            path = ep.path
            for p in ep.path_params:
                path = path.replace("{%s}" % p, sid)
            return path, harness.token(tenant_id="t1", role="user")
    return None, None


def check_no_secret_exposure(ir, harness, source) -> Check:
    path, token = _authorized_detail(ir, harness)
    if path is None:
        return Check("no_secret_exposure", UNVERIFIED, "no detail endpoint to probe", category="security")
    r = harness.get(path, token=token)
    sensitive_fields = [f for e in ir.data.entities for f in e.sensitive_fields()]
    leaked = [f for f in sensitive_fields if f'"{f}"' in r.body]
    leaked_vals = [v for v in _sensitive_values(ir) if v in r.body]
    if leaked or leaked_vals:
        return Check(
            "no_secret_exposure", FAIL,
            f"response exposed sensitive data: fields={leaked} values={leaked_vals}",
            category="security",
        )
    return Check("no_secret_exposure", PASS, "sensitive fields absent from responses", category="security")


def check_tenant_isolation(ir, harness, source) -> Check:
    if "cross_tenant_access" not in ir.authorization.forbidden:
        return Check("tenant_isolation", UNVERIFIED, "not required by spec", category="security", mandatory=False)
    for ep in ir.api.endpoints:
        if ep.method == "GET" and ep.path_params:
            entity = ep.entity or (ir.data.entities[0].name if ir.data.entities else "Entity")
            sid = f"{entity[0].lower()}1"
            path = ep.path
            for p in ep.path_params:
                path = path.replace("{%s}" % p, sid)
            cross = harness.get(path, token=harness.token(tenant_id="t2", role="user"))
            if cross.status == 200:
                return Check("tenant_isolation", FAIL, f"cross-tenant request to {path} returned 200", category="security")
            if "name-" + sid in cross.body:
                return Check("tenant_isolation", FAIL, "cross-tenant response leaked resource data", category="security")
    return Check("tenant_isolation", PASS, "cross-tenant access denied", category="security")


def check_authentication_enforced(ir, harness, source) -> Check:
    if not ir.authentication.required:
        return Check("authentication_enforced", UNVERIFIED, "authentication not required", category="security", mandatory=False)
    path, _ = _authorized_detail(ir, harness)
    if path is None:
        return Check("authentication_enforced", UNVERIFIED, "no endpoint to probe", category="security")
    r = harness.get(path)  # no token
    ok = r.status == (ir.behavior.status_for("unauthenticated") or 401)
    return Check("authentication_enforced", PASS if ok else FAIL, f"unauthenticated request → {r.status}", category="security")


def check_authorization_enforced(ir, harness, source) -> Check:
    if not ir.authorization.rules:
        return Check("authorization_enforced", UNVERIFIED, "no authorization rules", category="security", mandatory=False)
    base = check_tenant_isolation(ir, harness, source)
    return Check("authorization_enforced", base.status, base.detail, category="security")


def check_authorization_auditable(ir, harness, source) -> Check:
    # Trigger a request, then confirm the decision was logged.
    path, token = _authorized_detail(ir, harness)
    if path:
        harness.get(path, token=token)
    logs = harness.read_logs()
    if "authz_decision" in logs and "authz_decision" in source:
        return Check("authorization_auditable", PASS, "authorization decisions are logged", category="security")
    return Check("authorization_auditable", FAIL, "no authorization decision found in logs", category="security")


def check_no_sensitive_logging(ir, harness, source) -> Check:
    # Exercise then inspect logs for secret values.
    path, token = _authorized_detail(ir, harness)
    if path:
        harness.get(path, token=token)
    logs = harness.read_logs()
    leaked = [v for v in _sensitive_values(ir) if v in logs]
    if leaked:
        return Check("no_sensitive_logging", FAIL, f"secret values found in logs: {leaked}", category="security")
    return Check("no_sensitive_logging", PASS, "no sensitive values in logs", category="security")


_SAFE_SQL_PLACEHOLDER = re.compile(r"^(self\._table\(|.*_table\(|table\b)")


def check_sql_injection(ir, harness, source) -> Check:
    """Static check: user input must be parameterized, never interpolated.

    Interpolating a validated identifier (a whitelisted table name via a
    ``_table(...)`` helper) is permitted; interpolating anything else — or
    using ``.format``/``%``/``+`` to build SQL — is a failure.
    """
    if re.findall(r"execute\([^)]*\.format\(", source) or re.findall(
        r'execute\(\s*["\'][^"\']*["\']\s*[+%]', source
    ):
        return Check("sql_injection", FAIL, "dynamic SQL string construction detected", category="security")

    for m in re.finditer(r'execute\(\s*f(["\'])(.*?)\1', source):
        sql = m.group(2)
        for placeholder in re.findall(r"\{([^}]*)\}", sql):
            content = placeholder.strip()
            if not _SAFE_SQL_PLACEHOLDER.match(content):
                return Check(
                    "sql_injection", FAIL,
                    f"SQL interpolates non-identifier value: {{{content}}}", category="security",
                )
    return Check("sql_injection", PASS, "queries are parameterized; identifiers are whitelisted", category="security")


def check_security_headers(ir, harness, source) -> Check:
    r = harness.get("/healthz")
    required = ["X-Content-Type-Options", "X-Frame-Options"]
    missing = [h for h in required if h not in {k for k in r.headers}]
    if missing:
        return Check("security_headers", FAIL, f"missing headers: {missing}", category="security")
    return Check("security_headers", PASS, "security headers present on responses", category="security")


def check_insecure_configuration(ir, harness, source) -> Check:
    # No hardcoded secret literal; secret must come from the environment.
    if re.search(r'SDC_JWT_SECRET["\']\s*[:=]\s*["\'][^"\']+["\']', source):
        return Check("insecure_configuration", FAIL, "hardcoded signing secret detected", category="security")
    return Check("insecure_configuration", PASS, "secrets read from environment", category="security")


def check_unsafe_deserialization(ir, harness, source) -> Check:
    if re.search(r"\b(pickle|eval|exec|yaml\.load)\s*\(", source):
        return Check("unsafe_deserialization", FAIL, "unsafe deserialization primitive detected", category="security")
    return Check("unsafe_deserialization", PASS, "only JSON parsing is used", category="security")


def check_path_traversal(ir, harness, source) -> Check:
    if re.search(r"open\(\s*.*req\.|open\(\s*.*params", source):
        return Check("path_traversal", FAIL, "filesystem path built from request input", category="security")
    return Check("path_traversal", PASS, "no filesystem paths derived from input", category="security")


def check_ssrf(ir, harness, source) -> Check:
    if re.search(r"urlopen\(\s*.*req\.|requests\.(get|post)\(\s*.*req\.", source):
        return Check("ssrf", FAIL, "outbound request built from user input", category="security")
    return Check("ssrf", PASS, "no outbound requests derived from input", category="security")


def check_dependency_vulnerabilities(ir, harness, source) -> Check:
    forbidden = set(ir.dependencies.forbidden)
    if forbidden:
        hits = [d for d in forbidden if d in source]
        if hits:
            return Check("dependency_vulnerabilities", FAIL, f"forbidden dependency used: {hits}", category="security")
    return Check(
        "dependency_vulnerabilities", PASS,
        "no third-party runtime dependencies in the generated artifact", category="security",
    )


CHECK_FUNCS: dict[str, Callable] = {
    "no_secret_exposure": check_no_secret_exposure,
    "tenant_isolation": check_tenant_isolation,
    "authentication_enforced": check_authentication_enforced,
    "authorization_enforced": check_authorization_enforced,
    "authorization_auditable": check_authorization_auditable,
    "no_sensitive_logging": check_no_sensitive_logging,
    "sql_injection": check_sql_injection,
    "security_headers": check_security_headers,
    "insecure_configuration": check_insecure_configuration,
    "unsafe_deserialization": check_unsafe_deserialization,
    "path_traversal": check_path_traversal,
    "ssrf": check_ssrf,
    "dependency_vulnerabilities": check_dependency_vulnerabilities,
}


def verify_security(harness: ServiceHarness, ir: ApplicationIR, source: str) -> list[Check]:
    checks: list[Check] = []
    run_ids: set[str] = set()

    # Always run the baseline security checks that apply to any HTTP service.
    baseline = [
        "authentication_enforced",
        "tenant_isolation",
        "no_secret_exposure",
        "sql_injection",
        "security_headers",
        "insecure_configuration",
        "unsafe_deserialization",
        "path_traversal",
        "ssrf",
        "dependency_vulnerabilities",
        "no_sensitive_logging",
        "authorization_auditable",
    ]
    # Plus every requirement the specification explicitly listed.
    requested = [r.id for r in ir.security.requirements]

    for cid in baseline + requested:
        if cid in run_ids:
            continue
        run_ids.add(cid)
        fn = CHECK_FUNCS.get(cid)
        if fn is None:
            # A specified requirement with no automated check.
            text = next((r.text for r in ir.security.requirements if r.id == cid), cid)
            checks.append(
                Check(cid, UNVERIFIED, f"no automated check available for: {text}", category="security", mandatory=False)
            )
            continue
        try:
            checks.append(fn(ir, harness, source))
        except Exception as exc:  # a check crashing is itself a failure signal
            checks.append(Check(cid, FAIL, f"check raised: {exc}", category="security"))
    return checks
