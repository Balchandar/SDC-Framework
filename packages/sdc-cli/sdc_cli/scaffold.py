"""Project scaffolding for ``sdc init``."""

from __future__ import annotations

import os


def _files(name: str) -> dict[str, str]:
    return {
        "project.md": f"""# {name}

## Application

Name: {name.replace('-', '').replace('_', '').title() or 'MyService'}
Version: 0.1
Description: A service scaffolded by `sdc init`.
""",
        "api.md": """# API

### GET /items/{id}

Returns a single item belonging to the authenticated user's tenant.

### GET /items

Returns items visible to the authenticated principal within their own tenant.
""",
        "authentication.md": """# Authentication

OAuth2 bearer authentication is required. Tokens are JWTs carrying the
principal's tenant and role claims.
""",
        "authorization.md": """# Authorization

A normal user may access items belonging to their own tenant.

A tenant administrator may access all items belonging to their tenant.

Cross-tenant access is forbidden.

All authorization decisions must be auditable.
""",
        "data.md": """# Data

Items are stored in PostgreSQL within transactions.

### Item

| Field     | Type   | Sensitive |
|-----------|--------|-----------|
| id        | string | no        |
| tenant_id | string | no        |
| name      | string | no        |
| secret    | string | yes       |
""",
        "behavior.md": """# Behavior

If the request is unauthenticated:

401

If authenticated but unauthorized:

403

If the item does not exist:

404

If successful:

200
""",
        "security.md": """# Security

- Never expose secrets.
- Cross-tenant access must never occur.
- SQL injection must be prevented.
- Sensitive fields must never be written to logs.
""",
        "performance.md": """# Performance

- p99 latency must remain below 50ms.
""",
        "deployment.md": """# Deployment

Target: linux-x86_64

Ships as a Docker container for Linux on x86_64 with a health check.
""",
    }


def write_project(target: str, name: str | None = None) -> None:
    os.makedirs(target, exist_ok=True)
    display = name or os.path.basename(os.path.abspath(target))
    for rel, content in _files(display).items():
        path = os.path.join(target, rel)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
