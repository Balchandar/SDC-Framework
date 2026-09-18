"""sdc_codegen — turn (IR, plan) into a generated implementation.

Backends are selected by ``plan["backend"]``. Generated code is always marked
as an intermediate artifact; the specification remains the source of truth.
"""

from __future__ import annotations

from typing import Any

from sdc_ir import ApplicationIR
from sdc_ir.errors import GenerationError

from .backends import CodeBackend, PythonHttpBackend

_BACKENDS: dict[str, CodeBackend] = {
    PythonHttpBackend.name: PythonHttpBackend(),
}


def register_backend(backend: CodeBackend) -> None:
    _BACKENDS[backend.name] = backend


def generate_implementation(
    ir: ApplicationIR,
    plan: dict[str, Any],
    out_dir: str = "build/generated",
    metadata: dict[str, Any] | None = None,
) -> list[str]:
    backend_name = plan.get("backend", "python-stdlib-http")
    backend = _BACKENDS.get(backend_name)
    if backend is None:
        raise GenerationError(
            f"No code backend registered for '{backend_name}'",
            why=f"available backends: {sorted(_BACKENDS)}",
            component="codegen",
        )
    return backend.generate(ir, plan, out_dir, metadata=metadata)


__all__ = [
    "generate_implementation",
    "register_backend",
    "CodeBackend",
    "PythonHttpBackend",
]
