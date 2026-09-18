"""SDC error taxonomy.

Every failure in the toolchain is one of a fixed set of categories. Errors
never hide the cause: each carries what failed, why, which specification is
responsible, which component is affected, and whether regeneration can help.

This module lives in ``sdc_ir`` because the IR package is the common
dependency of every other package, but the taxonomy describes pipeline
stages, not the IR itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


class ErrorKind:
    SPECIFICATION_ERROR = "SPECIFICATION_ERROR"
    SEMANTIC_ERROR = "SEMANTIC_ERROR"
    COMPILER_ERROR = "COMPILER_ERROR"
    GENERATION_ERROR = "GENERATION_ERROR"
    VERIFICATION_ERROR = "VERIFICATION_ERROR"
    SECURITY_ERROR = "SECURITY_ERROR"
    PERFORMANCE_ERROR = "PERFORMANCE_ERROR"
    BUILD_ERROR = "BUILD_ERROR"
    RUNTIME_ERROR = "RUNTIME_ERROR"


@dataclass
class SDCError(Exception):
    kind: str
    what: str
    why: str = ""
    specification: Optional[str] = None  # which spec file/section caused it
    component: Optional[str] = None  # which component is affected
    regenerable: bool = True
    details: list[str] = field(default_factory=list)

    def __str__(self) -> str:  # pragma: no cover - formatting only
        parts = [f"[{self.kind}] {self.what}"]
        if self.why:
            parts.append(f"why: {self.why}")
        if self.specification:
            parts.append(f"specification: {self.specification}")
        if self.component:
            parts.append(f"component: {self.component}")
        parts.append(f"regenerable: {self.regenerable}")
        return "\n".join(parts)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "what": self.what,
            "why": self.why,
            "specification": self.specification,
            "component": self.component,
            "regenerable": self.regenerable,
            "details": list(self.details),
        }


class SpecificationError(SDCError):
    def __init__(self, what: str, **kw):
        super().__init__(kind=ErrorKind.SPECIFICATION_ERROR, what=what, **kw)


class SemanticError(SDCError):
    def __init__(self, what: str, **kw):
        super().__init__(kind=ErrorKind.SEMANTIC_ERROR, what=what, **kw)


class CompilerError(SDCError):
    def __init__(self, what: str, **kw):
        super().__init__(kind=ErrorKind.COMPILER_ERROR, what=what, **kw)


class GenerationError(SDCError):
    def __init__(self, what: str, **kw):
        super().__init__(kind=ErrorKind.GENERATION_ERROR, what=what, **kw)


class VerificationError(SDCError):
    def __init__(self, what: str, **kw):
        super().__init__(kind=ErrorKind.VERIFICATION_ERROR, what=what, **kw)


class SecurityError(SDCError):
    def __init__(self, what: str, **kw):
        super().__init__(kind=ErrorKind.SECURITY_ERROR, what=what, **kw)


class PerformanceError(SDCError):
    def __init__(self, what: str, **kw):
        super().__init__(kind=ErrorKind.PERFORMANCE_ERROR, what=what, **kw)


class BuildError(SDCError):
    def __init__(self, what: str, **kw):
        super().__init__(kind=ErrorKind.BUILD_ERROR, what=what, **kw)
