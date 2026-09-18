"""Semantic diff between two specification versions.

Unlike a Markdown line diff, this compares the *meaning* captured in the IR:
authorization rules added/removed, endpoints changed, behavior status changes,
security requirements, performance targets. It also classifies the impact and
lists the verification that the change requires.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sdc_ir import canonical_json
from .analysis import changed_sections


@dataclass
class Change:
    category: str
    kind: str  # "added" | "removed" | "changed"
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {"category": self.category, "kind": self.kind, "description": self.description}


@dataclass
class SemanticDiff:
    changes: list[Change] = field(default_factory=list)
    security_impact: list[str] = field(default_factory=list)
    performance_impact: list[str] = field(default_factory=list)
    data_impact: list[str] = field(default_factory=list)
    compatibility_impact: list[str] = field(default_factory=list)
    affected_apis: list[str] = field(default_factory=list)
    required_verification: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.changes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "changes": [c.to_dict() for c in self.changes],
            "security_impact": list(self.security_impact),
            "performance_impact": list(self.performance_impact),
            "data_impact": list(self.data_impact),
            "compatibility_impact": list(self.compatibility_impact),
            "affected_apis": list(self.affected_apis),
            "required_verification": list(self.required_verification),
        }


def _authz_rule_lines(ir: dict[str, Any]) -> list[str]:
    out = []
    for r in ir.get("authorization", {}).get("rules", []):
        out.append(f"{r['subject']} → {r['predicate']}")
    return sorted(out)


def semantic_diff(old_ir: dict[str, Any], new_ir: dict[str, Any]) -> SemanticDiff:
    diff = SemanticDiff()
    changed = set(changed_sections(old_ir, new_ir))

    # Authorization
    if "authorization" in changed:
        old_rules = set(_authz_rule_lines(old_ir))
        new_rules = set(_authz_rule_lines(new_ir))
        for added in sorted(new_rules - old_rules):
            diff.changes.append(Change("authorization", "added", f"rule: {added}"))
        for removed in sorted(old_rules - new_rules):
            diff.changes.append(Change("authorization", "removed", f"rule: {removed}"))
        old_roles = set(old_ir.get("authorization", {}).get("roles", []))
        new_roles = set(new_ir.get("authorization", {}).get("roles", []))
        for role in sorted(new_roles - old_roles):
            diff.changes.append(Change("authorization", "added", f"role: {role}"))
        for role in sorted(old_roles - new_roles):
            diff.changes.append(Change("authorization", "removed", f"role: {role}"))
        diff.security_impact.append("authorization surface changed; re-verify access control")
        diff.compatibility_impact.append("clients relying on prior access scope may be affected")

    # API endpoints
    if "api" in changed:
        old_eps = {f"{e['method']} {e['path']}" for e in old_ir.get("api", {}).get("endpoints", [])}
        new_eps = {f"{e['method']} {e['path']}" for e in new_ir.get("api", {}).get("endpoints", [])}
        for e in sorted(new_eps - old_eps):
            diff.changes.append(Change("api", "added", f"endpoint {e}"))
        for e in sorted(old_eps - new_eps):
            diff.changes.append(Change("api", "removed", f"endpoint {e}"))
            diff.compatibility_impact.append(f"removed endpoint {e} is a breaking change")

    # Behavior
    if "behavior" in changed:
        old_b = {r["condition"]: r["status"] for r in old_ir.get("behavior", {}).get("rules", [])}
        new_b = {r["condition"]: r["status"] for r in new_ir.get("behavior", {}).get("rules", [])}
        for cond in sorted(set(old_b) | set(new_b)):
            if old_b.get(cond) != new_b.get(cond):
                diff.changes.append(
                    Change("behavior", "changed", f"{cond}: {old_b.get(cond)} → {new_b.get(cond)}")
                )

    # Security
    if "security" in changed:
        old_s = {r["id"] for r in old_ir.get("security", {}).get("requirements", [])}
        new_s = {r["id"] for r in new_ir.get("security", {}).get("requirements", [])}
        for s in sorted(new_s - old_s):
            diff.changes.append(Change("security", "added", f"requirement {s}"))
            diff.security_impact.append(f"new mandatory security requirement: {s}")
        for s in sorted(old_s - new_s):
            diff.changes.append(Change("security", "removed", f"requirement {s}"))
            diff.security_impact.append(f"removed security requirement: {s}")

    # Data
    if "data" in changed:
        old_ent = {e["name"] for e in old_ir.get("data", {}).get("entities", [])}
        new_ent = {e["name"] for e in new_ir.get("data", {}).get("entities", [])}
        for e in sorted(new_ent - old_ent):
            diff.changes.append(Change("data", "added", f"entity {e}"))
        for e in sorted(old_ent - new_ent):
            diff.changes.append(Change("data", "removed", f"entity {e}"))
        # field-level
        old_fields = _entity_fields(old_ir)
        new_fields = _entity_fields(new_ir)
        for ent in sorted(set(old_fields) & set(new_fields)):
            added = set(new_fields[ent]) - set(old_fields[ent])
            removed = set(old_fields[ent]) - set(new_fields[ent])
            for f in sorted(added):
                diff.changes.append(Change("data", "added", f"{ent}.{f}"))
            for f in sorted(removed):
                diff.changes.append(Change("data", "removed", f"{ent}.{f}"))
        if old_ent != new_ent or old_fields != new_fields:
            diff.data_impact.append("data model changed; storage/migration review required")

    # Performance
    if "performance" in changed:
        o = old_ir.get("performance", {})
        n = new_ir.get("performance", {})
        for key in ("p99_latency_ms", "min_rps"):
            if o.get(key) != n.get(key):
                diff.changes.append(
                    Change("performance", "changed", f"{key}: {o.get(key)} → {n.get(key)}")
                )
                diff.performance_impact.append(f"performance target {key} changed")

    # Affected APIs (cross-cutting sections touch all endpoints)
    if changed & {"authorization", "behavior", "authentication", "data"}:
        diff.affected_apis = [
            f"{e['method']} {e['path']}" for e in new_ir.get("api", {}).get("endpoints", [])
        ]

    # Required verification
    from .analysis import _SECTION_TO_VERIFICATION

    for sec in sorted(changed):
        for v in _SECTION_TO_VERIFICATION.get(sec, []):
            if v not in diff.required_verification:
                diff.required_verification.append(v)

    return diff


def _entity_fields(ir: dict[str, Any]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for e in ir.get("data", {}).get("entities", []):
        out[e["name"]] = [f["name"] for f in e.get("fields", [])]
    return out
