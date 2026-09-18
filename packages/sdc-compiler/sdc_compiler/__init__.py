"""sdc_compiler — provider-neutral AI compiler, planning, drift and diff.

Boundaries: the compiler turns an Application IR into a validated
implementation plan and drives the code backend to generate an implementation.
It never verifies its own output — that is ``sdc_verifier``.
"""

from .aicompiler import AICompiler, CompileResult, COMPILER_VERSION
from .plan import ImplementationPlan, Component, validate_plan, KNOWN_BACKENDS
from .providers import (
    AIProvider,
    LocalDeterministicProvider,
    AnthropicProvider,
    OpenAIProvider,
    GoogleProvider,
    get_provider,
    register_provider,
)
from .planner import derive_plan
from .analysis import analyze_drift, changed_sections, DriftReport
from .diff import semantic_diff, SemanticDiff, Change

__all__ = [
    "AICompiler",
    "CompileResult",
    "COMPILER_VERSION",
    "ImplementationPlan",
    "Component",
    "validate_plan",
    "KNOWN_BACKENDS",
    "AIProvider",
    "LocalDeterministicProvider",
    "AnthropicProvider",
    "OpenAIProvider",
    "GoogleProvider",
    "get_provider",
    "register_provider",
    "derive_plan",
    "analyze_drift",
    "changed_sections",
    "DriftReport",
    "semantic_diff",
    "SemanticDiff",
    "Change",
]
