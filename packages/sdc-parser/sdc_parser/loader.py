"""Project loader: combine all Markdown specifications into one IR.

A project is a directory of ``.md`` files. Each file may focus on one
specification category or combine several. The loader parses every file,
merges their sections, and runs the semantic normalizers exactly once over the
merged blocks so the resulting IR is independent of how the author split their
files.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from sdc_ir import ApplicationIR
from sdc_ir.errors import SpecificationError

from .markdown import Block, parse_blocks
from . import sections as S


@dataclass
class LoadResult:
    ir: ApplicationIR
    files: dict[str, str]  # relative path -> text (for specification_hash)
    doc_title: str


def _read_spec_files(project_dir: str) -> dict[str, str]:
    files: dict[str, str] = {}
    for root, _dirs, names in os.walk(project_dir):
        # skip build output and hidden dirs
        rel_root = os.path.relpath(root, project_dir)
        parts = rel_root.split(os.sep)
        if any(p in (".build", "build", "dist", ".git", "__pycache__") for p in parts):
            continue
        for name in sorted(names):
            if name.endswith(".md"):
                full = os.path.join(root, name)
                rel = os.path.relpath(full, project_dir).replace(os.sep, "/")
                with open(full, "r", encoding="utf-8") as fh:
                    files[rel] = fh.read()
    return files


def load_from_files(files: dict[str, str]) -> LoadResult:
    """Build an :class:`ApplicationIR` from a mapping of path -> Markdown text."""
    if not files:
        raise SpecificationError(
            "No specification files found",
            why="a project must contain at least one .md specification file",
            regenerable=False,
        )

    merged: dict[str, list[Block]] = {}
    doc_title = ""
    # Deterministic order: sort by path.
    for path in sorted(files):
        blocks = parse_blocks(files[path])
        title, secs = S.extract_sections(blocks)
        if title and not doc_title:
            doc_title = title
        # If a whole file has no recognized category headings but has content,
        # and its filename matches a category, treat the whole file as that
        # category (supports minimal files like `security.md`).
        if not secs:
            stem = os.path.splitext(os.path.basename(path))[0].lower()
            cat = S.CATEGORY_ALIASES.get(stem)
            if cat:
                secs = {cat: [b for b in blocks if b.kind != "heading" or b.level > 1]}
        for cat, blist in secs.items():
            merged.setdefault(cat, []).extend(blist)

    ir = ApplicationIR()
    ir.application = S.normalize_application(merged.get("application", []), doc_title)
    if "api" in merged:
        ir.api = S.normalize_api(merged["api"])
    if "authentication" in merged:
        ir.authentication = S.normalize_authentication(merged["authentication"])
    if "authorization" in merged:
        ir.authorization = S.normalize_authorization(merged["authorization"])
    if "data" in merged:
        ir.data = S.normalize_data(merged["data"])
    if "behavior" in merged:
        ir.behavior = S.normalize_behavior(merged["behavior"])
    if "security" in merged:
        ir.security = S.normalize_security(merged["security"])
    if "performance" in merged:
        ir.performance = S.normalize_performance(merged["performance"])
    if "reliability" in merged:
        ir.reliability = S.normalize_reliability(merged["reliability"])
    if "observability" in merged:
        ir.observability = S.normalize_observability(merged["observability"])
    if "deployment" in merged:
        ir.deployment = S.normalize_deployment(merged["deployment"])
    if "testing" in merged:
        ir.testing = S.normalize_testing(merged["testing"])
    if "dependencies" in merged:
        ir.dependencies = S.normalize_dependencies(merged["dependencies"])

    # Wire endpoints to their entity's authentication requirement.
    if ir.authentication.required:
        for ep in ir.api.endpoints:
            ep.authenticated = True

    return LoadResult(ir=ir, files=files, doc_title=doc_title)


def load_project(project_dir: str) -> LoadResult:
    """Load a project directory into an :class:`ApplicationIR`."""
    if not os.path.isdir(project_dir):
        raise SpecificationError(
            f"Project directory not found: {project_dir}",
            why="the path does not exist or is not a directory",
            regenerable=False,
        )
    files = _read_spec_files(project_dir)
    return load_from_files(files)
