"""The structured implementation plan.

The AI compiler must first produce a *plan*, never free-form code that becomes
an artifact directly. The plan is validated before any code is generated. This
is the contract between the (partially trusted) compiler layer and the code
generator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sdc_ir.errors import CompilerError


@dataclass
class Component:
    name: str
    responsibility: str = ""
    # IR sections this component is derived from (used by drift analysis).
    derived_from: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "responsibility": self.responsibility,
            "derived_from": list(self.derived_from),
        }


@dataclass
class ImplementationPlan:
    target: str
    language: str
    framework: str
    components: list[Component] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    optimization_strategy: dict[str, Any] = field(default_factory=dict)
    # Which code backend should realize this plan.
    backend: str = "python-stdlib-http"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "language": self.language,
            "framework": self.framework,
            "backend": self.backend,
            "components": [c.to_dict() for c in self.components],
            "dependencies": list(self.dependencies),
            "optimization_strategy": dict(self.optimization_strategy),
            "notes": list(self.notes),
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "ImplementationPlan":
        return ImplementationPlan(
            target=d["target"],
            language=d["language"],
            framework=d["framework"],
            backend=d.get("backend", "python-stdlib-http"),
            components=[
                Component(
                    name=c["name"],
                    responsibility=c.get("responsibility", ""),
                    derived_from=list(c.get("derived_from", [])),
                )
                for c in d.get("components", [])
            ],
            dependencies=list(d.get("dependencies", [])),
            optimization_strategy=dict(d.get("optimization_strategy", {})),
            notes=list(d.get("notes", [])),
        )


# The known code backends this compiler build supports.
KNOWN_BACKENDS = {"python-stdlib-http"}
REQUIRED_COMPONENTS = {"http-server", "error-handling", "observability"}


def validate_plan(plan: ImplementationPlan) -> list[CompilerError]:
    """Validate a plan before code generation. Returns structured errors."""
    errors: list[CompilerError] = []
    if not plan.target:
        errors.append(CompilerError("Plan has no target", component="planner"))
    if not plan.language:
        errors.append(CompilerError("Plan has no language", component="planner"))
    if plan.backend not in KNOWN_BACKENDS:
        errors.append(
            CompilerError(
                f"Unknown code backend '{plan.backend}'",
                why=f"supported backends: {sorted(KNOWN_BACKENDS)}",
                component="planner",
            )
        )
    names = {c.name for c in plan.components}
    missing = REQUIRED_COMPONENTS - names
    if missing:
        errors.append(
            CompilerError(
                f"Plan is missing required components: {sorted(missing)}",
                why="every HTTP service plan must include these components",
                component="planner",
            )
        )
    return errors
