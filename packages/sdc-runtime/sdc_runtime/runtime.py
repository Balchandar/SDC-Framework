"""SDC runtime — the stable substrate that generated services target.

This module is deliberately dependency-free (Python standard library only) and
self-contained: the code generator inlines this exact source into the
standalone service artifact, so the runtime package is the single source of
truth for HTTP, configuration, logging, metrics, health, JWT verification,
authorization policy evaluation, and lifecycle. The compiler targets this
runtime rather than regenerating a web stack per project.

Everything here is intended to be importable and unit-testable on its own.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import signal
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Optional


RUNTIME_VERSION = "0.1.0"


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
class Config:
    """Environment-based configuration with typed accessors and defaults."""

    def __init__(self, environ: Optional[dict] = None):
        self._env = dict(os.environ if environ is None else environ)

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self._env.get(key, default)

    def int(self, key: str, default: int) -> int:
        try:
            return int(self._env.get(key, default))
        except (TypeError, ValueError):
            return default

    def bool(self, key: str, default: bool = False) -> bool:
        v = self._env.get(key)
        if v is None:
            return default
        return v.lower() in ("1", "true", "yes", "on")


# --------------------------------------------------------------------------- #
# Structured logging
# --------------------------------------------------------------------------- #
class StructuredLogger:
    """Emits one JSON object per line. Redacts configured sensitive keys."""

    def __init__(self, stream=None, sensitive_keys: Optional[list[str]] = None, base: Optional[dict] = None):
        self._stream = stream or sys.stdout
        self._sensitive = set(sensitive_keys or [])
        self._base = dict(base or {})
        self._lock = threading.Lock()

    def _redact(self, fields: dict) -> dict:
        out = {}
        for k, v in fields.items():
            if k in self._sensitive:
                out[k] = "***redacted***"
            else:
                out[k] = v
        return out

    def log(self, level: str, message: str, **fields):
        record = {"ts": round(time.time(), 6), "level": level, "message": message}
        record.update(self._base)
        record.update(self._redact(fields))
        line = json.dumps(record, sort_keys=True, separators=(",", ":"))
        with self._lock:
            self._stream.write(line + "\n")
            self._stream.flush()

    def info(self, message: str, **fields):
        self.log("info", message, **fields)

    def error(self, message: str, **fields):
        self.log("error", message, **fields)


# --------------------------------------------------------------------------- #
# Metrics (minimal Prometheus text exposition)
# --------------------------------------------------------------------------- #
class Metrics:
    def __init__(self):
        self._counters: dict[tuple, int] = {}
        self._latencies: list[float] = []
        self._lock = threading.Lock()

    def inc_request(self, endpoint: str, status: int):
        with self._lock:
            key = (endpoint, status)
            self._counters[key] = self._counters.get(key, 0) + 1

    def observe_latency(self, seconds: float):
        with self._lock:
            self._latencies.append(seconds)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            lat = sorted(self._latencies)
            p99 = lat[min(len(lat) - 1, int(len(lat) * 0.99))] if lat else 0.0
            return {
                "requests_total": sum(self._counters.values()),
                "p99_latency_ms": round(p99 * 1000, 3),
                "by_status": {f"{ep}|{st}": c for (ep, st), c in self._counters.items()},
            }

    def prometheus(self) -> str:
        snap = self.snapshot()
        lines = [
            "# HELP sdc_requests_total Total HTTP requests",
            "# TYPE sdc_requests_total counter",
            f"sdc_requests_total {snap['requests_total']}",
            "# HELP sdc_request_p99_latency_ms p99 request latency in ms",
            "# TYPE sdc_request_p99_latency_ms gauge",
            f"sdc_request_p99_latency_ms {snap['p99_latency_ms']}",
        ]
        for key, count in snap["by_status"].items():
            ep, st = key.split("|")
            safe_ep = ep.replace('"', "")
            lines.append(f'sdc_requests{{endpoint="{safe_ep}",status="{st}"}} {count}')
        return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# JWT (HS256) verification — no third-party dependency
# --------------------------------------------------------------------------- #
def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


class JWTError(Exception):
    pass


def jwt_encode(claims: dict, secret: str) -> str:
    """Mint an HS256 JWT. Used by tests/clients; the service only verifies."""
    header = {"alg": "HS256", "typ": "JWT"}
    seg = (
        _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64url_encode(json.dumps(claims, separators=(",", ":")).encode())
    )
    sig = hmac.new(secret.encode(), seg.encode(), hashlib.sha256).digest()
    return seg + "." + _b64url_encode(sig)


def jwt_verify(token: str, secret: str) -> dict:
    """Verify an HS256 JWT and return its claims, or raise :class:`JWTError`."""
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError:
        raise JWTError("malformed token")
    signing_input = f"{header_b64}.{payload_b64}".encode()
    expected = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    try:
        provided = _b64url_decode(sig_b64)
    except Exception:
        raise JWTError("bad signature encoding")
    if not hmac.compare_digest(expected, provided):
        raise JWTError("signature mismatch")
    try:
        claims = json.loads(_b64url_decode(payload_b64))
    except Exception:
        raise JWTError("bad payload")
    exp = claims.get("exp")
    if exp is not None and time.time() > float(exp):
        raise JWTError("token expired")
    return claims


@dataclass
class Principal:
    subject: str
    tenant_id: Optional[str]
    role: str = "user"
    claims: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Authorization policy interpreter (compiled rules are data)
# --------------------------------------------------------------------------- #
class Policy:
    """Evaluates compiled authorization rules against a principal/resource.

    Rules are the structured IR authorization rules (data). The interpreter is
    fixed and auditable: every decision returns a reason string suitable for an
    audit log.
    """

    def __init__(self, rules: list[dict]):
        self.rules = rules

    @staticmethod
    def _predicate_true(pred: dict, principal: Principal, resource: dict) -> bool:
        op = pred.get("op")
        if op == "cross_tenant":
            # True means the cross-tenant *violation* is present.
            return principal.tenant_id != resource.get("tenant_id")
        if op == "same_tenant":
            return principal.tenant_id == resource.get("tenant_id")
        if op == "assigned_department":
            depts = principal.claims.get("departments", [])
            return resource.get("department") in depts
        return False

    def decide(self, principal: Principal, resource: dict) -> tuple[bool, str]:
        # Deny rules take precedence.
        for r in self.rules:
            if r.get("effect") == "deny" and self._predicate_true(r.get("predicate", {}), principal, resource):
                return False, f"deny:{r.get('predicate', {}).get('op')}"
        # Allow rules matched by subject role.
        for r in self.rules:
            if r.get("effect") != "allow":
                continue
            subject = r.get("subject")
            if subject not in ("any", principal.role):
                continue
            if self._predicate_true(r.get("predicate", {}), principal, resource):
                return True, f"allow:{subject}:{r.get('predicate', {}).get('op')}"
        return False, "no-matching-allow-rule"


# --------------------------------------------------------------------------- #
# HTTP: Request / Response / Router / Server
# --------------------------------------------------------------------------- #
@dataclass
class Request:
    method: str
    path: str
    headers: dict[str, str]
    query: dict[str, str]
    params: dict[str, str]
    body: bytes
    request_id: str

    def bearer_token(self) -> Optional[str]:
        auth = self.headers.get("authorization") or self.headers.get("Authorization")
        if auth and auth.lower().startswith("bearer "):
            return auth[7:].strip()
        return None


@dataclass
class Response:
    status: int
    body: Any = None
    headers: dict[str, str] = field(default_factory=dict)


class Route:
    def __init__(self, method: str, pattern: str, handler: Callable[[Request], Response]):
        self.method = method.upper()
        self.pattern = pattern
        self.handler = handler
        self.regex, self.param_names = _compile_path(pattern)


def _compile_path(pattern: str) -> tuple[re.Pattern, list[str]]:
    names: list[str] = []
    regex_parts = []
    for seg in pattern.strip("/").split("/"):
        if seg.startswith("{") and seg.endswith("}"):
            name = seg[1:-1]
            names.append(name)
            regex_parts.append(r"(?P<%s>[^/]+)" % name)
        elif seg == "":
            continue
        else:
            regex_parts.append(re.escape(seg))
    regex = "^/" + "/".join(regex_parts) + "/?$" if regex_parts else "^/?$"
    return re.compile(regex), names


class Router:
    def __init__(self):
        self.routes: list[Route] = []

    def add(self, method: str, pattern: str, handler: Callable[[Request], Response]):
        self.routes.append(Route(method, pattern, handler))

    def match(self, method: str, path: str) -> tuple[Optional[Route], dict[str, str]]:
        path_only = path.split("?", 1)[0]
        matched_path = False
        for route in self.routes:
            m = route.regex.match(path_only)
            if m:
                matched_path = True
                if route.method == method.upper():
                    return route, m.groupdict()
        # 405 signalled by returning (None, {"__method_not_allowed__": ...})
        if matched_path:
            return None, {"__method_not_allowed__": "1"}
        return None, {}


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


class App:
    """Ties the router, config, logger, metrics and lifecycle together."""

    def __init__(
        self,
        router: Router,
        config: Config,
        logger: StructuredLogger,
        metrics: Metrics,
        telemetry: Optional[dict] = None,
        observability_fields: Optional[list[str]] = None,
    ):
        self.router = router
        self.config = config
        self.logger = logger
        self.metrics = metrics
        self.telemetry = telemetry or {}
        self.observability_fields = observability_fields or []
        self._server: Optional[ThreadingHTTPServer] = None
        self.started_at = time.time()

    # -- built-in endpoints -------------------------------------------------
    def _health(self, req: Request) -> Response:
        return Response(200, {"status": "ok", "uptime_s": round(time.time() - self.started_at, 3), **self.telemetry})

    def _metrics(self, req: Request) -> Response:
        return Response(200, self.metrics.prometheus(), headers={"Content-Type": "text/plain; version=0.0.4"})

    def install_builtin_routes(self):
        self.router.add("GET", "/healthz", self._health)
        self.router.add("GET", "/readyz", self._health)
        self.router.add("GET", "/metrics", self._metrics)

    # -- request handling ---------------------------------------------------
    def handle(self, method: str, path: str, headers: dict, body: bytes) -> Response:
        start = time.time()
        request_id = headers.get("x-request-id") or headers.get("X-Request-Id") or uuid.uuid4().hex
        query = {}
        if "?" in path:
            _, qs = path.split("?", 1)
            for pair in qs.split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    query[k] = v
        route, params = self.router.match(method, path)
        principal_tenant = None
        authz_decision = "n/a"
        if route is None:
            if params.get("__method_not_allowed__"):
                resp = Response(405, {"error": "method not allowed"})
            else:
                resp = Response(404, {"error": "not found"})
        else:
            req = Request(
                method=method,
                path=path,
                headers={k.lower(): v for k, v in headers.items()},
                query=query,
                params=params,
                body=body,
                request_id=request_id,
            )
            try:
                resp = route.handler(req)
            except _HttpError as he:
                resp = Response(he.status, {"error": he.message})
            except Exception as exc:  # never leak internals
                self.logger.error("unhandled error", request_id=request_id, error=str(exc))
                resp = Response(500, {"error": "internal server error"})
            principal_tenant = getattr(req, "_tenant_id", None)
            authz_decision = getattr(req, "_authz_decision", "n/a")

        # security headers + request id on every response
        resp.headers.setdefault("X-Request-Id", request_id)
        for k, v in SECURITY_HEADERS.items():
            resp.headers.setdefault(k, v)

        latency = time.time() - start
        endpoint = f"{method} {route.pattern}" if route else f"{method} {path.split('?')[0]}"
        self.metrics.inc_request(endpoint, resp.status)
        self.metrics.observe_latency(latency)
        self.logger.info(
            "request",
            request_id=request_id,
            tenant_id=principal_tenant,
            endpoint=endpoint,
            status=resp.status,
            latency_ms=round(latency * 1000, 3),
            authz_decision=authz_decision,
            **self.telemetry,
        )
        return resp

    # -- server lifecycle ---------------------------------------------------
    def serve(self, host: str = "0.0.0.0", port: int = 8080):
        app = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):  # silence default logging
                pass

            def _dispatch(self, method: str):
                length = int(self.headers.get("Content-Length", 0) or 0)
                body = self.rfile.read(length) if length else b""
                headers = {k: v for k, v in self.headers.items()}
                resp = app.handle(method, self.path, headers, body)
                if isinstance(resp.body, (dict, list)):
                    payload = json.dumps(resp.body).encode()
                    ctype = "application/json"
                elif isinstance(resp.body, str):
                    payload = resp.body.encode()
                    ctype = resp.headers.get("Content-Type", "text/plain")
                elif resp.body is None:
                    payload = b""
                    ctype = "application/json"
                else:
                    payload = str(resp.body).encode()
                    ctype = "text/plain"
                self.send_response(resp.status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(payload)))
                for k, v in resp.headers.items():
                    if k.lower() != "content-type":
                        self.send_header(k, v)
                self.end_headers()
                if payload:
                    self.wfile.write(payload)

            def do_GET(self):
                self._dispatch("GET")

            def do_POST(self):
                self._dispatch("POST")

            def do_PUT(self):
                self._dispatch("PUT")

            def do_PATCH(self):
                self._dispatch("PATCH")

            def do_DELETE(self):
                self._dispatch("DELETE")

        self._server = ThreadingHTTPServer((host, port), Handler)
        self.logger.info("server.start", host=host, port=port, **self.telemetry)

        def _shutdown(signum, frame):
            self.logger.info("server.shutdown", signal=signum)
            threading.Thread(target=self._server.shutdown, daemon=True).start()

        try:
            signal.signal(signal.SIGTERM, _shutdown)
            signal.signal(signal.SIGINT, _shutdown)
        except ValueError:
            # not in main thread (e.g. under the verifier) — that's fine
            pass
        self._server.serve_forever()
        self.logger.info("server.stopped")

    def stop(self):
        if self._server is not None:
            self._server.shutdown()


class _HttpError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(message)


def abort(status: int, message: str):
    raise _HttpError(status, message)


# --------------------------------------------------------------------------- #
# Data store abstraction
# --------------------------------------------------------------------------- #
class Store:
    """Data-access interface. Adapters below implement it."""

    def get(self, entity: str, key: str) -> Optional[dict]:  # pragma: no cover
        raise NotImplementedError

    def list(self, entity: str, tenant_id: Optional[str] = None) -> list[dict]:  # pragma: no cover
        raise NotImplementedError


class InMemoryStore(Store):
    """In-memory store seeded with fixtures. Used for verification and demos."""

    def __init__(self, seed: Optional[dict[str, list[dict]]] = None):
        self._data: dict[str, dict[str, dict]] = {}
        for entity, rows in (seed or {}).items():
            self._data[entity] = {}
            for row in rows:
                key = str(row.get("id"))
                self._data[entity][key] = dict(row)

    def get(self, entity: str, key: str) -> Optional[dict]:
        return self._data.get(entity, {}).get(str(key))

    def list(self, entity: str, tenant_id: Optional[str] = None) -> list[dict]:
        rows = list(self._data.get(entity, {}).values())
        if tenant_id is not None:
            rows = [r for r in rows if r.get("tenant_id") == tenant_id]
        return rows


class PostgresStore(Store):
    """PostgreSQL adapter using parameterized queries (psycopg).

    Selected when DATABASE_URL points at Postgres and the driver is available.
    Queries are always parameterized — never string-formatted — to prevent SQL
    injection. This adapter is optional; the generated service falls back to
    the in-memory store when the driver or database is unavailable.
    """

    def __init__(self, dsn: str):  # pragma: no cover - requires a live DB
        import psycopg  # type: ignore

        self._psycopg = psycopg
        self._dsn = dsn

    def _table(self, entity: str) -> str:
        # entity names are validated against a safe identifier pattern
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", entity):
            raise ValueError("unsafe entity name")
        return entity.lower() + "s"

    def get(self, entity: str, key: str) -> Optional[dict]:  # pragma: no cover
        with self._psycopg.connect(self._dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT * FROM {self._table(entity)} WHERE id = %s", (key,))
                row = cur.fetchone()
                if row is None:
                    return None
                cols = [d.name for d in cur.description]
                return dict(zip(cols, row))

    def list(self, entity: str, tenant_id: Optional[str] = None) -> list[dict]:  # pragma: no cover
        with self._psycopg.connect(self._dsn) as conn:
            with conn.cursor() as cur:
                if tenant_id is not None:
                    cur.execute(
                        f"SELECT * FROM {self._table(entity)} WHERE tenant_id = %s", (tenant_id,)
                    )
                else:
                    cur.execute(f"SELECT * FROM {self._table(entity)}")
                cols = [d.name for d in cur.description]
                return [dict(zip(cols, r)) for r in cur.fetchall()]


def make_store(config: Config, seed: Optional[dict] = None) -> Store:
    dsn = config.get("DATABASE_URL", "")
    if dsn and dsn.startswith(("postgres://", "postgresql://")):
        try:
            return PostgresStore(dsn)
        except Exception:
            # Fall back to in-memory if the driver/DB is unavailable.
            pass
    return InMemoryStore(seed=seed)


def project_fields(row: dict, sensitive: list[str]) -> dict:
    """Return a copy of ``row`` with sensitive fields removed."""
    return {k: v for k, v in row.items() if k not in set(sensitive)}
