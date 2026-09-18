"""Toolchain orchestration.

The CLI is allowed to orchestrate the otherwise-decoupled stages (parse ->
IR -> compile -> verify -> artifact). Each stage writes a machine-readable
artifact under ``.build/`` and the final binary to ``dist/``.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
from dataclasses import dataclass, field
from typing import Any, Optional

from sdc_ir import (
    ApplicationIR,
    ir_hash as compute_ir_hash,
    specification_hash as compute_spec_hash,
    build_id as compute_build_id,
    artifact_hash as compute_artifact_hash,
    canonical_json,
)
from sdc_ir.errors import SDCError, BuildError, VerificationError, SecurityError
from sdc_parser import load_project, validate_ir
from sdc_compiler import AICompiler, get_provider, COMPILER_VERSION, analyze_drift, semantic_diff
from sdc_verifier import verify as run_verification


BUILD_DIR = ".build"
GENERATED_DIR = ".build/generated"
DIST_DIR = "dist"


@dataclass
class Toolchain:
    project_dir: str
    provider_name: str = "local"
    build_dir: str = BUILD_DIR
    dist_dir: str = DIST_DIR

    # populated as stages run
    load: Any = None
    ir: Optional[ApplicationIR] = None
    ir_dict: dict = field(default_factory=dict)
    spec_hash: str = ""
    ir_h: str = ""
    build_ident: str = ""
    plan: Any = None
    generated_files: list[str] = field(default_factory=list)
    service_path: str = ""

    # -- helpers ------------------------------------------------------------
    def _abs(self, *parts: str) -> str:
        return os.path.join(self.project_dir, *parts)

    def _write_json(self, rel: str, obj: Any):
        path = self._abs(rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, sort_keys=True)
        return path

    prev_ir_dict: Optional[dict] = None

    # -- stages -------------------------------------------------------------
    def parse(self) -> "Toolchain":
        # Capture the previously built IR *before* anything overwrites it, so
        # drift/diff can compare the last build against this one.
        prev_path = self._abs(f"{BUILD_DIR}/application-ir.json")
        if self.prev_ir_dict is None and os.path.exists(prev_path):
            try:
                with open(prev_path) as fh:
                    self.prev_ir_dict = json.load(fh)
            except Exception:
                self.prev_ir_dict = None

        self.load = load_project(self.project_dir)
        self.ir = self.load.ir
        self.ir_dict = self.ir.to_dict()
        self.spec_hash = compute_spec_hash(self.load.files)
        self.ir_h = compute_ir_hash(self.ir_dict)
        self.build_ident = compute_build_id(self.spec_hash, self.ir_h, COMPILER_VERSION)
        return self

    def validate(self) -> list[SDCError]:
        if self.ir is None:
            self.parse()
        return validate_ir(self.ir)

    def compile(self) -> "Toolchain":
        if self.ir is None:
            self.parse()
        errors = validate_ir(self.ir)
        fatal = [e for e in errors if not e.regenerable or e.kind == "SPECIFICATION_ERROR"]
        if fatal:
            raise BuildError(
                "Specification is invalid; cannot compile",
                why="; ".join(e.what for e in fatal),
                details=[e.what for e in errors],
                regenerable=False,
            )
        metadata = {
            "specification_hash": self.spec_hash,
            "ir_hash": self.ir_h,
            "build_id": self.build_ident,
        }
        compiler = AICompiler(get_provider(self.provider_name))
        result = compiler.compile(
            self.ir,
            target=self.ir.deployment.target,
            out_dir=self._abs(GENERATED_DIR),
        )
        self.plan = result.plan
        self.generated_files = result.files
        self.service_path = self._abs(GENERATED_DIR, "service.py")

        # Re-emit the service with build metadata embedded for telemetry.
        from sdc_codegen import generate_implementation

        self.generated_files = generate_implementation(
            self.ir, self.plan.to_dict(), self._abs(GENERATED_DIR), metadata=metadata
        )

        # write stage artifacts
        self._write_json(f"{BUILD_DIR}/specification.json", self.load.files)
        self._write_json(f"{BUILD_DIR}/application-ir.json", self.ir_dict)
        self._write_json(f"{BUILD_DIR}/implementation-plan.json", self.plan.to_dict())
        return self

    def verify(self, run_performance: bool = True):
        if not self.service_path or not os.path.exists(self.service_path):
            self.compile()
        result = run_verification(
            self.ir,
            self.service_path,
            specification_hash=self.spec_hash,
            ir_hash=self.ir_h,
            run_performance=run_performance,
        )
        report = result.report
        self._write_json(f"{BUILD_DIR}/verification-report.json", report.to_dict())
        # security-report is the security-category slice
        sec = [c.to_dict() for c in report.checks if c.category == "security"]
        self._write_json(
            f"{BUILD_DIR}/security-report.json",
            {"status": "FAIL" if any(c["status"] == "FAIL" and c["mandatory"] for c in sec) else "PASS", "checks": sec},
        )
        bench = [c.to_dict() for c in report.checks if c.category == "performance"]
        self._write_json(f"{BUILD_DIR}/benchmark-report.json", {"checks": bench})
        return report

    def semantic_diff_vs_previous(self) -> Optional[dict]:
        """Semantic diff + drift of this build vs the previous one."""
        prev = self.prev_ir_dict
        if not prev or canonical_json(prev) == canonical_json(self.ir_dict):
            return None
        sdiff = semantic_diff(prev, self.ir_dict)
        out = {"semantic_diff": sdiff.to_dict()}
        if self.plan is not None:
            out["drift"] = analyze_drift(prev, self.ir_dict, self.plan).to_dict()
        self._write_json(f"{BUILD_DIR}/semantic-diff.json", out)
        return out

    def build(self) -> dict:
        """Compile + verify + (on PASS) produce the artifact and manifest.

        Returns a result dict that always includes ``report``; ``manifest`` and
        ``artifact_path`` are None when verification fails (no artifact is
        produced for a spec-violating build).
        """
        if self.ir is None:
            self.parse()
        report = self.verify()  # compiles first if needed
        diff = self.semantic_diff_vs_previous()
        if report.status == "FAIL":
            return {"report": report, "manifest": None, "artifact_path": None, "diff": diff}

        # produce the binary
        os.makedirs(self._abs(self.dist_dir), exist_ok=True)
        artifact_name = os.path.basename(os.path.abspath(self.project_dir))
        artifact_path = self._abs(self.dist_dir, artifact_name)
        with open(self.service_path, "r", encoding="utf-8") as fh:
            body = fh.read()
        with open(artifact_path, "w", encoding="utf-8") as fh:
            fh.write("#!/usr/bin/env python3\n" + body)
        st = os.stat(artifact_path)
        os.chmod(artifact_path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

        art_hash = compute_artifact_hash(artifact_path)

        manifest = {
            "application": self.ir.application.name,
            "version": self.ir.application.version,
            "specification_hash": self.spec_hash,
            "ir_hash": self.ir_h,
            "artifact_hash": art_hash,
            "build_id": self.build_ident,
            "compiler_version": COMPILER_VERSION,
            "provider": self.provider_name,
            "target": self.plan.target,
            "language": self.plan.language,
            "backend": self.plan.backend,
            "verification_status": report.status,
            "artifact": os.path.relpath(artifact_path, self.project_dir),
            "reproducibility": {
                "semantic": "deterministic IR; identical spec -> identical IR hash",
                "binary": "deterministic for the local provider; NOT guaranteed when a model provider is used",
            },
        }
        self._write_json(f"{BUILD_DIR}/manifest.json", manifest)
        return {"manifest": manifest, "report": report, "artifact_path": artifact_path, "diff": diff}
