"""Verification report data types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


PASS = "PASS"
FAIL = "FAIL"
UNVERIFIED = "UNVERIFIED"
WARN = "WARN"


@dataclass
class Check:
    name: str
    status: str
    detail: str = ""
    category: str = "behavior"
    mandatory: bool = True
    observed: Optional[dict] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "category": self.category,
            "mandatory": self.mandatory,
            "observed": self.observed,
        }


@dataclass
class VerificationReport:
    specification_hash: str = ""
    ir_hash: str = ""
    checks: list[Check] = field(default_factory=list)

    def add(self, check: Check):
        self.checks.append(check)

    @property
    def status(self) -> str:
        """Overall status: FAIL if any mandatory check failed, else PASS."""
        for c in self.checks:
            if c.mandatory and c.status == FAIL:
                return FAIL
        return PASS

    def by_category(self) -> dict[str, list[Check]]:
        out: dict[str, list[Check]] = {}
        for c in self.checks:
            out.setdefault(c.category, []).append(c)
        return out

    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.mandatory and c.status == FAIL]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "specification_hash": self.specification_hash,
            "ir_hash": self.ir_hash,
            "checks": [c.to_dict() for c in self.checks],
        }
