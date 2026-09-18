"""sdc_runtime — the stable runtime substrate for generated services.

The code generator inlines :mod:`sdc_runtime.runtime` into the standalone
artifact, so this package is the single source of truth for the runtime. It is
also importable and testable directly.
"""

from .runtime import (
    RUNTIME_VERSION,
    Config,
    StructuredLogger,
    Metrics,
    Principal,
    Policy,
    Request,
    Response,
    Router,
    App,
    Store,
    InMemoryStore,
    PostgresStore,
    make_store,
    project_fields,
    jwt_encode,
    jwt_verify,
    JWTError,
    abort,
    SECURITY_HEADERS,
)

import os as _os

RUNTIME_SOURCE_PATH = _os.path.join(_os.path.dirname(__file__), "runtime.py")


def runtime_source() -> str:
    """Return the runtime source text, for inlining into a standalone artifact."""
    with open(RUNTIME_SOURCE_PATH, "r", encoding="utf-8") as fh:
        return fh.read()


__all__ = [
    "RUNTIME_VERSION",
    "Config",
    "StructuredLogger",
    "Metrics",
    "Principal",
    "Policy",
    "Request",
    "Response",
    "Router",
    "App",
    "Store",
    "InMemoryStore",
    "PostgresStore",
    "make_store",
    "project_fields",
    "jwt_encode",
    "jwt_verify",
    "JWTError",
    "abort",
    "SECURITY_HEADERS",
    "runtime_source",
    "RUNTIME_SOURCE_PATH",
]
