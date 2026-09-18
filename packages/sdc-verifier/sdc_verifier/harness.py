"""Test harness: run the generated artifact and talk to it over HTTP.

The verifier runs the *actual generated service* in a subprocess with a fresh
signing secret and controlled seed data, then exercises it over real HTTP. This
is what makes verification independent of generation: the generator never gets
to declare its own output correct — observed behavior does.

The subprocess is confined: no production credentials are passed, a random
signing secret is minted per run, network egress is not required (it binds
loopback), and the process is killed on teardown with a timeout.
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

# The harness imports the runtime purely to mint test tokens.
from sdc_runtime import jwt_encode


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@dataclass
class HttpResult:
    status: int
    body: str
    headers: dict[str, str]

    def json(self):
        try:
            return json.loads(self.body)
        except Exception:
            return None


class ServiceHarness:
    def __init__(self, service_path: str, seed: Optional[dict] = None):
        self.service_path = service_path
        self.seed = seed
        self.secret = secrets.token_hex(16)
        self.port = _free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self._proc: Optional[subprocess.Popen] = None
        self.stdout_path = service_path + ".verify.log"

    def token(self, *, tenant_id: str, role: str = "user", subject: str = "test", **extra) -> str:
        claims = {"sub": subject, "tenant_id": tenant_id, "role": role}
        claims.update(extra)
        return jwt_encode(claims, self.secret)

    def start(self, timeout: float = 10.0):
        env = dict(os.environ)
        # Confined execution: fresh secret, controlled port, no prod creds.
        env["SDC_JWT_SECRET"] = self.secret
        env["PORT"] = str(self.port)
        env["HOST"] = "127.0.0.1"
        env.pop("DATABASE_URL", None)  # force in-memory store for verification
        if self.seed is not None:
            env["SDC_SEED_JSON"] = json.dumps(self.seed)
        logf = open(self.stdout_path, "w")
        self._logf = logf
        self._proc = subprocess.Popen(
            [sys.executable, self.service_path],
            env=env,
            stdout=logf,
            stderr=subprocess.STDOUT,
        )
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(
                    f"service exited early (code {self._proc.returncode}); see {self.stdout_path}"
                )
            try:
                r = self.get("/healthz")
                if r.status == 200:
                    return
            except Exception:
                time.sleep(0.05)
        raise RuntimeError("service did not become healthy in time")

    def request(self, method: str, path: str, token: Optional[str] = None, body: Optional[bytes] = None) -> HttpResult:
        req = urllib.request.Request(self.base + path, method=method, data=body)
        if token:
            req.add_header("Authorization", "Bearer " + token)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return HttpResult(resp.status, resp.read().decode(), dict(resp.headers))
        except urllib.error.HTTPError as e:
            return HttpResult(e.code, e.read().decode(), dict(e.headers))

    def get(self, path: str, token: Optional[str] = None) -> HttpResult:
        return self.request("GET", path, token=token)

    def read_logs(self) -> str:
        try:
            with open(self.stdout_path, "r") as fh:
                return fh.read()
        except Exception:
            return ""

    def stop(self):
        if self._proc is not None:
            try:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
            finally:
                self._proc = None
        try:
            self._logf.close()
        except Exception:
            pass

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()
        return False
