"""Schema and semantic validation of the Application IR.

Validation returns a list of structured errors rather than raising on the
first problem, so ``sdc validate`` can report everything at once. The CLI
treats a non-empty fatal list as a failed build.
"""

from __future__ import annotations

from sdc_ir import ApplicationIR
from sdc_ir.errors import SDCError, SpecificationError, SemanticError


def validate_ir(ir: ApplicationIR) -> list[SDCError]:
    errors: list[SDCError] = []

    # Application meta
    if not ir.application.name or ir.application.name == "UnnamedApplication":
        errors.append(
            SpecificationError(
                "Application name is missing",
                why="the Application section must declare a Name",
                specification="application",
                component="application",
                regenerable=False,
            )
        )

    # API
    if ir.api.endpoints:
        seen = set()
        for ep in ir.api.endpoints:
            if ep.key() in seen:
                errors.append(
                    SemanticError(
                        f"Duplicate endpoint {ep.key()}",
                        specification="api",
                        component="api",
                    )
                )
            seen.add(ep.key())
            for p in ep.path_params:
                if not p.isidentifier():
                    errors.append(
                        SemanticError(
                            f"Invalid path parameter '{p}' in {ep.key()}",
                            specification="api",
                            component="api",
                        )
                    )

    # Authentication vs behavior consistency
    if ir.authentication.required and ir.api.endpoints:
        if ir.behavior.status_for("unauthenticated") is None:
            errors.append(
                SemanticError(
                    "Authentication is required but Behavior does not define the "
                    "unauthenticated outcome",
                    why="add a rule mapping unauthenticated requests to 401",
                    specification="behavior",
                    component="behavior",
                )
            )

    # Authorization references
    if ir.authorization.rules:
        allowed_subjects = set(ir.authorization.roles) | {"any"}
        for r in ir.authorization.rules:
            if r.effect not in ("allow", "deny"):
                errors.append(
                    SemanticError(
                        f"Authorization rule has invalid effect '{r.effect}'",
                        specification="authorization",
                        component="authorization",
                    )
                )
            if r.subject not in allowed_subjects:
                errors.append(
                    SemanticError(
                        f"Authorization rule references unknown role '{r.subject}'",
                        why=f"declared roles are: {sorted(allowed_subjects)}",
                        specification="authorization",
                        component="authorization",
                    )
                )

    # Data entities
    for ent in ir.data.entities:
        if not ent.fields:
            errors.append(
                SpecificationError(
                    f"Entity '{ent.name}' has no fields",
                    specification="data",
                    component="data",
                )
            )
        if ir.authorization.forbidden and "cross_tenant_access" in ir.authorization.forbidden:
            if ent.tenant_field is None:
                errors.append(
                    SemanticError(
                        f"Cross-tenant access is forbidden but entity '{ent.name}' "
                        "has no tenant field",
                        why="add a tenant_id field to enable tenant isolation",
                        specification="data",
                        component="data",
                    )
                )

    # Performance sanity
    if ir.performance.p99_latency_ms is not None and ir.performance.p99_latency_ms <= 0:
        errors.append(
            SpecificationError(
                "Performance p99 latency must be positive",
                specification="performance",
                component="performance",
            )
        )

    return errors
