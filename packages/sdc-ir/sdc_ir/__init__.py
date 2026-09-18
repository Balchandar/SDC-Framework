"""sdc_ir — the strongly typed Application Intermediate Representation.

The IR is the semantic center of SDC. Markdown specifications are normalized
into these types; the compiler and verifier operate on the IR, never on raw
Markdown. The IR is deterministic: identical specifications produce an
identical canonical form and therefore an identical ``ir_hash``.
"""

from .model import (
    ApplicationIR,
    ApplicationMeta,
    Api,
    Endpoint,
    Authentication,
    Authorization,
    AuthorizationRule,
    Data,
    Entity,
    Field,
    Behavior,
    BehaviorRule,
    Security,
    SecurityRequirement,
    Performance,
    Reliability,
    Observability,
    Deployment,
    Testing,
    TestCase,
    Dependencies,
)
from .hashing import (
    canonical_json,
    ir_hash,
    specification_hash,
    build_id,
    artifact_hash,
)

__all__ = [
    "ApplicationIR",
    "ApplicationMeta",
    "Api",
    "Endpoint",
    "Authentication",
    "Authorization",
    "AuthorizationRule",
    "Data",
    "Entity",
    "Field",
    "Behavior",
    "BehaviorRule",
    "Security",
    "SecurityRequirement",
    "Performance",
    "Reliability",
    "Observability",
    "Deployment",
    "Testing",
    "TestCase",
    "Dependencies",
    "canonical_json",
    "ir_hash",
    "specification_hash",
    "build_id",
    "artifact_hash",
]

IR_SCHEMA_VERSION = "0.1"
