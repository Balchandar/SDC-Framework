"""Specification drift and dependency analysis.

When a specification changes, SDC should not blindly rebuild everything. This
module computes which IR sections changed and maps them to the implementation
components that must be regenerated and re-verified.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sdc_ir import canonical_json
from .plan import ImplementationPlan


def changed_sections(old_ir: dict[str, Any], new_ir: dict[str, Any]) -> list[str]:
    """Return the top-level IR sections whose canonical form differs."""
    changed: list[str] = []
    keys = set(old_ir) | set(new_ir)
    keys.discard("schema_version")
    for key in sorted(keys):
        if canonical_json(old_ir.get(key)) != canonical_json(new_ir.get(key)):
            changed.append(key)
    return changed


@dataclass
class DriftReport:
    changed_sections: list[str]
    affected_components: list[str]
    unaffected_components: list[str]
    affected_endpoints: list[str] = field(default_factory=list)
    affected_verification: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "changed_sections": list(self.changed_sections),
            "affected_components": list(self.affected_components),
            "unaffected_components": list(self.unaffected_components),
            "affected_endpoints": list(self.affected_endpoints),
            "affected_verification": list(self.affected_verification),
        }


# Which verification suites care about which IR sections.
_SECTION_TO_VERIFICATION = {
    "authentication": ["authentication"],
    "authorization": ["authorization", "tenant-isolation", "negative-tests"],
    "api": ["api-behavior"],
    "behavior": ["error-semantics", "api-behavior"],
    "security": ["security"],
    "data": ["tenant-isolation", "api-behavior"],
    "performance": ["performance"],
}


def analyze_drift(
    old_ir: dict[str, Any], new_ir: dict[str, Any], plan: ImplementationPlan
) -> DriftReport:
    changed = changed_sections(old_ir, new_ir)
    changed_set = set(changed)

    affected: list[str] = []
    unaffected: list[str] = []
    for comp in plan.components:
        if changed_set & set(comp.derived_from):
            affected.append(comp.name)
        else:
            unaffected.append(comp.name)

    # Endpoints affected: if api/authorization/data/behavior changed, endpoints
    # touching the relevant entities are affected. Conservatively, mark all
    # endpoints when authorization or behavior changed (cross-cutting).
    affected_endpoints: list[str] = []
    if changed_set & {"api", "authorization", "behavior", "data"}:
        for ep in new_ir.get("api", {}).get("endpoints", []):
            affected_endpoints.append(f"{ep['method']} {ep['path']}")

    verification: list[str] = []
    for sec in changed:
        for v in _SECTION_TO_VERIFICATION.get(sec, []):
            if v not in verification:
                verification.append(v)

    return DriftReport(
        changed_sections=changed,
        affected_components=affected,
        unaffected_components=unaffected,
        affected_endpoints=affected_endpoints,
        affected_verification=verification,
    )
