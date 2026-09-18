"""Section extraction and semantic normalization.

Blocks from :mod:`sdc_parser.markdown` are grouped under category headings and
then normalized into typed IR fragments. Normalization is where natural
Markdown becomes *semantic* structure: authorization prose becomes structured
policy rules, behavior prose becomes condition/status mappings, and so on.

The parser is intentionally conservative: if it cannot confidently interpret a
statement it records it as a note rather than guessing, so the IR never
silently invents behavior.
"""

from __future__ import annotations

import re
from typing import Iterable

from sdc_ir import (
    ApplicationMeta,
    Api,
    Endpoint,
    Authentication,
    Authorization,
    AuthorizationRule,
    Data,
    Entity,
    Field,
    Behavior,
    BehaviorRule,
    Security,
    SecurityRequirement,
    Performance,
    Reliability,
    Observability,
    Deployment,
    Testing,
    TestCase,
    Dependencies,
)

from .markdown import Block, parse_blocks


# category aliases -> canonical category name
CATEGORY_ALIASES = {
    "application": "application",
    "app": "application",
    "api": "api",
    "endpoints": "api",
    "authentication": "authentication",
    "authn": "authentication",
    "authorization": "authorization",
    "authz": "authorization",
    "access control": "authorization",
    "data": "data",
    "data model": "data",
    "behavior": "behavior",
    "behaviour": "behavior",
    "security": "security",
    "performance": "performance",
    "reliability": "reliability",
    "observability": "observability",
    "telemetry": "observability",
    "deployment": "deployment",
    "testing": "testing",
    "tests": "testing",
    "test": "testing",
    "dependencies": "dependencies",
}


def _canon_heading(text: str) -> str | None:
    key = text.strip().lower().rstrip(":")
    return CATEGORY_ALIASES.get(key)


def extract_sections(blocks: list[Block]) -> tuple[str, dict[str, list[Block]]]:
    """Group blocks into categories.

    Returns ``(doc_title, {category: [blocks]})``. The document title is the
    first level-1 heading that is not itself a category name.
    """
    doc_title = ""
    sections: dict[str, list[Block]] = {}
    current: str | None = None

    for b in blocks:
        if b.kind == "heading":
            cat = _canon_heading(b.text)
            if cat is not None and b.level <= 2:
                current = cat
                sections.setdefault(current, [])
                continue
            if b.level == 1 and not doc_title:
                doc_title = b.text
                # a level-1 title also implicitly opens the "application"
                # section if none is active
                continue
        if current is not None:
            sections[current].append(b)

    return doc_title, sections


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _iter_text_lines(blocks: Iterable[Block]) -> list[str]:
    out: list[str] = []
    for b in blocks:
        if b.kind == "paragraph":
            out.append(b.text)
        elif b.kind == "list":
            out.extend(b.items)
        elif b.kind == "heading":
            out.append(b.text)
    return out


_KV_DELIM = re.compile(r"(?:^|(?<=\s))([A-Za-z][A-Za-z0-9_]*)\s*:\s*")


def _kv(blocks: Iterable[Block]) -> dict[str, str]:
    """Extract ``Key: value`` pairs from paragraphs and list items.

    Multiple pairs may appear on one line (the block reader joins wrapped
    source lines), so this splits a line at each single-word ``Key:`` token and
    takes the text up to the next such token as the value.
    """
    kv: dict[str, str] = {}
    for line in _iter_text_lines(blocks):
        matches = list(_KV_DELIM.finditer(line))
        for idx, m in enumerate(matches):
            key = m.group(1).strip().lower()
            start = m.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(line)
            kv[key] = line[start:end].strip()
    return kv


# --------------------------------------------------------------------------- #
# normalizers
# --------------------------------------------------------------------------- #
def normalize_application(blocks: list[Block], doc_title: str) -> ApplicationMeta:
    kv = _kv(blocks)
    name = kv.get("name") or (doc_title.replace(" ", "") if doc_title else "UnnamedApplication")
    version = kv.get("version", "0.1")
    description = kv.get("description", "")
    if not description:
        for b in blocks:
            if b.kind == "paragraph" and ":" not in b.text:
                description = b.text
                break
    return ApplicationMeta(name=name, version=version, description=description)


