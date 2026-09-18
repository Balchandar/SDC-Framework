"""Typed Application IR model.

Every node is a frozen-ish dataclass with a ``to_dict`` that emits a
deterministic, JSON-serializable structure. Ordering of collections is
significant and is normalized by the parser before construction so that the
canonical form is stable.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


# --------------------------------------------------------------------------- #
# Application
# --------------------------------------------------------------------------- #
@dataclass
class ApplicationMeta:
    name: str = "UnnamedApplication"
    version: str = "0.0"
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "version": self.version, "description": self.description}


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@dataclass
class Endpoint:
    method: str
    path: str
    summary: str = ""
    # Path/query parameters extracted from the path template, e.g. {"id"}.
    path_params: list[str] = field(default_factory=list)
    # The primary entity this endpoint returns/operates on, if resolvable.
    entity: Optional[str] = None
    authenticated: bool = True

    def key(self) -> str:
        return f"{self.method} {self.path}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "path": self.path,
            "summary": self.summary,
            "path_params": list(self.path_params),
            "entity": self.entity,
            "authenticated": self.authenticated,
        }


@dataclass
class Api:
    endpoints: list[Endpoint] = field(default_factory=list)
    base_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_path": self.base_path,
            "endpoints": [e.to_dict() for e in self.endpoints],
        }


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #
@dataclass
class Authentication:
    # e.g. "none", "oauth2_bearer_jwt", "api_key"
    scheme: str = "none"
    required: bool = False
    # token format the runtime should validate, e.g. "jwt_hs256"
    token_format: str = "jwt_hs256"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scheme": self.scheme,
            "required": self.required,
            "token_format": self.token_format,
            "notes": list(self.notes),
        }


# --------------------------------------------------------------------------- #
# Authorization
# --------------------------------------------------------------------------- #
@dataclass
class AuthorizationRule:
    """A structured, compilable authorization rule.

    ``effect`` is "allow" or "deny". ``subject`` describes the principal role
    the rule applies to. ``predicate`` is a small structured expression the
    compiler turns into an executable policy and the verifier turns into
    positive/negative tests.
    """

    effect: str  # "allow" | "deny"
    subject: str  # e.g. "user", "tenant_admin", "any"
    predicate: dict[str, Any]  # structured expression, see policy language
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "effect": self.effect,
            "subject": self.subject,
            "predicate": self.predicate,
            "description": self.description,
        }


@dataclass
class Authorization:
    model: str = "none"  # "none" | "rbac_tenant" | "custom"
    rules: list[AuthorizationRule] = field(default_factory=list)
    # Named roles referenced by rules.
    roles: list[str] = field(default_factory=list)
    # Explicit forbidden invariants, e.g. "cross_tenant_access".
    forbidden: list[str] = field(default_factory=list)
    auditable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "roles": list(self.roles),
            "rules": [r.to_dict() for r in self.rules],
            "forbidden": list(self.forbidden),
            "auditable": self.auditable,
        }


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
@dataclass
class Field:
    name: str
    type: str = "string"
    nullable: bool = False
    sensitive: bool = False  # must never be exposed / logged
    primary_key: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "nullable": self.nullable,
            "sensitive": self.sensitive,
            "primary_key": self.primary_key,
        }


@dataclass
class Entity:
    name: str
    fields: list[Field] = field(default_factory=list)
    # field name used for tenant scoping, if any
    tenant_field: Optional[str] = None

    def field_names(self) -> list[str]:
        return [f.name for f in self.fields]

    def sensitive_fields(self) -> list[str]:
        return [f.name for f in self.fields if f.sensitive]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "tenant_field": self.tenant_field,
            "fields": [f.to_dict() for f in self.fields],
        }


@dataclass
class Data:
    store: str = "memory"  # "memory" | "postgres"
    entities: list[Entity] = field(default_factory=list)
    transactions: bool = False

    def entity(self, name: str) -> Optional[Entity]:
        for e in self.entities:
            if e.name.lower() == name.lower():
                return e
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "store": self.store,
            "transactions": self.transactions,
            "entities": [e.to_dict() for e in self.entities],
        }


# --------------------------------------------------------------------------- #
# Behavior
# --------------------------------------------------------------------------- #
@dataclass
class BehaviorRule:
    """A condition → outcome mapping.

    ``condition`` is a normalized key such as "unauthenticated",
    "unauthorized", "not_found", "success". ``status`` is the HTTP status the
    outcome maps to.
    """

    condition: str
    status: int
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"condition": self.condition, "status": self.status, "description": self.description}


@dataclass
class Behavior:
    rules: list[BehaviorRule] = field(default_factory=list)

    def status_for(self, condition: str) -> Optional[int]:
        for r in self.rules:
            if r.condition == condition:
                return r.status
        return None

    def to_dict(self) -> dict[str, Any]:
        return {"rules": [r.to_dict() for r in self.rules]}


# --------------------------------------------------------------------------- #
# Security
# --------------------------------------------------------------------------- #
@dataclass
class SecurityRequirement:
    """A security requirement mapped to a machine check id where possible."""

    id: str  # normalized check id, e.g. "no_secret_exposure"
    text: str  # human requirement text
    mandatory: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "text": self.text, "mandatory": self.mandatory}


@dataclass
class Security:
    requirements: list[SecurityRequirement] = field(default_factory=list)

    def check_ids(self) -> list[str]:
        return [r.id for r in self.requirements]

    def to_dict(self) -> dict[str, Any]:
        return {"requirements": [r.to_dict() for r in self.requirements]}


# --------------------------------------------------------------------------- #
# Performance / Reliability / Observability / Deployment
# --------------------------------------------------------------------------- #
@dataclass
class Performance:
    p99_latency_ms: Optional[int] = None
    min_rps: Optional[int] = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"p99_latency_ms": self.p99_latency_ms, "min_rps": self.min_rps, "notes": list(self.notes)}


@dataclass
class Reliability:
    graceful_db_failure: bool = False
    no_partial_commit: bool = False
    retry_transient: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "graceful_db_failure": self.graceful_db_failure,
            "no_partial_commit": self.no_partial_commit,
            "retry_transient": self.retry_transient,
            "notes": list(self.notes),
        }


@dataclass
class Observability:
    fields: list[str] = field(default_factory=list)  # fields to record per request
    telemetry: str = "structured_logs"  # "structured_logs" | "opentelemetry"
    metrics: bool = True
    health: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "telemetry": self.telemetry,
            "metrics": self.metrics,
            "health": self.health,
            "fields": list(self.fields),
        }


@dataclass
class Deployment:
    target: str = "linux-x86_64"
    container: bool = True
    healthcheck: bool = True
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "container": self.container,
            "healthcheck": self.healthcheck,
            "notes": list(self.notes),
        }


# --------------------------------------------------------------------------- #
# Testing / Dependencies
# --------------------------------------------------------------------------- #
@dataclass
class TestCase:
    name: str
    request: dict[str, Any]  # {"endpoint": "...", "principal": {...} | None}
    expect_status: int
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "request": self.request,
            "expect_status": self.expect_status,
            "description": self.description,
        }


@dataclass
class Testing:
    cases: list[TestCase] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"cases": [c.to_dict() for c in self.cases]}


@dataclass
class Dependencies:
    allowed: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"allowed": list(self.allowed), "forbidden": list(self.forbidden)}


# --------------------------------------------------------------------------- #
# Root
# --------------------------------------------------------------------------- #
@dataclass
class ApplicationIR:
    application: ApplicationMeta = field(default_factory=ApplicationMeta)
    api: Api = field(default_factory=Api)
    authentication: Authentication = field(default_factory=Authentication)
    authorization: Authorization = field(default_factory=Authorization)
    data: Data = field(default_factory=Data)
    behavior: Behavior = field(default_factory=Behavior)
    security: Security = field(default_factory=Security)
    performance: Performance = field(default_factory=Performance)
    reliability: Reliability = field(default_factory=Reliability)
    observability: Observability = field(default_factory=Observability)
    deployment: Deployment = field(default_factory=Deployment)
    testing: Testing = field(default_factory=Testing)
    dependencies: Dependencies = field(default_factory=Dependencies)
    # provenance
    schema_version: str = "0.1"

    def to_dict(self) -> dict[str, Any]:
        """Deterministic, ordered dictionary form of the whole IR."""
        return {
            "schema_version": self.schema_version,
            "application": self.application.to_dict(),
            "api": self.api.to_dict(),
            "authentication": self.authentication.to_dict(),
            "authorization": self.authorization.to_dict(),
            "data": self.data.to_dict(),
            "behavior": self.behavior.to_dict(),
            "security": self.security.to_dict(),
            "performance": self.performance.to_dict(),
            "reliability": self.reliability.to_dict(),
            "observability": self.observability.to_dict(),
            "deployment": self.deployment.to_dict(),
            "testing": self.testing.to_dict(),
            "dependencies": self.dependencies.to_dict(),
        }

    # The set of top-level sections, used by drift/diff analysis.
    SECTIONS = (
        "application",
        "api",
        "authentication",
        "authorization",
        "data",
        "behavior",
        "security",
        "performance",
        "reliability",
        "observability",
        "deployment",
        "testing",
        "dependencies",
    )
