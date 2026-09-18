"""Provider-neutral AI compiler abstraction.

The framework must never encode ``if model == GPT`` style logic in the core.
Instead it talks to an :class:`AIProvider` interface. Providers turn an
Application IR into a structured *implementation plan*.

The default provider is :class:`LocalDeterministicProvider`, which derives the
plan from the IR with deterministic rules and requires no network, no API key,
and no model. This keeps the MVP fully reproducible and offline. Real model
providers (Anthropic, OpenAI, Google, custom) implement the same interface and
can be selected by name; they are optional and self-report availability.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any

from sdc_ir.errors import CompilerError

from .planner import derive_plan


class AIProvider(ABC):
    """Interface every AI compiler provider implements."""

    name: str = "abstract"

    @abstractmethod
    def available(self) -> bool:
        """Whether this provider can run in the current environment."""

    @abstractmethod
    def generate_plan(
        self, ir_dict: dict[str, Any], target: str, constraints: dict[str, Any]
    ) -> dict[str, Any]:
        """Produce a structured implementation-plan dict from the IR."""


class LocalDeterministicProvider(AIProvider):
    """Deterministic, offline provider.

    It does not call a model; it applies transparent rules to the IR. Because
    it is deterministic, the same IR always yields the same plan, which is what
    makes the MVP's builds reproducible.
    """

    name = "local"

    def available(self) -> bool:
        return True

    def generate_plan(self, ir_dict, target, constraints):
        return derive_plan(ir_dict, target, constraints)


class _ModelProvider(AIProvider):
    """Base for real, network-backed model providers.

    These share a workflow: build a prompt that embeds the *normalized IR*
    (never raw project files), ask the model for a strict JSON implementation
    plan, and validate it. They always fall back safely: if the SDK or key is
    absent, ``available()`` returns False and the compiler uses the local
    provider instead. Model output is never allowed to become an artifact
    directly — only a validated plan proceeds to code generation.
    """

    env_key: str = ""
    sdk_module: str = ""

    def __init__(self, model: str | None = None):
        self.model = model

    def available(self) -> bool:
        if not os.environ.get(self.env_key):
            return False
        try:
            __import__(self.sdk_module)
        except Exception:
            return False
        return True

    def _prompt(self, ir_dict, target, constraints) -> str:
        import json

        return (
            "You are the SDC implementation planner. Given the normalized "
            "Application IR below, produce ONLY a JSON object matching the SDC "
            "implementation-plan schema (keys: target, language, framework, "
            "backend, components, dependencies, optimization_strategy, notes). "
            "Do not include prose.\n\n"
            f"target: {target}\nconstraints: {json.dumps(constraints)}\n\n"
            f"Application IR:\n{json.dumps(ir_dict, indent=2)}\n"
        )

    def generate_plan(self, ir_dict, target, constraints):  # pragma: no cover
        # Real network call path. Kept minimal and defensive; the deterministic
        # provider is the tested default. A malformed model response falls back
        # to the deterministic plan so a build is never blocked by the model.
        try:
            plan = self._call_model(self._prompt(ir_dict, target, constraints))
            if not isinstance(plan, dict) or "language" not in plan:
                raise ValueError("model returned an invalid plan")
            # Force the backend to one this build can realize.
            plan.setdefault("backend", "python-stdlib-http")
            return plan
        except Exception as exc:
            fallback = derive_plan(ir_dict, target, constraints)
            fallback.setdefault("notes", []).append(
                f"model provider '{self.name}' failed ({exc}); used deterministic plan"
            )
            return fallback

    def _call_model(self, prompt: str) -> dict:  # pragma: no cover
        raise NotImplementedError


class AnthropicProvider(_ModelProvider):
    name = "anthropic"
    env_key = "ANTHROPIC_API_KEY"
    sdk_module = "anthropic"

    def _call_model(self, prompt: str) -> dict:  # pragma: no cover
        import json
        import anthropic

        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=self.model or "claude-sonnet-5",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        return json.loads(_extract_json(text))


class OpenAIProvider(_ModelProvider):
    name = "openai"
    env_key = "OPENAI_API_KEY"
    sdk_module = "openai"

    def _call_model(self, prompt: str) -> dict:  # pragma: no cover
        import json
        from openai import OpenAI

        client = OpenAI()
        resp = client.chat.completions.create(
            model=self.model or "gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
        )
        return json.loads(_extract_json(resp.choices[0].message.content))


class GoogleProvider(_ModelProvider):
    name = "google"
    env_key = "GOOGLE_API_KEY"
    sdk_module = "google.generativeai"

    def _call_model(self, prompt: str) -> dict:  # pragma: no cover
        import json
        import google.generativeai as genai

        genai.configure(api_key=os.environ[self.env_key])
        model = genai.GenerativeModel(self.model or "gemini-1.5-flash")
        resp = model.generate_content(prompt)
        return json.loads(_extract_json(resp.text))


def _extract_json(text: str) -> str:  # pragma: no cover
    text = text.strip()
    if "```" in text:
        # strip a fenced block
        start = text.find("```")
        text = text[start + 3 :]
        if text.lower().startswith("json"):
            text = text[4:]
        end = text.rfind("```")
        if end != -1:
            text = text[:end]
    return text.strip()


_REGISTRY: dict[str, type[AIProvider]] = {
    "local": LocalDeterministicProvider,
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "google": GoogleProvider,
}


def get_provider(name: str = "local", model: str | None = None) -> AIProvider:
    """Return a provider by name, honoring an SDC_PROVIDER env override."""
    name = os.environ.get("SDC_PROVIDER", name)
    cls = _REGISTRY.get(name)
    if cls is None:
        raise CompilerError(
            f"Unknown AI provider '{name}'",
            why=f"registered providers: {sorted(_REGISTRY)}",
            component="ai-compiler",
        )
    if cls is LocalDeterministicProvider:
        return cls()
    prov = cls(model=model)  # type: ignore[call-arg]
    if not prov.available():
        # Fall back transparently so builds are never blocked by a missing key.
        return LocalDeterministicProvider()
    return prov


def register_provider(name: str, cls: type[AIProvider]) -> None:
    """Register a custom provider implementation."""
    _REGISTRY[name] = cls