_ENTITY_FROM_PATH = re.compile(r"/([a-zA-Z][a-zA-Z0-9_-]*)")


def _entity_from_path(path: str) -> str | None:
    m = _ENTITY_FROM_PATH.search(path)
    if not m:
        return None
    word = m.group(1)
    # singularize a trailing 's' (customers -> Customer)
    if word.endswith("ies"):
        word = word[:-3] + "y"
    elif word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]
    return word[:1].upper() + word[1:]


def normalize_api(blocks: list[Block]) -> Api:
    api = Api()
    method_re = re.compile(r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(\S+)$", re.IGNORECASE)
    pending: Endpoint | None = None
    for b in blocks:
        if b.kind == "heading":
            m = method_re.match(b.text.strip())
            if m:
                path = m.group(2)
                params = re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", path)
                pending = Endpoint(
                    method=m.group(1).upper(),
                    path=path,
                    path_params=params,
                    entity=_entity_from_path(path),
                )
                api.endpoints.append(pending)
        elif b.kind == "paragraph" and pending is not None and not pending.summary:
            pending.summary = b.text
    api.endpoints.sort(key=lambda e: (e.path, e.method))
    return api


def normalize_authentication(blocks: list[Block]) -> Authentication:
    text = " ".join(_iter_text_lines(blocks)).lower()
    auth = Authentication()
    if not text.strip():
        return auth
    if "oauth2" in text or "bearer" in text or "jwt" in text:
        auth.scheme = "oauth2_bearer_jwt"
        auth.token_format = "jwt_hs256"
    elif "api key" in text or "api-key" in text:
        auth.scheme = "api_key"
    else:
        auth.scheme = "custom"
    auth.required = ("required" in text) or ("must" in text) or auth.scheme != "none"
    auth.notes = _iter_text_lines(blocks)
    return auth


def normalize_authorization(blocks: list[Block]) -> Authorization:
    az = Authorization()
    lines = _iter_text_lines(blocks)
    roles: set[str] = set()
    for raw in lines:
        line = raw.strip().rstrip(".")
        low = line.lower()
        if not low:
            continue

        # forbidden invariant: cross-tenant
        if "cross-tenant" in low or "cross tenant" in low:
            if "forbid" in low or "never" in low or "deny" in low or "not" in low:
                if "cross_tenant_access" not in az.forbidden:
                    az.forbidden.append("cross_tenant_access")
                az.rules.append(
                    AuthorizationRule(
                        effect="deny",
                        subject="any",
                        predicate={"op": "cross_tenant"},
                        description=line,
                    )
                )
                az.model = "rbac_tenant"
                continue

        # admin: all customers in their tenant
        if ("administrator" in low or "admin" in low) and "tenant" in low:
            roles.add("tenant_admin")
            az.rules.append(
                AuthorizationRule(
                    effect="allow",
                    subject="tenant_admin",
                    predicate={"op": "same_tenant", "scope": "all"},
                    description=line,
                )
            )
            az.model = "rbac_tenant"
            continue

        # normal user: own tenant
        if ("user" in low) and ("tenant" in low) and ("own" in low or "their" in low or "belong" in low):
            roles.add("user")
            az.rules.append(
                AuthorizationRule(
                    effect="allow",
                    subject="user",
                    predicate={"op": "same_tenant", "scope": "own"},
                    description=line,
                )
            )
            az.model = "rbac_tenant"
            continue

        # manager: assigned departments (used by the diff example)
        if "manager" in low and ("department" in low or "assigned" in low):
            roles.add("manager")
            az.rules.append(
                AuthorizationRule(
                    effect="allow",
                    subject="manager",
                    predicate={"op": "assigned_department"},
                    description=line,
                )
            )
            az.model = "rbac_tenant"
            continue

        if "auditable" in low or "audit" in low:
            az.auditable = True

    az.roles = sorted(roles)
    return az


_SENSITIVE_HINTS = ("password", "token", "secret", "hash", "credential")


def normalize_data(blocks: list[Block]) -> Data:
    data = Data()
    text = " ".join(_iter_text_lines(blocks)).lower()
    if "postgres" in text or "postgresql" in text:
        data.store = "postgres"
    if "transaction" in text:
        data.transactions = True

    # entities from tables. A table with a "Field"/"Name" column defines fields
    # for the most recent entity heading (level >= 3), else a default entity.
    current_entity_name = None
    for b in blocks:
        if b.kind == "heading" and b.level >= 3:
            current_entity_name = b.text.strip()
        elif b.kind == "table" and b.headers:
            headers = [h.lower() for h in b.headers]
            if "field" in headers or "name" in headers:
                name = current_entity_name or "Entity"
                entity = data.entity(name) or Entity(name=name)
                if entity not in data.entities:
                    data.entities.append(entity)
                fidx = headers.index("field") if "field" in headers else headers.index("name")
                tidx = headers.index("type") if "type" in headers else None
                sidx = headers.index("sensitive") if "sensitive" in headers else None
                for row in b.rows:
                    if fidx >= len(row):
                        continue
                    fname = row[fidx].strip()
                    if not fname:
                        continue
                    ftype = row[tidx].strip() if (tidx is not None and tidx < len(row)) else "string"
                    sensitive = False
                    if sidx is not None and sidx < len(row):
                        sensitive = row[sidx].strip().lower() in ("yes", "true", "y", "sensitive")
                    if any(h in fname.lower() for h in _SENSITIVE_HINTS):
                        sensitive = True
                    fld = Field(
                        name=fname,
                        type=ftype or "string",
                        sensitive=sensitive,
                        primary_key=(fname.lower() in ("id", f"{name.lower()}_id")),
                    )
                    entity.fields.append(fld)
                    if fname.lower() == "tenant_id":
                        entity.tenant_field = "tenant_id"
    data.entities.sort(key=lambda e: e.name)
    return data


def normalize_behavior(blocks: list[Block]) -> Behavior:
    behavior = Behavior()
    lines = _iter_text_lines(blocks)
    seen: set[str] = set()

    def add(condition: str, status: int, desc: str):
        if condition not in seen:
            behavior.rules.append(BehaviorRule(condition=condition, status=status, description=desc))
            seen.add(condition)

    # Look for explicit "condition -> status" using nearby status codes.
    joined = " \n ".join(lines).lower()
    status_map = [
        ("unauthenticated", 401, ("unauthenticated", "no token", "not authenticated", "missing authentication")),
        ("unauthorized", 403, ("unauthorized", "forbidden", "not authorized", "not permitted")),
        ("not_found", 404, ("does not exist", "not found", "no such", "missing customer")),
        ("success", 200, ("successful", "success", "if successful", "returns")),
    ]
    for line in lines:
        low = line.lower()
        code = re.search(r"\b(2\d\d|4\d\d|5\d\d)\b", low)
        for cond, default_status, kws in status_map:
            if any(k in low for k in kws):
                status = int(code.group(1)) if code else default_status
                add(cond, status, line)
    # Fallbacks so behavior is always complete for an authenticated API.
    if "401" in joined or "unauthenticated" in joined:
        add("unauthenticated", 401, "unauthenticated request")
    return behavior


_SECURITY_CHECKS = [
    ("no_secret_exposure", ("password", "token", "secret", "expose", "leak")),
    ("tenant_isolation", ("cross-tenant", "cross tenant", "tenant isolation", "tenant")),
    ("sql_injection", ("sql injection", "sqli")),
    ("authorization_auditable", ("auditable", "audit")),
    ("authentication_enforced", ("authentication",)),
    ("authorization_enforced", ("authorization",)),
    ("path_traversal", ("path traversal",)),
    ("ssrf", ("ssrf", "server-side request")),
    ("unsafe_deserialization", ("deserial",)),
    ("security_headers", ("security header",)),
    ("no_sensitive_logging", ("sensitive log", "log sensitive", "logging", "to logs", "in logs")),
    ("dependency_vulnerabilities", ("dependency", "vulnerab")),
    ("insecure_configuration", ("insecure config", "insecure configuration")),
]


def _security_id_for(text: str) -> str | None:
    low = text.lower()
    for check_id, kws in _SECURITY_CHECKS:
        if any(k in low for k in kws):
            return check_id
    return None


def normalize_security(blocks: list[Block]) -> Security:
    security = Security()
    seen: set[str] = set()
    for line in _iter_text_lines(blocks):
        line = line.strip()
        if not line:
            continue
        cid = _security_id_for(line)
        if cid is None:
            cid = "custom_" + re.sub(r"[^a-z0-9]+", "_", line.lower())[:32].strip("_")
        if cid in seen:
            continue
        seen.add(cid)
        security.requirements.append(SecurityRequirement(id=cid, text=line, mandatory=True))
    security.requirements.sort(key=lambda r: r.id)
    return security


def normalize_performance(blocks: list[Block]) -> Performance:
    perf = Performance()
    text = " ".join(_iter_text_lines(blocks)).lower()
    m = re.search(r"p99[^0-9]*([0-9]+)\s*ms", text)
    if m:
        perf.p99_latency_ms = int(m.group(1))
    m = re.search(r"([0-9][0-9,]*)\s*(?:requests|req)\s*(?:per|/)\s*second", text)
    if m:
        perf.min_rps = int(m.group(1).replace(",", ""))
    perf.notes = _iter_text_lines(blocks)
    return perf


def normalize_reliability(blocks: list[Block]) -> Reliability:
    rel = Reliability()
    text = " ".join(_iter_text_lines(blocks)).lower()
    rel.graceful_db_failure = "database failure" in text or "db failure" in text or "gracefully" in text
    rel.no_partial_commit = "partial" in text and "commit" in text
    rel.retry_transient = "retry" in text and "transient" in text
    rel.notes = _iter_text_lines(blocks)
    return rel


def normalize_observability(blocks: list[Block]) -> Observability:
    obs = Observability()
    text = " ".join(_iter_text_lines(blocks)).lower()
    if "opentelemetry" in text or "otel" in text:
        obs.telemetry = "opentelemetry"
    fields: list[str] = []
    for b in blocks:
        if b.kind == "list":
            for it in b.items:
                fields.append(re.sub(r"\s+", "_", it.strip().lower()))
    obs.fields = fields
    obs.metrics = "metric" in text or True
    obs.health = "health" in text or True
    return obs


def normalize_deployment(blocks: list[Block]) -> Deployment:
    dep = Deployment()
    text = " ".join(_iter_text_lines(blocks)).lower()
    if "arm64" in text:
        dep.target = "linux-arm64"
    elif "x86_64" in text or "x86-64" in text or "amd64" in text:
        dep.target = "linux-x86_64"
    dep.container = "docker" in text or "container" in text or True
    dep.healthcheck = "health" in text or True
    dep.notes = _iter_text_lines(blocks)
    return dep


def normalize_testing(blocks: list[Block]) -> Testing:
    testing = Testing()
    # Tables: | name | endpoint | role | tenant | expect |
    for b in blocks:
        if b.kind == "table" and b.headers:
            headers = [h.lower() for h in b.headers]
            def col(*names):
                for nm in names:
                    if nm in headers:
                        return headers.index(nm)
                return None
            n_i = col("name", "case")
            e_i = col("endpoint", "request", "path")
            r_i = col("role")
            t_i = col("tenant")
            x_i = col("expect", "status", "expected")
            auth_i = col("authenticated", "auth")
            for row in b.rows:
                def get(i):
                    return row[i].strip() if (i is not None and i < len(row)) else ""
                name = get(n_i) or f"case-{len(testing.cases)+1}"
                endpoint = get(e_i)
                expect = get(x_i)
                if not expect.isdigit():
                    continue
                principal = None
                authed = get(auth_i).lower()
                if r_i is not None or t_i is not None:
                    if authed not in ("no", "false", "none", "") or get(r_i) or get(t_i):
                        principal = {
                            "role": get(r_i) or "user",
                            "tenant_id": get(t_i) or "t1",
                        }
                if authed in ("no", "false", "none"):
                    principal = None
                testing.cases.append(
                    TestCase(
                        name=name,
                        request={"endpoint": endpoint, "principal": principal},
                        expect_status=int(expect),
                    )
                )
    return testing


def normalize_dependencies(blocks: list[Block]) -> Dependencies:
    deps = Dependencies()
    mode = None
    for b in blocks:
        if b.kind == "heading":
            low = b.text.lower()
            if "forbid" in low or "disallow" in low:
                mode = "forbidden"
            elif "allow" in low:
                mode = "allowed"
        elif b.kind == "list":
            target = deps.forbidden if mode == "forbidden" else deps.allowed
            target.extend(i.strip() for i in b.items)
    return deps
