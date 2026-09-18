"""Deterministic implementation planner.

Turns an Application IR (as a dict) into an implementation-plan dict using
transparent rules. Every component records which IR sections it is
``derived_from`` so the drift analyzer can map a spec change to the components
that must be regenerated.

Note on language choice: the *specification never names a language*. The
planner selects one. For the runnable MVP the selected backend is
``python-stdlib-http`` (zero third-party dependencies, so the generated service
runs and is verified anywhere). The plan and IR are backend-agnostic: adding a
native backend (e.g. Rust/axum) is a matter of registering another code
backend that consumes the same IR + plan — no specification change required.
"""

from __future__ import annotations

from typing import Any


def derive_plan(ir: dict[str, Any], target: str, constraints: dict[str, Any]) -> dict[str, Any]:
    components: list[dict[str, Any]] = []

    def add(name: str, responsibility: str, derived_from: list[str]):
        components.append(
            {"name": name, "responsibility": responsibility, "derived_from": derived_from}
        )

    # Always present.
    add("http-server", "HTTP routing, request/response lifecycle", ["api"])
    add("configuration", "environment-based configuration", ["deployment"])
    add("error-handling", "map failures to specified status codes", ["behavior"])
    add("observability", "structured logging, request IDs, metrics, health", ["observability"])

    auth = ir.get("authentication", {})
    if auth.get("required"):
        add("authentication", f"validate {auth.get('token_format', 'token')} bearer tokens", ["authentication"])

    az = ir.get("authorization", {})
    if az.get("rules"):
        add("authorization", "compile authorization rules into an executable policy", ["authorization"])

    data = ir.get("data", {})
    if data.get("entities"):
        store = data.get("store", "memory")
        add("database", f"data access via {store} store with pluggable adapter", ["data"])
        if data.get("transactions"):
            add("transactions", "transactional reads/writes; no partial commits", ["data", "reliability"])

    obs = ir.get("observability", {})
    if obs.get("health", True):
        add("health", "health and readiness endpoints", ["observability", "deployment"])
    if obs.get("metrics", True):
        add("metrics", "metrics endpoint", ["observability"])

    rel = ir.get("reliability", {})
    if rel.get("retry_transient") or rel.get("graceful_db_failure"):
        add("reliability", "retry transient failures; graceful degradation", ["reliability"])

    # graceful shutdown is expected for a production service
    add("lifecycle", "graceful startup and shutdown", ["deployment", "reliability"])

    deps: list[str] = []
    # python-stdlib-http backend intentionally uses no third-party runtime deps
    optimization = {
        "strategy": "baseline",
        "notes": [
            "route dispatch via compiled table",
            "authorization compiled to a decision function",
        ],
    }

    plan = {
        "target": target or ir.get("deployment", {}).get("target", "linux-x86_64"),
        "language": "python",
        "framework": "stdlib-http",
        "backend": "python-stdlib-http",
        "components": components,
        "dependencies": deps,
        "optimization_strategy": optimization,
        "notes": [
            "Backend selected by the compiler; the specification is language-agnostic.",
            "Additional native backends (e.g. rust/axum) implement the same "
            "IR+plan contract and can be registered without changing specs.",
        ],
    }
    if constraints:
        plan["notes"].append(f"constraints applied: {sorted(constraints.keys())}")
    return plan
