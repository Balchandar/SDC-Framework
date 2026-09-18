"""Deterministic canonicalization and content hashing.

The canonical form of the IR is JSON with sorted keys, no insignificant
whitespace, and UTF-8 encoding. Hashing that canonical form yields the
``ir_hash``. The same technique is applied to raw specification text to yield
the ``specification_hash``.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(obj: Any) -> str:
    """Return a canonical JSON string: sorted keys, compact separators.

    This is the single source of determinism for the whole toolchain. Two
    structurally identical objects always serialize to the exact same bytes.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_hex(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def ir_hash(ir_dict: dict[str, Any]) -> str:
    """Content hash of a canonicalized IR dictionary."""
    return _sha256_hex(canonical_json(ir_dict).encode("utf-8"))


def specification_hash(files: dict[str, str]) -> str:
    """Content hash of the raw specification file set.

    ``files`` maps a stable relative path to file text. Hashing includes the
    paths (sorted) so that renaming or adding a spec file changes the hash.
    """
    normalized = {path: text.replace("\r\n", "\n") for path, text in files.items()}
    payload = canonical_json(normalized).encode("utf-8")
    return _sha256_hex(payload)


def artifact_hash(path_or_bytes: Any) -> str:
    """Content hash of a produced artifact (bytes or a filesystem path)."""
    if isinstance(path_or_bytes, (bytes, bytearray)):
        return _sha256_hex(bytes(path_or_bytes))
    with open(path_or_bytes, "rb") as fh:
        return _sha256_hex(fh.read())


def build_id(spec_hash: str, ir_h: str, compiler_version: str) -> str:
    """A deterministic build identifier derived from the inputs that matter.

    The build id is NOT random: the same specification compiled with the same
    compiler yields the same build id. This supports reproducibility auditing.
    """
    seed = canonical_json(
        {"spec": spec_hash, "ir": ir_h, "compiler": compiler_version}
    ).encode("utf-8")
    return hashlib.sha256(seed).hexdigest()[:16]
