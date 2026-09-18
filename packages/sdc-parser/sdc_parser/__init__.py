"""sdc_parser — Markdown specifications -> Application IR.

Pipeline: raw Markdown -> block reader -> section extraction -> semantic
normalization -> typed IR -> validation.
"""

from .loader import load_project, load_from_files, LoadResult
from .validate import validate_ir
from .markdown import parse_blocks, Block
from . import sections

__all__ = [
    "load_project",
    "load_from_files",
    "LoadResult",
    "validate_ir",
    "parse_blocks",
    "Block",
    "sections",
]
