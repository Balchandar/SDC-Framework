"""Code backend abstraction.

A backend turns (IR, plan) into generated source in an output directory. The
IR and plan are backend-agnostic, so new backends (other languages/runtimes)
implement this interface without any specification change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from sdc_ir import ApplicationIR


class CodeBackend(ABC):
    name: str = "abstract"

    @abstractmethod
    def generate(
        self,
        ir: ApplicationIR,
        plan: dict[str, Any],
        out_dir: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[str]:
        """Generate implementation files. Returns the list of written paths."""
