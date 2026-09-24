"""Reproduce the MVP defects listed in docs/ASSESSMENT.md §3.

Run from the repository root after ``pip install -e .``:

    python scripts/assessment_probe.py

Each line prints the observed behavior. Roadmap Phase 0 turns the relevant
probes into regression tests; later phases make the rest impossible by
construction.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

from sdc_compiler import get_provider
from sdc_ir import ir_hash
from sdc_parser import load_from_files, validate_ir
from sdc_runtime import jwt_encode, jwt_verify

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = {"project.md": "# X\n\n## Application\n\nName: X\nVersion: 1\n"}


def ir(files: dict[str, str]):
    return load_from_files({**BASE, **files}).ir


def parser_probes() -> None:
    b = ir({"behavior.md": "# Behavior\n\nIf the customer does not exist:\n\n418\n"}).behavior
    print("D1 explicit 418 ->", [(r.condition, r.status) for r in b.rules])

    a = ir({"authorization.md": "# Authorization\n\nCross-tenant access is not forbidden.\n"}).authorization
    print("D2 'not forbidden' ->", a.forbidden, [r.effect for r in a.rules])

    s = ir({"security.md": "# Security\n\n- Never expose passwords.\n"
            "- Never expose authentication tokens.\n"
            "- Tenant names are shown in the UI header.\n"}).security
    print("D3 security ->", [(r.id, r.text) for r in s.requirements])

    a = ir({"authorization.md": "# Authorization\n\nA clinician may read patients assigned to their ward.\n"}).authorization
    print("D4 clinician rule ->", a.rules, a.roles)

    i = ir({"api.md": "# API\n\n### GET /x/{id}\n\nget\n",
            "authentication.md": "# Authentication\n\nBearer JWT required.\n"})
    print("D5 errors (kind, regenerable) ->", [(e.kind, e.regenerable) for e in validate_ir(i)])

    h1 = ir_hash(ir({"performance.md": "# Performance\n\n- p99 latency must remain below 50ms.\n"}).to_dict())
    h2 = ir_hash(ir({"performance.md": "# Performance\n\n- The p99 latency must stay below 50ms.\n"}).to_dict())
    print("D6 same meaning, same ir_hash ->", h1 == h2)


def runtime_probes() -> None:
    forged = jwt_encode({"sub": "a", "tenant_id": "t1", "role": "tenant_admin"}, "")
    print("D7 token forged with empty key accepted ->", bool(jwt_verify(forged, "")))

    os.environ.pop("ANTHROPIC_API_KEY", None)
    print("D9 requested anthropic, provider used ->", get_provider("anthropic").name)


def _sha(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:16]


def build_probes() -> None:
    from sdc_cli.pipeline import Toolchain

    tmp = tempfile.mkdtemp()
    proj = os.path.join(tmp, "p")
    shutil.copytree(os.path.join(REPO, "examples", "customer-api"), proj)
    try:
        out = Toolchain(proj, provider_name="anthropic").build()
        m = out["manifest"]
        dist = os.path.join(proj, m["artifact"])
        print("D9 manifest provider ->", m["provider"])
        print("D10 verified", _sha(os.path.join(proj, ".build/generated/service.py")),
              "!= released", _sha(dist))
        src = open(dist, encoding="utf-8").read()
        print("D12 fixtures in prod artifact ->", "secret-password-c1" in src,
              "| SDC_SEED_JSON hook ->", "SDC_SEED_JSON" in src)
        print("D14 role defaults to user ->", 'claims.get("role", "user")' in src)

        with open(dist, "a", encoding="utf-8") as fh:
            fh.write("# tampered\n")
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        env = dict(os.environ, SDC_JWT_SECRET="x", PORT=str(port), HOST="127.0.0.1")
        proc = subprocess.Popen([sys.executable, dist], env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.5)
        print("D11 tampered artifact still running ->", proc.poll() is None)
        proc.terminate()
        proc.wait(timeout=5)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    parser_probes()
    runtime_probes()
    build_probes()
