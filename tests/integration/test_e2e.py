import json
import os
import shutil
import subprocess
import sys

import pytest

from sdc_cli.pipeline import Toolchain


def _copy_example(example_dir, tmp_path):
    dst = tmp_path / "proj"
    shutil.copytree(example_dir, dst)
    for d in (".build", "dist"):
        p = dst / d
        if p.exists():
            shutil.rmtree(p)
    return str(dst)


def test_end_to_end_build_produces_artifact(example_dir, tmp_path):
    proj = _copy_example(example_dir, tmp_path)
    tc = Toolchain(proj)
    result = tc.build()
    assert result["manifest"]["verification_status"] == "PASS"
    artifact = result["artifact_path"]
    assert os.path.exists(artifact)
    assert os.access(artifact, os.X_OK)

    # all required build artifacts exist
    for rel in [
        ".build/specification.json",
        ".build/application-ir.json",
        ".build/implementation-plan.json",
        ".build/verification-report.json",
        ".build/security-report.json",
        ".build/benchmark-report.json",
        ".build/manifest.json",
    ]:
        assert os.path.exists(os.path.join(proj, rel)), rel

    manifest = json.load(open(os.path.join(proj, ".build/manifest.json")))
    assert manifest["application"] == "CustomerService"
    assert manifest["specification_hash"].startswith("sha256:")
    assert manifest["artifact_hash"].startswith("sha256:")


def test_rebuild_is_stable_when_specs_unchanged(example_dir, tmp_path):
    proj = _copy_example(example_dir, tmp_path)
    m1 = Toolchain(proj).build()["manifest"]
    m2 = Toolchain(proj).build()["manifest"]
    # deterministic local provider -> identical hashes across rebuilds
    assert m1["ir_hash"] == m2["ir_hash"]
    assert m1["artifact_hash"] == m2["artifact_hash"]
    assert m1["build_id"] == m2["build_id"]


def test_drift_scenario(example_dir, tmp_path):
    proj = _copy_example(example_dir, tmp_path)
    Toolchain(proj).build()  # baseline
    # modify only authorization.md
    authz = os.path.join(proj, "authorization.md")
    with open(authz, "a") as fh:
        fh.write("\nA manager may access customers in their assigned departments.\n")
    result = Toolchain(proj).build()
    diff = result["diff"]
    assert diff is not None
    assert "authorization" in diff["drift"]["changed_sections"]
    assert "authorization" in diff["drift"]["affected_components"]
    assert "authentication" in diff["drift"]["unaffected_components"]
    changes = " ".join(c["description"] for c in diff["semantic_diff"]["changes"])
    assert "manager" in changes


def test_generated_artifact_runs_standalone(example_dir, tmp_path):
    """The produced binary runs on its own with only stdlib + a secret."""
    proj = _copy_example(example_dir, tmp_path)
    result = Toolchain(proj).build()
    artifact = result["artifact_path"]

    import socket
    import time
    import urllib.request
    import urllib.error
    from sdc_runtime import jwt_encode

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    env = dict(os.environ)
    env["SDC_JWT_SECRET"] = "e2e-secret"
    env["PORT"] = str(port)
    env["HOST"] = "127.0.0.1"
    proc = subprocess.Popen([sys.executable, artifact], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        base = f"http://127.0.0.1:{port}"
        deadline = time.time() + 10
        ok = False
        while time.time() < deadline:
            try:
                if urllib.request.urlopen(base + "/healthz", timeout=1).status == 200:
                    ok = True
                    break
            except Exception:
                time.sleep(0.05)
        assert ok, "standalone artifact did not become healthy"

        tok = jwt_encode({"sub": "u", "tenant_id": "t1", "role": "user"}, "e2e-secret")
        req = urllib.request.Request(base + "/customers/c1", headers={"Authorization": "Bearer " + tok})
        with urllib.request.urlopen(req, timeout=2) as r:
            assert r.status == 200
    finally:
        proc.terminate()
        proc.wait(timeout=5)
